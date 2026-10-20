#!/usr/bin/env python3
"""Georgia DPH adapter — normalizer + QA pass A (prototype v0.1).

Input : raw/ as fetched by ga_fetch.py (search pages + inspectionsData)
Output: OUTPUT/places_ga.json  (canonical Kyron model, mirrors FL shape)
        OUTPUT/manifest.json
        OUTPUT/qa_report.json  (pass A accounting)

Georgia publishes a native 0-100 score with state grade bands
A 90-100 / B 80-89 / C 70-79 / U <70 (GA DPH). Scores and violation
narratives are preserved verbatim; nothing is converted or invented.
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
PORTAL = "https://ga.healthinspections.us/stateofgeorgia/"
GNR_COUNTIES = {"GWINNETT", "NEWTON", "ROCKDALE"}

# Gate-driven exclusions (validate_seed.py G4): individually verified
# records whose published name is a placeholder, so their scores would
# ship attached to a non-name. Full provenance in OUTPUT/exclusions.json.
EXCLUSIONS = {
    "3135799": "G4: portal publishes this Fulton Co. permit "
               "(FSP-060-003550, 1197 Peachtree St Ste 517, Atlanta) "
               "under the literal name 'Establishment' with 5 scored "
               "inspections (85-96, 2023-2026). Placeholder name in the "
               "source itself; excluded rather than shipped, per the "
               "Workstream B gate precedent.",
}


def grade_of(score):
    if score is None:
        return None
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "U"


def strip_prefix(s, prefix):
    s = (s or "").strip()
    return s[len(prefix):].strip() if s.startswith(prefix) else s


def parse_us_date(s):
    """'MM-DD-YYYY' -> ('YYYY-MM-DD', 'M/D/YYYY') or (None, None)."""
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", (s or "").strip())
    if not m:
        return None, None
    mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= dy <= 31):
        return None, None
    return f"{yr:04d}-{mo:02d}-{dy:02d}", f"{mo}/{dy}/{yr}"


ADDR_TAIL = re.compile(r"^(.*),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$")
ONE_LINE_TAIL = re.compile(
    r"^(.*\S)\s+([A-Z][A-Z]+(?:\s[A-Z]+)?),\s*([A-Z]{2})\s+"
    r"(\d{5}(?:-\d{4})?)\s*$")


def permit_code(permit):
    """Extract the GA county code (3 digits) from a permit number.
    Formats seen: 'FSP-031-000328', 'FS044-884984', '03111085',
    'FSP-152-000021', '103-12345'. Returns '031' or None."""
    p = (permit or "").strip().upper()
    m = re.match(r"^(?:FSP|FS)-(\d{3})-\d+", p)
    if m:
        return m.group(1)
    m = re.match(r"^(?:FSP|FS)(\d{3})-\d+", p)
    if m:
        return m.group(1)
    m = re.match(r"^F-(\d{3})-\d+", p)          # legacy: F-058-2009-00065
    if m:
        return m.group(1)
    m = re.match(r"^(\d{3})-(?:FSP|FS)-", p)    # legacy: 058-FS-2013-05057
    if m:
        return m.group(1)
    m = re.match(r"^(\d{3})-\d+", p)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{3})\d{4,}$", p)
    if m:
        return m.group(1)
    return None


def parse_map_address(map_address):
    """-> (street, city, zip, addr_state, ok).

    Handles the portal's three shapes:
      'STREET \\r\\nCITY, GA ZIP'      (the norm)
      'STREET CITY, GA ZIP'           (single line; some counties)
      'CITY, GA ZIP'                  (no street in source; ok=False)
    A non-GA state in the tail is returned verbatim in addr_state
    (source typos like 'NEWNAN, TN 30263' keep their GA ZIP)."""
    parts = re.split(r"\r\n|\n", map_address or "")
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return "", "", "", "", False
    if len(parts) >= 2:
        street = parts[0]
        m = ADDR_TAIL.match(parts[-1])
        if not m:
            return street, "", "", "", False
        return street, m.group(1).strip(), m.group(3), m.group(2), True
    line = parts[0]
    m = ONE_LINE_TAIL.match(line)
    if m and re.search(r"\d", m.group(1)):
        # a real street segment carries a house number; without one the
        # line is a bare 'CITY, ST ZIP' (e.g. 'TYBEE ISLAND, GA 31328')
        return (m.group(1).strip(), m.group(2).strip(), m.group(4),
                m.group(3), True)
    m = ADDR_TAIL.match(line)
    if m:  # city/state/zip only — no street in the source
        return "", m.group(1).strip(), m.group(3), m.group(2), False
    return line, "", "", "", False


def _s(x):
    return (x or "").strip() if not isinstance(x, str) else x.strip()


def parse_violation(arr, shape_census):
    shape_census[len(arr)] += 1
    arr = [_s(x) for x in arr]
    v = {"raw": arr}
    if len(arr) >= 1:
        head = arr[0]
        if " - " in head:
            code, title = head.split(" - ", 1)
            v["item"] = code.strip()
            v["title"] = title.strip()
        else:
            v["item"] = None
            v["title"] = head
    if len(arr) >= 2:
        v["rule"] = arr[1]
    if len(arr) >= 3:
        m = re.search(r"Points:\s*(\d+)", arr[2])
        v["points"] = int(m.group(1)) if m else None
    if len(arr) >= 4:
        v["corrected"] = arr[3].endswith("Yes")
        v["corrected_raw"] = arr[3]
    if len(arr) >= 5:
        v["repeat"] = arr[4].endswith("Yes")
        v["repeat_raw"] = arr[4]
    if len(arr) >= 6:
        v["notes"] = strip_prefix(arr[5], "Inspector Notes:")
    if len(arr) == 6:
        v.pop("raw")
    return v


EXCLUDED_SEEN = set()


def main():
    qa = {
        "counties_searched": 0,
        "search_stubs_in": 0,
        "duplicate_facility_ids_across_counties": [],
        "places_out": 0,
        "inspections_in": 0,
        "inspections_out": 0,
        "inspections_unparseable_date": 0,
        "inspections_missing_score": 0,
        "score_out_of_range": [],
        "places_zero_inspections": 0,
        "places_latest_from_stub_only": 0,
        "address_parse_failures": 0,
        "purpose_census": collections.Counter(),
        "violation_shape_census": collections.Counter(),
        "county_place_counts": collections.Counter(),
        "inspection_date_min": None,
        "inspection_date_max": None,
    }

    # ---- pre-pass: permit-code -> county map. The portal's county
    # predicate is a prefix match, so county=CLAY also returns CLAYTON
    # facilities (the only prefix pair among GA's 159 counties). The
    # permit number's 3-digit county code is the permitting authority
    # of record and adjudicates the true county.
    code_county_votes = collections.defaultdict(collections.Counter)
    sightings = collections.defaultdict(set)
    for cdir in sorted(glob.glob(os.path.join(RAW, "search_pages", "*"))):
        c_raw = os.path.basename(cdir)
        for page_file in sorted(glob.glob(os.path.join(cdir, "p*.json"))):
            with open(page_file) as f:
                for stub in json.load(f):
                    fid_s = base64.b64decode(stub["id"]).decode()
                    sightings[fid_s].add(c_raw)
                    code = permit_code(strip_prefix(
                        stub.get("columns", {}).get("3"),
                        "Permit Number:"))
                    if code:
                        code_county_votes[code][c_raw] += 1
    # Permit codes are evidence, not authority (see adjudication in the
    # main loop): keep the census for QA reporting only.
    qa["permit_code_census"] = {
        code: dict(votes) for code, votes in code_county_votes.items()}
    qa["county_reassignments"] = []
    qa["county_multi_sighting_unresolved"] = []
    qa["permit_code_disagreements"] = []

    places = {}
    county_dirs = sorted(glob.glob(os.path.join(RAW, "search_pages", "*")))
    for cdir in county_dirs:
        county_raw = os.path.basename(cdir)
        qa["counties_searched"] += 1
        stubs = []
        for page_file in sorted(glob.glob(os.path.join(cdir, "p*.json"))):
            with open(page_file) as f:
                stubs.extend(json.load(f))
        seen_here = set()
        for stub in stubs:
            qa["search_stubs_in"] += 1
            fid_num = base64.b64decode(stub["id"]).decode()
            if fid_num in EXCLUSIONS:
                if fid_num not in EXCLUDED_SEEN:
                    EXCLUDED_SEEN.add(fid_num)
                    qa.setdefault("excluded_places", []).append({
                        "facility": fid_num, "county": county_raw,
                        "name": stub.get("name"),
                        "reason": EXCLUSIONS[fid_num]})
                continue
            if fid_num in seen_here:
                continue
            seen_here.add(fid_num)
            if fid_num in places:
                qa["duplicate_facility_ids_across_counties"].append(
                    {"facility": fid_num, "first_county":
                     places[fid_num]["ct_raw"], "also_in": county_raw})
                continue
            street, city, zipc, addr_state, addr_ok = parse_map_address(
                stub.get("mapAddress"))
            if not addr_ok:
                qa["address_parse_failures"] += 1
            if not street:
                # Workstream B precedent: a result with no street
                # address in the source does not ship (logged, with
                # provenance, in exclusions.json)
                if fid_num not in EXCLUDED_SEEN:
                    EXCLUDED_SEEN.add(fid_num)
                    qa.setdefault("excluded_places", []).append({
                        "facility": fid_num, "county": county_raw,
                        "name": stub.get("name"),
                        "reason": "G2-class: portal publishes no street "
                                  "address for this facility (mapAddress "
                                  f"was {stub.get('mapAddress')!r}); "
                                  "excluded rather than shipped."})
                continue
            cols = stub.get("columns", {})
            permit_txt = strip_prefix(cols.get("3"), "Permit Number:")
            # County adjudication. The search county is the portal's own
            # attribution and is authoritative EXCEPT for the portal's
            # prefix-match artifact: county=CLAY also returns CLAYTON
            # facilities (the only prefix pair among GA's 159 counties).
            # Rules: single sighting -> that county; prefix-chain
            # sightings -> the longest (most specific) name; otherwise
            # (rare multi-county sightings, e.g. mobile units) -> an
            # FSP/FS-format permit code naming one of the sighting
            # counties, else the search county + QA log entry. Permit
            # codes alone never move a facility: district offices issue
            # cross-county permits (e.g. an Alma/Bacon facility holding
            # a Coffee-coded permit), verified against addresses.
            seen_in = sightings.get(fid_num, {county_raw})
            adj_county = county_raw
            if len(seen_in) > 1:
                srt = sorted(seen_in, key=len)
                if srt[-1].startswith(srt[-2]) and len(srt) == 2:
                    adj_county = srt[-1]
                else:
                    code = permit_code(permit_txt)
                    code_county = None
                    if code:
                        votes = code_county_votes.get(code, {})
                        if votes:
                            top, n = votes.most_common(1)[0]
                            if n / sum(votes.values()) >= 0.80:
                                code_county = top
                    if code_county in seen_in:
                        adj_county = code_county
                    else:
                        qa["county_multi_sighting_unresolved"].append({
                            "facility": fid_num,
                            "sightings": sorted(seen_in),
                            "kept": county_raw, "permit": permit_txt})
            if adj_county != county_raw:
                qa["county_reassignments"].append({
                    "facility": fid_num, "from_search": county_raw,
                    "to_permit_county": adj_county, "permit": permit_txt})
            place = {
                "id": f"gadph_{fid_num}",
                "fid": int(fid_num) if fid_num.isdigit() else fid_num,
                "fid_b64": stub["id"],
                "n": (stub.get("name") or "").strip(),
                "a": street,
                "c": city,
                "z": zipc,
                "addr_state": addr_state or "GA",
                "ct": adj_county.title(),
                "ct_raw": adj_county,
                "search_county": county_raw,
                "st": "GA",
                "jur": "GA-DPH",
                "src": "GA-DPH",
                "phone": strip_prefix(cols.get("1"), "Phone Number:") or None,
                "permit": strip_prefix(cols.get("3"), "Permit Number:")
                          or None,
                "ptype": strip_prefix(cols.get("2"), "Permit Type:")
                         or None,
                "eh_phone": strip_prefix(
                    cols.get("6"), "For More Information Call:") or None,
                "lat": None,
                "lng": None,
                "insp": [],
                "s": None,
                "grade": None,
                "d": None,
                "du": None,
                "origin": "portal",
            }
            # inspections (fetched under the search county; the
            # adjudicated county's copy is identical when both exist)
            insp_path = os.path.join(RAW, "insp", county_raw,
                                     f"{fid_num}.json")
            if not os.path.exists(insp_path):
                alt = os.path.join(RAW, "insp", adj_county,
                                   f"{fid_num}.json")
                if os.path.exists(alt):
                    insp_path = alt
            insp_list = []
            if os.path.exists(insp_path):
                with open(insp_path) as f:
                    insp_list = json.load(f)
            else:
                qa.setdefault("missing_insp_files", []).append(
                    f"{county_raw}/{fid_num}")
            qa["inspections_in"] += len(insp_list)
            for ins in insp_list:
                if ins is None:
                    qa["inspections_null_entries"] = qa.get(
                        "inspections_null_entries", 0) + 1
                    continue
                icols = ins.get("columns", {})
                qa["purpose_census"][
                    strip_prefix(icols.get("1"), "Inspection Purpose:")] += 1
                d_iso, _ = parse_us_date(
                    strip_prefix(icols.get("0"), "Date:"))
                if d_iso is None:
                    qa["inspections_unparseable_date"] += 1
                    continue
                s_txt = strip_prefix(icols.get("2"), "Score:")
                try:
                    score = int(s_txt)
                except (TypeError, ValueError):
                    score = None
                    qa["inspections_missing_score"] += 1
                if score is not None and not (0 <= score <= 100):
                    qa["score_out_of_range"].append(
                        {"place": place["id"], "score": score})
                viols = []
                raw_viols = ins.get("violations") or {}
                for k in sorted(raw_viols, key=lambda x: int(x)):
                    viols.append(parse_violation(
                        raw_viols[k], qa["violation_shape_census"]))
                ppath = ins.get("printablePath") or ""
                du = ("https://ga.healthinspections.us/"
                      + ppath[6:]) if ppath.startswith("../../") else ppath
                insp_list_entry = {
                    "id": f"gadph_insp_{ins.get('inspectionId')}",
                    "vid": ins.get("inspectionId"),
                    "d": d_iso,
                    "draw": strip_prefix(icols.get("0"), "Date:"),
                    "t": strip_prefix(icols.get("1"),
                                      "Inspection Purpose:"),
                    "s": score,
                    "grade": grade_of(score),
                    "inspector": strip_prefix(icols.get("3"),
                                              "Inspector:") or None,
                    "v": viols,
                    "du": du,
                }
                place["insp"].append(insp_list_entry)
                qa["inspections_out"] += 1
                for key, val in (("inspection_date_min", d_iso),
                                 ("inspection_date_max", d_iso)):
                    if qa[key] is None:
                        qa[key] = val
                qa["inspection_date_min"] = min(
                    qa["inspection_date_min"], d_iso)
                qa["inspection_date_max"] = max(
                    qa["inspection_date_max"], d_iso)
            place["insp"].sort(key=lambda x: (x["d"], x["vid"] or 0),
                               reverse=True)
            if place["insp"]:
                latest = place["insp"][0]
                place["s"] = latest["s"]
                place["grade"] = latest["grade"]
                _, d_us = parse_us_date(latest["draw"])
                place["d"] = d_us
                place["du"] = latest["du"]
            else:
                qa["places_zero_inspections"] += 1
                # fall back to the stub's last-inspection columns for
                # place-level latest score/date (no inspection row is
                # fabricated); flag it.
                s_txt = strip_prefix(cols.get("4"),
                                     "Last Inspection Score:")
                d_txt = strip_prefix(cols.get("5"),
                                     "Last Inspection Date:")
                try:
                    place["s"] = int(s_txt)
                except (TypeError, ValueError):
                    place["s"] = None
                place["grade"] = grade_of(place["s"])
                _, d_us = parse_us_date(d_txt)
                place["d"] = d_us
                place["latest_from_stub_only"] = True
                qa["places_latest_from_stub_only"] += 1
            places[fid_num] = place
            qa["county_place_counts"][adj_county] += 1
            # QA evidence: FSP/FS-format permit code naming a different
            # county than the final attribution (district-issued or
            # legacy permits; reported, never auto-applied)
            _code = permit_code(permit_txt)
            if _code and re.match(r"^(?:FSP|FS|F)-?\d{3}|^\d{3}-(?:FSP|FS)",
                                  (permit_txt or "").upper()):
                _votes = code_county_votes.get(_code, {})
                if _votes:
                    _cc = _votes.most_common(1)[0][0]
                    if _cc != adj_county and len(
                            qa["permit_code_disagreements"]) < 25:
                        qa["permit_code_disagreements"].append({
                            "facility": fid_num, "county": adj_county,
                            "permit": permit_txt, "code_county": _cc,
                            "city": city})

    out_places = sorted(places.values(), key=lambda p: p["id"])
    qa["places_out"] = len(out_places)
    qa["purpose_census"] = dict(qa["purpose_census"])
    qa["violation_shape_census"] = {
        str(k): v for k, v in qa["violation_shape_census"].items()}
    qa["county_place_counts"] = dict(qa["county_place_counts"])

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "places_ga.json"), "w") as f:
        json.dump(out_places, f, ensure_ascii=False)
    with open(os.path.join(OUT, "qa_report.json"), "w") as f:
        json.dump(qa, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "exclusions.json"), "w") as f:
        json.dump(qa.get("excluded_places", []), f, indent=1,
                  ensure_ascii=False)

    total_viols = sum(len(p["insp"][i]["v"])
                      for p in out_places for i in range(len(p["insp"])))
    manifest = {
        "region": "us-ga",
        "state": "GA",
        "jurisdiction": "GA-DPH",
        "source": "Georgia Department of Public Health — State of Georgia "
                  "Health Inspection portal (Tyler DHD public portal), "
                  "ga.healthinspections.us/stateofgeorgia",
        "source_files": ["raw/search_pages/<COUNTY>/p<NNNN>.json",
                         "raw/insp/<COUNTY>/<facility_id>.json"],
        "score_model": "SCORE_100 (native GA DPH 0-100) + state grade "
                       "bands A 90-100 / B 80-89 / C 70-79 / U <70",
        "generated_at": time_now(),
        "adapter": "ga_dph prototype v0.1",
        "coverage_exclusions": "Gwinnett, Newton, Rockdale counties "
                               "publish via GNR Health District "
                               "(inspections.myhealthdepartment.com) and "
                               "are NOT in this dataset",
        "totals": {
            "places": qa["places_out"],
            "places_with_inspections": qa["places_out"]
                - qa["places_zero_inspections"],
            "inspections": qa["inspections_out"],
            "violations": total_viols,
            "inspection_date_min": qa["inspection_date_min"],
            "inspection_date_max": qa["inspection_date_max"],
            "counties_with_places": len(qa["county_place_counts"]),
        },
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(json.dumps(manifest["totals"], indent=1))
    print("QA:", json.dumps({k: qa[k] for k in (
        "search_stubs_in", "places_out", "inspections_in",
        "inspections_out", "inspections_unparseable_date",
        "inspections_missing_score", "places_zero_inspections",
        "places_latest_from_stub_only", "address_parse_failures")},
        indent=1))


def time_now():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    sys.exit(main())
