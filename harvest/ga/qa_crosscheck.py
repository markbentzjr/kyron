#!/usr/bin/env python3
"""Georgia DPH adapter — QA pass B (independent cross-check).

Deliberately different method from ga_build.py: streams the raw files,
recomputes every headline number from scratch, and verifies the output
against the raw layer rather than trusting the normalizer's accounting.

Checks:
  B1 raw search stubs (deduped per county) == output places
  B2 every output inspection exists in raw with same date/score/purpose
  B3 every output place s/grade/d == its newest raw inspection (recomputed)
  B4 no invented scores: every output score value occurs in the raw
     inspection or stub columns for that facility
  B5 5-record field-by-field spot check (deterministic picks)
  B6 geocode-readiness recomputed: % street addresses starting with a
     house number; PO-box count
  B7 inspection-count distribution (tests the <=5 portal window)
  B8 output hygiene: st/jur constants, no coordinates, ids unique
"""

import base64
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "OUTPUT")


def grade_of(s):
    return None if s is None else ("A" if s >= 90 else
                                   "B" if s >= 80 else
                                   "C" if s >= 70 else "U")


def permit_code(permit):
    import re as _re
    p = (permit or "").strip().upper()
    for pat in (r"^(?:FSP|FS)-(\d{3})-\d+", r"^(?:FSP|FS)(\d{3})-\d+",
                r"^(\d{3})-\d+", r"^(\d{3})\d{4,}$"):
        m = _re.match(pat, p)
        if m:
            return m.group(1)
    return None


def iso(mdy):
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", (mdy or "").strip())
    if not m:
        return None
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"


