#!/usr/bin/env python3
"""Mississippi MSDH food-facility fetcher — harvest/ms.

Portal: https://apps.msdh.ms.gov/food/ (custom ASP.NET / CodeCharge).

Three reachable levels (verified 2026-11-17):
  FacilityListing.aspx?...&FacListingPageSize=10000&FacListingPage=N
      -> paginated listing, ~16.9k facilities over 2 pages; each row
         links FacilityRecord.aspx?PimsID=<id>
  FacilityRecord.aspx?PimsID=<id>
      -> facility identity (name/street/city/zip/status) + the full
         inspection summary table (Ref# | Type | Grade A/B/C | Date |
         Inspector). ~23KB per facility.
  FacilityRecordDetailsNewInspection.aspx?PimsID=<id>&InspectionNumber=<n>
      -> per-inspection violation checklist (~41KB). NOT fetched in
         v1: ~40-60k pages. The record page already carries every
         published grade; details stay one official click away via
         the report URL we ship.

Phase A writes raw/listing_pNNNN.html and extracts PimsIDs into
work/facilities.jsonl. Phase B fetches raw/rec/<pimsid>.html per
facility — resumable (saved files are never re-fetched), single-
threaded, polite delay, failures logged to work/failures.jsonl.

Usage: python ms_fetch.py [--max N] [--listing-only]
"""

import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
UA = {"User-Agent": "KyronResearch/0.1 (public records aggregator)"}
DELAY = 1.2
TIMEOUT = 60

BASE = "https://apps.msdh.ms.gov/food/"
LISTING = (BASE + "FacilityListing.aspx?s_FacilityTypesID=&s_CountyID="
           "&s_FacilityName=&s_FacilityCity=&s_FacilityStreet="
           "&FacListingDir=Asc&FacListingPageSize=10000")
RECORD = BASE + "FacilityRecord.aspx?PimsID="

PIMS_RE = re.compile(r"FacilityRecord\.aspx\?PimsID=(\d+)")
PAGES_RE = re.compile(r"of&nbsp;?(\d+)|\bof\s+(\d+)")


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read()
        except Exception as e:
            last = e
            time.sleep(2 ** attempt * 2)
    raise last


def log_fetch(path, fname, url, status, body):
    with open(path, "a", encoding="utf-8") as f:
        f.write("\t".join([fname, url, utcnow(), str(status),
                           str(len(body))]) + "\n")


def log_failure(path, kind, key, err):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utcnow(), "kind": kind, "key": key,
                            "error": str(err)}) + "\n")


def fetch_listings(log_path, fail_path, listing_only):
    """Download every listing page; return sorted unique PimsIDs."""
    ids = set()
    page = 1
    total_pages = None
    while True:
        fname = f"listing_p{page:04d}.html"
        path = os.path.join(RAW, fname)
        if not os.path.exists(path):
            url = LISTING + f"&FacListingPage={page}"
            try:
                status, body = http_get(url)
                if status == 200 and b"FacilityRecord.aspx" not in body \
                        and page == 1:
                    raise RuntimeError("listing returned no facility rows")
                if status == 200 and b"FacilityRecord.aspx" not in body:
                    break  # ran past the last page
                with open(path, "wb") as f:
                    f.write(body)
                log_fetch(log_path, fname, url, status, body)
                print(f"[listing] page {page}: {len(body)}B", flush=True)
            except Exception as e:
                log_failure(fail_path, "listing", str(page), e)
                raise
            time.sleep(DELAY)
        with open(path, encoding="cp1252", errors="replace") as f:
            html = f.read()
        if total_pages is None:
            m = PAGES_RE.search(html)
            if m:
                total_pages = int(m.group(1) or m.group(2))
                print(f"[listing] portal reports {total_pages} pages",
                      flush=True)
        ids.update(PIMS_RE.findall(html))
        if total_pages is not None and page >= total_pages:
            break
        page += 1
    ids = sorted(ids, key=int)
    out = os.path.join(WORK, "facilities.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for pid in ids:
            f.write(json.dumps({"pimsid": pid}) + "\n")
    print(f"[listing] {len(ids)} facilities", flush=True)
    return ids


def fetch_records(ids, max_n, log_path, fail_path):
    import concurrent.futures
    import threading
    rec_dir = os.path.join(RAW, "rec")
    os.makedirs(rec_dir, exist_ok=True)
    todo = [p for p in ids
            if not os.path.exists(os.path.join(rec_dir, p + ".html"))]
    if max_n:
        todo = todo[:max_n]
    print(f"[records] {len(todo)} to fetch "
          f"({len(ids) - len(todo)} already saved)", flush=True)
    lock = threading.Lock()
    counter = [0]

    def one(pid):
        url = RECORD + pid
        path = os.path.join(rec_dir, pid + ".html")
        try:
            status, body = http_get(url)
            if status == 200 and \
                    b"The resource cannot be found" in body:
                with lock:
                    log_failure(fail_path, "record", pid, "404 body")
            else:
                with open(path, "wb") as f:
                    f.write(body)
                with lock:
                    log_fetch(log_path, "rec/" + pid + ".html", url,
                              status, body)
        except Exception as e:
            with lock:
                log_failure(fail_path, "record", pid, e)
        with lock:
            counter[0] += 1
            if counter[0] % 250 == 0:
                print(f"[records] {counter[0]}/{len(todo)}", flush=True)
        time.sleep(DELAY)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, todo))


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    args = sys.argv[1:]
    max_n = 0
    listing_only = "--listing-only" in args
    if "--max" in args:
        max_n = int(args[args.index("--max") + 1])
    log_path = os.path.join(WORK, "fetch_log.tsv")
    fail_path = os.path.join(WORK, "failures.jsonl")
    ids = fetch_listings(log_path, fail_path, listing_only)
    if not listing_only:
        fetch_records(ids, max_n, log_path, fail_path)


if __name__ == "__main__":
    main()
