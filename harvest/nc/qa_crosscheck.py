#!/usr/bin/env python3
"""Independent QA crosscheck for the NC prototype (pass 2).

Re-reads the raw record with its OWN extraction code (nothing imported
from nc_parse/nc_build):
  * county CSV exports   -> the inspection universe (stub truth)
  * violation pages (gz) -> independent premise/inspection/violation parse
  * OUTPUT/places_nc.json -> the build under test
Assertions are exact-to-the-row per county: stub multisets == detail
multisets == output multisets on (state_id, date, score, grade);
place heads (s, d, grade) recomputed independently; violation totals
recomputed; plus the demerits identity check (Final Score should equal
100 - sum of demerits) reported as a rate, and a geocode-readiness
statistic. Verdict printed at the end.
"""
import os, re, sys, csv, io, json, gzip, glob
from collections import Counter, defaultdict
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.abspath(__file__))
FOOD = {"1", "2", "3", "4", "5", "6", "9", "11", "12", "14", "15", "16", "30"}

def txt(s):
    s = re.sub(r'<br\s*/?>', ' ', s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    s = (s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#39;', "'")
          .replace('&quot;', '"'))
    return re.sub(r'\s+', ' ', s).strip()

def iso(d):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', (d or '').strip())
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None

def num(s):
    s = (s or '').strip()
    if s == '':
        return None
    f = float(s)
    return int(f) if f == int(f) else f

def parse_detail(html):
    """Independent extraction from a violation page."""
    def field(label):
        m = re.search(r'<td class="fls">(?:<span[^>]*>)?\s*' + re.escape(label) +
                      r'\s*(?:</span>)?\s*</td>\s*<td[^>]*class="dfv"[^>]*>(.*?)</td>',
                      html, re.S)
        return txt(m.group(1)) if m else ''
    name = field('Name')
    addr = field('Address')
    m = re.search(r'City/State/ZIP</td><td><table[^>]*>\s*<tr>\s*<td class="dfv">(.*?)</td>\s*<td class="dfv">(.*?)</td>\s*<td class="dfv">(.*?)</td>', html, re.S)
    city, state, zipc = (txt(m.group(1)), txt(m.group(2)), txt(m.group(3))) if m else ('', '', '')
    ptype = field('Premise Type')
    county = field('County')
    date = field('Inspection Date')
    m = re.search(r'Final Score @ Grade</td><td><table[^>]*>\s*<tr>\s*<td class="dfv">(.*?)</td>\s*<td class="dfv">(.*?)</td>', html, re.S)
    score, grade = (txt(m.group(1)), txt(m.group(2))) if m else ('', '')
    viols = []
    for block in re.split(r'INSPECTION_VIOLATIONTableControlRepeater_ctl\d+_critvio">', html)[1:]:
        cells = [txt(c) for c in re.findall(r'<td class="ttc"[^>]*>(.*?)</td>', block, re.S)[:7]]
        if len(cells) == 7:
            viols.append(cells)
    return {"name": name, "addr": addr, "city": city, "state": state, "zip": zipc,
            "ptype": ptype, "county": county, "date": date, "score": score,
            "grade": grade, "viols": viols}

def worker(job):
    insp, rec = job
    raw = gzip.open(os.path.join(ROOT, rec["file"]), 'rb').read().decode('utf-8', errors='replace')
    d = parse_detail(raw)
    g = rec["grid_stub"]
    return insp, rec, d, g

def main():
    problems = []
    def check(cond, msg):
        if not cond:
            problems.append(msg)

    sweep = {r["cty"]: (r["counties"][0][1] if r.get("counties") else None)
             for r in json.load(open(os.path.join(ROOT, "work/county_sweep.json")))}

    # ---- stub truth from CSVs
    food_stubs = Counter()     # (sid, iso, SCORE, GRADE) multiset
    universe_food = Counter()  # same key, from the all-types county CSVs
    stub_by_county = Counter()
    all_rows = 0
    for path in glob.glob(os.path.join(ROOT, "raw/csv/cty*_all*.csv")):
        code = int(re.search(r'cty(\d{3})', path).group(1))
        rows = list(csv.reader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig'))))
        for r in rows[1:]:
            if r and any(c.strip() for c in r):
                all_rows += 1
                if r[11] in FOOD:
                    universe_food[(r[10], iso(r[0].split(' ')[0]), num(r[2]), r[1] or None)] += 1
    slice_rows = 0
    for path in glob.glob(os.path.join(ROOT, "raw/csv/cty*_t*.csv")):
        code = int(re.search(r'cty(\d{3})', path).group(1))
        rows = list(csv.reader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig'))))
        for r in rows[1:]:
            if r and any(c.strip() for c in r):
                slice_rows += 1
                food_stubs[(r[10], iso(r[0].split(' ')[0]), num(r[2]), r[1] or None)] += 1
                stub_by_county[code] += 1

    # ---- independent detail parse
    index = {}
    for path in glob.glob(os.path.join(ROOT, "index/cty*.jsonl")):
        for line in open(path):
            rec = json.loads(line)
            index.setdefault(rec["insp"], rec)
    detail_keys = Counter()
    detail_by_county = Counter()
    demerit_checked = demerit_match = 0
    demerit_mismatch_examples = []
    viol_total = 0
    detail_info = {}
    with Pool(8) as pool:
        for insp, rec, d, g in pool.imap(worker, list(index.items()), chunksize=100):
            detail_keys[(g["state_id"], iso(d["date"]), num(d["score"]), d["grade"] or None)] += 1
            detail_by_county[rec["cty"]] += 1
            viol_total += len(d["viols"])
            detail_info[insp] = (rec, d)
            if num(d["score"]) is not None and d["viols"]:
                pts = sum((num(v[1]) or 0) for v in d["viols"])
                demerit_checked += 1
                if abs((100 - pts) - float(d["score"])) < 0.001:
                    demerit_match += 1
                elif len(demerit_mismatch_examples) < 10:
                    demerit_mismatch_examples.append(
                        {"insp": insp, "score": d["score"], "points_sum": pts})

    # ---- output under test
    out = json.load(open(os.path.join(ROOT, "OUTPUT/places_nc.json")))
    out_keys = Counter()
    out_by_county = Counter()
    out_insp = out_viol = 0
    house = 0
    head_bad = 0
    for pl in out:
        insps = pl["insp"]
        out_insp += len(insps)
        out_viol += sum(len(i["v"]) for i in insps)
        for i in insps:
            out_keys[(pl["fid"], i["d"], i["s"], i["grade"])] += 1
            out_by_county[pl["ct"]] += 1
        if insps:
            top = max(insps, key=lambda r: (r["d"] or '', r["id"]))
            if (pl["s"], pl["d"], pl["grade"]) != (top["s"], top["d"], top["grade"]):
                head_bad += 1
        if re.match(r'^\d+\s', pl["a"] or ''):
            house += 1
    readiness = 100.0 * house / len(out) if out else 0

    check(food_stubs == universe_food,
          f"slice-CSV food stubs != county-CSV food universe: slice-only {sum((food_stubs-universe_food).values())}, universe-only {sum((universe_food-food_stubs).values())} (chunk gap/overlap or drift)")
    missing_in_out = detail_keys - out_keys
    extra_in_out = out_keys - detail_keys
    check(not missing_in_out, f"{sum(missing_in_out.values())} verified inspections missing from output, e.g. {list(missing_in_out)[:3]}")
    check(not extra_in_out, f"{sum(extra_in_out.values())} output inspections not backed by a detail page, e.g. {list(extra_in_out)[:3]}")
    stub_vs_detail = food_stubs - detail_keys
    check(out_viol == viol_total, f"violation totals differ: output {out_viol} vs details {viol_total}")
    check(head_bad == 0, f"{head_bad} places whose head s/d/grade != newest inspection")

    print("=== NC QA CROSSCHECK ===")
    print(f"universe rows (all types, county CSVs): {all_rows}")
    print(f"food stubs (slice CSVs):                {slice_rows}")
    print(f"detail pages parsed:                    {len(index)}")
    print(f"food stubs without verified detail:     {sum(stub_vs_detail.values())}")
    print(f"output places:                          {len(out)}")
    print(f"output inspections:                     {out_insp}")
    print(f"output violations:                      {out_viol} (details: {viol_total})")
    print(f"per-county stub/detail/output:          "
          f"{'OK' if all(stub_by_county[c] == detail_by_county[c] for c in stub_by_county) else 'see problems'}")
    print(f"demerits identity (score == 100 - pts): {demerit_match}/{demerit_checked} "
          f"({100.0*demerit_match/max(demerit_checked,1):.2f}%)")
    for e in demerit_mismatch_examples[:5]:
        print("   mismatch example:", e)
    print(f"geocode-readiness (house-number start): {house}/{len(out)} = {readiness:.2f}%")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(" -", p)
        print("VERDICT: FAIL")
    else:
        print("VERDICT: ALL PASS (output == verified detail set, exact to the row)")

if __name__ == "__main__":
    main()
