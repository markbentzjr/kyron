#!/usr/bin/env python3
"""Kyron SC adapter — normalizer + QA pass A (prototype v0.1).

Union of the three public SC Food Grades sources by AuditResultGlobalID:
  - AGOL Steton table (inspections: permit, grade, type, date, zip)
  - rate.aspx leaves  (inspections: name, street, city, grade, date, type)
  - AGOL layer 0      (establishments: fuller name/address for 24,294
                       of the Steton permits; a lagged ~2016-2026 snapshot)

Native model: SC publishes a 100-point score and a letter grade for each
inspection. The numeric score exists ONLY inside the per-inspection PDF
reports (the GIS table's SCORE column is null on all 137,087 rows, and
pubdoc.dhec.sc.gov is unreachable over HTTPS from the build sandbox —
see report). Inspections therefore ship `s: null` with the published
POSTED_GRADE verbatim in `grade`; the score is never derived from the
grade. Violations likewise exist only in the PDFs -> `v: []`, `du`
points at the official PDF.

Places are keyed by PERMIT_ID where the GIS spine knows it. Rate-only
inspections (pre-dating the GIS window) attach to a permit only on an
exact, unique (name, street, city) match inside the same county;
otherwise they form rate-only places with fid = null (never guessed).
"""
import collections
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sc_parse import load_gis, load_rate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "OUTPUT")

COUNTY_NAME = {  # from the Advanced Search county vocabulary (01..46)
    "01": "Abbeville", "02": "Aiken", "03": "Allendale", "04": "Anderson",
    "05": "Bamberg", "06": "Barnwell", "07": "Beaufort", "08": "Berkeley",
    "09": "Calhoun", "10": "Charleston", "11": "Cherokee", "12": "Chester",
    "13": "Chesterfield", "14": "Clarendon", "15": "Colleton",
    "16": "Darlington", "17": "Dillon", "18": "Dorchester",
    "19": "Edgefield", "20": "Fairfield", "21": "Florence",
    "22": "Georgetown", "23": "Greenville", "24": "Greenwood",
    "25": "Hampton", "26": "Horry", "27": "Jasper", "28": "Kershaw",
    "29": "Lancaster", "30": "Laurens", "31": "Lee", "32": "Lexington",
    "33": "McCormick", "34": "Marion", "35": "Marlboro", "36": "Newberry",
    "37": "Oconee", "38": "Orangeburg", "39": "Pickens", "40": "Richland",
    "41": "Saluda", "42": "Spartanburg", "43": "Sumter", "44": "Union",
    "45": "Williamsburg", "46": "York",
}
PTYPE = {
    "206": "Retail Food Establishments", "211": "Grocery Stores",
    "204": "Mobile Food Units", "208": "Institutions",
}
PDF_URL = "https://pubdoc.dhec.sc.gov/Inspection/{}.pdf"


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def norm_key(name, street, city):
    return (clean(name).upper(), clean(street).upper(), clean(city).upper())


