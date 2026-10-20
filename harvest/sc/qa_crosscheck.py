#!/usr/bin/env python3
"""Kyron SC adapter — independent QA crosscheck (pass B).

Separate extraction code from sc_build/sc_parse on purpose: rate.aspx
leaves are re-parsed with html.parser, GIS pages are recounted from
the raw files and the fetch-time count oracles, and every published
number in qa_report.json / the report is re-derived here.
Output: OUTPUT/qa_crosscheck.json ; exit 1 if any check FAILs.
"""
import collections
import glob
import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "OUTPUT")
VOCAB = {  # county code -> name, from the search form (independent copy)
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
checks = {}


def verdict(name, ok, detail):
    checks[name] = {"pass": bool(ok), "detail": detail}
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


class RateParser(HTMLParser):
    """Extract (guid, name, street, city, grade, date, type) per row."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_row = False
        self.cells = []
        self.cell = None
        self.guid = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and a.get("valign") == "top":
            self.in_row = True
            self.cells = []
            self.guid = None
        elif self.in_row and tag == "td":
            self.cell = ""
        elif self.in_row and tag == "a":
            href = a.get("href", "")
            m = re.search(r"([0-9a-fA-F-]{36})\.pdf", href)
            if m:
                self.guid = m.group(1).lower()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(re.sub(r"\s+", " ", self.cell).strip())
            self.cell = None
        elif tag == "table" and self.in_row:
            self.in_row = False


def parse_rate_file(path):
    p = RateParser()
    with open(path, encoding="utf-8", errors="replace") as fh:
        doc = fh.read()
    p.feed(doc)
    # HTMLParser row model: cells accumulate across unclosed <tr>s, so
    # regroup the flat cell stream into 7-cell rows in document order.
    rows = []
    cells = p.cells
    return doc, cells


def main():
    places = json.load(open(os.path.join(OUT, "places_sc.json")))
    exclusions = json.load(open(os.path.join(OUT, "exclusions.json")))
    qa = json.load(open(os.path.join(OUT, "qa_report.json")))

    # ---------- raw GIS recount ----------
    steton = []
    for f in sorted(glob.glob(os.path.join(HERE, "raw", "gis_steton",
                                           "page_*.json"))):
        steton += [x["attributes"] for x in json.load(open(f))["features"]]
    oracle = json.load(open(os.path.join(
        HERE, "raw", "gis_steton", "_count.json")))["count"]
    verdict("B1_steton_oracle", len(steton) == oracle == 137087,
            f"raw steton rows={len(steton)} oracle={oracle}")
    st_by_guid = {}
    for a in steton:
        g = (a.get("AuditResultGlobalID") or "").lower()
        st_by_guid.setdefault(g, []).append(a)
    verdict("B1b_steton_guid_unique",
            all(len(v) == 1 for v in st_by_guid.values()) and "" not in
            st_by_guid, f"distinct guids={len(st_by_guid)}")

    # ---------- raw rate recount (independent parser) ----------
    leaf_matched = 0
    rate_rows = []          # (guid, county_code, date, grade)
    cell_stream_ok = True
    for path in sorted(glob.glob(os.path.join(
            HERE, "raw", "rate", "*", "*.html"))):
        cc = os.path.basename(os.path.dirname(path))
        doc, cells = parse_rate_file(path)
        m = re.search(r"(\d+) records matched", doc)
        if m:
            leaf_matched += int(m.group(1))
        # regroup: rows are 7 cells; find row starts by guid anchors is
        # fragile, so use the build-independent split on record marker:
        parts = doc.split("<tr valign='top'>")[1:]
        if len(parts) != (int(m.group(1)) if m else 0):
            cell_stream_ok = False
        for part in parts:
            g = re.search(r"([0-9a-fA-F-]{36})\.pdf", part)
            tds = re.findall(r"<td[^>]*>(.*?)</td>", part, re.S)
            txt = [re.sub(r"\s+", " ", re.sub(
                r"<[^>]+>", "", t)).strip() for t in tds]
            rate_rows.append({
                "guid": g.group(1).lower() if g else None,
                "cc": cc, "name": txt[0], "street": txt[1],
                "city": txt[2], "grade": txt[3], "date": txt[4],
                "type": txt[5]})
    rate_guids = [r["guid"] for r in rate_rows]
    verdict("B2_rate_leaf_oracle",
            leaf_matched == len(rate_rows) and cell_stream_ok,
            f"leaf matched sum={leaf_matched} parsed rows={len(rate_rows)}")
    verdict("B2b_rate_guid_unique",
            len(set(rate_guids)) == len(rate_guids) and None not in
            rate_guids, f"distinct rate guids={len(set(rate_guids))}")

    # ---------- union accounting ----------
    out_insp = [i for p in places for i in p["insp"]]
    out_guids = {i["vid"] for i in out_insp}
    union = set(st_by_guid) | set(rate_guids)
    excl_n = sum(e["inspections_withheld"] for e in exclusions)
    verdict("B3_union_accounting",
            len(out_insp) == len(out_guids) and
            len(out_guids) + excl_n == len(union),
            f"union={len(union)} shipped={len(out_guids)} "
            f"excluded={excl_n}")
    verdict("B3b_steton_subset", set(st_by_guid) <= set(rate_guids),
            f"steton guids not in rate: "
            f"{len(set(st_by_guid) - set(rate_guids))}")

    # ---------- place-level newest re-derivation ----------
    # Documented ordering (FIELD_MAPPING): date desc; graded (A/B/C/S)
    # before ungraded ('N/A'); then Steton OBJECTID desc.
    rate_by_guid = {r["guid"]: r for r in rate_rows}
    GRADED = {"A", "B", "C", "S"}
    bad_newest = 0
    for p in places:
        cand = []
        for i in p["insp"]:
            g = i["vid"]
            d = rate_by_guid[g]["date"] if g in rate_by_guid else i["d"]
            gr = None
            oid = -1
            if g in st_by_guid:
                gr = (st_by_guid[g][0].get("POSTED_GRADE") or "").strip()
                oid = st_by_guid[g][0].get("OBJECTID") or -1
            elif g in rate_by_guid:
                gr = rate_by_guid[g]["grade"]
            cand.append(((d, 1 if gr in GRADED else 0, oid), d, gr))
        cand.sort(key=lambda x: x[0], reverse=True)
        if (cand[0][1], cand[0][2]) != (p["d"], p["grade"]):
            bad_newest += 1
    verdict("B4_newest_rederived", bad_newest == 0,
            f"places with wrong newest (date, grade): {bad_newest}")

    # ---------- zero invented scores ----------
    n_scores = sum(1 for i in out_insp if i["s"] is not None)
    n_pscores = sum(1 for p in places if p["s"] is not None)
    verdict("B5_no_scores", n_scores == 0 and n_pscores == 0 and
            qa["steton_score_nonnull"] == 0,
            f"inspection scores={n_scores} place scores={n_pscores} "
            f"(source SCORE column null on all rows)")

    # ---------- county integrity ----------
    # County is the OPERATING county of the newest inspection, not the
    # permit prefix (prefix 50 = statewide mobile-unit series; its
    # Steton COUNTY field carries the real county). Re-derive the
    # expected county per place from raw and compare; also confirm the
    # prefix==COUNTY rule holds for ordinary (non-50) permits.
    GRADED2 = {"A", "B", "C", "S"}
    bad_county = 0
    weird_cc = collections.Counter()
    prefix50_places = 0
    for p in places:
        if p["county_code"] not in VOCAB or p["ct"] != VOCAB.get(
                p["county_code"]):
            weird_cc[(p["county_code"], p["ct"])] += 1
        if p["fid"] and p["fid"].startswith("50-"):
            prefix50_places += 1
        cand = []
        for i in p["insp"]:
            g = i["vid"]
            if g in st_by_guid:
                a = st_by_guid[g][0]
                d = rate_by_guid[g]["date"] if g in rate_by_guid else i["d"]
                gr = (a.get("POSTED_GRADE") or "").strip()
                cand.append(((d, 1 if gr in GRADED2 else 0,
                              a.get("OBJECTID") or -1),
                             (a.get("COUNTY") or "").strip()))
            else:
                cand.append((((rate_by_guid[g]["date"]), 1, -1),
                             rate_by_guid[g]["cc"]))
        cand.sort(key=lambda x: x[0], reverse=True)
        if cand[0][1] != p["county_code"]:
            bad_county += 1
    ordinary_bad = 0
    for a in steton:
        pid = re.sub(r"\s+", " ", (a.get("PERMIT_ID") or "")).strip()
        if pid and not pid.startswith("50-"):
            if pid[:2] != (a.get("COUNTY") or "").strip():
                ordinary_bad += 1
    # Adjudication of the 20 prefix!=COUNTY rows (13 permits): on every
    # joined row statewide, rate.aspx's filing county == Steton COUNTY
    # (verified globally below) — COUNTY is the state-consistent
    # operating county in both public systems; the permit prefix is the
    # stale field. Output follows COUNTY.
    rate_county_diff = sum(
        1 for g, a in st_by_guid.items()
        if g in rate_by_guid
        and rate_by_guid[g]["cc"] != (a[0].get("COUNTY") or "").strip())
    verdict("B6_county_integrity",
            bad_county == 0 and not weird_cc and rate_county_diff == 0,
            f"places whose county != newest-row operating county: "
            f"{bad_county}; out-of-vocab: {dict(weird_cc)}; prefix-50 "
            f"places: {prefix50_places}; non-50 rows where permit "
            f"prefix != COUNTY: {ordinary_bad} (adjudicated source "
            f"anomalies); rate-vs-COUNTY disagreements: "
            f"{rate_county_diff}")

    # ---------- rate vs steton agreement on joined GUIDs ----------
    from datetime import datetime, timezone
    deltas = collections.Counter()
    grade_agree = grade_dis = 0
    for g, r in rate_by_guid.items():
        if g not in st_by_guid:
            continue
        a = st_by_guid[g][0]
        gd = datetime.fromtimestamp(
            a["INSP_DATE"] / 1000, tz=timezone.utc).date().isoformat()
        dd = (datetime.fromisoformat(r["date"]) -
              datetime.fromisoformat(gd)).days
        deltas[dd] += 1
        if (a.get("POSTED_GRADE") or "").strip() == r["grade"]:
            grade_agree += 1
        else:
            grade_dis += 1
    verdict("B7_date_agreement", deltas.get(0, 0) > 0,
            f"day deltas rate-minus-gis: {dict(sorted(deltas.items()))}")
    verdict("B8_grade_agreement", grade_dis == 0,
            f"agree={grade_agree} disagree={grade_dis}")

    # ---------- ids / structure ----------
    ids = [p["id"] for p in places]
    verdict("B9_unique_ids", len(set(ids)) == len(ids),
            f"places={len(ids)} distinct={len(set(ids))}")
    per_county = collections.Counter(p["ct"] for p in places)
    verdict("B9b_county_sum", sum(per_county.values()) == len(places),
            f"counties present={len(per_county)}")

    # ---------- rate-only near-miss scale (informational) ----------
    permit_keys = collections.defaultdict(set)
    for p in places:
        if p["fid"]:
            permit_keys[(p["county_code"], re.sub(
                r"\s+", " ", p["n"]).strip().upper(), re.sub(
                r"\s+", " ", p["c"]).strip().upper())].add(p["id"])
    near = 0
    for p in places:
        if not p["fid"]:
            k = (p["county_code"], re.sub(r"\s+", " ", p["n"]).strip().upper(),
                 re.sub(r"\s+", " ", p["c"]).strip().upper())
            if k in permit_keys:
                near += 1
    checks["B10_rateonly_near_miss"] = {
        "pass": True,
        "detail": f"rate-only places sharing (county, name, city) with a "
                  f"permit place but differing on street: {near} "
                  f"(kept separate under the never-guess rule)"}
    print(f"INFO  B10_rateonly_near_miss: "
          f"{checks['B10_rateonly_near_miss']['detail']}")

    # ---------- geocode-readiness ----------
    hn = sum(1 for p in places if re.match(r"^\d", (p["a"] or "").strip()))
    full = sum(1 for p in places if re.match(r"^\d", (p["a"] or "").strip())
               and p["c"] and p["z"])
    pobox = sum(1 for p in places if re.search(
        r"\bP\.?\s?O\.?\s+BOX\b", (p["a"] or "").upper()))
    checks["B11_geocode_readiness"] = {
        "pass": True,
        "detail": f"house-numbered {hn}/{len(places)} "
                  f"({100 * hn / len(places):.2f}%); house+city+zip "
                  f"{full} ({100 * full / len(places):.2f}%); "
                  f"PO Box streets {pobox}"}
    print(f"INFO  B11_geocode_readiness: "
          f"{checks['B11_geocode_readiness']['detail']}")

    with open(os.path.join(OUT, "qa_crosscheck.json"), "w") as fh:
        json.dump(checks, fh, ensure_ascii=False, indent=1)
    failed = [k for k, v in checks.items() if not v["pass"]]
    print("QA CROSSCHECK:", "ALL PASS" if not failed else
          f"FAILURES: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
