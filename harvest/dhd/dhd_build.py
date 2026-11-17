#!/usr/bin/env python3
"""Generic healthinspections.us (DHD) normalizer — OUTPUT per state.

Reads raw/<key>/search_pages/<PART>/pNNNN.json + raw/<key>/insp/<PART>/
<id>.json and writes out/<key>/{places,manifest,exclusions,qa_report}.

Fields arrive as portal-labelled "Label: value" columns — parsed by
prefix, never position-guessed. Addresses arrive as flat
"STREET <multi-space> CITY ST ZIP" strings; the city is decided by
longest-suffix match against the state's published municipality list
(cfg['cities']) — never geocoded, never invented. Violations are the
portal's own item-numbered narratives shipped verbatim.

RI publishes no score and no pass/fail result -> s = NO_SCORE (-1),
disp = "".

Usage: python dhd_build.py ri
"""

import base64
import glob
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dhd_states import STATES  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
NO_SCORE = -1

PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'establishment',
    'facility', 'name', 'unnamed', 'test', '-', '--',
}


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def mdy_dash(s):
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", (s or "").strip())
    return ("%04d-%02d-%02d" % (int(m.group(3)), int(m.group(1)),
                              int(m.group(2)))) if m else ""


def inspection_date(columns):
    """RI labels it 'Inspection Date: MM-DD-YYYY'; LA ships the bare
    date in column 0. Prefer the label, else any bare-date cell."""
    labeled = col_val(columns, "Inspection Date")
    if labeled:
        return labeled
    for v in (columns or {}).values():
        if isinstance(v, str) and \
                re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", v.strip()):
            return v.strip()
    return ""


def col_val(columns, prefix):
    for v in (columns or {}).values():
        if isinstance(v, str) and v.lower().startswith(
                prefix.lower() + ":"):
            return v.split(":", 1)[1].strip()
    return ""


def split_address(cfg, raw_addr, city_hint=""):
    """'STREET  CITY ST ZIP' -> (street, city, zip). When the stub
    carries a structured City column (LA), city_hint decides the
    suffix; otherwise longest city suffix from cfg['cities'].
    Returns ('','','') pieces honestly."""
    a = re.sub(r"\s+", " ", (raw_addr or "").strip())
    m = re.match(r"^(.*?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$", a)
    if not m:
        return a, "", ""
    rest, st, zipc = m.group(1), m.group(2), m.group(3)
    if city_hint:
        for suf in (" " + city_hint.casefold() + ",",
                    " " + city_hint.casefold()):
            if rest.casefold().endswith(suf):
                return rest[:-len(suf)].strip(), city_hint, zipc
        return rest, city_hint, zipc
    best = ""
    for c in cfg.get("cities") or []:
        if rest.casefold().endswith(" " + c.casefold()) and \
                len(c) > len(best):
            best = c
    if best:
        street = rest[:-len(best)].strip()
        return street, best, zipc
    return rest, "", zipc


def report_url(cfg, printable_path):
    if not printable_path:
        return cfg["host"] + "/" + cfg["path"] + "/"
    p = printable_path.replace("\\", "/")
    p = re.sub(r"^\.\./", "/", p)
    if not p.startswith("/"):
        p = "/" + p
    return cfg["host"] + p


