"""One-shot geocode of the bundled Alabama seed via the US Census batch
geocoder (free, no key — same endpoint census_batch.py uses).

The full 4-stage pipeline predates the src/ -> app/src move; this script
targets the live asset directly and applies the same honesty rules:

- Places whose address returns Match get real lat/lng plus provenance:
  gs=ACCEPTED, ga=ADDRESS_RANGE, gp=CENSUS, gm=EXACT|NON_EXACT.
- No_Match / Tie / unsubmittable addresses keep lat/lng = null.
  No centroid or guessed coordinate is ever written.

Usage:  python geocode_seed_oneshot.py
Outputs: rewrites app/src/main/assets/places_seed_geocoded.json in place,
         and keeps the raw Census CSV at out/seed_results.csv.
"""
import csv
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geocode_common import normalize_address  # noqa: E402

SEED = os.path.join(HERE, "..", "..", "app", "src", "main", "assets", "places_seed_geocoded.json")
OUT = os.path.join(HERE, "out")
URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def main():
    os.makedirs(OUT, exist_ok=True)
    places = json.load(open(SEED, encoding="utf-8"))

    rows, meta = [], {}
    for p in places:
        norm = normalize_address(p.get("a", ""), p.get("c", ""), p.get("z", ""))
        if not norm["submittable"]:
            meta[p["id"]] = ("skipped:" + ",".join(norm["flags"]), None)
            continue
        aid = p["id"]
        rows.append([aid, norm["street_expanded"], norm["city"], "AL", norm["zip"]])
        meta[aid] = ("submitted", norm)
    print(f"{len(rows)} submittable of {len(places)} places")

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
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "multipart/form-data; boundary=b",
        "User-Agent": "kyron-geocode/1.0",
    })
    raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
    open(os.path.join(OUT, "seed_results.csv"), "w", encoding="utf-8").write(raw)

    matched = {}
    for r in csv.reader(io.StringIO(raw)):
        if len(r) < 6:
            continue
        aid, status, mtype, coords = r[0].strip(), r[2].strip(), r[3].strip(), r[5].strip()
        if status == "Match" and "," in coords:
            lng, lat = (float(x) for x in coords.split(","))
            matched[aid] = (lat, lng, mtype)

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

    json.dump(places, open(SEED, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"accepted {accepted}/{len(places)} -> {SEED}")
    misses = [p["n"] for p in places if p["lat"] is None]
    if misses:
        print("unresolved:", "; ".join(misses))


if __name__ == "__main__":
    main()
