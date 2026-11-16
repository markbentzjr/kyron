#!/usr/bin/env python3
"""Generic MyHealthDepartment detail fetcher — inspection pages.

Generalizes harvest/tn/tn_fetch_details.py across the MHD states in
states.py. For every FOOD inspection stub collected by mhd_fetch.py,
fetch the server-rendered detail page
  GET /<path>/inspection/?inspectionID=<GUID>
-> raw/<key>/insp/<inspectionID>.html, logged in fetch_log.tsv.

Deployments whose route answers the client-rendered SPA shell (VA)
are marked "unrendered" — the file is kept for evidence under
raw/<key>/unrendered/ and counted separately; those inspections ship
stub-level in mhd_build.py (never silently treated as fetched).

STUB VERIFICATION (the GA crossed-payload lesson, inherited): every
parsed detail is checked against its search stub — permitID, name,
date, and (where the stub publishes one) score must all agree.
Disagreements go to work/<key>/detail_mismatch.jsonl for re-fetch;
nothing is silently trusted.

Cookie sessions are primed per worker with a landing-page GET
(detail routes 403 cookieless agents), Chrome UA + Referer, refreshed
on failure with backoff.

Usage: python mhd_fetch_details.py va [wi co mt hi ...]
Skips states whose config detail != "server".
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
from states import STATES  # noqa: E402
from mhd_parse import parse_detail  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://inspections.myhealthdepartment.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
      "KyronResearch/0.1 (MHD generic adapter)")
DELAY = 0.15
RENDER_MARK = "establishment-page-left-name"

_log_lock = threading.Lock()
_fail_lock = threading.Lock()
_mm_lock = threading.Lock()
_http_sem = threading.Semaphore(8)
_tls = threading.local()


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_fetch(log_path, fname, url, status, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([fname, url, utcnow(), str(status),
                      str(len(body)), sha]) + "\n"
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)


def log_jsonl(path, lock, rec):
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def session():
    if not hasattr(_tls, "opener"):
        cj = http.cookiejar.CookieJar()
        _tls.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))
        _tls.primed = False
    return _tls.opener


def prime_session(cfg):
    opener = session()
    req = urllib.request.Request(
        ORIGIN + "/" + cfg["path"] + "/",
        headers={"User-Agent": UA})
    with _http_sem:
        with opener.open(req, timeout=60) as r:
            r.read()
    _tls.primed = True


def http_get_detail(cfg, inspection_id, retries=4):
    url = (ORIGIN + "/" + cfg["path"] +
           "/inspection/?inspectionID=" + inspection_id)
    last = None
    for attempt in range(retries):
        try:
            if not getattr(_tls, "primed", False):
                prime_session(cfg)
            req = urllib.request.Request(
                url, headers={"User-Agent": UA,
                              "Referer": ORIGIN + "/" + cfg["path"] + "/"})
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


def norm_date(v):
    """ISO 'YYYY-MM-DD[...]' or 'M/D/YYYY' -> 'YYYY-MM-DD' ('' if bad)."""
    v = (v or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return v[:10]
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if m:
        return "%04d-%02d-%02d" % (int(m.group(3)), int(m.group(1)),
                                 int(m.group(2)))
    return ""


def verify_stub(cfg, stub, parsed):
    """Return list of disagreement strings (empty = verified)."""
    probs = []
    if parsed["permitID"] != stub["permitID"].upper():
        probs.append(f"permitID {parsed['permitID']} != "
                     f"stub {stub['permitID']}")
    if norm_name(parsed["name"]) != norm_name(
            stub.get("establishmentName") or stub.get("name")):
        probs.append(f"name {parsed['name']!r} != stub "
                     f"{(stub.get('establishmentName') or stub.get('name'))!r}")
    if parsed["date"] != norm_date(stub.get("inspectionDate")):
        probs.append(f"date {parsed['date']} != stub "
                     f"{stub.get('inspectionDate')}")
    if cfg["score_field"]:
        if parsed["score"] != stub.get("score"):
            probs.append(f"score {parsed['score']} != stub "
                         f"{stub.get('score')}")
    if parsed["inspectionID"] and \
            parsed["inspectionID"] != stub["inspectionID"].upper():
        probs.append(f"inspectionID {parsed['inspectionID']} != "
                     f"stub {stub['inspectionID']}")
    return probs


def is_food_stub(cfg, r):
    text = " ".join(str(r.get(f) or "") for f in
                    ("programName", "permitType", "inspectionType")) \
        .casefold()
    return any(t in text for t in cfg["food_program"])


def load_food_stubs(cfg, paths):
    """All food stubs from the state's search pages."""
    stubs = {}
    cdir = os.path.join(paths, "search_pages", "STATEWIDE")
    if not os.path.isdir(cdir):
        return stubs
    for fname in sorted(os.listdir(cdir)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(cdir, fname), encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            if isinstance(r, dict) and r.get("inspectionID") and \
                    is_food_stub(cfg, r):
                stubs[r["inspectionID"]] = r
    return stubs


def fetch_one(cfg, raw_root, log_path, fail_path, mm_path, stub):
    iid = stub["inspectionID"]
    rel = f"insp/{iid}.html"
    path = os.path.join(raw_root, rel)
    if os.path.exists(path):
        return iid, "cached"
    url = (ORIGIN + "/" + cfg["path"] + "/inspection/?inspectionID=" + iid)
    try:
        status, body = http_get_detail(cfg, iid)
    except Exception as e:  # noqa: BLE001
        log_jsonl(fail_path, _fail_lock,
                  {"ts": utcnow(), "kind": "detail", "key": iid,
                   "url": url, "error": str(e)[:300]})
        return iid, "fail"
    text = body.decode("utf-8", "replace")
    if RENDER_MARK not in text:
        # SPA shell / unrendered route: keep the byte evidence under
        # unrendered/ and count separately — a shell is not a detail.
        urel = f"unrendered/{iid}.html"
        upath = os.path.join(raw_root, urel)
        os.makedirs(os.path.dirname(upath), exist_ok=True)
        with open(upath, "wb") as f:
            f.write(body)
        log_fetch(log_path, urel, url, status, body)
        return iid, "unrendered"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    log_fetch(log_path, rel, url, status, body)
    time.sleep(DELAY)
    try:
        parsed = parse_detail(text, cfg["path"])
        probs = verify_stub(cfg, stub, parsed)
    except Exception as e:  # noqa: BLE001
        probs = [f"parse error: {e}"]
    if probs:
        log_jsonl(mm_path, _mm_lock,
                  {"ts": utcnow(), "inspectionID": iid, "problems": probs})
        return iid, "mismatch"
    return iid, "ok"


def main():
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or \
        [k for k, c in STATES.items() if c["enabled"]]
    for key in keys:
        cfg = STATES.get(key)
        if cfg is None or not cfg["enabled"]:
            print(f"[skip] {key}: not enabled", flush=True)
            continue
        if cfg["detail"] != "server":
            print(f"[skip] {key}: detail='{cfg['detail']}' — "
                  f"stub-level only", flush=True)
            continue
        raw_root = os.path.join(ROOT, "raw", key)
        work = os.path.join(ROOT, "work", key)
        os.makedirs(raw_root, exist_ok=True)
        os.makedirs(work, exist_ok=True)
        log_path = os.path.join(work, "fetch_log.tsv")
        fail_path = os.path.join(work, "failures.jsonl")
        mm_path = os.path.join(work, "detail_mismatch.jsonl")
        done_path = os.path.join(work, "details_done.json")
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("file\turl\tfetched_utc\thttp_status\tbytes\tsha256\n")
        stubs = load_food_stubs(cfg, raw_root)
        todo = [s for iid, s in stubs.items()
                if not os.path.exists(os.path.join(raw_root, "insp",
                                                 iid + ".html"))]
        if not todo:
            print(f"[skip] {key}: all {len(stubs)} details cached",
                  flush=True)
            continue
        counts = {"ok": 0, "cached": 0, "fail": 0, "mismatch": 0,
                  "unrendered": 0}
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(fetch_one, cfg, raw_root, log_path,
                              fail_path, mm_path, s): s for s in todo}
            for fut in concurrent.futures.as_completed(futs):
                _, res = fut.result()
                counts[res] = counts.get(res, 0) + 1
        rec = {"stubs": len(stubs), "fetched_now": len(todo),
               **counts, "ts": utcnow(),
               "seconds": round(time.time() - t0, 1)}
        with open(done_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        print(f"[done] {key}: {len(stubs)} food inspections, "
              f"{counts}, {rec['seconds']}s", flush=True)
    print("DETAIL FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
