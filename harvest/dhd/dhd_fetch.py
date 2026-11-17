#!/usr/bin/env python3
"""Generic healthinspections.us (DHD) fetcher.

Generalizes harvest/ga/ga_fetch.py: per deployment, discover search
partitions from /filters (a County-style filter when present, else a
single STATEWIDE partition), paginate /search/<json>/<page> 5-at-a-
time into raw/<key>/search_pages/<PART>/pNNNN.json, then fetch
/inspectionsData/<b64 facility id> per facility into
raw/<key>/insp/<PART>/<numeric id>.json.

Resumable: saved files are never re-fetched; completed partitions are
marked in work/<key>/parts_done.json. Every response is logged to
fetch_log.tsv. Retries with exponential backoff.

Usage: python dhd_fetch.py ri [--pages N] [--limit N]
  --pages caps search pages per partition (proof runs)
  --limit caps facilities whose inspectionsData is fetched
"""

import base64
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dhd_states import STATES  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
      "KyronResearch/0.1 (DHD generic adapter)")
PAGE_SIZE = 5
MAX_PAGES = 10000
DELAY = 0.20

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_done_lock = threading.Lock()
_http_sem = threading.Semaphore(8)


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_fetch(log_path, fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([fname, url, utcnow(), str(status),
                      str(len(body)), sha]) + "\n"
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)


def log_failure(fail_path, kind, key, url, err):
    rec = {"ts": utcnow(), "kind": kind, "key": key, "url": url,
           "error": str(err)[:300]}
    with _fail_lock:
        with open(fail_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def http_get(url, retries=4):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _http_sem:
                with urllib.request.urlopen(req, timeout=90) as r:
                    return r.status, r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (2 ** attempt))
    raise last


def b64(s):
    return base64.b64encode(s.encode()).decode()


def search_url(api, county, permit_type, page):
    obj = {"county": b64(county) if county else "",
           "permitType": b64(permit_type) if permit_type else "",
           "keyword": ""}
    js = json.dumps(obj, separators=(",", ":")).replace("/", "%2F")
    return api + "/search/" + urllib.parse.quote(js, safe="%") \
        + "/" + str(page)


def fetch_meta(cfg, raw, log_path):
    api = cfg["host"] + "/" + cfg["path"] + "/API/index.cfm"
    for name, url in [
            ("meta_clientData.json", api + "/clientData"),
            ("meta_filters.json", api + "/filters")]:
        path = os.path.join(raw, name)
        if os.path.exists(path):
            continue
        status, body = http_get(url)
        with open(path, "wb") as f:
            f.write(body)
        log_fetch(log_path, name, url, status, body)
        print(f"[meta] {name}: {len(body)}B", flush=True)


def partition_list(cfg, raw):
    if cfg["partitions"] == "statewide":
        return ["STATEWIDE"]
    with open(os.path.join(raw, "meta_filters.json"),
              encoding="utf-8") as f:
        filters = json.load(f)
    for flt in filters:
        if flt.get("name", "").startswith("County"):
            return sorted(flt["values"])
    return ["STATEWIDE"]


def fetch_partition_search(cfg, raw, log_path, fail_path, part,
                           max_pages):
    api = cfg["host"] + "/" + cfg["path"] + "/API/index.cfm"
    pdir = os.path.join(raw, "search_pages", part)
    stubs, seen = [], set()
    page = 0
    while page < MAX_PAGES and (max_pages <= 0 or page < max_pages):
        rel = f"search_pages/{part}/p{page:04d}.json"
        path = os.path.join(raw, rel)
        if os.path.exists(path):
            with open(path, "rb") as f:
                body = f.read()
        else:
            url = search_url(api, "" if part == "STATEWIDE" else part,
                             cfg["permit_type"], page)
            try:
                status, body = http_get(url)
            except Exception as e:  # noqa: BLE001
                # persistent page failure (e.g. a row that 500s the
                # server-side serializer on every attempt) — log the
                # gap and continue; the facilities on this page are
                # a declared loss, not a silent truncation.
                log_failure(fail_path, "search", f"{part}/p{page}",
                            url, e)
                page += 1
                continue
            os.makedirs(pdir, exist_ok=True)
            with open(path, "wb") as f:
                f.write(body)
            log_fetch(log_path, rel, url, status, body)
            time.sleep(DELAY)
        recs = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(recs, list):
            break
        for rec in recs:
            if rec.get("id") and rec["id"] not in seen:
                seen.add(rec["id"])
                stubs.append(rec)
        if len(recs) < PAGE_SIZE:
            break
        page += 1
    return stubs


