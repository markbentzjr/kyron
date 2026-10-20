#!/usr/bin/env python3
"""
Kyron FL-DBPR adapter prototype (LF-5 prep).

Pipeline per gameplan adapter contract: fetch (done separately, raw/ is immutable)
-> parse -> normalize to canonical place/inspection/violation -> validate -> emit pack.

Inputs (raw/, exactly as published by FL DBPR, all 7 districts):
  hrfood{N}.csv  licensee/establishment extracts (35 cols)
  {N}fdinspi.csv inspection extracts, current FY (82 cols; Violation 01..58 are
                 COUNTS per violation category, not narrative text)

Outputs (OUTPUT/):
  places_fl.json   canonical places with embedded inspections (Alabama seed philosophy)
  manifest.json    build metadata + counts
  qa_report.json   full row accounting + completeness stats (QA pass A)

Florida publishes NO 0-100 score. raw_score_text stays null; the native result
carried per inspection is the Inspection Disposition string, preserved verbatim.
Nothing is invented: no score, no normalized band, no per-violation severity
(the extracts only give per-inspection High/Intermediate/Basic totals).
"""
import csv, glob, json, re, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
OUT = ROOT / "OUTPUT"
CATS = {int(k): v["title"] for k, v in json.load(open(ROOT / "work" / "violation_categories.json")).items()}

def norm_header(h):
    return h.strip()

def rows_of(path):
    """Yield (lineno, dict) with stripped header names; count data rows."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rdr = csv.reader(fh)
        header = [norm_header(h) for h in next(rdr)]
        n = 0
        for i, row in enumerate(rdr, start=2):
            if not row or all(c.strip() == "" for c in row):
                yield ("__blank__", i, None)
                continue
            n += 1
            if len(row) != len(header):
                yield ("__badwidth__", i, (len(header), len(row)))
                continue
            yield ("row", i, dict(zip(header, row)))
        return n

def digits(s):
    return re.sub(r"\D", "", s or "")

def parse_date(s):
    """MM/DD/YYYY -> ISO date string or None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None

def al_style_date(iso):
    """ISO -> M/D/YYYY like the Alabama seed."""
    if not iso:
        return None
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{d.month}/{d.day}/{d.year}"

def to_int(s):
    s = (s or "").strip()
    try:
        return int(s)
    except ValueError:
        return None

qa = {
    "files": {},
    "licensee": {"rows_in": 0, "rows_kept": 0, "duplicate_rows_superseded": 0, "blank_lines": 0, "bad_width_rows": 0},
    "inspections": {"rows_in": 0, "rows_kept": 0, "blank_lines": 0, "bad_width_rows": 0,
                    "duplicate_visit_ids": 0, "unparseable_dates": 0},
    "join": {"insp_rows_matched_to_licensee": 0, "insp_rows_unmatched": 0,
             "ambiguous_digit_keys": 0, "insp_only_places": 0},
    "notes": [],
}

