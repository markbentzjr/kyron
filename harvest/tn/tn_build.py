#!/usr/bin/env python3
"""Tennessee normalizer — Kyron TN adapter prototype v0.1.

Reads the raw harvest (search stubs + verified inspection detail
pages) and writes the GA-mirrored OUTPUT set:

  OUTPUT/places_tn.json   compact-key place dicts (see FIELD_MAPPING.md)
  OUTPUT/manifest.json    coverage + totals
  OUTPUT/exclusions.json  places withheld by the Workstream B gate
                          rules (blank name/street, placeholder name)
  OUTPUT/qa_report.json   build-side accounting

Discipline inherited from FL/GA:
  * native scores verbatim (TN 0-100 stays 0-100); TN publishes no
    letter grade -> grade is null, never derived;
  * an inspection is emitted ONLY when its detail page was fetched
    and stub-verified (permitID, name, date, score all agree) — the
    GA crossed-payload lesson; stub-only inspections are counted in
    qa_report.json, never silently shipped;
  * violations are the detail page's published "Observations &
    Corrective Actions" entries unioned with the checklist's OUT
    items — item numbers published by the portal, narrative text kept
    where the portal prints it (it is blank on many follow-ups);
  * places failing the gate classes are excluded and logged, never
    repaired by hand.
"""

import base64
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tn_parse import parse_detail  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "OUTPUT")
ORIGIN = "https://inspections.myhealthdepartment.com"

PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'total',
    'subtotal', 'establishment', 'facility', 'facility name',
    'food service', 'name', 'business name', 'unnamed', 'test',
    'restaurant', 'the', '-', '--', 'see remarks',
    'county health department', 'health department',
}

FOOD_TYPES = ("Commercial Food",)


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm_name(s):
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def is_food_stub(r):
    return (r.get("permitType", "").startswith(FOOD_TYPES)
            and r.get("inspectionType")
            == "Food Service Establishment Inspection")


def load_stubs():
    """(stubs_by_inspection, stubs_by_permit, stats). County of a stub
    = the county whose search returned it (dir name)."""
    by_insp = {}
    conflicts = []
    per_county_rows = Counter()
    total_rows = 0
    spages = os.path.join(RAW, "search_pages")
    for cdir in sorted(os.listdir(spages)):
        cpath = os.path.join(spages, cdir)
        if not os.path.isdir(cpath):
            continue
        for fname in sorted(os.listdir(cpath)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(cpath, fname)) as f:
                rows = json.load(f)
            for r in rows:
                if not isinstance(r, dict) or "inspectionID" not in r:
                    continue
                total_rows += 1
                if not is_food_stub(r):
                    continue
                per_county_rows[cdir] += 1
                iid = r["inspectionID"]
                if iid in by_insp:
                    prev = by_insp[iid]["stub"]
                    if prev != r:
                        conflicts.append(iid)
                    continue
                by_insp[iid] = {"stub": r, "county_dir": cdir}
    by_permit = defaultdict(list)
    for iid, rec in by_insp.items():
        by_permit[rec["stub"]["permitID"]].append(iid)
    stats = {"search_rows_total": total_rows,
             "food_stubs_unique": len(by_insp),
             "food_permits_unique": len(by_permit),
             "stub_conflicts": sorted(set(conflicts)),
             "food_stub_rows_by_county": dict(per_county_rows)}
    return by_insp, by_permit, stats


def detail_index():
    idx = {}
    iroot = os.path.join(RAW, "insp")
    if os.path.isdir(iroot):
        for cdir in sorted(os.listdir(iroot)):
            cpath = os.path.join(iroot, cdir)
            if not os.path.isdir(cpath):
                continue
            for fname in sorted(os.listdir(cpath)):
                if fname.endswith(".html"):
                    idx[fname[:-5]] = os.path.join(cpath, fname)
    return idx


def verify(stub, parsed):
    probs = []
    if parsed["permitID"] != stub["permitID"].upper():
        probs.append("permitID")
    if norm_name(parsed["name"]) != norm_name(
            stub["establishmentName"]):
        probs.append("name")
    if parsed["date"] != stub["inspectionDate"][:10]:
        probs.append("date")
    if parsed["score"] != stub.get("score"):
        probs.append("score")
    if parsed["inspectionID"] != stub["inspectionID"].upper():
        probs.append("inspectionID")
    return probs


