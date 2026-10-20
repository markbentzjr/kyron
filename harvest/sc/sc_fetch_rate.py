#!/usr/bin/env python3
"""Kyron SC adapter — rate.aspx (Advanced Search) fetcher (prototype v0.1).

The SC Food Grades Advanced Search at apps.dhec.sc.gov returns full
inspection history as an HTML table (establishment, street, city, grade,
date, type, PDF link whose GUID is the inspection's AuditResultGlobalID).

Paging contract (measured 2026-10-15): the endpoint prints the TRUE
match count ("N records matched your search") but displays at most
2000 rows. Enumeration therefore uses adaptive date partitioning per
county: a window whose matched count exceeds its displayed rows is
split in half recursively until every leaf window displays its full
match count (provably exhausted). Adjacent windows never overlap
(ed = mid, next sd = mid + 1 day; the endpoint treats both bounds
inclusively). Every response is saved raw and SHA-256-logged to
fetch_log.tsv; only leaf pages go to raw/rate/, probes to work/.
Resumable: completed leaf windows are recorded in work/rate_done.tsv.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw", "rate")
WORK = os.path.join(HERE, "work")
LOG = os.path.join(HERE, "fetch_log.tsv")
DONE = os.path.join(WORK, "rate_done.tsv")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE = "https://apps.dhec.sc.gov/Environment/FoodGrades/rate.aspx"
START = date(2015, 1, 1)
END = date(2026, 10, 15)
CAP = 2000

COUNTIES = {
    "01": "ABBEVILLE", "02": "AIKEN", "03": "ALLENDALE", "04": "ANDERSON",
    "05": "BAMBERG", "06": "BARNWELL", "07": "BEAUFORT", "08": "BERKELEY",
    "09": "CALHOUN", "10": "CHARLESTON", "11": "CHEROKEE", "12": "CHESTER",
    "13": "CHESTERFIELD", "14": "CLARENDON", "15": "COLLETON",
    "16": "DARLINGTON", "17": "DILLON", "18": "DORCHESTER", "19": "EDGEFIELD",
    "20": "FAIRFIELD", "21": "FLORENCE", "22": "GEORGETOWN",
    "23": "GREENVILLE", "24": "GREENWOOD", "25": "HAMPTON", "26": "HORRY",
    "27": "JASPER", "28": "KERSHAW", "29": "LANCASTER", "30": "LAURENS",
    "31": "LEE", "32": "LEXINGTON", "33": "MCCORMICK", "34": "MARION",
    "35": "MARLBORO", "36": "NEWBERRY", "37": "OCONEE", "38": "ORANGEBURG",
    "39": "PICKENS", "40": "RICHLAND", "41": "SALUDA", "42": "SPARTANBURG",
    "43": "SUMTER", "44": "UNION", "45": "WILLIAMSBURG", "46": "YORK",
}

_lock = threading.Lock()
_done = set()
if os.path.exists(DONE):
    with open(DONE) as fh:
        for line in fh:
            _done.add(line.rstrip("\n"))


def log(url, path, status, body):
    sha = hashlib.sha256(body).hexdigest()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rel = os.path.relpath(path, HERE)
    with _lock:
        with open(LOG, "a") as fh:
            fh.write(f"{rel}\t{url}\t{ts}\t{status}\t{len(body)}\t{sha}\n")


def http_get(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.status, resp.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def parse_counts(html):
    # Zero-match windows return a bare page: "No records found with that
    # search criteria." and no "N records matched" line (measured
    # 2026-10-15, county 02, 2015-01-01..2020-11-22).
    if "No records found with that search criteria" in html:
        return 0, 0
    m = re.search(r"(\d+) records matched", html)
    matched = int(m.group(1)) if m else None
    rows = html.count("<tr valign='top'>")
    return matched, rows


def fmt(d):
    return d.strftime("%m/%d/%Y")


def query(cc, d0, d1):
    url = (f"{BASE}?fn=&pg=&ft=&aa=&ci=&cy={cc}"
           f"&sd={fmt(d0)}&ed={fmt(d1)}")
    status, body = http_get(url)
    html = body.decode("utf-8", "replace")
    matched, rows = parse_counts(html)
    if matched is None:
        raise RuntimeError(f"no match-count in response for {cc} {d0}..{d1}")
    return url, status, body, matched, rows


def save_leaf(cc, d0, d1, url, status, body):
    outdir = os.path.join(RAW, cc)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{d0.isoformat()}_{d1.isoformat()}.html")
    with open(path, "wb") as fh:
        fh.write(body)
    log(url, path, status, body)


def walk(cc, d0, d1, depth=0):
    key = f"{cc}\t{d0.isoformat()}\t{d1.isoformat()}"
    if key in _done:
        return 0
    url, status, body, matched, rows = query(cc, d0, d1)
    if matched == 0:
        _mark(key)
        return 0
    if rows >= matched:
        save_leaf(cc, d0, d1, url, status, body)
        _mark(key)
        return matched
    if d0 == d1:
        raise RuntimeError(f"single day still capped: {cc} {d0} "
                           f"matched={matched} rows={rows}")
    mid = d0 + timedelta(days=(d1 - d0).days // 2)
    total = walk(cc, d0, mid, depth + 1)
    total += walk(cc, mid + timedelta(days=1), d1, depth + 1)
    return total


def _mark(key):
    with _lock:
        _done.add(key)
        with open(DONE, "a") as fh:
            fh.write(key + "\n")


def run_county(cc):
    t0 = time.time()
    try:
        n = walk(cc, START, END)
    except Exception as e:  # noqa: BLE001 — one county must not kill the run
        print(f"county {cc} {COUNTIES[cc]}: FAILED {e}", flush=True)
        return cc, -1
    print(f"county {cc} {COUNTIES[cc]}: {n} rows "
          f"({time.time() - t0:.0f}s)", flush=True)
    return cc, n


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for cc, n in ex.map(run_county, sorted(COUNTIES)):
            results[cc] = n
    with open(os.path.join(WORK, "rate_totals.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    print("rate fetch complete:", sum(results.values()), "rows total")


if __name__ == "__main__":
    sys.exit(main())