# ---------------- Pass 1: licensee files -> places ----------------
places = {}           # full License Number -> place dict
digit_index = defaultdict(list)  # digits-only license number -> [full numbers]
for path in sorted(glob.glob(str(RAW / "hrfood*.csv"))):
    fname = Path(path).name
    st = {"rows": 0}
    for kind, lineno, payload in rows_of(path):
        if kind == "__blank__":
            qa["licensee"]["blank_lines"] += 1
            continue
        if kind == "__badwidth__":
            qa["licensee"]["bad_width_rows"] += 1
            qa["notes"].append(f"{fname}:{lineno} bad width {payload}")
            continue
        row = payload
        st["rows"] += 1
        qa["licensee"]["rows_in"] += 1
        lic = row["License Number"].strip()
        if not lic:
            qa["notes"].append(f"{fname}:{lineno} missing License Number, row kept in rejects")
            qa.setdefault("rejects", []).append({"file": fname, "line": lineno, "reason": "missing license number"})
            continue
        addr_parts = [row["Location Street Address"].strip(), row["Location Address Line 2"].strip(),
                      row["Location Address Line 3"].strip()]
        place = {
            "id": f"fldbpr_{lic}",
            "n": row["Business Name"].strip(),
            "a": " ".join(p for p in addr_parts if p),
            "c": row["Location City"].strip(),
            "z": row["Location Zip Code"].strip(),
            "ct": row["Location County"].strip(),
            "st": "FL",
            "jur": "FL-DBPR",
            "src": "FL-DBPR",
            "dist": row["District"].strip(),
            "lic": lic,
            "lic_digits": digits(lic),
            "licensee_name": row["Licensee Name"].strip(),
            "ltype": row["License Type Code"].strip(),
            "rank": row["Rank Code"].strip(),
            "status_p": row["Primary Status Code"].strip(),
            "status_s": row["Secondary Status Code"].strip(),
            "risk": row["Base Risk Level"].strip() or None,
            "risk2": row["Secondary Risk Level"].strip() or None,
            "seats": to_int(row["Number of Seats or Rental Units"]),
            "phone": row["Secondary Phone Number"].strip() or None,
            "expiry": parse_date(row["License Expiry Date"]),
            "lic_last_insp": parse_date(row["Last Inspection Date"]),
            "lat": None,
            "lng": None,
            "du": f"https://www.myfloridalicense.com/wl11.asp?mode=inspections&lic={lic}",
            "insp": [],
            "_origin": "licensee",
        }
        if lic in places:
            qa["licensee"]["duplicate_rows_superseded"] += 1
            qa.setdefault("dup_license_numbers", []).append(lic)
            # deterministic rule: keep the row whose District matches the file district,
            # otherwise keep the first seen. Log either way.
            file_dist = fname.replace("hrfood", "").replace(".csv", "")
            if places[lic]["dist"] != file_dist and place["dist"] == file_dist:
                places[lic] = place
            continue
        places[lic] = place
        digit_index[place["lic_digits"]].append(lic)
        qa["licensee"]["rows_kept"] += 1
    qa["files"][fname] = st