def epoch_date(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def main():
    qa = {"adapter": "scda prototype v0.1"}
    layer0 = load_gis("gis_layer0")
    steton = load_gis("gis_steton")
    rate = load_rate()
    qa["gis_layer0_rows"] = len(layer0)
    qa["gis_steton_rows"] = len(steton)
    qa["rate_rows"] = len(rate)

    # ---------------- layer 0 establishments by permit ----------------
    l0 = {}
    for f in layer0:
        a = f["attributes"]
        pid = clean(a.get("PERMIT_ID"))
        if pid:
            l0[pid] = a
    qa["layer0_permits"] = len(l0)

    # ---------------- inspections: union by GUID ----------------------
    insp = {}   # guid -> merged record
    for f in steton:
        a = f["attributes"]
        g = (a.get("AuditResultGlobalID") or "").lower()
        if not g:
            qa.setdefault("steton_guid_missing", 0)
            qa["steton_guid_missing"] += 1
            continue
        insp[g] = {
            "guid": g, "permit": clean(a.get("PERMIT_ID")),
            "oid": a.get("OBJECTID"),
            "prog": clean(a.get("PROG_CODE")),
            "county_code": clean(a.get("COUNTY")),
            "st_name": clean(a.get("FACILITY")),
            "st_street": clean(a.get("ADDRESS")),
            "st_city": clean(a.get("CITY")),
            "st_state": clean(a.get("STATE")),
            "st_zip": clean(a.get("ZIPCODE")),
            "grade_gis": clean(a.get("POSTED_GRADE")),
            "t_gis": clean(a.get("AuditTypeName")),
            "tcode": clean(a.get("AC_CODE")),
            "date_gis": epoch_date(a.get("INSP_DATE")),
            "active_raw": a.get("Active"),
            "score_gis": a.get("SCORE"),
        }
    qa["steton_score_nonnull"] = sum(
        1 for r in insp.values() if r["score_gis"] is not None)

    skeleton = {
        "permit": None, "oid": None, "prog": None, "county_code": None,
        "st_name": "",
        "st_street": "", "st_city": "", "st_state": "", "st_zip": "",
        "grade_gis": "", "t_gis": "", "tcode": "", "date_gis": None,
        "active_raw": None, "score_gis": None,
    }
    rate_dupes = 0
    for r in rate:
        g = r["guid"]
        if g in insp and "rate" in insp[g]:
            rate_dupes += 1
            continue
        rec = insp.setdefault(g, {"guid": g, **skeleton})
        rec["rate"] = r
    qa["rate_rows_duplicate_guid"] = rate_dupes
    qa["inspections_union"] = len(insp)
    qa["inspections_both"] = sum(
        1 for r in insp.values() if "rate" in r and r["permit"])
    qa["inspections_gis_only"] = sum(
        1 for r in insp.values() if "rate" not in r)
    qa["inspections_rate_only"] = sum(
        1 for r in insp.values() if "rate" in r and not r["permit"])

    # ---------------- permit identity index for rate-only rows --------
    # (name, street, city) -> permits, within the same county, from rows
    # that DO have a permit (Steton FACILITY is 30-char-capped, so index
    # both the Steton spelling and the layer-0 spelling, plus rate
    # spellings of joined rows).
    idx = collections.defaultdict(set)
    for g, r in insp.items():
        if not r["permit"]:
            continue
        # County key = the row's operating county (Steton COUNTY). The
        # permit prefix is NOT the county: prefix 50 is the statewide
        # mobile-food-unit series (4,842 rows) whose COUNTY field holds
        # the real operating county.
        cc = r["county_code"] or (
            r["rate"]["county_code"] if "rate" in r else None)
        if not cc:
            continue
        keys = set()
        if "rate" in r:
            keys.add(norm_key(r["rate"]["name"], r["rate"]["street"],
                              r["rate"]["city"]))
        if r["st_name"]:
            keys.add(norm_key(r["st_name"], r["st_street"], r["st_city"]))
        la = l0.get(r["permit"])
        if la:
            keys.add(norm_key(la.get("FACILITY"), la.get("ADDRESS"),
                              la.get("CITY")))
        for k in keys:
            idx[(cc,) + k].add(r["permit"])

    attached = ambiguous = 0
    for g, r in insp.items():
        if r["permit"] or "rate" not in r:
            continue
        cc = r["rate"]["county_code"]
        k = (cc,) + norm_key(r["rate"]["name"], r["rate"]["street"],
                             r["rate"]["city"])
        cands = idx.get(k, set())
        if len(cands) == 1:
            r["permit"] = next(iter(cands))
            r["attached_via"] = "rate_key_match"
            attached += 1
        else:
            if len(cands) > 1:
                ambiguous += 1
            r["permit"] = None
    qa["rate_only_attached_to_permit"] = attached
    qa["rate_only_ambiguous_key"] = ambiguous

    # ---------------- group into places -------------------------------
    places = {}   # place key -> mutable place record
    for g, r in insp.items():
        if r["permit"]:
            pk = r["permit"]
        else:
            rr = r["rate"]
            raw = "|".join([rr["county_code"]] + list(norm_key(
                rr["name"], rr["street"], rr["city"])))
            pk = "RATE-" + hashlib.sha1(raw.encode()).hexdigest()[:12]
        p = places.setdefault(pk, {"key": pk, "rows": []})
        p["rows"].append(r)

    GRADED = {"A", "B", "C", "S"}

    def row_date(r):
        return (r["rate"]["date"] if "rate" in r else None) or r["date_gis"]

    def row_grade(r):
        return r["grade_gis"] or (r["rate"]["grade"] if "rate" in r
                                  else None)

    def row_order(r):
        # Documented "newest inspection" ordering: date desc; on a date
        # tie a record with a posted grade (A/B/C/S) outranks an
        # ungraded one ('N/A'); then the GIS table's OBJECTID desc
        # (the source's own insertion order) decides.
        return (row_date(r) or "", 1 if row_grade(r) in GRADED else 0,
                r["oid"] or -1)

    out_places = []
    exclusions = []
    for pk, p in sorted(places.items()):
        rows = sorted(p["rows"], key=row_order, reverse=True)
        newest = rows[0]
        permit = newest["permit"]
        la = l0.get(permit) if permit else None

        def newest_rate(field):
            for r in rows:
                if "rate" in r and r["rate"][field]:
                    return r["rate"][field]
            return None

        def newest_st(field):
            for r in rows:
                if r[field]:
                    return r[field]
            return None

        def longest_st(field):
            vals = [r[field] for r in rows if r[field]]
            return max(vals, key=len) if vals else None

        name = (clean(la.get("FACILITY")) if la and clean(la.get("FACILITY"))
                else newest_rate("name") or longest_st("st_name"))
        street = (clean(la.get("ADDRESS")) if la and clean(la.get("ADDRESS"))
                  else newest_rate("street") or longest_st("st_street"))
        city = (clean(la.get("CITY")) if la and clean(la.get("CITY"))
                else newest_rate("city") or newest_st("st_city"))
        zipc = (clean(la.get("ZIPCODE")) if la and clean(la.get("ZIPCODE"))
                else newest_st("st_zip"))
        # County = operating county of the newest inspection (Steton
        # COUNTY, falling back to the rate.aspx query county). NOT the
        # permit prefix: prefix 50 is the statewide mobile-unit series.
        cc = None
        for r in rows:
            cc = r["county_code"] or (
                r["rate"]["county_code"] if "rate" in r else None)
            if cc:
                break
        prog = newest_st("prog") or (permit.split("-")[1] if permit else None)

        insps = []
        for r in rows:
            d = (r["rate"]["date"] if "rate" in r else None) or r["date_gis"]
            grade = r["grade_gis"] or (
                r["rate"]["grade"] if "rate" in r else None)
            t = r["t_gis"] or (r["rate"]["type"] if "rate" in r else None)
            insps.append({
                "id": f"scda_insp_{r['guid']}",
                "vid": r["guid"],
                "d": d,
                "t": t,
                "tcode": r.get("tcode") or None,
                "s": None,
                "grade": grade,
                "inspector": None,
                "comments": None,
                "v": [],
                "du": PDF_URL.format(r["guid"]),
                "origin": ("gis+rate" if "rate" in r and r.get("date_gis")
                           else "gis" if r.get("date_gis") else "rate"),
            })
        insps.sort(key=lambda x: x["d"] or "", reverse=True)
        top = insps[0]
        place = {
            "id": f"scda_{permit}" if permit else f"scda_{pk.lower()}",
            "fid": permit,
            "permit": permit,
            "n": name,
            "a": street,
            "c": city,
            "z": zipc,
            "addr_state": newest_st("st_state") or "SC",
            "ct": COUNTY_NAME.get(cc),
            "ct_raw": COUNTY_NAME.get(cc, "").upper(),
            "county_code": cc,
            "search_county": COUNTY_NAME.get(cc, "").upper(),
            "st": "SC",
            "jur": "SCDA",
            "src": "SCDA",
            "phone": None,
            "eh_phone": None,
            "ptype": PTYPE.get(prog) if prog else None,
            "prog_code": prog,
            "lat": None,
            "lng": None,
            "s": None,
            "grade": top["grade"],
            "d": top["d"],
            "du": top["du"],
            "origin": "gis" if permit else "rate",
            "insp": insps,
        }
        # Workstream B gate discipline at the normalizer: a result-bearing
        # place (it has graded inspections) must ship with a real name and
        # a street address, else it is excluded with provenance.
        reason = None
        if not place["n"]:
            reason = "blank name in all sources (G1-class)"
        elif not place["a"]:
            reason = "blank street in all sources (G2-class)"
        if reason:
            exclusions.append({
                "place_key": pk, "permit": permit, "reason": reason,
                "inspections_withheld": len(insps),
                "newest": {"name": name, "street": street, "city": city,
                           "date": top["d"], "grade": top["grade"]},
            })
            continue
        out_places.append(place)

    out_places.sort(key=lambda p: p["id"])
    qa["places_newest_date_ties"] = sum(
        1 for p in out_places
        if sum(1 for i in p["insp"] if i["d"] == p["d"]) > 1)
    county_sets = collections.defaultdict(set)
    for r in insp.values():
        if r["permit"] and r["county_code"]:
            county_sets[r["permit"]].add(r["county_code"])
    qa["permits_multi_county"] = sum(
        1 for v in county_sets.values() if len(v) > 1)
    qa["places"] = len(out_places)
    qa["places_with_permit"] = sum(1 for p in out_places if p["fid"])
    qa["places_rate_only"] = sum(1 for p in out_places if not p["fid"])
    qa["inspections"] = sum(len(p["insp"]) for p in out_places)
    qa["excluded_places"] = len(exclusions)
    qa["excluded_inspections"] = sum(
        e["inspections_withheld"] for e in exclusions)
    qa["counties_with_places"] = len({p["ct"] for p in out_places})
    dates = [i["d"] for p in out_places for i in p["insp"] if i["d"]]
    qa["inspection_date_min"] = min(dates)
    qa["inspection_date_max"] = max(dates)
    qa["grade_census"] = dict(collections.Counter(
        i["grade"] for p in out_places for i in p["insp"]))
    qa["places_grade_census"] = dict(collections.Counter(
        p["grade"] for p in out_places))
    qa["scores_nonnull"] = sum(
        1 for p in out_places for i in p["insp"] if i["s"] is not None)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "places_sc.json"), "w") as fh:
        json.dump(out_places, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "exclusions.json"), "w") as fh:
        json.dump(exclusions, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "qa_report.json"), "w") as fh:
        json.dump(qa, fh, ensure_ascii=False, indent=1)
    manifest = {
        "region": "us-sc",
        "state": "SC",
        "jurisdiction": "SCDA",
        "source": ("South Carolina Food Grades — SC Dept. of Agriculture "
                   "(program transferred from SC DHEC 2024-07-01): AGOL "
                   "Restaurants FeatureServer (layer 0 + Restaurants_Steton "
                   "table) and Advanced Search rate.aspx, "
                   "apps.dhec.sc.gov/Environment/FoodGrades/"),
        "source_files": [
            "raw/gis_layer0/page_*.json", "raw/gis_steton/page_*.json",
            "raw/rate/<county-code>/<start>_<end>.html",
        ],
        "score_model": ("GRADE (native SCDA posted letter grade A/B/C/S "
                        "verbatim) + SCORE_100 published per inspection "
                        "only inside the official PDF report; the GIS "
                        "SCORE column is null on every row, so inspection "
                        "s is null — never derived from the grade"),
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "adapter": "scda prototype v0.1",
        "coverage_exclusions": (
            "All four Regulation 61-25 facility types are in scope "
            "(206 Retail Food Establishments, 211 Grocery Stores, 204 "
            "Mobile Food Units, 208 Institutions). One layer-0 permit "
            "with no inspections in either inspection source is not a "
            "place. PDF-only content (numeric scores, violations) is "
            "referenced via du, not harvested: pubdoc.dhec.sc.gov "
            "refuses HTTPS connections from the build sandbox."),
        "totals": {
            "places": qa["places"],
            "places_with_inspections": qa["places"],
            "inspections": qa["inspections"],
            "violations": 0,
            "inspection_date_min": qa["inspection_date_min"],
            "inspection_date_max": qa["inspection_date_max"],
            "counties_with_places": qa["counties_with_places"],
        },
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(json.dumps(qa, indent=1))


if __name__ == "__main__":
    main()
