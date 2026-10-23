#!/usr/bin/env python3
"""Delaware DPH normalizer — Socrata 384s-wygj violation rows -> the
canonical Kyron places model the pack builder consumes (FL/GA/TN/SC
shape: compact-key place dicts with nested `insp`).

Input : out/raw_de_rows.jsonl (fetch_de.py, one raw row per line)
Output: out/places.json  (builder input, GA/TN key conventions)
        out/qa_report.json (build-side accounting)
        (manifest.json is written by the pack builder, not here)

Source facts, verified live 2026-10-22 (33,519 rows):
  * one row per VIOLATION; rows with a null `violation` are
    inspections with NO listed violation (948 of them) and still yield
    an inspection record with an empty violation list;
  * NO numeric score exists in this dataset — every score is the
    NO_SCORE sentinel (-1) and every native result stays "" (the
    DE-DPH result model is VIOLATIONS_ONLY, not even a disposition);
  * violations carry only a code (`violation`) and a short description
    (`vio_desc`) — no points, no critical flag, no narrative: p=0,
    c=false, remarks = "CODE violation, DESC" (FL's "code text"
    remarks shape);
  * geocoding is provided by the SOURCE itself (geocoded_column):
    coordinates ship only where the source geocoded them. Nothing is
    geocoded, estimated or invented here — null geocodes (511 rows)
    become places without coordinates;
  * establishments with ZERO violations ever are ABSENT from the
    source dataset by construction (violations-only extract). That is
    a real coverage limitation, reported, not repaired: a DE place in
    this pack is a place with >= 1 listed violation OR >= 1 recorded
    no-violation inspection INSIDE the window.

Place identity (id style mirrors the gadph_/tndh_ packs):
  id = "de-dph_" + first 10 hex of sha256(norm name + "|" + norm street
       + "|" + zip), norm = casefold, collapse whitespace; city is NOT
       hashed (street + zip pins the address).

Inspections group within a place by (insp_date, insp_type) — the
dataset has no inspection id column, so this pair is the only key.
Two same-day same-type visits would merge into one record; the QA
report counts exactly how many times that occurred (it never hid
data: all their violation rows ship, merged in source row order).

ALL rows are consumed; nothing is silently dropped. Rows with a blank
establishment name or blank street are EXCLUDED (a place with no name
or no address must not ship — same gate principle as GA/TN's G1/G2
classes) and every exclusion is counted in the QA report.
"""

import hashlib
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
RAW = os.path.join(OUT, "raw_de_rows.jsonl")
SOURCE_ID = "de-dph"
SOURCE_NAME = "Delaware Division of Public Health (Open Data portal)"
DETAIL_URL = "https://data.delaware.gov/d/384s-wygj"
JURISDICTION = "DE-DPH"
STATE = "DE"
REGION = "us-de"
NO_SCORE = -1


def norm_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def norm_key(s):
    return norm_text(s).casefold()


def place_id(name, street, zipc):
    digest = hashlib.sha256(
        f"{norm_key(name)}|{norm_key(street)}|{norm_key(zipc)}"
        .encode("utf-8")).hexdigest()
    return f"{SOURCE_ID}_{digest[:10]}"


