#!/usr/bin/env python3
"""Tennessee detail mop-up — Kyron TN adapter prototype v0.1.

Sequentially re-fetches every inspection detail that (a) failed to
download in tn_fetch_details.py (work/failures.jsonl, kind=detail), or
(b) failed stub verification (work/detail_mismatch.jsonl). Sequential
on purpose: the GA portal crossed payloads under parallel load, so
repairs are fetched one at a time with a fresh session each, then
re-verified against the stub. Survivors that still disagree are left
in work/detail_mismatch.jsonl (rewritten) for the report — the build
excludes them; nothing is hand-waved through.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tn_fetch_details as fd  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")


def wanted_ids():
    ids = {}
    fp = os.path.join(WORK, "failures.jsonl")
    if os.path.exists(fp):
        with open(fp) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if rec.get("kind") == "detail":
                    county, iid = rec["key"].split("/", 1)
                    ids[iid] = county
    mp = os.path.join(WORK, "detail_mismatch.jsonl")
    if os.path.exists(mp):
        with open(mp) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                ids[rec["inspectionID"]] = rec["county"]
    return ids


def main():
    ids = wanted_ids()
    print(f"mop-up targets: {len(ids)}", flush=True)
    # stub lookup across all counties
    stub_by_id = {}
    for cdir in sorted(os.listdir(os.path.join(RAW, "search_pages"))):
        for iid, stub in fd.load_food_stubs(cdir).items():
            stub_by_id.setdefault(iid, (cdir, stub))
    still_bad = []
    fixed = 0
    for iid, cdir in sorted(ids.items()):
        entry = stub_by_id.get(iid)
        if entry is None:
            still_bad.append({"inspectionID": iid, "county": cdir,
                              "problems": ["stub not found"]})
            continue
        real_cdir, stub = entry
        path = os.path.join(RAW, "insp", real_cdir, iid + ".html")
        if os.path.exists(path):
            os.remove(path)
        # reset this thread's session for a genuinely fresh fetch
        fd._tls.primed = False
        if hasattr(fd._tls, "opener"):
            del fd._tls.opener
        _, res = fd.fetch_one(real_cdir, stub)
        if res in ("ok", "cached"):
            fixed += 1
            print(f"[fixed] {iid}", flush=True)
        else:
            still_bad.append({"inspectionID": iid, "county": real_cdir,
                              "problems": [f"refetch result: {res}"]})
            print(f"[still bad] {iid}: {res}", flush=True)
        time.sleep(0.3)
    mp = os.path.join(WORK, "detail_mismatch.jsonl")
    with open(mp, "w") as f:
        for rec in still_bad:
            rec["ts"] = fd.utcnow()
            f.write(json.dumps(rec) + "\n")
    print(f"MOPUP COMPLETE fixed={fixed} still_bad={len(still_bad)}",
          flush=True)


if __name__ == "__main__":
    main()
