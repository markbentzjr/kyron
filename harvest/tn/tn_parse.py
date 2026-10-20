#!/usr/bin/env python3
"""Parser for Tennessee MyHealthDepartment inspection detail pages
(server-rendered HTML at /tennessee/inspection/?inspectionID=<GUID>).

Extracts: permit id, establishment name, address, inspection type /
purpose, date, native score, additional comments, the
"Observations & Corrective Actions" violation entries (item number +
rule citation + narrative), and the full 1..58 checklist statuses
(IN / OUT / NO / NA per FDA-style item).

Used by tn_fetch_details.py (stub verification) and tn_build.py.
"""

import html as htmlmod
import re

MONTHS = {m: i + 1 for i, m in enumerate([
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"])}

CITATION_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}(?:\s*-\s*[\dA-Za-z().]+)?(?:\.\d{2}(?:\([0-9a-zA-Z]+\))*[0-9a-zA-Z.]*)?)\s*[.:]?\s+")


def _text(fragment):
    t = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    return re.sub(r"[ \t]+", " ", t).strip()


def parse_detail(html_text):
    """Return a dict of parsed fields, or raise ValueError."""
    out = {}

    # --- identity: permit link in the header h1
    m = re.search(
        r'<h1 class="establishment-page-left-name">\s*<a href="/tennessee/'
        r'permit/\?permitID=([0-9A-Fa-f-]{36})"[^>]*>(.*?)</a>',
        html_text, re.S)
    if not m:
        raise ValueError("permit header not found")
    out["permitID"] = m.group(1).upper()
    out["name"] = _text(m.group(2))

    # --- address line directly after the header h1. The raw fragment
    # separates street from "City, ST ZIP" with a double space (or a
    # <br>); split BEFORE whitespace collapsing destroys it.
    m = re.search(
        r'</h1>\s*<div>(.*?)</div>', html_text[m.end():], re.S)
    frag = m.group(1) if m else ""
    frag = re.sub(r"<br\s*/?>", "\x00", frag, flags=re.I)
    frag = htmlmod.unescape(re.sub(r"<[^>]+>", " ", frag))
    parts = [p.strip() for p in re.split(r"\x00|\s{2,}", frag) if p.strip()]
    addr_raw = " ".join(re.sub(r"[ \t]+", " ", p) for p in parts)
    out["address_full"] = addr_raw
    am = None
    if len(parts) >= 2:
        cm = re.match(r"^(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$",
                      re.sub(r"[ \t]+", " ", parts[-1]))
        if cm:
            am = (parts[0], cm)
    if am:
        out["addressLine1"] = re.sub(r"[ \t]+", " ", am[0]).strip()
        out["city"] = am[1].group(1).strip()
        out["state"] = am[1].group(2)
        out["zip"] = am[1].group(3)
    else:
        out["addressLine1"] = addr_raw
        out["city"] = out["state"] = out["zip"] = None

    # --- inspection type | purpose + written date. The inspection
    # header is the h1 whose text contains a literal "|" and no anchor.
    m = re.search(
        r'<h1 class="establishment-page-left-name">([^<]*\|[^<]*)</h1>'
        r'\s*<div>\s*([A-Za-z]+ \d{1,2}, \d{4})', html_text, re.S)
    if not m:
        raise ValueError("inspection header not found")
    tp = _text(m.group(1))
    if "|" in tp:
        out["inspectionType"], out["purpose"] = \
            [s.strip() for s in tp.split("|", 1)]
    else:
        out["inspectionType"], out["purpose"] = tp, None
    dm = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})", m.group(2))
    out["date"] = "%04d-%02d-%02d" % (int(dm.group(3)),
                                      MONTHS[dm.group(1)],
                                      int(dm.group(2)))
    out["date_written"] = m.group(2)

    # --- printable PDF link (carries the inspectionID)
    m = re.search(r'pKey=([0-9A-Fa-f-]{36})', html_text)
    out["inspectionID"] = m.group(1).upper() if m else None

    # --- score (first <strong> inside the score span; may be empty)
    m = re.search(r'inspection-score-v2.*?Score &amp; Grade:\s*'
                  r'<strong>(.*?)</strong>', html_text, re.S)
    if not m:
        m = re.search(r'inspection-score-v2.*?Score & Grade:\s*'
                      r'<strong>(.*?)</strong>', html_text, re.S)
    raw_score = _text(m.group(1)) if m else ""
    out["score"] = int(raw_score) if raw_score.isdigit() else None
    out["score_raw"] = raw_score

    # --- sections: observations & corrective actions; additional comments
    sections = re.findall(
        r'<h[35] class="observations-header">(.*?)</h[35]>\s*'
        r'<p class="observations-text">(.*?)</p>', html_text, re.S)
    out["observations_entries"] = []
    out["comments"] = None
    for title, body in sections:
        title_t = _text(title)
        if title_t.startswith("Observations"):
            body_html = body
            parts = re.split(r"<br\s*/>\s*<br\s*/>", body_html)
            for part in parts:
                t = _text(part)
                if not t:
                    continue
                em = re.match(r"^(\d{1,2}):\s*(.*)$", t, re.S)
                if em:
                    num, rest = int(em.group(1)), em.group(2).strip()
                    citation, notes = None, rest
                    cm = CITATION_RE.match(rest)
                    if cm and re.search(
                            r"\d{4}-\d{2}-\d{2}", rest[:40]):
                        citation = cm.group(1).strip(" .: ")
                        notes = rest[cm.end():].strip()
                    out["observations_entries"].append(
                        {"item": num, "rule": citation,
                         "notes": notes if notes else None,
                         "raw": t})
                else:
                    out["observations_entries"].append(
                        {"item": None, "rule": None,
                         "notes": t, "raw": t})
        elif title_t.startswith("Additional Comments"):
            c = _text(body)
            out["comments"] = None if c == "No comments" else c

    # --- checklist line items: status label + item title
    items = []
    for block in re.split(r'inspection-line-item-detail', html_text)[1:]:
        lab = re.search(
            r'<span class="(?:in|out|na|no)-label[^"]*"[^>]*>'
            r'([^<]*)</span>', block)
        tit = re.search(r'text-block-11">([^<]+)</div>', block)
        if not (lab and tit):
            continue
        title_t = _text(tit.group(1))
        nm = re.match(r"^(\d{1,2})\s+(.*)$", title_t)
        items.append({
            "item": int(nm.group(1)) if nm else None,
            "title": nm.group(2) if nm else title_t,
            "status": lab.group(1).strip(),
        })
    out["checklist"] = items
    out["out_items"] = [i["item"] for i in items
                        if i["status"].upper() == "OUT"]
    return out


if __name__ == "__main__":
    import json
    import sys
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8", errors="replace") as f:
            parsed = parse_detail(f.read())
        print(json.dumps(parsed, indent=1)[:2600])
        print("=" * 60)