def build_violations(parsed):
    """Union of published observation entries and checklist OUT items,
    keyed by item number, in item order."""
    titles = {i["item"]: i["title"] for i in parsed["checklist"]
              if i["item"] is not None}
    statuses = {i["item"]: i["status"] for i in parsed["checklist"]
                if i["item"] is not None}
    vmap = {}
    for e in parsed["observations_entries"]:
        if e["item"] is None:
            vmap.setdefault(("raw", len(vmap)), {
                "item": None, "title": None, "rule": None,
                "notes": e["notes"], "status": None})
            continue
        vmap[e["item"]] = {
            "item": e["item"],
            "title": titles.get(e["item"]),
            "rule": e["rule"],
            "notes": e["notes"],
            "status": statuses.get(e["item"]),
        }
    for item in parsed["out_items"]:
        if item not in vmap:
            vmap[item] = {"item": item, "title": titles.get(item),
                          "rule": None, "notes": None,
                          "status": statuses.get(item, "OUT")}
    return [vmap[k] for k in sorted(
        vmap, key=lambda k: (9999, str(k)) if isinstance(k, tuple)
        else (k, ""))]


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(WORK, "counties.json")) as f:
        guid2name = json.load(f)
    dir2name = {name.upper().replace(" ", "_"): name
                for name in guid2name.values()}

    by_insp, by_permit, stats = load_stubs()
    didx = detail_index()

    places = []
    exclusions = []
    qa = {
        **stats,
        "detail_files": len(didx),
        "inspections_emitted": 0,
        "inspections_dropped_no_detail": 0,
        "inspections_dropped_unverified": 0,
        "dropped_detail_ids": [],
        "unverified": [],
        "violations": 0,
        "violations_with_notes": 0,
        "places_without_any_inspection": 0,
        "cross_county_permits": [],
        "score_null_inspections": 0,
    }

    # county attribution per permit: the county of its newest stub
    permit_counties = {}
    for pid, iids in by_permit.items():
        counties = {by_insp[i]["county_dir"] for i in iids}
        if len(counties) > 1:
            qa["cross_county_permits"].append(
                {"permitID": pid,
                 "counties": sorted(dir2name.get(c, c)
                                    for c in counties)})
        newest = max(iids, key=lambda i: by_insp[i]["stub"]
                     ["inspectionDate"])
        permit_counties[pid] = by_insp[newest]["county_dir"]

    for pid in sorted(by_permit):
        iids = by_permit[pid]
        cdir = permit_counties[pid]
        county = dir2name.get(cdir, cdir.title())
        stubs = sorted((by_insp[i]["stub"] for i in iids),
                       key=lambda s: s["inspectionDate"],
                       reverse=True)
        newest_stub = stubs[0]

        insp_out = []
        for stub in stubs:
            iid = stub["inspectionID"]
            path = didx.get(iid)
            if path is None:
                qa["inspections_dropped_no_detail"] += 1
                qa["dropped_detail_ids"].append(iid)
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                try:
                    parsed = parse_detail(f.read())
                    probs = verify(stub, parsed)
                except Exception as e:  # noqa: BLE001 - hollow pages
                    parsed, probs = None, [f"parse error: {e}"]
            if probs:
                qa["inspections_dropped_unverified"] += 1
                qa["unverified"].append(
                    {"inspectionID": iid, "problems": probs})
                continue
            v = build_violations(parsed)
            qa["violations"] += len(v)
            qa["violations_with_notes"] += sum(
                1 for x in v if x["notes"])
            if stub.get("score") is None:
                qa["score_null_inspections"] += 1
            d_iso = stub["inspectionDate"][:10]
            insp_out.append({
                "id": f"tndh_insp_{iid}",
                "vid": iid,
                "d": d_iso,
                "draw": parsed["date_written"],
                "t": stub.get("purpose") or parsed["purpose"],
                "s": stub.get("score"),
                "grade": None,
                "inspector": None,
                "comments": parsed["comments"],
                "v": v,
                "du": (ORIGIN + "/tennessee/inspection/"
                       f"?inspectionID={iid}"),
            })
        qa["inspections_emitted"] += len(insp_out)

        name = (newest_stub.get("establishmentName") or "").strip()
        street_parts = [newest_stub.get("addressLine1") or ""]
        if (newest_stub.get("addressLine2") or "").strip():
            street_parts.append(newest_stub["addressLine2"].strip())
        street = ", ".join(p.strip() for p in street_parts if p.strip())

        # gate-class exclusions (Workstream B rules, applied at the
        # normalizer like GA did)
        reason = None
        if not name:
            reason = ("G1-class: portal publishes a blank establishment "
                      "name for this permit; excluded rather than "
                      "shipped.")
        elif name.casefold() in PLACEHOLDER_NAMES or \
                name.rstrip().endswith("#"):
            reason = ("G4-class: portal publishes the placeholder name "
                      f"{name!r} for this permit; excluded rather "
                      "than shipped.")
        elif not street:
            reason = ("G2-class: portal publishes no street address "
                      "for this permit; excluded rather than shipped.")
        elif not insp_out:
            reason = ("no stub-verified inspection detail available "
                      "for any inspection of this permit; excluded "
                      "rather than shipping unverified rows.")
            qa["places_without_any_inspection"] += 1
        if reason:
            exclusions.append({
                "permitID": pid,
                "county": county,
                "name": name or None,
                "reason": reason,
            })
            continue

        newest_insp = insp_out[0]
        places.append({
            "id": f"tndh_{pid}",
            "fid": pid,
            "fid_b64": base64.b64encode(pid.encode()).decode(),
            "n": name,
            "a": street,
            "c": (newest_stub.get("city") or "").strip(),
            "z": (newest_stub.get("zip") or "").strip(),
            "addr_state": (newest_stub.get("state") or "TN").strip(),
            "ct": county,
            "ct_raw": county.upper(),
            "search_county": cdir,
            "st": "TN",
            "jur": "TN-DOH",
            "src": "TN-DOH",
            "phone": None,
            "permit": None,
            "ptype": newest_stub.get("permitType"),
            "eh_phone": None,
            "lat": None,
            "lng": None,
            "s": newest_insp["s"],
            "d": newest_insp["d"],
            "grade": None,
            "du": newest_insp["du"],
            "origin": "portal",
            "insp": insp_out,
        })

    places.sort(key=lambda p: (p["ct"], p["n"]))
    dates = [i["d"] for p in places for i in p["insp"]]
    manifest = {
        "region": "us-tn",
        "state": "TN",
        "jurisdiction": "TN-DOH",
        "source": ("Tennessee Department of Health — MyHealthDepartment "
                   "inspection portal, "
                   "inspections.myhealthdepartment.com/tennessee"),
        "source_files": [
            "raw/search_pages/<COUNTY>/<range>_p<NNNN>.json",
            "raw/insp/<COUNTY>/<inspectionID>.html",
        ],
        "score_model": ("SCORE_100 (native TN DOH 0-100); the portal "
                        "publishes no letter grade (its grade element "
                        "is hidden and empty) -> grade is null, never "
                        "derived"),
        "generated_at": utcnow(),
        "adapter": "tn_doh prototype v0.1",
        "coverage_exclusions": (
            "Non-food permits on the same portal (swimming pools, "
            "hotels/motels, tattoo & body piercing, child-care "
            "facilities) are out of scope; only Commercial Food "
            "permits are included."),
        "totals": {
            "places": len(places),
            "places_with_inspections": sum(
                1 for p in places if p["insp"]),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": sum(len(i["v"]) for p in places
                              for i in p["insp"]),
            "inspection_date_min": min(dates) if dates else None,
            "inspection_date_max": max(dates) if dates else None,
            "counties_with_places": len({p["ct"] for p in places}),
        },
    }

    with open(os.path.join(OUT, "places_tn.json"), "w") as f:
        json.dump(places, f, ensure_ascii=False)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(OUT, "exclusions.json"), "w") as f:
        json.dump(exclusions, f, indent=1)
    qa["exclusions"] = len(exclusions)
    qa["places_out"] = len(places)
    with open(os.path.join(OUT, "qa_report.json"), "w") as f:
        json.dump(qa, f, indent=1)
    print(json.dumps(manifest["totals"], indent=1))
    print(f"exclusions: {len(exclusions)}  "
          f"dropped(no detail): {qa['inspections_dropped_no_detail']}  "
          f"dropped(unverified): {qa['inspections_dropped_unverified']}")


if __name__ == "__main__":
    main()
