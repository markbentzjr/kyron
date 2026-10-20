#!/usr/bin/env python3
"""Parser for CDPEHS violation-detail pages (INSPECTION_VIOLATION)."""
import re
import html as ihtml

def clean(s):
    if s is None:
        return ""
    s = re.sub(r'<br\s*/?>', ' ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = ihtml.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()

def _fls_value(html, label):
    """Value cell following a <td class="fls">LABEL</td> (label may be
    wrapped in a span). Returns raw inner HTML or None."""
    pat = (r'<td class="fls">(?:<span[^>]*>)?\s*' + re.escape(label) +
           r'\s*(?:</span>)?\s*</td>\s*<td[^>]*class="dfv"[^>]*>(.*?)</td>')
    m = re.search(pat, html, re.S)
    return m.group(1) if m else None

def _nested_values(html, label, n):
    pat = (r'<td class="fls">(?:<span[^>]*>)?\s*' + re.escape(label) +
           r'\s*(?:</span>)?\s*</td>\s*<td><table[^>]*>\s*<tr>\s*' +
           r'</td>'.join([r'<td class="dfv">(.*?)</td>'] * n))
    m = re.search(pat, html, re.S)
    return list(m.groups()) if m else None

CITE_RE = re.compile(r'^(\d+-\d{3}\.\d{1,4}[A-Za-z]?)\s+(.*)$', re.S)

def split_rule(comment):
    """NC narratives are '<citation> <rule text> (P/Pf/C) <narrative>'.
    rule = the FDA Food Code citation; notes = the remainder verbatim."""
    m = CITE_RE.match(comment or "")
    if m:
        return m.group(1), m.group(2).strip()
    return None, (comment or "")

def parse_score(s):
    s = (s or "").strip()
    if s == "":
        return None
    f = float(s)
    return int(f) if f == int(f) else f

def parse_page(html):
    out = {}
    out["name"] = clean(_fls_value(html, "Name"))
    out["addr1"] = clean(_fls_value(html, "Address"))
    m = re.search(r'<td class="fls">Address</td><td class="dfv">.*?</td></tr>'
                  r'<tr><td class="fls"></td><td class="dfv">(.*?)</td>', html, re.S)
    out["addr2"] = clean(m.group(1)) if m else ""
    if out["addr2"] in ("&nbsp;",):
        out["addr2"] = ""
    csz = _nested_values(html, "City/State/ZIP", 3)
    out["city"], out["state"], out["zip"] = [clean(x) for x in csz] if csz else ("", "", "")
    out["ptype_label"] = clean(_fls_value(html, "Premise Type"))
    out["county"] = clean(_fls_value(html, "County"))
    out["date_str"] = clean(_fls_value(html, "Inspection Date"))
    sg = _nested_values(html, "Final Score @ Grade", 2)
    out["score_str"] = clean(sg[0]) if sg else ""
    out["grade_str"] = clean(sg[1]) if sg else ""
    out["comments"] = clean(_fls_value(html, "General Comments")) or None
    # violations
    viols = []
    parts = re.split(
        r'<tr id="ctl00_PageContent_INSPECTION_VIOLATIONTableControlRepeater_ctl\d+_critvio">',
        html)
    for block in parts[1:]:
        cells = re.findall(r'<td class="ttc"[^>]*>(.*?)</td>', block, re.S)[:7]
        if len(cells) < 7:
            viols.append({"parse_error": f"{len(cells)} cells"})
            continue
        item_s, dem_s, title, cdi, r_, vr, comment = [clean(c) for c in cells]
        try:
            item = int(item_s)
        except ValueError:
            item = item_s
        try:
            points = float(dem_s)
            if points == int(points):
                points = int(points)
        except ValueError:
            points = None
        rule, notes = split_rule(comment)
        viols.append({
            "item": item, "title": title, "rule": rule, "notes": notes,
            "points": points,
            "corrected": cdi == "Yes", "repeat": r_ == "Yes", "vr": vr == "Yes",
        })
    out["violations"] = viols
    return out

def date_iso(date_str):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', (date_str or "").strip())
    if not m:
        return None
    mm, dd, y = int(m.group(1)), int(m.group(2)), m.group(3)
    return f"{y}-{mm:02d}-{dd:02d}"

def date_draw(date_str):
    months = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
    iso = date_iso(date_str)
    if not iso:
        return date_str
    y, mm, dd = iso.split("-")
    return f"{months[int(mm)-1]} {int(dd)}, {y}"