def build_state(key, cfg):
    out_dir = os.path.join(ROOT, "out", key)
    os.makedirs(out_dir, exist_ok=True)
    raw = os.path.join(ROOT, "raw", key)

    stubs = {}
    for pf in glob.glob(os.path.join(raw, "search_pages", "*",
                                     "*.json")):
        part = pf.replace("\\", "/").split("/")[-2]
        with open(pf, encoding="utf-8") as f:
            recs = json.load(f)
        for rec in recs:
            if isinstance(rec, dict) and rec.get("id"):
                stubs.setdefault(rec["id"], (part, rec))

    places = []
    exclusions = []
    qa = {"facilities_stubbed": len(stubs), "places_out": 0,
          "inspections_emitted": 0, "violations": 0,
          "facilities_without_detail": 0, "detail_files": 0,
          "purpose_values": Counter(), "addr_no_city": 0,
          "detail_empty": 0}

    for fid, (part, rec) in stubs.items():
        name = (rec.get("name") or "").strip()
        addr_raw = rec.get("mapAddress") or \
            col_val(rec.get("columns"), "")
        street, city, zipc = split_address(
            cfg, addr_raw, col_val(rec.get("columns"), "City"))
        county = col_val(rec.get("columns"), "Parish") or \
            col_val(rec.get("columns"), "County")
        lic = col_val(rec.get("columns"), "License #")
        ltype = col_val(rec.get("columns"), "License Type")
        reason = None
        if not name:
            reason = ("G1-class: portal publishes a blank name for "
                      "this facility; excluded rather than shipped.")
        elif name.casefold() in PLACEHOLDER_NAMES:
            reason = ("G4-class: portal publishes the placeholder "
                      f"name {name!r}; excluded rather than shipped.")
        elif not street:
            reason = ("G2-class: portal publishes no street address "
                      "for this facility; excluded rather than "
                      "shipped.")
        if reason:
            exclusions.append({"facilityId": fid, "name": name or None,
                               "reason": reason})
            continue
        if not city:
            qa["addr_no_city"] += 1
        try:
            fid_num = base64.b64decode(fid).decode()
        except Exception:
            fid_num = fid
        ipath = os.path.join(raw, "insp", part, fid_num + ".json")
        insp_out = []
        if os.path.exists(ipath):
            qa["detail_files"] += 1
            with open(ipath, encoding="utf-8") as f:
                entries = json.load(f)
            if not entries:
                qa["detail_empty"] += 1
            for ent in entries:
                d_iso = mdy_dash(inspection_date(
                    ent.get("columns")))
                purpose = col_val(ent.get("columns"),
                                  "Inspection Purpose")
                qa["purpose_values"][purpose] += 1
                viol = []
                for group in (ent.get("violations") or {}).values():
                    if not isinstance(group, list):
                        group = [group]
                    if len(group) >= 2:
                        # [category, narrative, flag] shape (LA)
                        cat, txt, flag = group[0], group[1], \
                            (group[2] if len(group) > 2 else None)
                        if not txt:
                            continue
                        crit = cat and "critical" in \
                            str(cat).lower() and "non" not in \
                            str(cat).lower()
                        viol.append({
                            "p": 0, "c": bool(crit),
                            "r": (str(txt) + (flag or "")).strip()})
                        continue
                    for vtxt in group:
                        if vtxt:
                            viol.append({"p": 0, "c": False,
                                         "r": str(vtxt).strip()})
                qa["violations"] += len(viol)
                qa["inspections_emitted"] += 1
                insp_out.append({
                    "d": d_iso, "t": purpose, "s": NO_SCORE,
                    "disp": "", "comments": None, "v": viol,
                    "du": report_url(cfg, ent.get("printablePath"))})
        else:
            qa["facilities_without_detail"] += 1
        insp_out.sort(key=lambda i: i["d"], reverse=True)
        newest = insp_out[0] if insp_out else None
        places.append({
            "id": f"{cfg['source_id'].replace('-', '')}_"
                  f"{base64.urlsafe_b64encode(fid_num.encode()).decode()[:12]}",
            "n": name, "a": street, "c": city, "z": zipc,
            "ct": county, "st": cfg["state"], "jur": cfg["jur"],
            "src": cfg["source_id"],
            "du": newest["du"] if newest else report_url(cfg, None),
            "lat": None, "lng": None,
            "gs": "UNRESOLVED", "ga": "NONE", "gp": "", "gm": "",
            "s": NO_SCORE, "d": newest["d"] if newest else "",
            "disp": newest["disp"] if newest else "",
            "origin": f"dhd-{cfg['path'] or cfg['host'].split('//')[1].split('.')[0]}",
            "insp": insp_out,
            "license_no": lic, "license_type": ltype,
        })

    places.sort(key=lambda p: p["id"])
    dates = [i["d"] for p in places for i in p["insp"] if i["d"]]
    manifest = {
        "region": cfg["region"], "state": cfg["state"],
        "jurisdiction": cfg["jur"],
        "source": cfg["agency"] + " — " + cfg["host"] + "/" +
                  cfg["path"],
        "score_model": cfg["model"] + " (no numeric score or result "
                        "text is published; violation narratives "
                        "verbatim)",
        "generated_at": utcnow(), "adapter": "dhd generic v1.0",
        "coverage_exclusions": (
            "inspectionsData returns each facility's most recent "
            "inspections (portal cap); older history beyond the "
            "portal's published window is absent by design of the "
            "source, not dropped by the adapter."),
        "totals": {
            "places": len(places),
            "places_with_inspections": sum(
                1 for p in places if p["insp"]),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": sum(len(i["v"]) for p in places
                              for i in p["insp"]),
            "inspection_date_min": min(dates) if dates else None,
            "inspection_date_max": max(dates) if dates else None,
        }}
    with open(os.path.join(out_dir, "places.json"), "w",
              encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False)
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(out_dir, "exclusions.json"), "w",
              encoding="utf-8") as f:
        json.dump(exclusions, f, indent=1)
    qa["exclusions"] = len(exclusions)
    qa["places_out"] = len(places)
    qa["purpose_values"] = dict(qa["purpose_values"].most_common(25))
    with open(os.path.join(out_dir, "qa_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(qa, f, indent=1, default=str)
    print(f"[build] {key}: {json.dumps(manifest['totals'])}")
    print(f"        exclusions={len(exclusions)} "
          f"no-detail={qa['facilities_without_detail']} "
          f"no-city={qa['addr_no_city']}")


def main():
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or \
        [k for k, c in STATES.items() if c["enabled"]]
    for key in keys:
        cfg = STATES.get(key)
        if cfg is None or not cfg["enabled"]:
            print(f"[skip] {key}", flush=True)
            continue
        build_state(key, cfg)


if __name__ == "__main__":
    main()