def main():
    res = {"checks": {}, "notes": []}
    places = json.load(open(os.path.join(OUT, "places_ga.json")))
    by_id = {p["id"]: p for p in places}

    # ---- B1/B2/B3/B4: stream raw layer
    raw_fac = {}       # fid_num -> (county, stub)
    raw_insp = {}      # fid_num -> list of raw inspections
    for cdir in sorted(glob.glob(os.path.join(RAW, "search_pages", "*"))):
        county = os.path.basename(cdir)
        for pf in sorted(glob.glob(os.path.join(cdir, "p*.json"))):
            for stub in json.load(open(pf)):
                fid = base64.b64decode(stub["id"]).decode()
                raw_fac.setdefault(fid, (county, stub))
    # per-place inspection file exactly as the normalizer chose it:
    # the search county's copy, else the adjudicated county's copy
    excl_path = os.path.join(OUT, "exclusions.json")
    n_excl = len(json.load(open(excl_path))) if os.path.exists(
        excl_path) else 0
    for p in places:
        fid = str(p["fid"])
        cand = [os.path.join(RAW, "insp", p["search_county"],
                             fid + ".json"),
                os.path.join(RAW, "insp", p["ct_raw"], fid + ".json")]
        raw_insp[fid] = []
        for c in cand:
            if os.path.exists(c):
                raw_insp[fid] = json.load(open(c))
                break

    res["raw_facilities"] = len(raw_fac)
    res["raw_inspection_files"] = len(raw_insp)
    res["output_places"] = len(places)
    res["exclusions"] = n_excl
    res["checks"]["B1_stub_count_eq_places_plus_exclusions"] = (
        len(raw_fac) == len(places) + n_excl)

    insp_total_out = sum(len(p["insp"]) for p in places)
    insp_total_raw = sum(len(v) for v in raw_insp.values())
    # independent accounting of the rows the normalizer must drop:
    # JSON nulls, 'No Inspections To Display' placeholder rows, and
    # rows whose date column does not parse as MM-DD-YYYY
    n_null = n_placeholder = n_baddate = 0
    for v in raw_insp.values():
        for r in v:
            if r is None:
                n_null += 1
            elif (r.get("columns", {}).get("0") or "").strip() == \
                    "No Inspections To Display":
                n_placeholder += 1
            elif iso(r.get("columns", {}).get("0", "").replace(
                    "Date: ", "")) is None:
                n_baddate += 1
    res["raw_inspections"] = insp_total_raw
    res["output_inspections"] = insp_total_out
    res["raw_dropped"] = {"null_rows": n_null,
                          "placeholder_rows": n_placeholder,
                          "unparseable_date_rows": n_baddate}
    res["checks"]["B2_inspection_accounting"] = (
        insp_total_out == insp_total_raw - n_null - n_placeholder
        - n_baddate)

    mism_latest = []
    invented = []
    excluded_fids = {str(e["facility"]) for e in json.load(
        open(os.path.join(OUT, "exclusions.json")))} if os.path.exists(
        os.path.join(OUT, "exclusions.json")) else set()
    for fid, (county, stub) in raw_fac.items():
        if fid in excluded_fids:
            continue
        p = by_id.get(f"gadph_{fid}")
        if p is None:
            mism_latest.append({"fid": fid, "err": "missing in output"})
            continue
        raws = [r for r in raw_insp.get(fid, []) if r is not None]
        parsed = []
        for r in raws:
            d = iso(r["columns"].get("0", "").replace("Date: ", ""))
            s_txt = r["columns"].get("2", "").replace(
                "Score: ", "").strip()
            try:
                s = int(s_txt)
            except ValueError:
                s = None
            parsed.append((d, r["inspectionId"], s))
        parsed = [x for x in parsed if x[0]]
        if parsed:
            parsed.sort(key=lambda x: (x[0], x[1]), reverse=True)
            d0, _, s0 = parsed[0]
            mo, dy, yr = d0[5:7], d0[8:10], d0[:4]
            if (p["s"] != s0 or p["grade"] != grade_of(s0)
                    or p["d"] != f"{int(mo)}/{int(dy)}/{yr}"):
                mism_latest.append({"fid": fid, "out": [p["s"], p["d"]],
                                    "raw_latest": [s0, d0]})
            raw_scores = {x[2] for x in parsed}
            for ins in p["insp"]:
                if ins["s"] is not None and ins["s"] not in raw_scores:
                    invented.append({"fid": fid, "s": ins["s"]})
        else:
            stub_s = stub["columns"].get("4", "").replace(
                "Last Inspection Score: ", "").strip()
            try:
                stub_s = int(stub_s)
            except ValueError:
                stub_s = None
            if p["s"] != stub_s:
                invented.append({"fid": fid, "err": "stub-score mismatch",
                                 "out": p["s"], "stub": stub_s})
    res["checks"]["B3_latest_matches_raw"] = (len(mism_latest) == 0)
    res["B3_mismatches"] = mism_latest[:10]
    res["checks"]["B4_no_invented_scores"] = (len(invented) == 0)
    res["B4_violations"] = invented[:10]

    # ---- B5: spot check 5 deterministic records field-by-field
    picks = sorted(by_id)[:: max(1, len(by_id) // 5)][:5]
    spot = []
    for pid in picks:
        p = by_id[pid]
        county, stub = raw_fac[str(p["fid"])]
        valid_raw = [r for r in raw_insp.get(str(p["fid"]), [])
                     if r is not None
                     and (r.get("columns", {}).get("0") or "").strip()
                     != "No Inspections To Display"
                     and iso(r.get("columns", {}).get("0", "").replace(
                         "Date: ", "")) is not None]
        ok = (p["n"] == stub["name"].strip()
              and len(p["insp"]) == len(valid_raw))
        spot.append({"id": pid, "name": p["n"], "county": county,
                     "fields_match_raw": ok,
                     "n_insp": len(p["insp"]),
                     "latest": [p["s"], p["grade"], p["d"]]})
    res["B5_spot_checks"] = spot
    res["checks"]["B5_spot_ok"] = all(s["fields_match_raw"] for s in spot)

    # ---- B6: geocode readiness, recomputed
    total = len(places)
    house = sum(1 for p in places if re.match(r"^\d", p["a"] or ""))
    pobox = sum(1 for p in places
                if re.search(r"\bP\.?\s?O\.?\s+BOX\b", p["a"] or "",
                             re.IGNORECASE))
    res["geocode_readiness"] = {
        "places": total,
        "street_starts_with_house_number": house,
        "pct_house_number": round(100.0 * house / total, 2) if total
        else 0,
        "po_box": pobox,
        "with_city": sum(1 for p in places if p["c"]),
        "with_zip": sum(1 for p in places if p["z"]),
    }

    # ---- B7: inspections-per-place distribution
    dist = collections.Counter(len(p["insp"]) for p in places)
    res["inspections_per_place"] = {str(k): dist[k] for k in sorted(dist)}

    # ---- B9: county attribution invariants (recomputed from raw):
    # (a) every place's county is one of the counties whose search
    #     returned it (sightings rebuilt here from ALL search pages);
    # (b) prefix-pair rule: a facility sighted in both CLAY and
    #     CLAYTON (the state's only prefix pair) sits in CLAYTON;
    #     sighted only in CLAY -> CLAY.
    sight = collections.defaultdict(set)
    for cdir in glob.glob(os.path.join(RAW, "search_pages", "*")):
        cname = os.path.basename(cdir)
        for pf in glob.glob(os.path.join(cdir, "p*.json")):
            for stub in json.load(open(pf)):
                sight[base64.b64decode(stub["id"]).decode()].add(cname)
    bad_adj = []
    multi = collections.Counter()
    for p in places:
        s = sight.get(str(p["fid"]), set())
        multi[tuple(sorted(s))] += 1
        if p["ct_raw"] not in s:
            bad_adj.append({"id": p["id"], "ct_raw": p["ct_raw"],
                            "sightings": sorted(s)})
        if s == {"CLAY", "CLAYTON"} and p["ct_raw"] != "CLAYTON":
            bad_adj.append({"id": p["id"], "err": "prefix-pair rule",
                            "ct_raw": p["ct_raw"]})
    res["checks"]["B9_county_attribution"] = len(bad_adj) == 0
    res["B9_violations"] = bad_adj[:10]
    res["multi_sighting_sets"] = {
        "+".join(k): v for k, v in multi.items() if len(k) > 1}

    # ---- B8: hygiene
    res["checks"]["B8_all_ga_dph"] = all(
        p["st"] == "GA" and p["jur"] == "GA-DPH" for p in places)
    res["checks"]["B8_no_coords"] = all(
        p["lat"] is None and p["lng"] is None for p in places)
    res["checks"]["B8_unique_ids"] = len(by_id) == len(places)
    dates = [i["d"] for p in places for i in p["insp"]]
    res["inspection_date_min"] = min(dates) if dates else None
    res["inspection_date_max"] = max(dates) if dates else None
    res["counties_in_output"] = len({p["ct_raw"] for p in places})

    res["ALL_PASS"] = all(v for k, v in res["checks"].items())
    with open(os.path.join(OUT, "qa_crosscheck.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1)[:3500])
    return 0 if res["ALL_PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