def fetch_one_insp(cfg, raw, log_path, fail_path, part, stub):
    api = cfg["host"] + "/" + cfg["path"] + "/API/index.cfm"
    fid_b64 = stub["id"]
    try:
        fid_num = base64.b64decode(fid_b64).decode()
    except Exception:
        fid_num = fid_b64
    rel = f"insp/{part}/{fid_num}.json"
    path = os.path.join(raw, rel)
    if os.path.exists(path):
        return fid_num, True
    url = api + "/inspectionsData/" + urllib.parse.quote(fid_b64,
                                                       safe="")
    try:
        status, body = http_get(url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        log_fetch(log_path, rel, url, status, body)
        time.sleep(DELAY)
        return fid_num, True
    except Exception as e:  # noqa: BLE001
        log_failure(fail_path, "inspectionsData",
                    f"{part}/{fid_num}", url, e)
        return fid_num, False


def main():
    args, max_pages, limit = [], 0, 0
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--pages" and i + 1 < len(sys.argv):
            max_pages = int(sys.argv[i + 1]); i += 2; continue
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1]); i += 2; continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    keys = args or [k for k, c in STATES.items() if c["enabled"]]
    for key in keys:
        cfg = STATES.get(key)
        if cfg is None or not cfg["enabled"]:
            print(f"[skip] {key}", flush=True)
            continue
        raw = os.path.join(ROOT, "raw", key)
        work = os.path.join(ROOT, "work", key)
        os.makedirs(raw, exist_ok=True)
        os.makedirs(work, exist_ok=True)
        log_path = os.path.join(work, "fetch_log.tsv")
        fail_path = os.path.join(work, "failures.jsonl")
        done_path = os.path.join(work, "parts_done.json")
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("file\turl\tfetched_utc\thttp_status\tbytes"
                        "\tsha256\n")
        fetch_meta(cfg, raw, log_path)
        parts = partition_list(cfg, raw)
        done = {}
        if os.path.exists(done_path):
            with open(done_path, encoding="utf-8") as f:
                done = json.load(f)
        for part in parts:
            if done.get(part, {}).get("complete"):
                continue
            t0 = time.time()
            stubs = fetch_partition_search(cfg, raw, log_path,
                                           fail_path, part, max_pages)
            todo = stubs[:limit] if limit else stubs
            ok = fail = 0
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=3) as ex:
                futs = {ex.submit(fetch_one_insp, cfg, raw, log_path,
                                  fail_path, part, s): s
                        for s in todo}
                for fut in concurrent.futures.as_completed(futs):
                    _, good = fut.result()
                    ok += good
                    fail += not good
            rec = {"facilities": len(stubs), "detail_fetched": ok,
                   "detail_fail": fail,
                   "complete": fail == 0 and not max_pages
                   and not limit,
                   "ts": utcnow(), "seconds": round(time.time() - t0, 1)}
            with _done_lock:
                done[part] = rec
                with open(done_path, "w", encoding="utf-8") as f:
                    json.dump(done, f, indent=1)
            print(f"[done] {key}/{part}: {len(stubs)} facilities, "
                  f"insp ok={ok} fail={fail}, {rec['seconds']}s",
                  flush=True)
    print("DHD FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
