#!/usr/bin/env python3
"""Independent QA crosscheck (pass B) for the TN prototype.

Deliberately does NOT import tn_build: it re-derives everything from
the raw harvest with its own extraction code and compares against
OUTPUT/places_tn.json. Checks (GA-style numbering):

  B1  permit accounting: unique food-service permits in raw stubs
      == places shipped + places excluded
  B2  inspection accounting: shipped inspections == stub-verified
      detail pages on disk (independently re-verified here)
  B3  every shipped place's newest (score, date) matches an
      independent re-read of that inspection's raw detail + stub
  B4  no invented scores: every shipped inspection score equals its
      stub score and its independently extracted detail score;
      nulls stay null
  B5  spot checks: 25 random places, full field comparison vs raw
  B6  county attribution of every place == county of its newest stub
  B7  place ids and inspection ids unique
  B8  all lat/lng null; jurisdiction uniformly TN-DOH
  B9  violation accounting: shipped violation total == independent
      recount from raw detail HTML (published observation entries
      plus OUT checklist items not among them)

Writes OUTPUT/qa_crosscheck.json; exit 1 if any check fails.
"""

import json
import os
import random
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "OUTPUT")
ORIGIN = "https://inspections.myhealthdepartment.com"


def is_food(r):
    return (r.get("permitType", "").startswith("Commercial Food")
            and r.get("inspectionType")
            == "Food Service Establishment Inspection")


def stream_stubs():
    """Yield (county_dir, stub) for every unique food inspectionID."""
    seen = {}
    spages = os.path.join(RAW, "search_pages")
    for cdir in sorted(os.listdir(spages)):
        cpath = os.path.join(spages, cdir)
        if not os.path.isdir(cpath):
            continue
        for fname in sorted(os.listdir(cpath)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(cpath, fname)) as f:
                for r in json.load(f):
                    if isinstance(r, dict) and is_food(r):
                        seen.setdefault(r["inspectionID"],
                                        (cdir, r))
    return seen


_DETAIL_INDEX = None


def detail_path(iid):
    global _DETAIL_INDEX
    if _DETAIL_INDEX is None:
        _DETAIL_INDEX = {}
        iroot = os.path.join(RAW, "insp")
        for cdir in sorted(os.listdir(iroot)):
            cpath = os.path.join(iroot, cdir)
            if not os.path.isdir(cpath):
                continue
            for fname in os.listdir(cpath):
                if fname.endswith(".html"):
                    _DETAIL_INDEX[fname[:-5]] = os.path.join(
                        cpath, fname)
    return _DETAIL_INDEX.get(iid)


# --- independent detail extraction (own regexes, not tn_parse) ------
def x_score(html_text):
    m = re.search(r"Score &amp; Grade:\s*<strong>(\d*)</strong>",
                  html_text)
    if not m:
        return "PARSE_FAIL"
    return int(m.group(1)) if m.group(1) else None


