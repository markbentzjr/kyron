#!/usr/bin/env python3
"""Kyron SC adapter — parsers for the three raw sources (prototype v0.1).

- GIS layer 0 / Steton table pages (JSON) under raw/gis_*/
- rate.aspx leaf pages (HTML) under raw/rate/<county-code>/

Rate row layout (measured 2026-10-15):
  <tr valign='top'>
    <td name><div><strong>NAME</strong></div></td>
    <td street><div>STREET</div></td>
    <td city><div>CITY</div></td>
    <td grade><div><strong>A</strong></div></td>
    <td date><div>YYYY-MM-DD</div></td>
    <td type><div>Follow Up</div></td>
    <td pdf><a href='http://pubdoc.dhec.sc.gov/Inspection/<GUID>.pdf'>
"""
import glob
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

ROW_SPLIT = "<tr valign='top'>"
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
GUID_RE = re.compile(r"Inspection/([0-9a-fA-F-]{36})\.pdf")


def _text(cell):
    return html.unescape(TAG_RE.sub("", cell)).strip()


def parse_rate_html(path):
    """Yield inspection dicts from one saved rate.aspx leaf page."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        doc = fh.read()
    m = re.search(r"(\d+) records matched", doc)
    matched = int(m.group(1)) if m else None
    rows = []
    # Rows are never closed with </tr> — each runs into the next
    # <tr valign='top'> (measured: a 616-row page contains one </tr>).
    for row_html in doc.split(ROW_SPLIT)[1:]:
        cells = CELL_RE.findall(row_html)
        if len(cells) < 7:
            raise ValueError(f"{path}: row with {len(cells)} cells")
        g = GUID_RE.search(row_html)
        if not g:
            raise ValueError(f"{path}: row without PDF guid: {row_html[:120]}")
        rows.append({
            "guid": g.group(1).lower(),
            "name": _text(cells[0]),
            "street": _text(cells[1]),
            "city": _text(cells[2]),
            "grade": _text(cells[3]),
            "date": _text(cells[4]),
            "type": _text(cells[5]),
        })
    if matched is not None and matched != len(rows):
        raise ValueError(f"{path}: matched={matched} rows={len(rows)}")
    return rows


def load_gis(subdir):
    feats = []
    for p in sorted(glob.glob(os.path.join(HERE, "raw", subdir, "page_*.json"))):
        with open(p) as fh:
            feats += json.load(fh)["features"]
    return feats


def load_rate():
    """All rate rows, tagged with the county code of their query."""
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, "raw", "rate", "*", "*.html"))):
        cc = os.path.basename(os.path.dirname(p))
        for r in parse_rate_html(p):
            r["county_code"] = cc
            r["page"] = os.path.relpath(p, HERE)
            out.append(r)
    return out
