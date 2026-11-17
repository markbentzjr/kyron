#!/usr/bin/env python3
"""Mississippi MSDH normalizer — harvest/ms.

Reads raw/rec/<pimsid>.html (FacilityRecord pages) and writes
out/ms/{places,manifest,exclusions,qa_report}.json.

Each record page carries:
  facility block  — Name / Status / Street / City / State / Zip /
                    Permit + Expire dates
  inspection rows — <td class="KnockoutDataTD">Ref | Type | Grade |
                    MM/DD/YYYY | Inspector | Details-link
                    (repeaters inspectionListing*; dedupe by Ref#)

Model: LETTER_GRADE — the portal publishes A/B/C letters only, no
numeric score. Grade -> disp verbatim, s = NO_SCORE.

Usage: python ms_build.py
"""

import datetime
import glob
import html as htmllib
import json
import os
import re
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "out", "ms")
NO_SCORE = -1
BASE = "https://apps.msdh.ms.gov/food/"

CELL_RE = re.compile(
    r'<td class="KnockoutDataTD">(.*?)</td>', re.S)
ROW_RE = re.compile(r"<tr>\s*((?:\s*<td class=\"KnockoutDataTD\">"
                    r".*?</td>\s*)+)\s*</tr>", re.S)
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return htmllib.unescape(s).replace("\xa0", " ").strip()


def mdy(s):
    m = DATE_RE.match((s or "").strip())
    return ("%04d-%02d-%02d" % (int(m.group(3)), int(m.group(1)),
                              int(m.group(2)))) if m else ""


def field(page, label, nxt_labels):
    """'Label: value <NextLabel:' -> value."""
    i = page.find(label + ":")
    if i < 0:
        return ""
    i += len(label) + 1
    end = len(page)
    for nl in nxt_labels:
        j = page.find(nl + ":", i)
        if 0 <= j < end:
            end = j
    return clean(page[i:end])


def parse_record(pid, page):
    text = re.sub(r"<br\s*/?>", " ", page)
    name = field(text, "Name", ["Status"])
    status = field(text, "Status", ["Street"])
    street = field(text, "Street", ["City"])
    city = field(text, "City", ["State"])
    znorm = page.replace("&nbsp;", " ")
    zipm = re.search(r"Zip:\s*(\d{5,9})", znorm)
    zipc = zipm.group(1)[:5] if zipm else ""
    insp = {}
    for rm in ROW_RE.finditer(page):
        cells = [clean(c) for c in CELL_RE.findall(rm.group(1))]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        ref, typ, grade, date, inspector = cells[:5]
        if not DATE_RE.match(date):
            continue
        durl = ""
        dm = re.search(
            r'href="(FacilityRecordDetailsNewInspection\.aspx[^"]*)"',
            rm.group(1))
        if dm:
            durl = BASE + htmllib.unescape(dm.group(1))
        insp[ref] = {"ref": ref, "t": typ, "disp": grade,
                     "d": mdy(date), "du": durl}
    return name, status, street, city, zipc, insp


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = sorted(glob.glob(os.path.join(RAW, "rec", "*.html")))
    places, exclusions = [], []
    qa = {"records": len(recs), "no_name": 0, "no_street": 0,
          "grades": Counter(), "types": Counter()}
    for path in recs:
        pid = os.path.basename(path)[:-5]
        with open(path, encoding="cp1252", errors="replace") as f:
            page = f.read()
        name, status, street, city, zipc, insp = parse_record(
            pid, page)
        reason = None
        if not name:
            reason, qa["no_name"] = ("portal publishes a blank "
                                     "facility name",
                                     qa["no_name"] + 1)
        elif not street:
            reason, qa["no_street"] = ("portal publishes no street "
                                       "address", qa["no_street"] + 1)
        if reason:
            exclusions.append({"pimsid": pid, "name": name or None,
                               "reason": reason})
            continue
        today = datetime.date.today().isoformat()
        future = [i for i in insp.values() if i["d"] > today]
        for f in future:
            exclusions.append({"pimsid": pid, "name": name,
                               "reason": "future-dated %s row "
                               "(portal placeholder, not a "
                               "completed inspection): %s"
                               % (f["t"], f["d"])})
        rows = sorted((i for i in insp.values() if i["d"] <= today),
                      key=lambda i: i["d"], reverse=True)
        for r in rows:
            qa["grades"][r["disp"]] += 1
            qa["types"][r["t"]] += 1
        newest = rows[0] if rows else {}
        places.append({
            "id": "msdh_" + pid,
            "n": name, "a": street, "c": city, "z": zipc, "ct": "",
            "st": "MS", "jur": "MS-MSDH", "src": "ms-msdh",
            "du": newest.get("du") or BASE +
                  "FacilityRecord.aspx?PimsID=" + pid,
            "lat": None, "lng": None,
            "gs": "UNRESOLVED", "ga": "NONE", "gp": "", "gm": "",
            "s": NO_SCORE, "d": newest.get("d", ""),
            "disp": newest.get("disp", ""),
            "permit_status": status,
            "origin": "ms-msdh",
            "insp": [{"d": r["d"], "t": r["t"], "s": NO_SCORE,
                      "disp": r["disp"], "comments": None, "v": [],
                      "du": r["du"]} for r in rows],
        })
    places.sort(key=lambda p: p["id"])
    dates = [i["d"] for p in places for i in p["insp"] if i["d"]]
    manifest = {
        "region": "us-ms", "state": "MS", "jurisdiction": "MS-MSDH",
        "source": "Mississippi State Department of Health — Food "
                  "Facility Inspections — " + BASE,
        "score_model": "LETTER_GRADE (portal publishes A/B/C "
                       "inspection grades only; no numeric score)",
        "generated_at": utcnow(), "adapter": "ms-msdh v1.0",
        "coverage_exclusions": (
            "Per-inspection violation detail pages "
            "(FacilityRecordDetailsNewInspection) exist but are not "
            "fetched in v1 — grades, types and dates are complete; "
            "violation text remains one click away at the report "
            "URL shipped per inspection."),
        "totals": {
            "places": len(places),
            "places_with_inspections": sum(
                1 for p in places if p["insp"]),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": 0,
            "inspection_date_min": min(dates) if dates else None,
            "inspection_date_max": max(dates) if dates else None,
        }}
    for fn, obj in [("places.json", places),
                    ("manifest.json", manifest),
                    ("exclusions.json", exclusions),
                    ("qa_report.json", {**qa,
                                        "grades": dict(qa["grades"]),
                                        "types": dict(
                                            qa["types"].most_common(30)),
                                        "exclusions": len(exclusions),
                                        "places_out": len(places)})]:
        with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False,
                      indent=None if fn == "places.json" else 1)
    print(f"[build] ms: {json.dumps(manifest['totals'])}")
    print(f"        exclusions={len(exclusions)} "
          f"grades={dict(qa['grades'])}")


if __name__ == "__main__":
    main()
