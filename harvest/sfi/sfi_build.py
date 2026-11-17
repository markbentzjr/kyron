#!/usr/bin/env python3
"""Generic SafeFoodInspection normalizer — OUTPUT per state.

Reads raw/<st>/search/*/*.html (+ raw/<st>/viol/*.html panels and
raw/<st>/pdf/*.pdf reports) and writes:

  out/<st>/places.json      compact-key place dicts
  out/<st>/manifest.json    coverage + totals
  out/<st>/exclusions.json  places withheld by the gate rules
  out/<st>/qa_report.json   build-side accounting

Honesty rules (same as MHD/Socrata paths):
  * numeric Score column -> real score on numeric deployments (VT/SD);
    Compliance column ("In"/"Out") -> result_text only, score stays
    NO_SCORE. score_col="auto" defers to the parsed header label:
    a 'Score' header emitting only digits ships numeric, anything else
    ships result_text — the column is never reinterpreted;
  * violations ship only from fetched artifacts: a parsed
    wucPublicInspectionViolations panel or an observations-parsed
    report PDF. Inspections whose detail wasn't fetched emit
    violations=[] and are counted — never fabricated;
  * places keyed by the portal's own establishment Key; places with no
    street or a blank/placeholder name are excluded and logged.

Usage: python sfi_build.py vt [sd wy ...]
"""

import base64
import glob
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfi_states import STATES  # noqa: E402
from sfi_parse import (parse_results_page, parse_violations_panel,
                       parse_pdf_observations)  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
NO_SCORE = -1

PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'establishment',
    'facility', 'name', 'business name', 'unnamed', 'test', '-', '--',
    'restaurant', 'the',
}


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def is_numeric_result(cfg, headers, val):
    """Decide score-vs-result per row value; a 'Score' header +
    digit-only value -> numeric. 'Compliance'/'In Compliance' header ->
    result text, always."""
    if val is None or val == "":
        return None
    hdr = ""
    for h in headers:
        if h.lower() in ("score", "compliance", "in compliance"):
            hdr = h.lower()
            break
    if cfg["score_col"] == "numeric" or (
            cfg["score_col"] == "auto" and hdr == "score"
            and val.strip().isdigit()):
        return int(val)
    return "text"


def load_violations(key, estab_key, d_iso):
    fname = os.path.join(ROOT, "raw", key, "viol",
                         f"{estab_key}_{d_iso.replace('-', '')}.html")
    if os.path.exists(fname):
        with open(fname, encoding="utf-8", errors="replace") as f:
            panel = parse_violations_panel(f.read())
        if panel and panel["items"]:
            out = []
            for it in panel["items"]:
                parts = [p for p in (it["code"], it["explanation"])
                         if p]
                r = " — ".join(parts)
                if it["comments"]:
                    r += " // " + it["comments"]
                out.append({"p": 0, "c": False, "r": r})
            return out, "panel"
    fname = os.path.join(ROOT, "raw", key, "pdf",
                         f"{estab_key}_{d_iso.replace('-', '')}.pdf")
    if os.path.exists(fname):
        with open(fname, "rb") as f:
            obs = parse_pdf_observations(f.read())
        if obs:
            return [{"p": 0, "c": False,
                     "r": f"{o['num']} {o['code']} — {o['text']}"}
                    for o in obs], "pdf"
    return [], None


