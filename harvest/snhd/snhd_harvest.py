#!/usr/bin/env python3
"""Southern Nevada Health District (SNHD) harvest: fetch -> normalize -> validate.

SNHD publishes a best-in-class nightly developer dump: restaurants.zip
(~9 MB) of semicolon-CSV extracts mirroring their MySQL schema
(restaurants.sql.txt documents the tables). Covers Clark County
(Las Vegas, Henderson, North Las Vegas, Boulder City, Mesquite, …).

Model: demerit points = PENALTY (lower is better), letter grade A/B/C/X
and result text ("A Grade", "B Downgrade", "Closed with Fees", …) ship
verbatim in disp — same shape the NYC/KingCo Socrata adapters emit.

Source-data traps verified 2026-11-16 (handle by VALUE, never by header):
  * the "latitude" column actually holds LONGITUDE (-115.x) for every
    populated row — resolve each coordinate pair by numeric range.
  * record_status '01' = the source's active-permit set (~19.7k rows,
    nearly all 2026-graded); '02'/'04'/'05'/'Y'/blank are inactive or
    legacy rows — excluded, counted in exclusions.json.
  * restaurant_inspections_stanford.csv is the legacy-archive system
    (serials DA…, dates from 2005); included as deeper history, dedup'd
    on serial_number. Orphan inspection rows are excluded, never
    attached to the wrong place.

Usage:  python snhd_harvest.py
Output: out/snhd/{places.json, fetch_log.json, validate_report.json,
        exclusions.json, manifest.json}
Then:   python ../../tools/packs/build_pack_snhd.py snhd
"""
import csv
import datetime
import hashlib
import io
import json
import os
import urllib.request
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "out", "snhd")
ZIP_URL = ("https://www.southernnevadahealthdistrict.org"
           "/restaurants/download/restaurants.zip")
SEARCH_URL = ("https://www.southernnevadahealthdistrict.org"
              "/permits-and-regulations/restaurant-inspections/"
              "restaurant-inspection-search/")
UA = "KyronHarvest/1.0 (public data; github.com/markbentzjr/kyron)"
NO_SCORE = -1

# Nevada bounds sanity: lat 35..42, lng -120..-110.
def resolve_coords(lat_txt, lng_txt):
    """The dump's 'latitude' column holds the longitude value on every
    populated row (verified 2026-11-16: 36,054 rows, zero exceptions).
    Resolve by VALUE: the -120..-110 member is lng, the 35..42 member
    is lat. Anything else (blank, 0, out-of-state) ships ungeocoded."""
    try:
        a, b = float(lat_txt), float(lng_txt)
    except (TypeError, ValueError):
        return None, None
    if a == 0 or b == 0:
        return None, None
    if -120 <= a <= -110 and 35 <= b <= 42:
        return round(b, 6), round(a, 6)   # a was really lng, b was lat
    if 35 <= a <= 42 and -120 <= b <= -110:
        return round(a, 6), round(b, 6)   # columns already sane
    return None, None


def csv_rows(z, name):
    f = io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace")
    return list(csv.reader(f, delimiter=";"))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _iso(dt):
    return (dt or "")[:10]


def _title_city(c):
    return c.title() if c.isupper() else c


