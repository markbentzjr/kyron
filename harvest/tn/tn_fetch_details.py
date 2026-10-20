#!/usr/bin/env python3
"""Tennessee MyHealthDepartment fetcher — inspection detail phase.
Kyron TN adapter prototype v0.1.

For every FOOD SERVICE inspection stub collected by tn_fetch.py
(permitType "Commercial Food*" and inspectionType "Food Service
Establishment Inspection"), fetch the server-rendered detail page
  GET /tennessee/inspection/?inspectionID=<GUID>
-> raw/insp/<COUNTY>/<inspectionID>.html, logged in fetch_log.tsv.

Detail pages 403 / hang for cookieless or non-browser agents, so each
worker keeps a cookie session (primed with a landing-page GET) with a
Chrome UA + Referer, refreshed on failure with exponential backoff.

STUB VERIFICATION (the GA crossed-payload lesson): every parsed detail
is checked against its search stub — permitID, name, date, and score
must all agree. Disagreements are logged to work/detail_mismatch.jsonl
and the record is queued for a sequential re-fetch (tn_mopup.py);
nothing is silently trusted.

Resumable: inspections already on disk are skipped. Counties are
processed once their search phase is marked complete in
work/search_done.json (pass --all to use whatever search pages exist).
"""

import hashlib
import http.cookiejar
import json
import os
import re
import sys
import threading
import time
import urllib.request
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tn_parse import parse_detail  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
LOG_PATH = os.path.join(ROOT, "fetch_log.tsv")
DONE_PATH = os.path.join(WORK, "details_done.json")
FAIL_PATH = os.path.join(WORK, "failures.jsonl")
MISMATCH_PATH = os.path.join(WORK, "detail_mismatch.jsonl")

ORIGIN = "https://inspections.myhealthdepartment.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
      "KyronResearch/0.1")
DELAY = 0.15

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_done_lock = threading.Lock()
_mm_lock = threading.Lock()
_http_sem = threading.Semaphore(10)
_tls = threading.local()


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_fetch(fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([fname, url, utcnow(), str(status),
                      str(len(body)), sha]) + "\n"
    with _log_lock:
        with open(LOG_PATH, "a") as f:
            f.write(line)


def log_jsonl(path, lock, rec):
    with lock:
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")


def session():
    if not hasattr(_tls, "opener"):
        cj = http.cookiejar.CookieJar()
        _tls.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))
        _tls.primed = False
    return _tls.opener


def prime_session():
    opener = session()
    req = urllib.request.Request(
        ORIGIN + "/tennessee/",
        headers={"User-Agent": UA})
    with _http_sem:
        with opener.open(req, timeout=60) as r:
            r.read()
    _tls.primed = True


def http_get_detail(inspection_id, retries=4):
    url = (ORIGIN + "/tennessee/inspection/?inspectionID="
           + inspection_id)
    last = None
    for attempt in range(retries):
        try:
            if not getattr(_tls, "primed", False):
                prime_session()
            req = urllib.request.Request(
                url, headers={"User-Agent": UA,
                              "Referer": ORIGIN + "/tennessee/"})
            with _http_sem:
                with session().open(req, timeout=120) as r:
                    return r.status, r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            _tls.primed = False
            time.sleep(1.5 * (2 ** attempt))
    raise last


def norm_name(s):
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def verify_stub(stub, parsed):
    """Return list of disagreement strings (empty = verified)."""
    probs = []
    if parsed["permitID"] != stub["permitID"].upper():
        probs.append(f"permitID {parsed['permitID']} != "
                     f"stub {stub['permitID']}")
    if norm_name(parsed["name"]) != norm_name(
            stub["establishmentName"]):
        probs.append(f"name {parsed['name']!r} != stub "
                     f"{stub['establishmentName']!r}")
    if parsed["date"] != stub["inspectionDate"][:10]:
        probs.append(f"date {parsed['date']} != stub "
                     f"{stub['inspectionDate'][:10]}")
    if parsed["score"] != stub.get("score"):
        probs.append(f"score {parsed['score']} != stub "
                     f"{stub.get('score')}")
    if parsed["inspectionID"] != stub["inspectionID"].upper():
        probs.append(f"inspectionID {parsed['inspectionID']} != "
                     f"stub {stub['inspectionID']}")
    return probs