def name_key(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

def join_signals(row, place):
    """Score how well an inspection row matches a candidate place (tiebreak only)."""
    score = 0
    dba, pname = name_key(row["Business (DBA-Does Business As) Name"]), name_key(place["n"])
    if dba and pname and (dba in pname or pname in dba):
        score += 4
    if row["Location City"].strip().upper() == (place["c"] or "").upper():
        score += 2
    if row["Location Zip Code"].strip()[:5] == (place["z"] or "")[:5]:
        score += 2
    insp_addr = name_key(row["Location Address"])
    place_addr = name_key(place["a"])
    if insp_addr and place_addr and (insp_addr[:12] == place_addr[:12]):
        score += 3
    return score

# ---------------- Pass 2: inspection files -> inspections ----------------
insp_only = {}  # digits license -> place stub built from inspection rows
seen_visit_ids = set()
for path in sorted(glob.glob(str(RAW / "*fdinspi.csv"))):
    fname = Path(path).name
    st = {"rows": 0}
    file_dist = fname[0]
    for kind, lineno, payload in rows_of(path):
        if kind == "__blank__":
            qa["inspections"]["blank_lines"] += 1
            continue
        if kind == "__badwidth__":
            qa["inspections"]["bad_width_rows"] += 1
            qa["notes"].append(f"{fname}:{lineno} bad width {payload}")
            continue
        row = payload
        st["rows"] += 1
        qa["inspections"]["rows_in"] += 1
        vid = row["Inspection Visit ID"].strip()
        if vid in seen_visit_ids:
            qa["inspections"]["duplicate_visit_ids"] += 1
            qa["notes"].append(f"{fname}:{lineno} duplicate Inspection Visit ID {vid} skipped")
            continue
        seen_visit_ids.add(vid)
        iso = parse_date(row["Inspection Date"])
        if iso is None:
            qa["inspections"]["unparseable_dates"] += 1
        viols = []
        for n in range(1, 59):
            cnt = to_int(row[f"Violation {n:02d}"])
            if cnt:
                viols.append({"code": f"{n:02d}", "cnt": cnt, "r": CATS.get(n)})
        insp = {
            "id": f"fldbpr_insp_{vid}",
            "vid": vid,
            "insp_no": row["Inspection Number"].strip(),
            "visit": to_int(row["Visit Number"]),
            "d": iso,
            "draw": row["Inspection Date"].strip(),
            "t": row["Inspection Type"].strip(),
            "class": row["Inspection Class"].strip(),
            "disp": row["Inspection Disposition"].strip(),
            "tot": to_int(row["Number of Total Violations"]),
            "hp": to_int(row["Number of High Priority Violations"]),
            "im": to_int(row["Number of Intermediate Violations"]),
            "ba": to_int(row["Number of Basic Violations"]),
            "pda": row["PDA Status"].strip() or None,
            "v": viols,
        }
        lic_digits = digits(row["License Number"])
        candidates = digit_index.get(lic_digits, [])
        target = None
        # FL license numbers are unique per license TYPE + number, and the inspection
        # extract omits the rank prefix the licensee file embeds in the number.
        # Join key is therefore (digits, License Type Code); residual ties are broken
        # by name/city/zip/address signals and flagged when signals cannot separate.
        join_method = None
        if len(candidates) == 1:
            target = places[candidates[0]]
            join_method = "digits_unique"
        elif len(candidates) > 1:
            qa["join"]["ambiguous_digit_keys"] += 1
            insp_ltype = row["License Type Code"].strip()
            typed = [c for c in candidates if places[c]["ltype"] == insp_ltype]
            if len(typed) == 1:
                target = places[typed[0]]
                join_method = "digits+ltype"
            elif not typed:
                # No licensee of this license type carries these digits: the true
                # licensee lives outside the food-service extracts (e.g. lodging
                # license types 2001-2023). Do NOT guess among wrong-type places.
                target = None
                join_method = "unmatched_ltype_absent"
            else:
                pool = typed
                scored = sorted(((join_signals(row, places[c]), c) for c in pool), reverse=True)
                if len(scored) == 1 or scored[0][0] > scored[1][0]:
                    target = places[scored[0][1]]
                    join_method = "digits+ltype+signals" if typed else "digits+signals"
                else:
                    target = places[scored[0][1]]
                    join_method = "AMBIGUOUS_tie"
                    qa["join"]["ambiguous_unresolved_ties"] = qa["join"].get("ambiguous_unresolved_ties", 0) + 1
        insp["jm"] = join_method
        if target is not None:
            qa["join"]["insp_rows_matched_to_licensee"] += 1
            qa["join"].setdefault("by_method", Counter())[join_method] += 1
        else:
            qa["join"]["insp_rows_unmatched"] += 1
            if lic_digits not in insp_only:
                insp_only[lic_digits] = {
                    "id": f"fldbpr_insp_only_{lic_digits}",
                    "n": row["Business (DBA-Does Business As) Name"].strip(),
                    "a": row["Location Address"].strip(),
                    "c": row["Location City"].strip(),
                    "z": row["Location Zip Code"].strip(),
                    "ct": row["County Name"].strip(),
                    "st": "FL",
                    "jur": "FL-DBPR",
                    "src": "FL-DBPR",
                    "dist": file_dist,
                    "lic": None,
                    "lic_digits": lic_digits,
                    "licensee_name": None,
                    "ltype": row["License Type Code"].strip(),
                    "rank": None,
                    "status_p": None, "status_s": None,
                    "risk": None, "risk2": None, "seats": None, "phone": None,
                    "expiry": None, "lic_last_insp": None,
                    "lat": None, "lng": None, "du": None,
                    "insp": [],
                    "_origin": "inspections_only",
                }
            target = insp_only[lic_digits]
        target["insp"].append(insp)
        qa["inspections"]["rows_kept"] += 1
    qa["files"][fname] = st

qa["join"]["insp_only_places"] = len(insp_only)
places.update({p["id"]: p for p in insp_only.values()})

# ---------------- Pass 2.5: name-completeness reject (Workstream C1) ----------------
# A place whose displayed name is blank or a placeholder/header token is not
# an establishment a user can attach a result to. Mirroring the ADPH/MCHD
# completeness guards (Workstream B) and the validate_seed.py G4 predicate
# exactly: such records are EXCLUDED from the shipped dataset and logged —
# never renamed (a legal-entity licensee_name is not a storefront name, and
# inventing one is forbidden). Result-bearing rejects are the critical class:
# a disposition/inspection attached to no real name must never ship.
PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'total', 'subtotal',
    'establishment', 'facility', 'facility name', 'food service', 'name',
    'business name', 'unnamed', 'test', 'restaurant', 'the', '-', '--',
    'see remarks', 'county health department', 'health department',
}
name_rejects = []
kept_places = []
for p in list(places.values()):
    raw_name = p["n"] or ""
    nname = re.sub(r"\s+", " ", raw_name).strip().lower()
    if nname in PLACEHOLDER_NAMES or raw_name.rstrip().endswith("#"):
        bearing = bool(p["insp"]) or bool(p.get("disp"))
        name_rejects.append({
            "id": p["id"], "name": raw_name, "city": p["c"], "county": p["ct"],
            "origin": p["_origin"], "licensee_name": p.get("licensee_name"),
            "inspections_dropped": len(p["insp"]),
            "result_bearing": bearing,
            "reason": "blank_name" if nname == "" else "placeholder_name",
        })
        print(f"NAME REJECT {p['id']}: name={raw_name!r} city={p['c']} "
              f"result_bearing={bearing} inspections_dropped={len(p['insp'])}")
    else:
        kept_places.append(p)