def build_state(key, cfg):
    out_dir = os.path.join(ROOT, "out", key)
    os.makedirs(out_dir, exist_ok=True)
    raw = os.path.join(ROOT, "raw", key)

    estabs = {}
    headers = []
    pages = sorted(glob.glob(os.path.join(raw, "search", "*", "*.html")))
    n_pages = 0
    for pf in pages:
        with open(pf, encoding="utf-8", errors="replace") as f:
            page = parse_results_page(f.read())
        n_pages += 1
        if len(page["headers"]) > len(headers):
            headers = page["headers"]
        for row in page["rows"]:
            ekey = row["estab_key"] or ("nok:" + row["name_raw"])
            e = estabs.setdefault(ekey, {
                "name": row["name"], "address": row["address"],
                "city": row["city"], "st": row["addr_state"],
                "zip": row["zip"], "phone": row["phone"],
                "inspections": {}})
            for ins in [row["latest"], *row["past"]]:
                if not ins["date"]:
                    continue
                e["inspections"].setdefault(ins["date"], ins)
    qa = {
        "search_pages": n_pages, "establishments": len(estabs),
        "inspections_emitted": 0, "violations": 0,
        "viols_from_panel": 0, "viols_from_pdf": 0,
        "inspections_without_detail": 0, "score_numeric": 0,
        "score_text": 0, "disp_values": Counter(),
        "type_values": Counter(),
    }
    places = []
    exclusions = []
    for ekey, e in estabs.items():
        reason = None
        name = (e["name"] or "").strip()
        if not name:
            reason = ("G1-class: portal publishes a blank establishment "
                      "name for this permit; excluded rather than "
                      "shipped.")
        elif name.casefold() in PLACEHOLDER_NAMES:
            reason = ("G4-class: portal publishes the placeholder name "
                      f"{name!r}; excluded rather than shipped.")
        elif not (e["address"] or "").strip():
            reason = ("G2-class: portal publishes no street address "
                      "for this establishment; excluded rather than "
                      "shipped.")
        elif not e["inspections"]:
            reason = ("no inspection rows for this establishment; "
                      "excluded rather than shipping an empty place.")
        if reason:
            exclusions.append({"estab_key": ekey,
                               "name": name or None, "reason": reason})
            continue
        insp_out = []
        for d_iso in sorted(e["inspections"], reverse=True):
            ins = e["inspections"][d_iso]
            res = (ins.get("result") or "").strip()
            score = NO_SCORE
            disp = ""
            verdict = is_numeric_result(cfg, headers, res)
            if isinstance(verdict, int):
                score = verdict
                qa["score_numeric"] += 1
            elif res:
                disp = res
                qa["score_text"] += 1
            viol, vsrc = load_violations(key, ekey, d_iso)
            if vsrc == "panel":
                qa["viols_from_panel"] += 1
            elif vsrc == "pdf":
                qa["viols_from_pdf"] += 1
            else:
                qa["inspections_without_detail"] += 1
            qa["violations"] += len(viol)
            qa["disp_values"][disp] += 1
            qa["type_values"][ins["type"]] += 1
            qa["inspections_emitted"] += 1
            insp_out.append({
                "d": d_iso, "t": ins["type"], "s": score,
                "disp": disp, "comments": None, "v": viol,
                "du": cfg["url"]})
        newest = insp_out[0]
        newest_e = max(e["inspections"].values(),
                       key=lambda x: x["date"])
        places.append({
            "id": f"{cfg['source_id'].replace('-', '')}_"
                  f"{base64.urlsafe_b64encode(ekey.encode()).decode()[:12]}",
            "_ekey": ekey,
            "n": name, "a": e["address"].strip(),
            "c": (e["city"] or "").strip(), "z": (e["zip"] or "")[:5],
            "ct": (newest_e.get("jurisdiction") or "").strip(),
            "st": cfg["state"], "jur": cfg["jur"],
            "src": cfg["source_id"], "du": cfg["url"],
            "lat": None, "lng": None,
            "gs": "UNRESOLVED", "ga": "NONE", "gp": "", "gm": "",
            "s": newest["s"], "d": newest["d"],
            "disp": newest["disp"], "origin": "sfi",
            "insp": insp_out})
    # different ekeys can truncate to the same 12-char b64 id prefix
    # (nok: fallbacks share name prefixes — PA canteen trucks).
    # Disambiguate collisions with a digest of the full ekey; unique
    # ids keep their stable short form.
    by_id = {}
    for p in places:
        by_id.setdefault(p["id"], []).append(p)
    for pid, group in by_id.items():
        if len(group) > 1:
            for p in group:
                p["id"] = pid + "_" + hashlib.sha256(
                    p["_ekey"].encode()).hexdigest()[:8]
    for p in places:
        p.pop("_ekey", None)
    places.sort(key=lambda p: p["id"])
    dates = [i["d"] for p in places for i in p["insp"]]
    manifest = {
        "region": cfg["region"], "state": cfg["state"],
        "jurisdiction": cfg["jur"],
        "source": cfg["agency"] + " — safefoodinspection.com portal",
        "score_model": cfg["model"],
        "generated_at": utcnow(), "adapter": "sfi generic v1.0",
        "coverage_exclusions": (
            "Portal-published records only; jurisdictions running "
            "their own programs (see source notes) are absent from "
            "this feed, as documented by the agency."),
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
    qa["disp_values"] = dict(qa["disp_values"].most_common(25))
    qa["type_values"] = dict(qa["type_values"].most_common(25))
    with open(os.path.join(out_dir, "qa_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(qa, f, indent=1, default=str)
    print(f"[build] {key}: {json.dumps(manifest['totals'])}")
    print(f"        exclusions={len(exclusions)} "
          f"panel={qa['viols_from_panel']} pdf={qa['viols_from_pdf']} "
          f"no-detail={qa['inspections_without_detail']} "
          f"scores={qa['score_numeric']}")


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
