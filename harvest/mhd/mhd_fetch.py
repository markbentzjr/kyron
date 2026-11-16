#!/usr/bin/env python3
"""Generic MyHealthDepartment (MHD) search fetcher — all config states.

Generalizes the TN adapter (harvest/tn/tn_fetch.py) across every
inspections.myhealthdepartment.com deployment in states.py. The portal's
own client POSTs {"task":"searchInspections","data":{...}} to the site
root; the only per-state differences are the `path` token and the
vocabulary — both live in states.py.

Unlike TN (which partitioned by county GUIDs it had hand-captured),
this adapter enumerates STATEWIDE (county:"") with ADAPTIVE DATE
PARTITIONING, because the server paging rules are identical everywhere
(measured on TN 2026-10-15, re-verified on VA/WI/CO/MT/HI 2026-11-16):
  * page size is FIXED at 25 rows; `count` is ignored;
  * `start` must be a multiple of 25 and <= 200 — beyond that the API
    answers {"err":true,"msg":"bad request"}. One query can therefore
    expose at most the newest 225 rows of its result set.
A range that exhausts its window on a full page is split in half and
re-queried recursively; at the 1-day floor it is partitioned by
inspection `purpose` instead (seed vocabulary from states.py plus
every purpose value actually observed in that day's rows). A single
(day, purpose) range that still overflows is recorded in
work/failures.jsonl as "unpartitionable" — NEVER silently truncated.

Per state, leaf-range pages land in raw/<key>/search_pages/STATEWIDE/
<range-tag>_p<NNNN>.json. Resumable: valid saved pages are never
re-fetched; progress in work/<key>/search_done.json; failures in
work/<key>/failures.jsonl; every HTTP response is logged to
work/<key>/fetch_log.tsv.

Politeness: bounded concurrency, per-request delay, exponential
backoff, 600 s timeouts (cold first queries ran ~190 s on TN).

Usage: python mhd_fetch.py va [wi co mt hi ...] [--from YYYY-MM-DD]
"""

import datetime
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from states import STATES  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://inspections.myhealthdepartment.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
      "KyronResearch/0.1 (MHD generic adapter)")
PAGE_SIZE = 25
MAX_START = 200
DELAY = 0.25
WORKERS = 6

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_http_sem = threading.Semaphore(8)


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class StatePaths:
    def __init__(self, key):
        self.raw = os.path.join(ROOT, "raw", key)
        self.work = os.path.join(ROOT, "work", key)
        self.log = os.path.join(self.work, "fetch_log.tsv")
        self.done = os.path.join(self.work, "search_done.json")
        self.fail = os.path.join(self.work, "failures.jsonl")
        os.makedirs(self.raw, exist_ok=True)
        os.makedirs(self.work, exist_ok=True)
        if not os.path.exists(self.log):
            with open(self.log, "w", encoding="utf-8") as f:
                f.write("file\turl\tfetched_utc\thttp_status\tbytes\tsha256\n")


