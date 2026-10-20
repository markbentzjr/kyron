#!/usr/bin/env python3
"""Mop-up: re-fetch inspectionsData for facilities whose saved copy is
inconsistent with their search stub's last-score/last-date columns
(possible crossed responses during parallel fetch). Sequential and
gentle. Each re-fetch is appended to fetch_log.tsv; the raw file is
replaced only when the fresh copy parses as a JSON list.
"""

import base64
import glob
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://ga.healthinspections.us/stateofgeorgia/API/index.cfm"
UA = "Mozilla/5.0 (X11; Linux x86_64) KyronResearch/0.1 (GA mop-up)"


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stub_latest(cols):
    s = (cols.get("4") or "").replace("Last Inspection Score: ", "").strip()
    d = (cols.get("5") or "").replace("Last Inspection Date: ", "").strip()
    try:
        s = int(s)
    except ValueError:
        s = None
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", d)
    return s, (f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None)


def copy_latest(entries):
    best = None
    for i in entries:
        if not i:
            continue
        dt = (i["columns"].get("0") or "").replace("Date: ", "").strip()
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", dt)
        if not m:
            continue
        iso = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        sc = (i["columns"].get("2") or "").replace("Score: ", "").strip()
        try:
            sc = int(sc)
        except ValueError:
            sc = None
        key = (iso, i.get("inspectionId") or 0)
        if best is None or key > best[0]:
            best = (key, sc)
    return (best[0][0], best[1]) if best else (None, None)


def consistent(entries, ss, sd):
    iso, sc = copy_latest(entries)
    if iso is None:
        return False
    return iso == sd and sc == ss


def main():
    bad = json.load(open(os.path.join(ROOT, "work",
                                      "insp_stub_mismatches.json")))
    # stubs (first sighting) for county + b64 id
    stubs = {}
    for cdir in sorted(glob.glob(os.path.join(ROOT, "raw",
                                              "search_pages", "*"))):
        c = os.path.basename(cdir)
        for pf in sorted(glob.glob(os.path.join(cdir, "p*.json"))):
            for s in json.load(open(pf)):
                stubs.setdefault(base64.b64decode(s["id"]).decode(),
                                  (c, s))
    fixed = still = 0
    still_list = []
    for fid, county, (ss, sd), _old in bad:
        c, stub = stubs[fid]
        url = API + "/inspectionsData/" + urllib.parse.quote(
            stub["id"], safe="")
        body = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 * (attempt + 1))
        if body is None:
            still += 1
            still_list.append((fid, "fetch failed"))
            continue
        entries = json.loads(body.decode("utf-8", "replace"))
        rel = f"insp/{c}/{fid}.json"
        path = os.path.join(ROOT, "raw", rel)
        with open(path, "wb") as f:
            f.write(body)
        with open(os.path.join(ROOT, "fetch_log.tsv"), "a") as f:
            f.write("\t".join([
                rel + " (mopup)", url, utcnow(), "200", str(len(body)),
                hashlib.sha256(body).hexdigest()]) + "\n")
        if consistent(entries, ss, sd):
            fixed += 1
        else:
            iso, sc = copy_latest(entries)
            # a fresh copy NEWER than the stub is also acceptable
            # (search-index lag); only older/different is a failure
            if iso is not None and sd is not None and iso > sd:
                fixed += 1
            else:
                still += 1
                still_list.append((fid, f"stub=({ss},{sd}) copy=({sc},{iso})"))
        time.sleep(0.35)
    print(f"mop-up: {len(bad)} suspects, fixed {fixed}, still bad {still}")
    for x in still_list:
        print("  STILL:", x)
    json.dump(still_list, open(os.path.join(
        ROOT, "work", "mopup_still_bad.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