def normalize(z, log):
    excl = Counter()

    # --- lookups -----------------------------------------------------------
    itypes = {r[0]: r[1] for r in csv_rows(z, "restaurant_inspection_types.csv")[1:]
              if len(r) > 1}
    viol_ref = {}
    for r in csv_rows(z, "restaurant_violations.csv")[1:]:
        if len(r) < 5:
            continue
        viol_ref[r[0]] = {"code": r[1],
                          "demerits": _int(r[3]) or 0,
                          "desc": (r[4] or "").strip()}
    # The legacy (stanford) archive cites a DIFFERENT code space — small
    # integer ids resolved by query_insp_violations.csv (id;name;value;
    # isActive), never by restaurant_violations.csv. Tried in that order.
    viol_legacy = {r[0]: {"demerits": _int(r[2]) or 0, "desc": (r[1] or "").strip()}
                   for r in csv_rows(z, "query_insp_violations.csv")[1:]
                   if len(r) > 2}

    # --- establishments ----------------------------------------------------
    est = csv_rows(z, "restaurant_establishments.csv")
    eh = est[0]
    i = {k: eh.index(k) for k in
         ("permit_number", "restaurant_name", "location_name", "address",
          "latitude", "longitude", "city_name", "zip_code", "record_status")}
    places = {}
    for r in est[1:]:
        if len(r) <= max(i.values()):
            continue
        status = r[i["record_status"]].strip()
        if status != "01":
            excl[f"record_status:{status or 'blank'}"] += 1
            continue
        name = r[i["restaurant_name"]].strip() or r[i["location_name"]].strip()
        if not name:
            excl["no_name"] += 1
            continue
        lat, lng = resolve_coords(r[i["latitude"]], r[i["longitude"]])
        permit = r[i["permit_number"]].strip()
        pid = "snhd_" + hashlib.sha1(permit.encode()).hexdigest()[:10]
        has = lat is not None
        places[permit] = {
            "id": pid, "n": name, "a": r[i["address"]].strip(),
            "c": _title_city(r[i["city_name"]].strip()),
            "z": r[i["zip_code"]].strip()[:5],
            "ct": "Clark", "st": "NV", "jur": "NV-SNHD", "src": "nv-snhd",
            "du": SEARCH_URL,
            "lat": lat, "lng": lng,
            "gs": "ACCEPTED" if has else "UNRESOLVED",
            "ga": "ADDRESS_RANGE" if has else "NONE",
            "gp": "nv-snhd-published-latlng" if has else "", "gm": "",
            "s": NO_SCORE, "d": "", "disp": "",
            "origin": "snhd-restaurants-zip", "_insp": {},
        }

    # --- inspections (current system + legacy stanford archive) ------------
    def add_inspections(rows, tag):
        ih = rows[0]
        j = {k: ih.index(k) for k in
             ("serial_number", "permit_number", "inspection_date",
              "inspection_type_id", "inspection_demerits", "inspection_grade",
              "inspection_result", "violations")}
        for r in rows[1:]:
            if len(r) <= max(j.values()):
                continue
            permit = r[j["permit_number"]].strip()
            p = places.get(permit)
            if p is None:
                excl[f"orphan_inspection:{tag}"] += 1
                continue
            serial = r[j["serial_number"]].strip()
            d = _iso(r[j["inspection_date"]])
            if not d:
                excl[f"insp_no_date:{tag}"] += 1
                continue
            viols = []
            for vid in (r[j["violations"]] or "").split(","):
                vid = vid.strip()
                if not vid:
                    continue
                ref = viol_ref.get(vid) or viol_legacy.get(vid)
                if ref is None:
                    excl["violation_id_unknown"] += 1
                    continue
                viols.append({"p": ref["demerits"], "c": False,
                              "r": ref["desc"]})
            demerits = _int(r[j["inspection_demerits"]])
            if demerits is not None and demerits > 200:
                # Implausible on SNHD's own scale (closures land ~44+;
                # verified max legit ~60). The one observed case (serial
                # 1173098, "A Grade" with demerits=1630) is internally
                # inconsistent — ship the grade text, withhold the number.
                excl["demerits_implausible"] += 1
                demerits = None
            grade = (r[j["inspection_grade"]] or "").strip()
            result = (r[j["inspection_result"]] or "").strip()
            disp = result or (f"{grade} Grade" if grade else "")
            p["_insp"][f"{tag}:{serial}"] = {
                "d": d, "t": itypes.get(r[j["inspection_type_id"]],
                                        r[j["inspection_type_id"]]),
                "s": demerits if demerits is not None else NO_SCORE,
                "disp": disp, "v": viols,
            }

    add_inspections(csv_rows(z, "restaurant_inspections.csv"), "cur")
    add_inspections(csv_rows(z, "restaurant_inspections_stanford.csv"), "arc")

    # --- finish ------------------------------------------------------------
    out = []
    for p in places.values():
        insp = sorted(p.pop("_insp").values(), key=lambda x: x["d"],
                      reverse=True)
        # newest first; within a day keep deterministic order by type
        p["insp"] = insp
        if insp:
            p["d"], p["s"], p["disp"] = insp[0]["d"], insp[0]["s"], insp[0]["disp"]
        out.append(p)
    out.sort(key=lambda p: p["id"])
    log["violations_codebook"] = len(viol_ref)
    return out, excl


def validate(places):
    errs = []
    ids = set()
    for p in places:
        if p["id"] in ids:
            errs.append(f"duplicate id {p['id']}")
        ids.add(p["id"])
        if not p["n"]:
            errs.append(f"{p['id']}: empty name")
        if (p["lat"] is None) != (p["gs"] != "ACCEPTED"):
            errs.append(f"{p['id']}: geo/provenance mismatch")
        for i in p["insp"]:
            if i["s"] != -1 and not (0 <= i["s"] <= 300):
                errs.append(f"{p['id']}: demerits out of range {i['s']}")
            if not i["d"]:
                errs.append(f"{p['id']}: inspection without date")
    return {"places": len(places),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": sum(len(i["v"]) for p in places for i in p["insp"]),
            "with_coords": sum(p["lat"] is not None for p in places),
            "errors": errs[:50], "error_count": len(errs)}


def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    t0 = datetime.datetime.now(datetime.timezone.utc)

    zpath = os.path.join(RAW, "restaurants.zip")
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": UA})
    body = urllib.request.urlopen(req, timeout=300).read()
    with open(zpath, "wb") as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    print(f"zip {len(body):,} bytes sha256={sha[:16]}")

    z = zipfile.ZipFile(io.BytesIO(body))
    log = {"url": ZIP_URL, "fetched_utc": t0.isoformat(), "bytes": len(body),
           "sha256": sha, "members": {n: z.getinfo(n).file_size
                                      for n in z.namelist()}}
    places, excl = normalize(z, log)
    rep = validate(places)
    rep["exclusions"] = dict(excl)
    for name, obj in (
            ("places.json", places),
            ("fetch_log.json", log),
            ("validate_report.json", rep),
            ("exclusions.json", dict(excl)),
            ("manifest.json",
             {"generated_at": t0.isoformat(), "source": "snhd",
              "dataset": "restaurants.zip",
              "dataset_version": t0.date().isoformat() + ".1"})):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    print(json.dumps({k: v for k, v in rep.items() if k != "errors"}))
    return 1 if rep["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
