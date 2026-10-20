#!/usr/bin/env python3
"""Georgia DPH (Tyler DHD portal) fetcher — Kyron GA adapter prototype v0.1.

Source: State of Georgia Health Inspection portal
  https://ga.healthinspections.us/stateofgeorgia/
  API base: https://ga.healthinspections.us/stateofgeorgia/API/index.cfm
  (the portal's own public JSON backend, used by its web UI)

What it fetches, per county (all 159 portal counties):
  * search pages: permitType="Food Service", county=<COUNTY>, 5/page
    -> raw/search_pages/<COUNTY>/p<NNNN>.json
  * inspectionsData per facility (<=5 most recent inspections w/ violation
    narratives) -> raw/insp/<COUNTY>/<facility numeric id>.json

Gwinnett / Newton / Rockdale publish via GNR Health District
(inspections.myhealthdepartment.com) and return ZERO results here;
they are probed once and skipped (evidence in fetch_log.tsv).

Resumable: completed counties are marked in work/counties_done.json;
existing raw files are never re-fetched. Every HTTP response is logged
to fetch_log.tsv (file, url, fetched_utc, status, bytes, sha256).

Politeness: 4 workers max, per-request delay, exponential backoff on
errors, abort-and-continue per county on persistent failure.
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

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
LOG_PATH = os.path.join(ROOT, "fetch_log.tsv")
DONE_PATH = os.path.join(WORK, "counties_done.json")
FAIL_PATH = os.path.join(WORK, "failures.jsonl")

LOG_PATH = os.environ.get("GA_LOG", LOG_PATH)
DONE_PATH = os.environ.get("GA_DONE", DONE_PATH)
API = "https://ga.healthinspections.us/stateofgeorgia/API/index.cfm"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 KyronResearch/0.1 (GA adapter prototype)"
PAGE_SIZE = 5
MAX_PAGES = 4000
DELAY = 0.20  # seconds per request per worker
GNR_COUNTIES = ["GWINNETT", "NEWTON", "ROCKDALE"]

# 2020-Census population priority (largest first) — only affects fetch
# order, so a partial run maximizes population coverage.
PRIORITY = [
    "FULTON", "DEKALB", "COBB", "CLAYTON", "CHATHAM", "CHEROKEE",
    "FORSYTH", "HENRY", "MUSCOGEE", "RICHMOND", "HALL", "PAULDING",
    "HOUSTON", "COLUMBIA", "BIBB", "COWETA", "DOUGLAS", "CARROLL",
    "FAYETTE", "LOWNDES", "WHITFIELD", "BARTOW", "FLOYD", "WALTON",
    "BARROW", "BULLOCH", "GLYNN", "CATOOSA", "CAMDEN", "BRYAN",
    "EFFINGHAM", "LEE", "TROUP", "WALKER", "SPALDING", "LIBERTY",
    "NEWTON", "ROCKDALE", "GWINNETT", "CLARKE", "DOUGHERTY", "BALDWIN",
    "HABERSHAM", "JACKSON", "MADISON", "MONROE", "PEACH", "PIKE",
]

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_done_lock = threading.Lock()
_http_sem = threading.Semaphore(8)  # cap total concurrent HTTP requests


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_fetch(fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([
        fname, url, utcnow(), str(status), str(len(body)), sha,
    ]) + "\n"
    with _log_lock:
        with open(LOG_PATH, "a") as f:
            f.write(line)


def log_failure(kind, key, url, err):
    rec = {"ts": utcnow(), "kind": kind, "key": key, "url": url,
           "error": str(err)[:300]}
    with _fail_lock:
        with open(FAIL_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")


def http_get(url, retries=4):
    """Return (status, body_bytes). Raises after retries exhausted."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _http_sem:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, r.read()
        except Exception as e:  # noqa: BLE001 - harvest robustness
            last = e
            time.sleep(1.5 * (2 ** attempt))
    raise last


