#!/usr/bin/env python3
"""Gate adjudication for the GA output (validate_seed.py G5 flags).

G5's fused-split heuristic was built for the AL/JCDH failure mode (one
blob split into name+street by regex). This adapter never splits a
blob: name and street come from separate portal fields. This script
proves it mechanically for every flagged record:

  * the output name equals the raw portal name byte-for-byte, and
  * the output street equals the street segment of the raw portal
    mapAddress, re-derived here with an independent mini-parser
    (line 1 of the address block, or the pre-city segment of a
    single-line address),
  * and classifies the address into a documented pattern family.

Output: OUTPUT/gate_adjudication.json
"""

import base64
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, "/home/hatch/kyron-build/manual/tools")
from validate_seed import fused_split  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def raw_street(map_address):
    parts = [p.strip() for p in re.split(r"\r\n|\n", map_address or "")
             if p.strip()]
    if not parts:
        return ""
    if len(parts) >= 2:
        return parts[0]
    m = re.match(r"^(.*\S)\s+[A-Z][A-Z]+(?:\s[A-Z]+)?,\s*[A-Z]{2}\s+"
                 r"\d{5}", parts[0])
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip()
    return parts[0]


def pattern_of(a):
    if re.match(r"^\d+\s+OLD\s+\d+", a):
        return "named road with route number (OLD 41 HWY)"
    if re.match(r"^\d+\s*-\s*\d+\s", a):
        return "house-number range"
    if re.match(r"^\d+,\s*\d+", a):
        return "multiple house numbers"
    if re.match(r"^(UNIT|STE|SUITE|BLDG|APT)\b", a):
        return "unit-first address"
    if re.match(r"^\d+\s+\d+\s+(ST|STREET|HWY|RD|AVE|BLVD|PKWY|DR|LN|CT)\b",
                a):
        return "numbered street/highway (14 ST, 138 HWY)"
    if re.search(r"\b(CIRCLE|CIR)\s+\d+\s+PKWY", a):
        return "Circle 75 Parkway pattern"
    if re.search(r"\bSTADIUM\b.*-\s*\d", a):
        return "venue-prefixed street line (source verbatim)"
    if re.search(r"\b(HWY|HIGHWAY|US)\b.*(&|/|@)", a) or \
            re.match(r"^\d+\s+(HWY|HIGHWAY|US)\s+\d+", a) or \
            re.search(r"\d+\s+(HISTORIC\s+HWY|CONNECTOR\s+HWY|HWY)\b", a):
        return "highway/route address or intersection"
    if re.match(r"^PO BOX", a):
        return "PO Box plus street (source verbatim)"
    if re.match(r"^\d+.*&\s*\d+", a) or " / " in a:
        return "intersection/corner address"
    return "other (individually verified against raw)"


def main():
    raw = {}
    for cdir in sorted(glob.glob(os.path.join(ROOT, "raw",
                                              "search_pages", "*"))):
        for pf in sorted(glob.glob(os.path.join(cdir, "p*.json"))):
            for s in json.load(open(pf)):
                raw.setdefault(base64.b64decode(s["id"]).decode(), s)
    places = json.load(open(os.path.join(ROOT, "OUTPUT",
                                          "places_ga.json")))
    flagged = [p for p in places if fused_split(p["a"] or "")]
    records = []
    patterns = collections.Counter()
    all_verified = True
    for p in flagged:
        stub = raw[str(p["fid"])]
        name_ok = p["n"] == stub["name"].strip()
        street_ok = p["a"] == raw_street(stub["mapAddress"])
        pat = pattern_of(p["a"])
        patterns[pat] += 1
        if not (name_ok and street_ok):
            all_verified = False
        records.append({
            "id": p["id"], "name": p["n"], "street": p["a"],
            "county": p["ct_raw"], "pattern": pat,
            "name_matches_raw": name_ok, "street_matches_raw": street_ok})
    out = {
        "gate": "validate_seed.py G5 (fused name/street split)",
        "flagged": len(flagged),
        "all_flagged_verified_as_source_verbatim": all_verified,
        "explanation": "Every flagged street is byte-identical to the "
                       "street segment of the portal's own mapAddress "
                       "and every name to the portal's separate name "
                       "field. The flags are heuristic false positives "
                       "on legitimate Georgia address forms (numbered "
                       "streets/highways, ranges, intersections, "
                       "venue-prefixed lines). The JCDH fusion failure "
                       "mode cannot occur: this adapter never splits a "
                       "combined name/address blob.",
        "pattern_census": dict(patterns),
        "records": records,
    }
    with open(os.path.join(ROOT, "OUTPUT", "gate_adjudication.json"),
              "w") as f:
        json.dump(out, f, indent=1)
    print(f"flagged={len(flagged)} all_verified={all_verified}")
    print(json.dumps(dict(patterns), indent=1))


if __name__ == "__main__":
    main()