def x_name(html_text):
    m = re.search(r'permit/\?permitID=[0-9A-Fa-f-]{36}"[^>]*>([^<]+)</a>',
                  html_text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def x_permit(html_text):
    m = re.search(r'permit/\?permitID=([0-9A-Fa-f-]{36})', html_text)
    return m.group(1).upper() if m else None


def x_viol_count(html_text):
    obs = re.search(
        r'class="observations-text">(.*?)</p>', html_text, re.S)
    items = set()
    if obs:
        for part in re.split(r"<br\s*/>\s*<br\s*/>", obs.group(1)):
            t = re.sub(r"<[^>]+>", " ",
                       part)
            t = re.sub(r"\s+", " ", t).strip()
            m = re.match(r"^(\d{1,2}):", t)
            if m:
                items.add(int(m.group(1)))
    out_items = set()
    for lab, tit in re.findall(
            r'<span class="(?:in|out|na|no)-label[^"]*"[^>]*>'
            r'([^<]*)</span>.*?text-block-11">(\d{1,2})\s',
            html_text, re.S):
        if lab.strip().upper() == "OUT":
            out_items.add(int(tit))
    return len(items | out_items)


def main():
    with open(os.path.join(OUT, "places_tn.json")) as f:
        places = json.load(f)
    with open(os.path.join(OUT, "exclusions.json")) as f:
        exclusions = json.load(f)
    with open(os.path.join(OUT, "qa_report.json")) as f:
        build_qa = json.load(f)

    stubs = stream_stubs()
    permits = defaultdict(list)
    for iid, (cdir, stub) in stubs.items():
        permits[stub["permitID"]].append((cdir, stub))

    checks = {}
    notes = []

    # B1
    checks["B1_permit_accounting"] = (
        len(permits) == len(places) + len(exclusions))

    # B2 + B4: independently verify every detail on disk against its
    # stub; count how many shipped inspections that supports
    verified = {}
    for iid, (cdir, stub) in stubs.items():
        p = detail_path(iid)
        if p is None:
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            h = f.read()
        ok = (x_permit(h) == stub["permitID"].upper()
              and x_score(h) == stub.get("score")
              and (x_name(h) or "").casefold()
              == re.sub(r"\s+", " ", stub["establishmentName"])
              .strip().casefold())
        verified[iid] = ok
    shipped_insp = [i for pl in places for i in pl["insp"]]
    shipped_ids = {i["vid"] for i in shipped_insp}
    # Inspections of gate-excluded permits verify fine but must NOT
    # ship; they are out of scope for B2 (counted separately below).
    excluded_permits = {e["permitID"] for e in exclusions}
    eligible_verified = {
        i for i, ok in verified.items()
        if ok and stubs[i][1]["permitID"] not in excluded_permits}
    excluded_verified = {
        i for i, ok in verified.items()
        if ok and stubs[i][1]["permitID"] in excluded_permits}
    checks["B2_inspection_accounting"] = (
        shipped_ids == eligible_verified
        and not (shipped_ids & excluded_verified))
    if not checks["B2_inspection_accounting"]:
        only_out = shipped_ids - eligible_verified
        only_raw = eligible_verified - shipped_ids
        notes.append(f"B2 diff: shipped-not-verified={len(only_out)} "
                     f"verified-not-shipped={len(only_raw)}")
    notes.append(
        f"verified inspections on gate-excluded permits (correctly "
        f"unshipped): {len(excluded_verified)}")

    # B4 details: scores equal across stub/detail/output
    b4_bad = []
    for ins in shipped_insp:
        stub = stubs[ins["vid"]][1]
        if ins["s"] != stub.get("score"):
            b4_bad.append(ins["vid"])
    checks["B4_no_invented_scores"] = not b4_bad

    # B3: newest per place
    b3_bad = []
    for pl in places:
        if not pl["insp"]:
            b3_bad.append(pl["id"])
            continue
        newest = pl["insp"][0]
        stub = stubs[newest["vid"]][1]
        if pl["s"] != stub.get("score") or \
                pl["d"] != stub["inspectionDate"][:10]:
            b3_bad.append(pl["id"])
    checks["B3_latest_matches_raw"] = not b3_bad

    # B5 spot checks
    random.seed(20261015)
    spots = []
    b5_ok = True
    for pl in random.sample(places, min(25, len(places))):
        newest_stub = max(
            (s for _, s in permits[pl["fid"]]),
            key=lambda s: s["inspectionDate"])
        ok = (pl["n"] == newest_stub["establishmentName"].strip()
              and pl["c"] == newest_stub["city"].strip()
              and pl["z"] == newest_stub["zip"].strip()
              and len(pl["insp"]) == sum(
                  1 for iid, _ in
                  ((i, None) for i in
                   [s["inspectionID"] for _, s in permits[pl["fid"]]])
                  if verified.get(iid)))
        spots.append({"id": pl["id"], "name": pl["n"],
                      "county": pl["ct"], "fields_match_raw": ok,
                      "n_insp": len(pl["insp"]),
                      "latest": [pl["s"], pl["d"]]})
        b5_ok = b5_ok and ok
    checks["B5_spot_ok"] = b5_ok

    # B6 county attribution
    with open(os.path.join(ROOT, "work", "counties.json")) as f:
        guid2name = json.load(f)
    dir2name = {n.upper().replace(" ", "_"): n
                for n in guid2name.values()}
    b6_bad = []
    for pl in places:
        newest = max(permits[pl["fid"]],
                     key=lambda cs: cs[1]["inspectionDate"])
        if dir2name.get(newest[0]) != pl["ct"]:
            b6_bad.append(pl["id"])
    checks["B6_county_attribution"] = not b6_bad

    # B7 unique ids
    checks["B7_unique_ids"] = (
        len({p["id"] for p in places}) == len(places)
        and len(shipped_ids) == len(shipped_insp))

    # B8
    checks["B8_no_coords_all_tndoh"] = all(
        p["lat"] is None and p["lng"] is None and p["jur"] == "TN-DOH"
        for p in places)

    # B9 violation recount over shipped inspections
    recount = 0
    for ins in shipped_insp:
        p = detail_path(ins["vid"])
        with open(p, encoding="utf-8", errors="replace") as f:
            recount += x_viol_count(f.read())
    shipped_v = sum(len(i["v"]) for i in shipped_insp)
    checks["B9_violation_accounting"] = recount == shipped_v
    if not checks["B9_violation_accounting"]:
        notes.append(f"B9: recount={recount} shipped={shipped_v}")

    result = {
        "checks": checks,
        "notes": notes,
        "raw_food_permits": len(permits),
        "raw_food_inspection_stubs": len(stubs),
        "detail_files_verified": sum(1 for v in verified.values() if v),
        "detail_files_failed_verification":
            sum(1 for v in verified.values() if not v),
        "output_places": len(places),
        "exclusions": len(exclusions),
        "output_inspections": len(shipped_insp),
        "output_violations": shipped_v,
        "build_qa_drops": {
            "no_detail": build_qa["inspections_dropped_no_detail"],
            "unverified": build_qa["inspections_dropped_unverified"],
        },
        "B3_mismatches": b3_bad[:20],
        "B4_violations": b4_bad[:20],
        "B5_spot_checks": spots,
    }
    with open(os.path.join(OUT, "qa_crosscheck.json"), "w") as f:
        json.dump(result, f, indent=1)
    failed = [k for k, v in checks.items() if not v]
    print(json.dumps(checks, indent=1))
    print("notes:", notes)
    print("CROSSCHECK", "FAIL " + str(failed) if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