def save_body(relpath, url, status, body):
    path = os.path.join(RAW, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    log_fetch(relpath, url, status, body)


def b64(s):
    return base64.b64encode(s.encode()).decode()


def search_url(county, page):
    obj = {"county": b64(county), "permitType": b64("Food Service"),
           "keyword": ""}
    js = json.dumps(obj, separators=(",", ":")).replace("/", "%2F")
    return (API + "/search/" + urllib.parse.quote(js, safe="%")
            + "/" + str(page))


def fetch_meta():
    for name, url in [
        ("meta_clientData.json", API + "/clientData"),
        ("meta_filters.json", API + "/filters"),
    ]:
        if os.path.exists(os.path.join(RAW, name)):
            continue
        status, body = http_get(url)
        save_body(name, url, status, body)
        print(f"[meta] {name}: HTTP {status} {len(body)}B", flush=True)


def county_list():
    with open(os.path.join(RAW, "meta_filters.json")) as f:
        filters = json.load(f)
    for f in filters:
        if f.get("name", "").startswith("County"):
            counties = list(f["values"])
            break
    else:
        raise SystemExit("county filter not found")
    ordered = [c for c in PRIORITY if c in counties]
    ordered += sorted(c for c in counties if c not in ordered)
    return ordered


def fetch_county_search(county):
    """Paginate the county's Food Service search. Returns list of stubs
    (deduped by facility id, API order preserved)."""
    cdir = os.path.join(RAW, "search_pages", county)
    stubs, seen = [], set()
    page = 0
    while page < MAX_PAGES:
        rel = f"search_pages/{county}/p{page:04d}.json"
        path = os.path.join(RAW, rel)
        if os.path.exists(path):
            with open(path, "rb") as f:
                body = f.read()
        else:
            url = search_url(county, page)
            status, body = http_get(url)
            save_body(rel, url, status, body)
            time.sleep(DELAY)
        recs = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(recs, list):
            raise ValueError(f"search page not a list: {county} p{page}")
        for rec in recs:
            if rec["id"] not in seen:
                seen.add(rec["id"])
                stubs.append(rec)
        if len(recs) < PAGE_SIZE:
            break
        page += 1
    return stubs


def fetch_one_insp(county, stub):
    fid_b64 = stub["id"]
    fid_num = base64.b64decode(fid_b64).decode()
    rel = f"insp/{county}/{fid_num}.json"
    path = os.path.join(RAW, rel)
    if os.path.exists(path):
        return fid_num, True
    url = API + "/inspectionsData/" + urllib.parse.quote(fid_b64, safe="")
    try:
        status, body = http_get(url)
        save_body(rel, url, status, body)
        time.sleep(DELAY)
        return fid_num, True
    except Exception as e:  # noqa: BLE001
        log_failure("inspectionsData", f"{county}/{fid_num}", url, e)
        return fid_num, False


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w") as f:
            f.write("file\turl\tfetched_utc\thttp_status\tbytes\tsha256\n")
    fetch_meta()
    counties = county_list()
    shard = int(os.environ.get("GA_SHARD", "0"))
    nshards = int(os.environ.get("GA_NSHARDS", "1"))
    if nshards > 1:
        counties = counties[shard::nshards]
        print(f"[shard] {shard}/{nshards}: {len(counties)} counties",
              flush=True)
    done = {}
    if os.path.exists(DONE_PATH):
        with open(DONE_PATH) as f:
            done = json.load(f)

    only = sys.argv[1:] or None

    def process_county(county):
        if done.get(county, {}).get("complete"):
            print(f"[skip] {county} (done)", flush=True)
            return
        t0 = time.time()
        try:
            stubs = fetch_county_search(county)
        except Exception as e:  # noqa: BLE001
            log_failure("search", county, search_url(county, 0), e)
            print(f"[FAIL search] {county}: {e}", flush=True)
            return
        ok = fail = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(fetch_one_insp, county, s): s for s in stubs}
            for fut in concurrent.futures.as_completed(futs):
                _, good = fut.result()
                if good:
                    ok += 1
                else:
                    fail += 1
        rec = {
            "facilities": len(stubs), "insp_ok": ok, "insp_fail": fail,
            "complete": fail == 0, "ts": utcnow(),
            "seconds": round(time.time() - t0, 1),
        }
        with _done_lock:
            done[county] = rec
            with open(DONE_PATH, "w") as f:
                json.dump(done, f, indent=1)
        print(f"[done] {county}: {len(stubs)} facilities, insp ok={ok} "
              f"fail={fail}, {rec['seconds']}s", flush=True)

    todo = [c for c in counties if not only or c in only]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(process_county, todo))
    print("FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
