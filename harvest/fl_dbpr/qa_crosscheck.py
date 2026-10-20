#!/usr/bin/env python3
"""
QA pass B — INDEPENDENT cross-check for the FL-DBPR prototype (Mark's rule: test twice,
two different ways). Deliberately shares no code with fl_dbpr_build.py: DictReader
streaming instead of positional csv.reader, independent join + totals recomputation,
plus ambiguity-risk analysis on the license-number join. Spot checks are done
separately with grep against the raw files.
"""
import csv, glob, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
RAW, OUT = ROOT / "raw", ROOT / "OUTPUT"
places_out = json.load(open(OUT / "places_fl.json"))
manifest = json.load(open(OUT / "manifest.json"))

res = {}

# --- B1: raw row counts via line counts (files have no embedded newlines in fields;
#         verified separately that csv row counts == wc -l - 1) ---
raw_counts = {}
for f in sorted(glob.glob(str(RAW / "*.csv"))):
    with open(f, "rb") as fh:
        raw_counts[Path(f).name] = sum(1 for _ in fh) - 1  # minus header
res["raw_data_rows_by_file"] = raw_counts
res["raw_licensee_rows_total"] = sum(v for k, v in raw_counts.items() if k.startswith("hrfood"))
res["raw_insp_rows_total"] = sum(v for k, v in raw_counts.items() if "fdinspi" in k)

# --- B2: independent recount of distinct license numbers + inspections ---
lic_full = Counter()
lic_by_digits = defaultdict(set)
for f in sorted(glob.glob(str(RAW / "hrfood*.csv"))):
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            ln = row["License Number"].strip()
            lic_full[ln] += 1
            lic_by_digits[re.sub(r"\D", "", ln)].add(ln)
res["distinct_license_numbers"] = len(lic_full)
res["duplicate_license_numbers"] = {k: v for k, v in lic_full.items() if v > 1}
res["digit_keys_with_multiple_license_numbers"] = sum(1 for v in lic_by_digits.values() if len(v) > 1)

visit_ids = Counter()
insp_per_digits = Counter()
tot_vs_sumcat = Counter()
tot_vs_sumcat_nonreporting = Counter()
name_mismatch_ambig = 0
ambig_rows = 0
for f in sorted(glob.glob(str(RAW / "*fdinspi.csv"))):
    dist = Path(f).name[0]
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            visit_ids[row["Inspection Visit ID"].strip()] += 1
            dg = re.sub(r"\D", "", row[" License Number"])
            insp_per_digits[dg] += 1
            s = sum(int(row[f"Violation {i:02d}"] or 0) for i in range(1, 59))
            s_nr = sum(int(row[f"Violation {i:02d}"] or 0) for i in range(1, 59) if not 45 <= i <= 49)
            t = int(row[" Number of Total Violations"] or 0)
            tot_vs_sumcat["eq" if s == t else ("sum_gt" if s > t else "sum_lt")] += 1
            tot_vs_sumcat_nonreporting["eq" if s_nr == t else ("sum_gt" if s_nr > t else "sum_lt")] += 1
res["distinct_visit_ids"] = len(visit_ids)
res["dup_visit_ids"] = sum(1 for v in visit_ids.values() if v > 1)
res["total_field_vs_sum_of_category_counts"] = dict(tot_vs_sumcat)
res["total_field_vs_sum_excl_reporting_45_49"] = dict(tot_vs_sumcat_nonreporting)

# --- B3: reconcile against builder output ---
out_insp = sum(len(p["insp"]) for p in places_out)
out_places = len(places_out)
out_lic = sum(1 for p in places_out if p.get("lic"))
res["output_places"] = out_places
res["output_places_with_license_number"] = out_lic
res["output_inspections"] = out_insp
builder_qa = json.load(open(OUT / "qa_report.json"))
res["reconcile_places"] = (out_places == len(lic_full) + builder_qa["totals"]["places_inspection_only"])
res["reconcile_inspections"] = (out_insp == res["raw_insp_rows_total"])
res["manifest_places_match"] = (manifest["totals"]["places"] == out_places)
res["manifest_inspections_match"] = (manifest["totals"]["inspections"] == out_insp)

# --- B4: join-risk — for inspections whose digits map to >1 license number,
#         does the builder's chosen place DBA name match the inspection DBA name? ---
by_lic = {p["lic"]: p for p in places_out if p.get("lic")}
mismatch_examples = []
checked = matched_names = 0
for f in sorted(glob.glob(str(RAW / "*fdinspi.csv"))):
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            dg = re.sub(r"\D", "", row[" License Number"])
            if len(lic_by_digits.get(dg, ())) <= 1:
                continue
            checked += 1
            dba = re.sub(r"[^A-Z0-9]", "", row["Business (DBA-Does Business As) Name"].upper())
            # find the output place holding this visit
            vid = row["Inspection Visit ID"].strip()
            holder = None
            for cand in lic_by_digits[dg]:
                p = by_lic.get(cand)
                if p and any(i["vid"] == vid for i in p["insp"]):
                    holder = p
                    break
            if holder is None:
                mismatch_examples.append({"vid": vid, "reason": "visit not found under any candidate"})
                continue
            pname = re.sub(r"[^A-Z0-9]", "", (holder["n"] or "").upper())
            if dba and pname and (dba in pname or pname in dba or dba[:12] == pname[:12]):
                matched_names += 1
            else:
                mismatch_examples.append({"vid": vid, "insp_dba": row["Business (DBA-Does Business As) Name"],
                                          "chosen_place": holder["n"], "chosen_lic": holder["lic"]})
res["ambiguous_join_rows_checked"] = checked
res["ambiguous_join_name_consistent"] = matched_names
res["ambiguous_join_name_mismatch_examples"] = mismatch_examples[:10]

# --- B5: output hygiene — Florida must have NO invented score anywhere ---
bad = [p["id"] for p in places_out if p.get("s") is not None or p.get("score") is not None]
res["places_with_any_score_field"] = len(bad)
res["places_missing_state_or_jurisdiction"] = sum(1 for p in places_out if p.get("st") != "FL" or p.get("jur") != "FL-DBPR")
res["places_with_coordinates"] = sum(1 for p in places_out if p.get("lat") is not None)

print(json.dumps(res, indent=1))
json.dump(res, open(OUT / "qa_crosscheck.json", "w"), indent=1)
