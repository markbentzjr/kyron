#!/usr/bin/env python3
"""Checker for the emulator smoke run (.github/workflows/emulator-smoke.yml).

Modes:
  locate-filter <ui.xml>          print "X Y" tap point of the Coverage
                                  screen's filter EditText.
  exact-name <name> <ui.xml>      exit 0 iff a rendered text node's text is
                                  EXACTLY <name> (a state card's title).
  verify-report <report.tsv>      exit 0 iff all 50 state codes plus DC
                                  PASSed (51 rows) and nothing unexpected.

Text nodes come from `uiautomator dump`; the Coverage list renders one card
per registry jurisdiction, so "the state's card renders when filtering by
its USPS code" is the honest assertion that the state is select-able in the
app. Exact matching is deliberate (substring would let filtering AK match
California by name).
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

STATE_CODES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
               "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
               "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
               "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
               "VT", "VA", "WA", "WV", "WI", "WY"}
EXPECT = STATE_CODES | {"DC"}


def texts(root):
    for el in root.iter("node"):
        t = el.get("text", "").strip()
        if t:
            yield el, t


def find_filter(path):
    """Print the tap point of the first EditText (the filter field)."""
    root = ET.parse(path).getroot()
    nodes = [el for el in root.iter("node")
             if el.get("class") == "android.widget.EditText"]
    if not nodes:
        sys.exit("FATAL: no EditText found on the coverage screen")
    b = [int(v) for v in nodes[0].get("bounds", "[0,0][0,0]").strip("[]").split("][")]
    print((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def exact_name(name, path):
    """exit 0 iff a node's text is exactly NAME."""
    root = ET.parse(path).getroot()
    for _, t in texts(root):
        if t == name:
            print(f"FOUND: {t}")
            return 0
    print(f"NOT FOUND: {name}", file=sys.stderr)
    return 1


def verify_report(report):
    """exit 0 iff exactly the 50 state codes + DC all PASSed."""
    rows = {}
    for line in Path(report).read_text().splitlines():
        if line.strip():
            code, verdict = line.split()[:2]
            rows[code] = verdict
    missing = sorted(c for c in EXPECT if rows.get(c) != "PASS")
    extra = sorted(c for c in rows if c not in EXPECT)
    passed = sum(1 for v in rows.values() if v == "PASS")
    print(f"report: {len(rows)} rows; PASS={passed}")
    if extra:
        print("unexpected codes:", extra)
    if missing or extra:
        sys.exit(f"FAIL ({len(missing)} of {len(EXPECT)} missing): {missing}")
    print("ALL 50 STATES + D.C. RENDER ON THE COVERAGE SCREEN")


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--help"
    if mode == "locate-filter" and len(argv) == 3:
        find_filter(argv[2])
        return 0
    if mode == "exact-name" and len(argv) == 4:
        return exact_name(argv[2], argv[3])
    if mode == "verify-report" and len(argv) == 3:
        verify_report(argv[2])
        return 0
    sys.exit("usage: emulator_smoke_check.py {locate-filter ui.xml | "
             "exact-name NAME ui.xml | verify-report report.tsv}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