def load_food_stubs(county_dir):
    """All food-service stubs from one county's search pages."""
    stubs = {}
    cdir = os.path.join(RAW, "search_pages", county_dir)
    if not os.path.isdir(cdir):
        return stubs
    for fname in sorted(os.listdir(cdir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(cdir, fname)) as f:
            rows = json.load(f)
        for r in rows:
            if not (r.get("permitType", "").startswith("Commercial Food")
                    and r.get("inspectionType")
                    == "Food Service Establishment Inspection"):
                continue
            stubs[r["inspectionID"]] = r
    return stubs


def fetch_one(county_dir, stub):
    iid = stub["inspectionID"]
    rel = f"insp/{county_dir}/{iid}.html"
    path = os.path.join(RAW, rel)
    if os.path.exists(path):
        return iid, "cached"
    url = (ORIGIN + "/tennessee/inspection/?inspectionID=" + iid)
    try:
        status, body = http_get_detail(iid)
    except Exception as e:  # noqa: BLE001
        log_jsonl(FAIL_PATH, _fail_lock,
                  {"ts": utcnow(), "kind": "detail",
                   "key": f"{county_dir}/{iid}", "url": url,
                   "error": str(e)[:300]})
        return iid, "fail"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    log_fetch(rel, url, status, body)
    time.sleep(DELAY)
    try:
        parsed = parse_detail(body.decode("utf-8", "replace"))
        probs = verify_stub(stub, parsed)
    except Exception as e:  # noqa: BLE001
        probs = [f"parse error: {e}"]
    if probs:
        log_jsonl(MISMATCH_PATH, _mm_lock,
                  {"ts": utcnow(), "county": county_dir,
                   "inspectionID": iid, "problems": probs})
        return iid, "mismatch"
    return iid, "ok"


def main():
    use_all = "--all" in sys.argv
    done_search = {}
    sp = os.path.join(WORK, "search_done.json")
    if os.path.exists(sp):
        with open(sp) as f:
            done_search = json.load(f)
    done = {}
    if os.path.exists(DONE_PATH):
        with open(DONE_PATH) as f:
            done = json.load(f)

    with open(os.path.join(WORK, "counties.json")) as f:
        guid2name = json.load(f)
    dir2name = {name.upper().replace(" ", "_"): name
                for name in guid2name.values()}
    counties = []
    spages = os.path.join(RAW, "search_pages")
    for cdir in sorted(os.listdir(spages)):
        cname = dir2name.get(cdir, cdir)
        if not use_all and not done_search.get(cname, {}).get(
                "complete"):
            continue
        counties.append((cdir, cname))

    for cdir, cname in counties:
        stubs = load_food_stubs(cdir)
        todo = [s for s in stubs.values()
                if not os.path.exists(
                    os.path.join(RAW, "insp", cdir,
                                 s["inspectionID"] + ".html"))]
        if not todo:
            print(f"[skip] {cname}: all {len(stubs)} details cached",
                  flush=True)
            continue
        counts = {"ok": 0, "cached": 0, "fail": 0, "mismatch": 0}
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(fetch_one, cdir, s): s for s in todo}
            for fut in concurrent.futures.as_completed(futs):
                _, res = fut.result()
                counts[res] = counts.get(res, 0) + 1
        rec = {"stubs": len(stubs), "fetched_now": len(todo),
               **counts, "ts": utcnow(),
               "seconds": round(time.time() - t0, 1)}
        with _done_lock:
            done[cname] = rec
            with open(DONE_PATH, "w") as f:
                json.dump(done, f, indent=1)
        print(f"[done] {cname}: {len(stubs)} food inspections, "
              f"{counts}, {rec['seconds']}s", flush=True)
    print("DETAIL FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
