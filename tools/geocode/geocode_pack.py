"""Geocode a built pack's places.json via the US Census batch geocoder.

Same honesty rules as geocode_seed_oneshot.py: only real Match results
write coordinates (gs=ACCEPTED, ga=ADDRESS_RANGE, gp=CENSUS,
gm=EXACT|NON_EXACT); everything else keeps lat/lng=null. No fabricated
or centroid coordinates ever.

Chunked + resumable: each chunk's raw Census CSV lands in
<work>/geo/chunk_NNNN.csv; completed chunks are skipped on rerun.

Usage:  python geocode_pack.py <places.json> <STATE>
        python geocode_pack.py harvest/ms/out/ms/places.json MS
"""
import csv
import io
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geocode_common import normalize_address  # noqa: E402

URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CHUNK = 3000


def post_rows(rows, retries=4):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    body = (
        "--b\r\n"
        'Content-Disposition: form-data; name="addressFile"; filename="a.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n" + buf.getvalue() + "\r\n"
        "--b\r\n"
        'Content-Disposition: form-data; name="benchmark"\r\n\r\n'
        "Public_AR_Current\r\n--b--\r\n"
    ).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                "Content-Type": "multipart/form-data; boundary=b",
                "User-Agent": "kyron-geocode/1.0",
            })
            return urllib.request.urlopen(req, timeout=600).read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(15 * (attempt + 1))
            print(f"  retry {attempt + 1} after {e}", flush=True)


def parse_results(raw):
    out = {}
    for r in csv.reader(io.StringIO(raw)):
        if len(r) < 6:
            continue
        aid, status, mtype, coords = r[0].strip(), r[2].strip(), r[3].strip(), r[5].strip()
        if status == "Match" and "," in coords:
            lng, lat = (float(x) for x in coords.split(","))
            out[aid] = (lat, lng, mtype)
    return out


def main():
    seed_path, state = sys.argv[1], sys.argv[2].upper()
    work = os.path.join(os.path.dirname(seed_path), "geo")
    os.makedirs(work, exist_ok=True)
    places = json.load(open(seed_path, encoding="utf-8"))

    rows, row_set = [], set()
    skipped = 0
    for p in places:
        try:
            norm = normalize_address(p.get("a", ""), p.get("c", ""), p.get("z", ""))
        except Exception:
            norm = {"submittable": False}
        if not norm["submittable"]:
            skipped += 1
            continue
        rows.append([p["id"], norm["street_expanded"], norm["city"], state, norm["zip"]])
        row_set.add(p["id"])
    print(f"{len(rows)} submittable / {skipped} skipped of {len(places)}", flush=True)

    matched = {}
    chunks = [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)]
    for ci, chunk in enumerate(chunks):
        cpath = os.path.join(work, f"chunk_{ci:04d}.csv")
        if os.path.exists(cpath):
            print(f"chunk {ci}: cached ({len(chunk)} rows)", flush=True)
        else:
            t0 = time.time()
            raw = post_rows(chunk)
            open(cpath, "w", encoding="utf-8").write(raw)
            print(f"chunk {ci}: {len(chunk)} rows in {time.time() - t0:.0f}s", flush=True)
        matched.update(parse_results(open(cpath, encoding="utf-8", errors="replace").read()))

    accepted = 0
    for p in places:
        m = matched.get(p["id"])
        if m:
            p["lat"], p["lng"] = m[0], m[1]
            p["gs"], p["ga"], p["gp"] = "ACCEPTED", "ADDRESS_RANGE", "CENSUS"
            p["gm"] = m[2].upper()
            accepted += 1
        else:
            p["lat"], p["lng"] = None, None
            p["gs"], p["ga"], p["gp"], p["gm"] = "UNRESOLVED", "NONE", "", ""

    json.dump(places, open(seed_path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"accepted {accepted}/{len(places)} -> {seed_path}", flush=True)


if __name__ == "__main__":
    main()