def log_fetch(paths, fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([fname, url, utcnow(), str(status),
                      str(len(body)), sha]) + "\n"
    with _log_lock:
        with open(paths.log, "a", encoding="utf-8") as f:
            f.write(line)


def log_failure(paths, kind, key, err):
    rec = {"ts": utcnow(), "kind": kind, "key": key,
           "error": str(err)[:300]}
    with _fail_lock:
        with open(paths.fail, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def http_post_search(cfg, d0, d1, purpose, start, retries=4):
    payload = {
        "task": "searchInspections",
        "data": {
            "path": cfg["path"], "programName": "",
            "filters": {"date": f"{d0.isoformat()} to {d1.isoformat()}",
                        "purpose": purpose, "county": ""},
            "start": start, "count": PAGE_SIZE, "searchStr": "",
            "lat": 0, "lng": 0, "sort": {},
        },
    }
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                ORIGIN + "/", data=body, method="POST",
                headers={"User-Agent": UA,
                         "Content-Type": "application/json",
                         "Origin": ORIGIN,
                         "Referer": ORIGIN + "/" + cfg["path"] + "/"})
            with _http_sem:
                with urllib.request.urlopen(req, timeout=600) as r:
                    status, raw = r.status, r.read()
            parsed = json.loads(raw.decode("utf-8", "replace"))
            if isinstance(parsed, dict) and (
                    parsed.get("err") or parsed.get("error")):
                raise ValueError(f"api err: {parsed.get('msg')}")
            if not isinstance(parsed, list):
                raise ValueError("search response not a list")
            return status, raw, parsed
        except Exception as e:  # noqa: BLE001 - harvest robustness
            last = e
            time.sleep(2.0 * (2 ** attempt))
    raise last


def range_tag(d0, d1, purpose):
    tag = f"{d0.strftime('%Y%m%d')}_{d1.strftime('%Y%m%d')}"
    if purpose:
        tag += "_" + purpose.upper().replace("-", "").replace(" ", "")
    return tag


def save_body(paths, relpath, url, status, body):
    path = os.path.join(paths.raw, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    log_fetch(paths, relpath, url, status, body)


class Scheduler:
    """Adaptive range-tree for ONE state's statewide search."""

    def __init__(self, key, cfg, paths, date_from, date_to):
        self.key = key
        self.cfg = cfg
        self.paths = paths
        self.rows = 0
        self.leaf_ranges = 0
        self.splits = 0
        self.failed = []
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.pending = 0
        self.t0 = time.time()
        self.date_from = date_from
        self.date_to = date_to
        self.done = {}
        if os.path.exists(paths.done):
            with open(paths.done, encoding="utf-8") as f:
                self.done = json.load(f)
        if self.done.get("STATEWIDE", {}).get("complete"):
            self.finished = True
        else:
            self.finished = False

    def submit(self, ex, d0, d1, purpose):
        with self.lock:
            self.pending += 1
        ex.submit(self.run_range, ex, d0, d1, purpose)

    def run_range(self, ex, d0, d1, purpose):
        try:
            self._range(ex, d0, d1, purpose)
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.failed.append(f"{d0}..{d1}/{purpose}: {e}")
            log_failure(self.paths, "search_range",
                        f"{self.key} {d0} {d1} {purpose}", e)
        finally:
            with self.lock:
                self.pending -= 1
                last = self.pending == 0
            if last:
                self.finish()

    def _range(self, ex, d0, d1, purpose):
        tag = range_tag(d0, d1, purpose)
        start = 0
        observed_purposes = set()
        while True:
            rel = (f"search_pages/STATEWIDE/"
                   f"{tag}_p{start // PAGE_SIZE:04d}.json")
            path = os.path.join(self.paths.raw, rel)
            recs = None
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        cached = json.load(f)
                    if isinstance(cached, list):
                        recs = cached
                except Exception:  # noqa: BLE001
                    recs = None
                if recs is None:
                    os.remove(path)
            if recs is None:
                status, raw, recs = http_post_search(
                    self.cfg, d0, d1, purpose, start)
                save_body(self.paths, rel, ORIGIN + "/#searchInspections",
                          status, raw)
                time.sleep(DELAY)
            with self.lock:
                self.rows += len(recs)
            for r in recs:
                if isinstance(r, dict):
                    observed_purposes.add(r.get("purpose") or "")
            if len(recs) < PAGE_SIZE:
                with self.lock:
                    self.leaf_ranges += 1
                return
            if start >= MAX_START:
                break
            start += PAGE_SIZE
        # window exhausted with a full last page -> split
        with self.lock:
            self.splits += 1
        if d0 < d1:
            mid = d0 + (d1 - d0) / 2
            self.submit(ex, d0, mid, purpose)
            self.submit(ex, mid + datetime.timedelta(days=1),
                        d1, purpose)
        else:
            # 1-day floor: partition by purpose (seed vocab + every
            # purpose value actually observed in this day's rows).
            observed_purposes.discard("")
            purposes = sorted(set(self.cfg["purposes"]) |
                              observed_purposes)
            if not purpose:
                for p in purposes:
                    self.submit(ex, d0, d1, p)
                if not purposes:
                    raise ValueError(
                        f"unpartitionable overflow: {self.key} {d0} "
                        "(no purpose vocabulary to split on)")
            else:
                raise ValueError(
                    f"unpartitionable overflow: {self.key} {d0} "
                    f"{purpose} (single day+purpose exceeds server cap)")

    def finish(self):
        if self.failed:
            print(f"[INCOMPLETE] {self.key}: {len(self.failed)} range "
                  f"failures (see failures.jsonl)", flush=True)
        else:
            rec = {"rows_with_dupes": self.rows, "complete": True,
                   "ts": utcnow(),
                   "seconds": round(time.time() - self.t0, 1),
                   "leaf_ranges": self.leaf_ranges,
                   "splits": self.splits}
            self.done["STATEWIDE"] = rec
            with open(self.paths.done, "w", encoding="utf-8") as f:
                json.dump(self.done, f, indent=1)
            print(f"[done] {self.key}: {self.rows} rows (incl. split "
                  f"dupes), leaves={self.leaf_ranges} "
                  f"splits={self.splits}, {rec['seconds']}s",
                  flush=True)
        self.finished = True
        with self.cond:
            self.cond.notify_all()


def main():
    args = []
    date_from = datetime.date(2015, 1, 1)
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--from" and i + 1 < len(sys.argv):
            date_from = datetime.date.fromisoformat(sys.argv[i + 1])
            i += 2
            continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    keys = args or [k for k, c in STATES.items() if c["enabled"]]
    todo = []
    for k in keys:
        cfg = STATES.get(k)
        if cfg is None:
            print(f"[skip] {k}: not in states.py", flush=True)
            continue
        if not cfg["enabled"]:
            print(f"[skip] {k}: disabled ({cfg['path']} — see "
                  f"states.py notes)", flush=True)
            continue
        todo.append((k, cfg))
    if not todo:
        print("nothing to do", flush=True)
        return
    for key, cfg in todo:
        paths = StatePaths(key)
        sched = Scheduler(key, cfg, paths, date_from,
                          datetime.date.today())
        if sched.finished:
            print(f"[skip] {key} (done)", flush=True)
            continue
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=WORKERS) as ex:
            sched.submit(ex, date_from, datetime.date.today(), "")
            with sched.cond:
                while not sched.finished:
                    sched.cond.wait(timeout=30)
    print("SEARCH FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
