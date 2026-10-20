#!/usr/bin/env python3
"""Tennessee Dept. of Health (MyHealthDepartment portal) fetcher — search phase.
Kyron TN adapter prototype v0.3.

Source: Tennessee Department of Health inspection portal
  https://inspections.myhealthdepartment.com/tennessee/
The portal is an AngularJS SPA whose own client POSTs JSON
{"task":"searchInspections","data":{...}} to the site root. That public
backend is what this adapter reads — the same requests the portal's
landing page makes (no keyword search is used: keyword search is the
only flow the UI gates behind reCAPTCHA; enumeration here uses the
ungated county/date filter flow exactly as the landing page issues it).

SERVER PAGING RULES (measured 2026-10-15, probes in work/):
  * page size is FIXED at 25 rows; the `count` parameter is ignored;
  * `start` must be a multiple of 25 and <= 200 — beyond that the API
    answers {"err":true,"msg":"bad request"}. A single query can
    therefore expose at most the newest 225 rows of its result set.
Enumeration copes by ADAPTIVE DATE PARTITIONING: each county is
queried over a date range; if the start=200 page comes back full, the
range is split in half and both halves are re-queried, recursively,
until every leaf range ends on a short page (provably exhausted). At
the 1-day floor the range is partitioned by inspection purpose
instead. Rows are deduplicated by inspectionID downstream, so
overlapping ranges are harmless.

v0.3 runs the range tree on a GLOBAL work queue (8 range workers):
sibling subtrees of a county are explored concurrently and small
counties no longer queue behind the metros. Per county (all 95 TN
counties; the 96th filter entry is an out-of-state body-art
pseudo-county, skipped), leaf-range pages land in
raw/search_pages/<COUNTY>/<range-tag>_p<NNNN>.json. Each row is one
INSPECTION stub (all permit types; the normalizer keeps Commercial
Food).

Resumable: valid saved pages are never re-fetched (a cached page that
does not parse as a JSON list is deleted and refetched); per-county
progress in work/search_done.json; failures in work/failures.jsonl.
Every HTTP response is appended to fetch_log.tsv (file, url,
fetched_utc, status, bytes, sha256).

Politeness: HTTP concurrency capped by semaphore, per-request delay,
backoff retries, 600 s timeouts (a cold first query once took ~190 s;
uncached range queries run up to ~20 s, warm ones 1-4 s).
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

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
LOG_PATH = os.path.join(ROOT, "fetch_log.tsv")
DONE_PATH = os.path.join(WORK, "search_done.json")
FAIL_PATH = os.path.join(WORK, "failures.jsonl")
COUNTIES_PATH = os.path.join(WORK, "counties.json")

ORIGIN = "https://inspections.myhealthdepartment.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "KyronResearch/0.1 (TN adapter prototype)")
PAGE_SIZE = 25
MAX_START = 200
DATE_FROM = datetime.date(2015, 1, 1)
DATE_TO = datetime.date.today()
DELAY = 0.25
PURPOSES = ["Routine", "Complete", "Follow-Up", "Complaint"]
WORKERS = 8

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_done_lock = threading.Lock()
_http_sem = threading.Semaphore(10)


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_fetch(fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([fname, url, utcnow(), str(status),
                      str(len(body)), sha]) + "\n"
    with _log_lock:
        with open(LOG_PATH, "a") as f:
            f.write(line)


def log_failure(kind, key, err):
    rec = {"ts": utcnow(), "kind": kind, "key": key,
           "error": str(err)[:300]}
    with _fail_lock:
        with open(FAIL_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")


def http_post_search(county_guid, d0, d1, purpose, start, retries=4):
    payload = {
        "task": "searchInspections",
        "data": {
            "path": "tennessee", "programName": "",
            "filters": {"date": f"{d0.isoformat()} to {d1.isoformat()}",
                        "purpose": purpose, "county": county_guid},
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
                         "Referer": ORIGIN + "/tennessee/"})
            with _http_sem:
                with urllib.request.urlopen(req, timeout=600) as r:
                    status, raw = r.status, r.read()
            parsed = json.loads(raw.decode("utf-8", "replace"))
            if isinstance(parsed, dict) and parsed.get("err"):
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
        tag += "_" + purpose.upper().replace("-", "")
    return tag


def save_body(relpath, url, status, body):
    path = os.path.join(RAW, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    log_fetch(relpath, url, status, body)


def county_dir_name(name):
    return name.upper().replace(" ", "_")


class CountyJob:
    def __init__(self, name, guid):
        self.name = name
        self.guid = guid
        self.cdir = county_dir_name(name)
        self.pending = 0
        self.rows = 0
        self.leaf_ranges = 0
        self.splits = 0
        self.failed = []
        self.lock = threading.Lock()
        self.t0 = time.time()


class Scheduler:
    def __init__(self, jobs):
        self.jobs = {j.name: j for j in jobs}
        self.remaining = len(jobs)
        self.cond = threading.Condition()
        self.done = {}
        if os.path.exists(DONE_PATH):
            with open(DONE_PATH) as f:
                self.done = json.load(f)

    def submit(self, ex, job, d0, d1, purpose):
        with job.lock:
            job.pending += 1
        ex.submit(self.run_range, ex, job, d0, d1, purpose)

    def run_range(self, ex, job, d0, d1, purpose):
        try:
            self._range(ex, job, d0, d1, purpose)
        except Exception as e:  # noqa: BLE001
            with job.lock:
                job.failed.append(f"{d0}..{d1}/{purpose}: {e}")
            log_failure("search_range", f"{job.name} {d0} {d1}",
                        e)
        finally:
            with job.lock:
                job.pending -= 1
                last = job.pending == 0
            if last:
                self.finish(job)

    def _range(self, ex, job, d0, d1, purpose):
        tag = range_tag(d0, d1, purpose)
        start = 0
        while True:
            rel = (f"search_pages/{job.cdir}/"
                   f"{tag}_p{start // PAGE_SIZE:04d}.json")
            path = os.path.join(RAW, rel)
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
                    job.guid, d0, d1, purpose, start)
                save_body(rel, ORIGIN + "/#searchInspections",
                          status, raw)
                time.sleep(DELAY)
            with job.lock:
                job.rows += len(recs)
            if len(recs) < PAGE_SIZE:
                with job.lock:
                    job.leaf_ranges += 1
                return
            if start >= MAX_START:
                break
            start += PAGE_SIZE
        # window exhausted with a full last page -> split
        with job.lock:
            job.splits += 1
        if d0 < d1:
            mid = d0 + (d1 - d0) / 2
            self.submit(ex, job, d0, mid, purpose)
            self.submit(ex, job, mid + datetime.timedelta(days=1),
                        d1, purpose)
        elif not purpose:
            for p in PURPOSES:
                self.submit(ex, job, d0, d1, p)
        else:
            raise ValueError(
                f"unpartitionable overflow: {job.name} {d0} {purpose}")

    def finish(self, job):
        if job.failed:
            print(f"[INCOMPLETE] {job.name}: {len(job.failed)} range "
                  f"failures (see failures.jsonl)", flush=True)
            with self.cond:
                self.remaining -= 1
                self.cond.notify_all()
            return
        rec = {"rows_with_dupes": job.rows, "complete": True,
               "ts": utcnow(),
               "seconds": round(time.time() - job.t0, 1),
               "leaf_ranges": job.leaf_ranges, "splits": job.splits}
        with _done_lock:
            self.done[job.name] = rec
            with open(DONE_PATH, "w") as f:
                json.dump(self.done, f, indent=1)
        print(f"[done] {job.name}: {job.rows} rows (incl. split "
              f"dupes), leaves={job.leaf_ranges} splits={job.splits}, "
              f"{rec['seconds']}s", flush=True)
        with self.cond:
            self.remaining -= 1
            self.cond.notify_all()


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w") as f:
            f.write("file\turl\tfetched_utc\thttp_status\tbytes\tsha256\n")
    with open(COUNTIES_PATH) as f:
        counties = json.load(f)
    done = {}
    if os.path.exists(DONE_PATH):
        with open(DONE_PATH) as f:
            done = json.load(f)
    only = sys.argv[1:] or None
    jobs = []
    for guid, name in counties.items():
        if name.startswith("OOS"):
            continue
        if only and name not in only:
            continue
        if done.get(name, {}).get("complete"):
            print(f"[skip] {name} (done)", flush=True)
            continue
        jobs.append(CountyJob(name, guid))
    if not jobs:
        print("nothing to do", flush=True)
        return
    sched = Scheduler(jobs)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=WORKERS) as ex:
        for job in jobs:
            sched.submit(ex, job, DATE_FROM, DATE_TO, "")
        with sched.cond:
            while sched.remaining > 0:
                sched.cond.wait(timeout=30)
    print("SEARCH FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
