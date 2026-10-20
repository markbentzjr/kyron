#!/usr/bin/env python3
"""NC build: assemble places_nc.json from harvested CDPEHS data.

Universe = the portal's own CSV exports. Every food-service
inspection must be stub-verified against its violation-detail page
(name, date, score, grade, premise identity) before it ships;
failures are excluded with reasons (TN discipline). Scores are
carried verbatim as JSON numbers - NC uses half points (95.5) and
they are NEVER rounded.
"""
import os, re, sys, csv, io, json, gzip, glob
import datetime as dt
from collections import Counter
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nc_parse import parse_page, parse_score, date_iso, date_draw  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
FOOD_TYPES = {"1", "2", "3", "4", "5", "6", "9", "11", "12", "14", "15", "16", "30"}

def norm(s):
    return re.sub(r'\s+', ' ', (s or '').upper()).strip().rstrip(',').strip()

def skey(s):
    return (s["state_id"], date_iso(s["date"]) or s["date"], norm(s["name"]))

def load_csv_stubs(path):
    rows = list(csv.reader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig'))))
    out = []
    for r in rows[1:]:
        if not r or not any(c.strip() for c in r):
            continue
        out.append({"date": r[0].split(" ")[0], "grade": r[1], "score": r[2],
                    "inspector": r[3], "name": r[4], "addr1": r[5], "addr2": r[6],
                    "city": r[7], "state": r[8], "zip": r[9], "state_id": r[10],
                    "type": r[11]})
    return out

def _verify_worker(job):
    insp, rec, county_name = job
    g = rec["grid_stub"]
    stub = {"date": g["date"], "grade": g["grade"], "score": g["score"],
            "name": g["name"], "state_id": g["state_id"],
            "inspector": g["inspector"], "type": rec["type"]}
    raw = gzip.open(os.path.join(ROOT, rec["file"]), 'rb').read().decode(
        'utf-8', errors='replace')
    p = parse_page(raw)
    errs = []
    if norm(p["name"]) != norm(stub["name"]):
        errs.append(f"name detail={p['name']!r} stub={stub['name']!r}")
    if date_iso(p["date_str"]) != date_iso(stub["date"]):
        errs.append(f"date detail={p['date_str']} stub={stub['date']}")
    if parse_score(p["score_str"]) != parse_score(stub["score"]):
        errs.append(f"score detail={p['score_str']} stub={stub['score']}")
    if (p["grade_str"] or None) != (stub["grade"] or None):
        errs.append(f"grade detail={p['grade_str']!r} stub={stub['grade']!r}")
    if p["ptype_label"].split(" - ")[0].strip() != str(rec["type"]):
        errs.append(f"type detail={p['ptype_label']!r} task={rec['type']}")
    if norm(p["county"]) != norm(county_name):
        errs.append(f"county detail={p['county']!r}")
    if any("parse_error" in v for v in p["violations"]):
        errs.append("violation row parse error")
    return insp, rec, stub, p, errs

def assemble_one(places, insp, rec, stub, p, county_names):
    sid = stub["state_id"]
    iso = date_iso(p["date_str"])
    viols = [{"item": v["item"], "title": v["title"], "rule": v["rule"],
              "notes": v["notes"], "points": v["points"],
              "corrected": v["corrected"], "repeat": v["repeat"],
              "vr": v["vr"]} for v in p["violations"]]
    insp_rec = {
        "id": f"ncdpehs_insp_{insp}", "vid": insp, "d": iso,
        "draw": date_draw(p["date_str"]), "t": None,
        "s": parse_score(p["score_str"]), "grade": p["grade_str"] or None,
        "inspector": stub["inspector"] or None,
        "comments": p["comments"], "v": viols, "du": rec["url"],
    }
    premise = {
        "n": p["name"],
        "a": ", ".join(x for x in [p["addr1"], p["addr2"]] if x),
        "c": p["city"].title() if p["city"].isupper() else p["city"],
        "z": p["zip"], "ptype": p["ptype_label"],
    }
    pl = places.get(sid)
    if pl is None:
        pl = {"id": f"ncdpehs_{sid}", "fid": sid, "fid_b64": sid,
              "n": "", "a": "", "c": "", "z": "", "addr_state": "NC",
              "ct": county_names.get(rec["cty"], p["county"]),
              "ct_raw": county_names.get(rec["cty"], p["county"]),
              "search_county": county_names.get(rec["cty"], p["county"]),
              "st": "NC", "jur": "NC-CDPEHS", "src": "NC-CDPEHS",
              "phone": None, "permit": sid, "ptype": "",
              "eh_phone": None, "lat": None, "lng": None,
              "s": None, "d": None, "grade": None, "du": None,
              "origin": "portal", "insp": [], "_newest": ("", None)}
        places[sid] = pl
    if iso and iso >= pl["_newest"][0]:
        pl["_newest"] = (iso, premise)
    pl["insp"].append(insp_rec)

def main():
    county_names = {}
    sweep = json.load(open(os.path.join(ROOT, "work/county_sweep.json")))
    for row in sweep:
        if row.get("counties"):
            county_names[row["cty"]] = row["counties"][0][1]

    counties = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "raw/csv/cty*_all*.csv"))):
        code = int(re.search(r'cty(\d{3})_all', path).group(1))
        counties.setdefault(code, []).extend(load_csv_stubs(path))
    food_stub_keys = Counter()
    slice_stub_total = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "raw/csv/cty*_t*.csv"))):
        for s in load_csv_stubs(path):
            slice_stub_total += 1
            food_stub_keys[skey(s)] += 1
    universe_total = sum(len(v) for v in counties.values())
    universe_food = 0
    nonfood = Counter()
    for stubs in counties.values():
        for s in stubs:
            if s["type"] in FOOD_TYPES:
                universe_food += 1
            else:
                nonfood[s["type"]] += 1

    index = {}
    dup_index = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "index/cty*.jsonl"))):
        for line in open(path):
            rec = json.loads(line)
            if rec["insp"] in index:
                dup_index += 1
                continue
            index[rec["insp"]] = rec

    problems = []
    harvested_keys = Counter()
    verified_stub_keys = Counter()
    places = {}
    insp_total = 0
    viol_total = 0
    jobs = [(insp, rec, county_names.get(rec["cty"], ""))
            for insp, rec in index.items()]
    with Pool(8) as pool:
        for insp, rec, stub, p, errs in pool.imap(_verify_worker, jobs, chunksize=100):
            if errs:
                problems.append({"insp": insp, "cty": rec["cty"],
                                 "state_id": stub["state_id"], "errors": errs})
                continue
            harvested_keys[skey(stub)] += 1
            verified_stub_keys[skey(stub)] += 1
            assemble_one(places, insp, rec, stub, p, county_names)
            insp_total += 1
            viol_total += len(p["violations"])
    unmatched_index = sum(1 for k, n in harvested_keys.items()
                          if food_stub_keys.get(k, 0) < n)

    out_places = []
    for sid, pl in places.items():
        pl["insp"].sort(key=lambda r: (r["d"] or "", r["id"]), reverse=True)
        top = pl["insp"][0]
        pl["s"], pl["d"], pl["grade"], pl["du"] = top["s"], top["d"], top["grade"], top["du"]
        _, premise = pl.pop("_newest")
        pl.update(premise)
        out_places.append(pl)
    out_places.sort(key=lambda x: x["id"])

    missing = food_stub_keys - verified_stub_keys
    miss_by_county_name = {}
    exclusions = []
    for (sid, diso, nname), n in sorted(missing.items()):
        exclusions.append({"permitID": sid, "county": "", "name": nname,
                           "reason": f"{n} food inspection stub(s) with no verified detail page (fetch failure or stub/detail mismatch; see qa_report.json)"})
    for pr in problems:
        exclusions.append({"permitID": pr["state_id"], "county": county_names.get(pr["cty"], ""),
                           "name": "", "reason": f"inspection {pr['insp']} failed stub verification: " + "; ".join(pr["errors"][:3])})

    os.makedirs(os.path.join(ROOT, "OUTPUT"), exist_ok=True)
    with open(os.path.join(ROOT, "OUTPUT/places_nc.json"), "w") as f:
        json.dump(out_places, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(ROOT, "OUTPUT/exclusions.json"), "w") as f:
        json.dump(exclusions, f, indent=1, ensure_ascii=False)

    dates = [i["d"] for pl in out_places for i in pl["insp"] if i["d"]]
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    qa = {
        "universe_inspection_rows_all_types": universe_total,
        "universe_food_stubs": universe_food,
        "slice_csv_food_stubs": slice_stub_total,
        "nonfood_rows_by_type": dict(nonfood),
        "index_records": len(index), "index_duplicates": dup_index,
        "verified_inspections": len(index) - len(problems),
        "verification_problems": len(problems),
        "problems_sample": problems[:25],
        "unmatched_verified_keys": unmatched_index,
        "missing_stub_inspections": sum(missing.values()),
        "places_out": len(out_places),
        "inspections_out": insp_total,
        "violations_out": viol_total,
        "inspection_date_min": min(dates) if dates else None,
        "inspection_date_max": max(dates) if dates else None,
        "counties_with_places": len({pl['ct'] for pl in out_places}),
        "generated_at": generated,
    }
    with open(os.path.join(ROOT, "OUTPUT/qa_report.json"), "w") as f:
        json.dump(qa, f, indent=1)
    with open(os.path.join(ROOT, "OUTPUT/problems.json"), "w") as f:
        json.dump(problems, f, indent=1)
    manifest = {
        "region": "us-nc", "state": "NC", "jurisdiction": "NC-CDPEHS",
        "source": "North Carolina Public Health Inspections portal (CDPEHS, public.cdpehs.com) - county health department inspections under the NC DHHS environmental health program",
        "source_files": ["places_nc.json"],
        "score_model": "Native NC sanitation score published per inspection: Final Score 0-100 with HALF-POINT granularity (e.g. 95.5), computed by the source as 100 minus violation demerits, plus the posted letter grade verbatim (A = 90+, B = 80-89.5, C = 70-79.5; below 70 the permit is revoked). Both forms are carried verbatim and NEITHER is derived from the other. Scores are stored as JSON numbers - half points are preserved exactly and never rounded. Grade may be 'N/A' or blank on some records; score is then whatever the source published (including null when the source published none).",
        "generated_at": generated,
        "adapter": "nc_fetch.py (CDPEHS WebForms CSV-export enumeration + Violation Details postback harvest, stub-verified) -> nc_parse.py -> nc_build.py",
        "coverage_exclusions": "Food-service establishment types only (NC establishment types 1,2,3,4,5,6,9,11,12,14,15,16,30), mirroring the TN food-permit-only rule. All other CDPEHS programs (lodging, camps, child care, residential care, hospitals, school buildings, pools/spas, tattoo) are enumerated in the county CSVs and counted in qa_report.json but excluded: their 'Final Score' column is a demerit count or program classification, not a sanitation score. Alexander and Buncombe counties return zero rows on CDPEHS (Buncombe publishes via its own Accela portal) - documented gaps, no data fabricated.",
        "totals": {"places": len(out_places),
                   "places_with_inspections": sum(1 for pl in out_places if pl["insp"]),
                   "inspections": insp_total, "violations": viol_total,
                   "inspection_date_min": qa["inspection_date_min"],
                   "inspection_date_max": qa["inspection_date_max"],
                   "counties_with_places": qa["counties_with_places"]},
    }
    with open(os.path.join(ROOT, "OUTPUT/manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps({k: qa[k] for k in ("universe_inspection_rows_all_types",
          "universe_food_stubs", "slice_csv_food_stubs", "verified_inspections",
          "verification_problems", "places_out", "inspections_out",
          "violations_out", "missing_stub_inspections")}, indent=1))

if __name__ == "__main__":
    main()