def parse_iso(ts):
    """'2025-11-04T00:00:00.000' -> ('2025-11-04', '11/4/2025') or
    (None, None) — unparseable dates are counted, never invented."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:T|$)", (ts or "").strip())
    if not m:
        return None, None
    iso = m.group(1) + "-" + m.group(2) + "-" + m.group(3)
    return iso, f"{int(m.group(2))}/{int(m.group(3))}/{m.group(1)}"


def parse_geocode(col):
    """geocoded_column -> (lat, lng) floats or (None, None).
    The source column carries strings; a non-parsable or null geocode
    yields (None, None). NEVER invents coordinates."""
    if not isinstance(col, dict):
        return None, None
    try:
        lat, lng = float(col["latitude"]), float(col["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None
    if lat == 0.0 and lng == 0.0:      # null island is not a location
        return None, None
    return lat, lng


def violation_remark(code, desc):
    """"CODE violation, DESC" — the FL-pack 'code prefix + own text'
    remarks shape (the app's Violation.ruleText strips the code
    prefix). With no code or no desc, ships the part that exists."""
    code, desc = norm_text(code), norm_text(desc)
    if code and desc:
        return f"{code} violation, {desc}"
    if code:
        return f"{code} violation"
    return desc


def main() -> int:
    qa = {
        "rows_in": 0,
        "rows_bad_date": 0,
        "rows_excluded_blank_name": 0,
        "rows_excluded_blank_street": 0,
        "rows_null_violation": 0,
        "rows_violation_without_desc": 0,
        "rows_desc_without_code": 0,
        "rows_bad_geocode": 0,
        "inspections_merged_same_date_type": 0,
        "place_id_collisions": [],
        "establishments": 0,
        "places_out": 0,
        "inspections_out": 0,
        "violations_out": 0,
        "places_with_coords": 0,
        "places_without_coords": 0,
        "zip_len_census": Counter(),
        "insp_type_census": Counter(),
        "inspection_date_min": None,
        "inspection_date_max": None,
        "inspections_dated_after_2026_10_22": 0,  # source pre-schedules
    }
    EXCLUDED = []
    places = {}
    establishments = set()

    with open(RAW, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            qa["rows_in"] += 1
            rid = row.get("_socrata_rowid")          # from fetch pass 2
            name = norm_text(row.get("restname"))
            street = norm_text(row.get("restaddress"))
            zipc = norm_text(row.get("restzip"))
            city = norm_text(row.get("restcity"))
            iso, mdy = parse_iso(row.get("insp_date"))
            itype = norm_text(row.get("insp_type"))
            code = row.get("violation")
            desc = row.get("vio_desc")
            lat, lng = parse_geocode(row.get("geocoded_column"))
            if iso is None:
                qa["rows_bad_date"] += 1
                EXCLUDED.append({"rowid": rid,
                                 "reason": "unparseable insp_date",
                                 "insp_date": row.get("insp_date")})
                continue
            if not name:
                qa["rows_excluded_blank_name"] += 1
                EXCLUDED.append({"rowid": rid,
                                 "reason": "blank establishment name"})
                continue
            if not street:
                qa["rows_excluded_blank_street"] += 1
                EXCLUDED.append({"rowid": rid,
                                 "reason": "blank street address",
                                 "name": name})
                continue
            establishments.add((norm_key(name), norm_key(street),
                                norm_key(zipc)))
            if lat is None and lng is None:
                qa["rows_bad_geocode"] += 1
            qa["zip_len_census"][len(zipc)] += 1
            if not code:
                qa["rows_null_violation"] += 1
            else:
                if not norm_text(desc):
                    qa["rows_violation_without_desc"] += 1
                if not norm_text(code):
                    qa["rows_desc_without_code"] += 1
            qa["insp_type_census"][itype or "(blank)"] += 1

            pid = place_id(name, street, zipc)
            if pid in places:
                pl = places[pid]
            else:
                pl = {
                    "id": pid,
                    "n": name,
                    "a": street,
                    "c": city,
                    "z": zipc,
                    "st": STATE,
                    "jur": JURISDICTION,
                    "src": SOURCE_ID,
                    "du": DETAIL_URL,
                    "lat": None,
                    "lng": None,
                    "gs": "UNRESOLVED",   # no source geocode
                    "ga": "NONE",
                    "gp": "",
                    "gm": "",
                    "s": NO_SCORE,
                    "d": None,
                    "disp": "",
                    "origin": "socrata-384s-wygj",
                    "insp": [],
                }
                places[pid] = pl
            # coordinates: keep only source-provided, and only the
            # FIRST non-null geocode seen for the place (rows of one
            # establishment repeat the same point)
            if (pl["lat"] is None and pl["lng"] is None
                    and lat is not None and lng is not None):
                pl["lat"], pl["lng"] = lat, lng
                pl["gs"] = "ACCEPTED"           # SOURCE-provided geocode
                pl["ga"] = "ADDRESS_RANGE"      # address-level class
                # honest provenance: this is the state's own Socrata
                # geocoded_column, NOT a Census geocoder result — gp
                # names it, gm stays "" (no EXACT/NON_EXACT claim of
                # the kind the Census-geocoded packs make)
                pl["gp"] = "de-dph-socrata-geocoded_column"
                pl["gm"] = ""

            insp = pl.setdefault("_by_key", {})
            key = (iso, itype)
            if key in insp:
                insp = insp[key]
                qa["inspections_merged_same_date_type"] += 1
            else:
                # NOTE: never write `insp = insp[key] = rec` here —
                # Python's chained assignment binds the LEFTMOST target
                # first, which would rebind `insp` to the record and then
                # store the record inside itself, leaving _by_key empty.
                rec = {"d": iso, "t": itype,
                       "s": NO_SCORE, "disp": "", "v": []}
                insp[key] = rec
                insp = rec
                qa["inspections_out"] += 1
            if code:
                insp["v"].append(
                    {"p": 0, "c": False,
                     "r": violation_remark(code, desc)})
                qa["violations_out"] += 1
            qa["inspection_date_min"] = (iso if
                                         qa["inspection_date_min"] is None
                                         else min(qa["inspection_date_min"],
                                                  iso))
            qa["inspection_date_max"] = (iso if
                                         qa["inspection_date_max"] is None
                                         else max(qa["inspection_date_max"],
                                                  iso))
            if iso > "2026-10-22":
                qa["inspections_dated_after_2026_10_22"] += 1

    for pid, pl in places.items():
        by_key = pl.pop("_by_key")
        entries = [by_key[k] for k in sorted(by_key, reverse=True)]
        if pl["d"] is None:
            pl["d"] = entries[0]["d"]
        pl["insp"] = entries

    out_places = sorted(places.values(), key=lambda p: p["id"])
    qa["establishments"] = len(establishments)
    qa["places_out"] = len(out_places)
    qa["places_with_coords"] = sum(
        1 for p in out_places
        if p["lat"] is not None and p["lng"] is not None)
    qa["places_without_coords"] = (
        len(out_places) - qa["places_with_coords"])
    qa["place_id_collisions"] = qa["place_id_collisions"] or []
    qa["excluded_rows"] = len(EXCLUDED)
    qa["zip_len_census"] = dict(qa["zip_len_census"])
    qa["insp_type_census"] = dict(qa["insp_type_census"])

    with open(os.path.join(OUT, "places.json"), "w",
              encoding="utf-8") as f:
        json.dump(out_places, f, ensure_ascii=False)
    with open(os.path.join(OUT, "excluded_rows.json"), "w") as f:
        json.dump(EXCLUDED, f, indent=1)
    with open(os.path.join(OUT, "qa_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(qa, f, indent=1)

    print(json.dumps({k: qa[k] for k in (
        "rows_in", "excluded_rows", "establishments", "places_out",
        "inspections_out", "violations_out", "places_with_coords",
        "places_without_coords", "inspection_date_min",
        "inspection_date_max", "inspections_dated_after_2026_10_22",
        "inspections_merged_same_date_type", "rows_bad_geocode",
        "rows_null_violation")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
