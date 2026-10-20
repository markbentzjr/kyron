#!/usr/bin/env python3
"""NC mopup: close the gap between slice-CSV food stubs and verified
detail pages, sequentially (TN discipline).

Two failure classes are handled:
  A. Verification problems (from OUTPUT/qa_report.json): the violation
     page is re-fetched by direct GET of its URL and overwritten.
  B. Missing stubs: for each affected (county, type) slice the grid is
     re-run and ONLY the rows whose stub key is still missing get a
     Violation Details postback, appended to the county index.
Run after a build; then re-run nc_build.py and qa_crosscheck.py.
"""
import os, re, sys, csv, io, json, gzip
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import nc_fetch as F  # noqa: E402
from nc_fetch import Cdpehs, items_count, parse_grid_rows, apply_filters  # noqa: E402
from nc_parse import date_iso  # noqa: E402
import requests  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))

def norm(s):
    return re.sub(r'\s+', ' ', (s or '').upper()).strip().rstrip(',').strip()

def skey(state_id, date, name):
    return (state_id, date_iso(date) or date, norm(name))

def main():
    # current verified state: index keys
    index_keys = Counter()
    index = {}
    for path in sorted(os.listdir(os.path.join(ROOT, "index"))):
        if not path.endswith(".jsonl"):
            continue
        for line in open(os.path.join(ROOT, "index", path)):
            rec = json.loads(line)
            index[rec["insp"]] = rec
    qa = json.load(open(os.path.join(ROOT, "OUTPUT/qa_report.json")))
    problems = qa.get("problems_sample", [])
    # NOTE: build stores only a sample; recompute problem insp ids by
    # re-deriving stub mismatch is overkill - instead treat ALL index
    # records whose stub key is not matched by a slice CSV as suspects
    # is wrong too. Mopup A uses the problems list persisted by build:
    prob_path = os.path.join(ROOT, "OUTPUT/problems.json")
    if os.path.exists(prob_path):
        problems = json.load(open(prob_path))

    # ---- A: sequential direct re-GET of problem pages
    s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0"})
    fixed_a = 0
    for pr in problems:
        rec = index.get(pr["insp"])
        if not rec:
            continue
        try:
            r = s.get(rec["url"], timeout=120)
            if r.status_code == 200 and b"Premises Information" in r.content:
                F.save_gz(rec["file"], r.content)
                F.log_fetch(rec["file"], rec["url"] + " [mopup A]", 200, r.content)
                fixed_a += 1
        except Exception as e:
            print("mopup A fail", pr["insp"], e, flush=True)
    print(f"mopup A: re-fetched {fixed_a}/{len(problems)} problem pages", flush=True)

    # ---- B: missing stubs per (county, type)
    # harvested stub keys (from index grid stubs)
    have = Counter()
    for rec in index.values():
        g = rec["grid_stub"]
        have[skey(g["state_id"], g["date"], g["name"])] += 1
    # problem inspections count as NOT verified: subtract them
    for pr in problems:
        rec = index.get(pr["insp"])
        if rec:
            g = rec["grid_stub"]
            have[skey(g["state_id"], g["date"], g["name"])] -= 1
    want = Counter()
    for fn in sorted(os.listdir(os.path.join(ROOT, "raw/csv"))):
        if "_t" not in fn:
            continue
        rows = list(csv.reader(io.StringIO(
            open(os.path.join(ROOT, "raw/csv", fn), 'rb').read().decode('utf-8-sig'))))
        for r in rows[1:]:
            if r and any(c.strip() for c in r):
                want[skey(r[10], r[0].split(" ")[0], r[4])] += 1
    missing = want - have
    print(f"mopup B: {sum(missing.values())} missing inspection stubs", flush=True)
    groups = defaultdict(list)
    for (sid, diso, nname), n in missing.items():
        code = int(sid[1:4]); typ = str(int(sid[4:6]))
        groups[(code, typ)].append(((sid, diso, nname), n))
    for (code, typ), keys in sorted(groups.items()):
        need = Counter(dict(keys))
        client = Cdpehs()
        url, html = client.get_county(code)
        filtered = apply_filters(client, url, html, type_id=typ)
        ic = items_count(filtered)
        grid = client.postback(
            url, filtered, target="ctl00$PageContent$Pagination$_PageSizeButton",
            overrides={"ctl00$PageContent$Pagination$_PageSize": "500",
                       "ctl00$PageContent$Pagination$_CurrentPage": "1"}).text
        total = ic[1] if ic else 0
        npages = (total + 499) // 500
        got = 0
        for page in range(1, npages + 1):
            for row in parse_grid_rows(grid):
                if "parse_error" in row:
                    continue
                k = skey(row["state_id"], row["date"], row["name"])
                if need.get(k, 0) <= 0:
                    continue
                target = (f"ctl00$PageContent$VW_PUBLIC_ESTINSPTableControlRepeater"
                          f"${row['ctl']}$ViolationDetails")
                try:
                    r = client.postback(url, grid, target=target)
                except Exception as e:
                    print("  mopup B postback fail", code, typ, k, e, flush=True)
                    continue
                m = re.search(r'ESTABLISHMENT=(\d+)&INSPECTION=(\d+)', r.url)
                if not m:
                    continue
                estab, insp = m.group(1), m.group(2)
                vrel = F.save_gz(f"raw/viol/cty{code:03d}/{insp}.html.gz", r.content)
                F.log_fetch(vrel, r.url + " [mopup B]", r.status_code, r.content)
                rec = {"cty": code, "county": "", "type": typ, "chunk": [None, None],
                       "estab": estab, "insp": insp, "url": r.url, "file": vrel,
                       "grid_stub": {kk: row[kk] for kk in
                                     ("date", "name", "address", "state_id",
                                      "type_label", "score", "grade", "inspector")}}
                with open(os.path.join(ROOT, "index", f"cty{code:03d}.jsonl"), "a") as f:
                    f.write(json.dumps(rec) + "\n")
                need[k] -= 1
                got += 1
            if page < npages:
                grid = client.postback(url, grid,
                                       target="ctl00$PageContent$Pagination$_NextPage").text
        left = sum(need.values())
        print(f"  cty {code} type {typ}: fetched {got}, still missing {left}", flush=True)

if __name__ == "__main__":
    main()
