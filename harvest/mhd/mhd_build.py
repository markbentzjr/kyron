#!/usr/bin/env python3
"""Generic MyHealthDepartment normalizer — OUTPUT per state.

Reads raw/<key>/ (search stubs + verified detail pages) and writes:

  out/<key>/places.json      compact-key place dicts (socrata_cities
                             shape: id,n,a,c,z,ct,st,jur,src,du,lat,lng,
                             gs,ga,gp,gm,s,d,disp,origin,insp[])
  out/<key>/manifest.json    coverage + totals
  out/<key>/exclusions.json  places withheld by the gate rules
  out/<key>/qa_report.json   build-side accounting

Discipline inherited from FL/GA/TN/SC:
  * native results verbatim: stub scoreDisplay / detail "Score &
    Grade" result text ("Pass", "Re-Inspection Required", ...) ships in
    `disp` — the small integer in the stub `score` field is a
    demerit-count artifact on these deployments, NOT a published
    score, so `s` is always the NO_SCORE sentinel (-1) (none of the
    covered jurisdictions publishes a 0-100 score);
  * violations ship only from stub-VERIFIED detail pages (permitID,
    name, date must agree — the GA crossed-payload lesson), rendered
    to {p, c, r} at pack time; deployments with no server-rendered
    detail (VA) ship stub-level inspections with violations=[] and
    qa counts them separately;
  * places failing the gate classes (blank/placeholder name, no
    street) are excluded and logged, never repaired;
  * county: only when the stub itself publishes it (CO ADCounty) —
    never geocoded or inferred.

Usage: python mhd_build.py va [wi co mt hi ...]
"""

import base64
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from states import STATES  # noqa: E402
from mhd_parse import parse_detail  # noqa: E402
from mhd_fetch_details import is_food_stub, norm_date, verify_stub  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "https://inspections.myhealthdepartment.com"
NO_SCORE = -1

PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'total',
    'subtotal', 'establishment', 'facility', 'facility name',
    'food service', 'name', 'business name', 'unnamed', 'test',
    'restaurant', 'the', '-', '--', 'see remarks',
    'county health department', 'health department',
}


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def norm_name(s):
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()