places = {p["id"]: p for p in kept_places}
qa["name_rejects"] = name_rejects
qa["name_rejects_count"] = len(name_rejects)
qa["name_rejects_result_bearing"] = sum(1 for r in name_rejects if r["result_bearing"])
print(f"NAME REJECTS: {len(name_rejects)} excluded "
      f"({qa['name_rejects_result_bearing']} result-bearing); "
      f"{len(kept_places)} places ship")

# ---------------- Pass 3: finalize places ----------------
all_places = list(places.values())
date_min, date_max = None, None
for p in all_places:
    p["insp"].sort(key=lambda x: (x["d"] or "", x["visit"] or 0), reverse=True)
    if p["insp"]:
        latest = p["insp"][0]
        p["d"] = al_style_date(latest["d"]) if latest["d"] else None
        p["disp"] = latest["disp"]
        for ins in p["insp"]:
            if ins["d"]:
                date_min = ins["d"] if date_min is None or ins["d"] < date_min else date_min
                date_max = ins["d"] if date_max is None or ins["d"] > date_max else date_max
    else:
        p["d"] = al_style_date(p["lic_last_insp"])
        p["disp"] = None
    p["origin"] = p.pop("_origin")

all_places.sort(key=lambda p: p["id"])

# completeness stats
FIELDS = ["n", "a", "c", "z", "ct", "lic", "ltype", "rank", "status_p", "risk", "seats", "phone", "d"]
comp = {}
for f in FIELDS:
    comp[f] = round(100.0 * sum(1 for p in all_places if p.get(f) not in (None, "")) / max(len(all_places), 1), 2)
qa["completeness_pct"] = comp
qa["totals"] = {
    "places": len(all_places),
    "places_from_licensee": qa["licensee"]["rows_kept"],
    "places_inspection_only": len(insp_only),
    "places_with_inspections": sum(1 for p in all_places if p["insp"]),
    "inspections": sum(len(p["insp"]) for p in all_places),
    "violation_category_counts_total": sum(v["cnt"] for p in all_places for i in p["insp"] for v in i["v"]),
    "inspection_date_min": date_min,
    "inspection_date_max": date_max,
}

if "by_method" in qa["join"]:
    qa["join"]["by_method"] = dict(qa["join"]["by_method"])

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "places_fl.json", "w") as fh:
    json.dump(all_places, fh, separators=(",", ":"))
manifest = {
    "region": "us-fl",
    "state": "FL",
    "jurisdiction": "FL-DBPR",
    "source": "Florida DBPR Division of Hotels & Restaurants public-records extracts",
    "source_files": sorted(qa["files"].keys()),
    "score_model": "DISPOSITION (native; Florida publishes no numeric score)",
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "adapter": "fl_dbpr prototype v0.1",
    "totals": qa["totals"],
}
with open(OUT / "manifest.json", "w") as fh:
    json.dump(manifest, fh, indent=1)
with open(OUT / "qa_report.json", "w") as fh:
    json.dump(qa, fh, indent=1)
with open(OUT / "fl_name_rejects.json", "w") as fh:
    json.dump(name_rejects, fh, indent=1)

print(json.dumps(qa["totals"], indent=1))
print("licensee:", qa["licensee"])
print("inspections:", qa["inspections"])
print("join:", qa["join"])
print("completeness:", comp)