def load_stubs(key):
    """(stubs_by_inspection, stats). Deduped by inspectionID across
    overlapping date-range pages."""
    by_insp = {}
    total_rows = 0
    spages = os.path.join(ROOT, "raw", key, "search_pages", "STATEWIDE")
    if not os.path.isdir(spages):
        return by_insp, {"search_rows_total": 0}
    for fname in sorted(os.listdir(spages)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(spages, fname), encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            if not isinstance(r, dict) or "inspectionID" not in r:
                continue
            total_rows += 1
            by_insp.setdefault(r["inspectionID"], r)
    return by_insp, {"search_rows_total": total_rows,
                     "unique_inspections": len(by_insp)}


def build_violations(parsed):
    """Union of published observation entries and checklist OUT items —
    the TN rule, unchanged (item order, narrative verbatim)."""
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
            "item": e["item"], "title": titles.get(e["item"]),
            "rule": e["rule"], "notes": e["notes"],
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
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or \
        [k for k, c in STATES.items() if c["enabled"]]
    for key in keys:
        cfg = STATES.get(key)
        if cfg is None or not cfg["enabled"]:
            print(f"[skip] {key}: not enabled", flush=True)
            continue
        build_state(key, cfg)


def build_state(key, cfg):
    out_dir = os.path.join(ROOT, "out", key)
    os.makedirs(out_dir, exist_ok=True)
    by_insp, stats = load_stubs(key)
    food = {iid: r for iid, r in by_insp.items() if is_food_stub(cfg, r)}

    didx = {}
    iroot = os.path.join(ROOT, "raw", key, "insp")
    if os.path.isdir(iroot):
        for fname in sorted(os.listdir(iroot)):
            if fname.endswith(".html"):
                didx[fname[:-5]] = os.path.join(iroot, fname)

    places = {}
    exclusions = []
    qa = {
        **stats,
        "food_stubs_unique": len(food),
        "detail_files": len(didx),
        "inspections_emitted": 0,
        "inspections_stub_level": 0,
        "inspections_dropped_no_detail": 0,
        "inspections_dropped_unverified": 0,
        "unverified": [],
        "violations": 0,
        "places_without_any_inspection": 0,
        "score_null_inspections": 0,
        "disp_values": Counter(),
        "purpose_values": Counter(),
        "county_field_present": 0,
    }

    by_permit = defaultdict(list)
    for iid, r in food.items():
        pid = r.get("permitID")
        if pid:
            by_permit[pid].append(iid)
    qa["food_permits_unique"] = len(by_permit)

    for pid in sorted(by_permit):
        iids = by_permit[pid]
        stubs = sorted((food[i] for i in iids),
                       key=lambda s: norm_date(s.get("inspectionDate")),
                       reverse=True)
        newest_stub = stubs[0]
        county = (newest_stub.get(cfg["county_field"])
                  if cfg["county_field"] else None) or ""
        if county:
            qa["county_field_present"] += 1

        insp_out = []
        for stub in stubs:
            iid = stub["inspectionID"]
            d_iso = norm_date(stub.get("inspectionDate"))
            qa["purpose_values"][stub.get("purpose") or ""] += 1
            disp = str(stub.get(cfg["disp_field"]) or "").strip()
            if disp.casefold() in ("none", "null", "n/a"):
                disp = ""
            detail_path = didx.get(iid)
            viol = []
            comments = None
            parsed = None
            if detail_path is not None:
                with open(detail_path, encoding="utf-8",
                          errors="replace") as f:
                    try:
                        parsed = parse_detail(f.read(), cfg["path"])
                        probs = verify_stub(cfg, stub, parsed)
                    except Exception as e:  # noqa: BLE001
                        parsed, probs = None, [f"parse error: {e}"]
                if probs:
                    qa["inspections_dropped_unverified"] += 1
                    qa["unverified"].append(
                        {"inspectionID": iid, "problems": probs})
                    parsed = None
                else:
                    viol = build_violations(parsed)
                    comments = parsed.get("comments")
                    if not disp and parsed.get("result_text"):
                        disp = parsed["result_text"]
            elif cfg["detail"] == "server":
                qa["inspections_dropped_no_detail"] += 1
            else:
                qa["inspections_stub_level"] += 1
            qa["violations"] += len(viol)
            qa["disp_values"][disp] += 1
            qa["inspections_emitted"] += 1
            insp_out.append({
                "d": d_iso,
                "t": stub.get("purpose") or
                (parsed or {}).get("purpose") or
                stub.get("inspectionType") or "",
                "s": NO_SCORE,
                "disp": disp,
                "comments": comments,
                "v": viol,
                "du": (ORIGIN + "/" + cfg["path"] +
                       "/inspection/?inspectionID=" + iid),
            })
        insp_out.sort(key=lambda i: i["d"], reverse=True)

        name = (newest_stub.get("establishmentName") or
                newest_stub.get("name") or "").strip()
        street_parts = [newest_stub.get("addressLine1") or ""]
        if (newest_stub.get("addressLine2") or "").strip():
            street_parts.append(newest_stub["addressLine2"].strip())
        street = ", ".join(p.strip() for p in street_parts if p.strip())

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
            reason = ("no inspection rows for this permit; excluded "
                      "rather than shipping an empty place.")
            qa["places_without_any_inspection"] += 1
        if reason:
            exclusions.append({"permitID": pid, "name": name or None,
                               "reason": reason})
            continue

        newest = insp_out[0]
        places[pid] = {
            "id": f"{cfg['source_id'].replace('-', '')}_{base64.urlsafe_b64encode(pid.encode()).decode()[:12]}",
            "n": name,
            "a": street,
            "c": (newest_stub.get("city") or "").strip(),
            "z": (newest_stub.get("zip") or "")[:5],
            "ct": county,
            "st": cfg["state"],
            "jur": cfg["jur"],
            "src": cfg["source_id"],
            "du": newest["du"],
            "lat": None, "lng": None,
            "gs": "UNRESOLVED", "ga": "NONE", "gp": "", "gm": "",
            "s": NO_SCORE,
            "d": newest["d"],
            "disp": newest["disp"],
            "origin": f"mhd-{cfg['path']}",
            "insp": insp_out,
        }

    out_places = sorted(places.values(), key=lambda p: p["id"])
    dates = [i["d"] for p in out_places for i in p["insp"] if i["d"]]
    manifest = {
        "region": cfg["region"],
        "state": cfg["state"],
        "jurisdiction": cfg["jur"],
        "source": cfg["agency"] + " — inspections.myhealthdepartment.com/"
                + cfg["path"],
        "score_model": cfg["model"] + " (native result text in disp; "
                        "the stub 'score' field is a demerit-count "
                        "artifact on these deployments, never shipped)",
        "generated_at": utcnow(),
        "adapter": "mhd generic v1.0",
        "coverage_exclusions": (
            "Non-food programs on the same portal (lodging, pools, "
            "body art, mobile/transient non-food units) are out of "
            "scope; only rows matching the state's food program are "
            "included."),
        "totals": {
            "places": len(out_places),
            "places_with_inspections": sum(
                1 for p in out_places if p["insp"]),
            "inspections": sum(len(p["insp"]) for p in out_places),
            "violations": sum(len(i["v"]) for p in out_places
                              for i in p["insp"]),
            "inspection_date_min": min(dates) if dates else None,
            "inspection_date_max": max(dates) if dates else None,
        },
    }

    with open(os.path.join(out_dir, "places.json"), "w",
              encoding="utf-8") as f:
        json.dump(out_places, f, ensure_ascii=False)
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(out_dir, "exclusions.json"), "w",
              encoding="utf-8") as f:
        json.dump(exclusions, f, indent=1)
    qa["exclusions"] = len(exclusions)
    qa["places_out"] = len(out_places)
    qa["disp_values"] = dict(qa["disp_values"].most_common(25))
    qa["purpose_values"] = dict(qa["purpose_values"].most_common(25))
    with open(os.path.join(out_dir, "qa_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(qa, f, indent=1, default=str)
    print(f"[build] {key}: {json.dumps(manifest['totals'])}")
    print(f"        exclusions={len(exclusions)} "
          f"no-detail={qa['inspections_dropped_no_detail']} "
          f"unverified={qa['inspections_dropped_unverified']} "
          f"stub-level={qa['inspections_stub_level']}")


if __name__ == "__main__":
    main()
