#!/usr/bin/env python3
"""Parser for SafeFoodInspection (Food Safety 5.x) portal pages.

Two parse targets:

  parse_results_page(html) -> {"headers": [...], "rows": [master_row]}
      master_row: {estab_key, seq_key, name, address_raw, phone,
                   latest: {date, type, result, viol_uid, report_uid,
                            viol_count},
                   past:   [{date, type, viol_uid, report_uid,
                             viol_count}]}
      The master grid nests each establishment's gvPastInspections
      inside its last cell — rows are extracted depth-aware so nested
      <tr>s never masquerade as master rows.

  parse_violations_panel(html) -> {header, facility, items:[{code,
      explanation, comments}]} for the wucPublicInspectionViolations
      block populated by a lnkViolations postback.

  parse_pdf_observations(pdf_bytes) -> [{num, code, text}] — the
      "Observations and Corrective Actions" table of the official
      report PDF (VT-class deployments where violations ride only in
      the PDF). Pure zlib+regex text extraction; if the stream doesn't
      decode, returns [] — never fabricates.
"""

import html as htmlmod
import re
import zlib

TAG_RE = re.compile(r"</?(table|tr)\b[^>]*>", re.I | re.S)
CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S | re.I)


def _text(fragment):
    t = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _extract_table(html_text, id_pattern):
    """Inner html of the <table ...id=...> block whose id matches
    id_pattern (a regex fragment inside the quotes), balanced against
    nested tables."""
    m = re.search(r'<table\b[^>]*id="(' + id_pattern
                  + r')"[^>]*>', html_text)
    if not m:
        return None
    depth, i = 1, m.end()
    for t in TAG_RE.finditer(html_text, i):
        if t.group(1).lower() == "table":
            depth += 0 if t.group(0).startswith("</") else 1
            if t.group(0).startswith("</"):
                depth -= 1
                if depth == 0:
                    return html_text[m.end():t.start()]
    return html_text[m.end():]


def _iter_top_rows(table_inner):
    """Yield (row_html, row_attrs) for <tr>s at depth 1 — nested
    tables' rows are part of their parent's cell content, never
    yielded."""
    rows = []
    i = 0
    while True:
        m = re.search(r"<tr\b([^>]*)>", table_inner[i:])
        if not m:
            return rows
        start = i + m.start()
        attrs = m.group(1)
        depth_table = 0
        j = i + m.end()
        end = None
        for t in TAG_RE.finditer(table_inner, j):
            tag = t.group(1).lower()
            closing = t.group(0).startswith("</")
            if tag == "table":
                depth_table += -1 if closing else 1
            elif tag == "tr" and depth_table == 0:
                if closing:
                    end = t.end()
                    break
        if end is None:
            end = len(table_inner)
        rows.append((table_inner[start:end], attrs))
        i = end


def _mdy(s):
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", (s or "").strip())
    return ("%04d-%02d-%02d" % (int(m.group(3)), int(m.group(1)),
                              int(m.group(2)))) if m else ""


_NAMEADDR = re.compile(
    r'NonFormattedNameAddress="([^"]*)"')
_KEYSEQ = re.compile(
    r'Key="(\d+)"\s*InspectionSequenceKey="(\d+)"')
_LNK_VIOL = re.compile(
    r"PostBackOptions\(&quot;(ctl00\$[^&]*lnkViolations)&quot;|"
    r'PostBackOptions\("?(ctl00\$[^" ]*lnkViolations)"?')
_REPORT = re.compile(
    r'name="(ctl00\$[^"]*btnInspectionReport)"')
_VIOL_CNT = re.compile(r"Violation\(s\)\s*(\d+)", re.I)


def _inspection_cells(row_html, header_n):
    """date/type/result/jurisdiction from a grid row, by header
    position (headers are parsed, not assumed)."""
    cells = CELL_RE.findall(row_html)
    texts = [_text(c) for c in cells]
    return cells, texts


def _row_controls(row_html):
    vm = _LNK_VIOL.search(row_html)
    viol_uid = next((g for g in (vm.groups() if vm else ()) if g), None)
    rm = _REPORT.search(row_html)
    cm = _VIOL_CNT.search(row_html)
    return {
        "viol_uid": viol_uid,
        "report_uid": rm.group(1) if rm else None,
        "viol_count": int(cm.group(1)) if cm else None,
    }


def parse_results_page(html_text):
    headers = []
    inner = _extract_table(html_text, r'[^"]*gvInspections')
    if inner is None:
        return {"headers": headers, "rows": []}
    out_rows = []
    for row_html, attrs in _iter_top_rows(inner):
        if "GridHeader" in attrs or \
                re.match(r"<tr[^>]*>\s*<th", row_html):
            headers = [_text(c) for c in TH_RE.findall(row_html)]
            continue
        nam = _NAMEADDR.search(attrs)
        cells, texts = _inspection_cells(row_html, len(headers))
        if len(cells) < 3:
            continue
        ks = _KEYSEQ.search(row_html)
        name_raw = nam.group(1) if nam else texts[0]
        # cell0 holds name<BR> + italic street + city/state/zip + phone
        c0 = re.split(r"<br\s*/?>|</div>", cells[0], flags=re.I)
        name = _text(c0[0]) if c0 else ""
        # the portal separates street from 'CITY, ST ZIP' with a run of
        # 2+ spaces in the same italic div — split on the RAW fragment
        # before whitespace is collapsed
        addr_segs = []
        for bit in c0[1:]:
            for seg in re.split(r"\s{2,}", bit):
                if _text(seg):
                    addr_segs.append(_text(seg))
        phone = ""
        if addr_segs and re.search(r"\d{3}[-.)\s]\d{3}[-.]\d{4}",
                                   addr_segs[-1]):
            phone = addr_segs.pop()
        street = city = st = zipc = ""
        csz = None
        for j, seg in enumerate(addr_segs):
            cm = re.match(r"^(.+?),\s*([A-Z]{2})\s+"
                          r"(\d{5}(?:-\d{4})?)\s*$", seg)
            if cm:
                csz = cm
                street = " ".join(addr_segs[:j])
                city, st, zipc = cm.group(1), cm.group(2), cm.group(3)
                break
        if csz is None:
            street = " ".join(addr_segs)
        address = " ".join(addr_segs)
        ctl = _row_controls(row_html)
        latest = {"date": _mdy(texts[1] if len(texts) > 1 else ""),
                  "type": texts[2] if len(texts) > 2 else "",
                  "result": texts[3] if len(texts) > 3 else "",
                  "jurisdiction": (texts[4] if len(texts) > 4 and
                                   len(headers) > 4 and
                                   headers[4].lower() == "jurisdiction"
                                   else ""),
                  **ctl}
        nested = _extract_table(row_html,
                                r'[^"]*gvPastInspections_\d+')
        past = []
        if nested:
            for prow, pattrs in _iter_top_rows(nested):
                if "GridHeader" in pattrs or \
                        re.match(r"<tr[^>]*>\s*<th", prow):
                    continue
                pc, pt = _inspection_cells(prow, 0)
                if len(pc) < 2:
                    continue
                pctl = _row_controls(prow)
                past.append({"date": _mdy(pt[0]),
                             "type": pt[1] if len(pt) > 1 else "",
                             "result": "",
                             **pctl})
        out_rows.append({
            "estab_key": ks.group(1) if ks else None,
            "seq_key": ks.group(2) if ks else None,
            "name_raw": name_raw, "name": name,
            "address": street or address,
            "city": city, "addr_state": st, "zip": zipc,
            "phone": phone,
            "latest": latest, "past": past})
    return {"headers": headers, "rows": out_rows}


_VIOL_PANEL_RE = re.compile(
    r'id="MainContent_wucPublicInspectionViolations_', re.S)
_CODE_LINE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.:()\-/]*$")


def parse_violations_panel(html_text):
    """Extract the populated violations popup; returns None when the
    panel is empty (postback missed / inspection has no violations)."""
    hdr = re.search(
        r'id="MainContent_wucPublicInspectionViolations_lblHeader"'
        r'[^>]*>(.*?)</span>', html_text, re.S)
    fac = re.search(
        r'id="MainContent_wucPublicInspectionViolations'
        r'_lblFacilityInformation"[^>]*>(.*?)</span>', html_text, re.S)
    if not (hdr and _text(hdr.group(1))):
        return None
    i = html_text.find('id="tbPublicInspectionMain"')
    seg = html_text[i:i + 40000] if i >= 0 else html_text
    # cut at the page-load script / footer that trails the table
    for tail in ("function pageLoad", "</body"):
        j = seg.find(tail)
        if j > 0:
            seg = seg[:j]
    items = []
    # each violation renders code text, then 'Explain Code', 'Code
    # Explanation' + text, 'Inspector Comments' + text — walk the flat
    # token stream: a bare code opens a violation, the two labels gate
    # where following text lands
    cur = None
    section = None
    tokens = []
    for m in re.finditer(
            r'<(?:td|span|div)\b[^>]*>(.*?)</(?:td|span|div)>', seg, re.S):
        t = _text(m.group(1))
        if t:
            tokens.append(t)
    for t in tokens:
        if t in ("Code Explanation", "Inspector Comments"):
            section = t
            continue
        if t == "Explain Code":
            continue
        if _CODE_LINE.match(t) and len(t) <= 20 and section is None:
            cur = {"code": t, "explanation": "", "comments": ""}
            items.append(cur)
            continue
        if cur is None:
            continue
        if section == "Code Explanation":
            cur["explanation"] = (cur["explanation"] + " " + t).strip()
        elif section == "Inspector Comments":
            cur["comments"] = (cur["comments"] + " " + t).strip()
        elif not cur["explanation"]:
            cur["explanation"] = t
    return {"header": _text(hdr.group(1)),
            "facility": _text(fac.group(1)) if fac else "",
            "items": items}


def parse_pdf_observations(pdf_bytes):
    """Observations & Corrective Actions rows from the report PDF."""
    streams = re.findall(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S)
    blob = b""
    for s in streams:
        try:
            blob += zlib.decompress(s)
        except Exception:
            pass
    if not blob:
        return []
    # the report generator uses WinAnsi — map its printable high
    # bytes so quotes/dashes/bullets don't render as control chars
    cp1252 = {i: chr(c) for i, c in {
        0x91: 0x2018, 0x92: 0x2019, 0x93: 0x201C, 0x94: 0x201D,
        0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014, 0x85: 0x2026,
    }.items()}
    strings = [m.decode("latin-1").translate(cp1252)
               .replace("\\(", "(").replace("\\)", ")")
               .replace("\\\\", "\\")
               for m in re.findall(rb"\((.*?)\)", blob)]
    text = re.sub(r"\s+", " ", " ".join(strings))
    start = text.find("Observations and Corrective Actions")
    if start < 0:
        return []
    end = text.find("Item Debit Points", start)
    body = text[start:end if end > 0 else start + 12000]
    # rows: "<num> <code> <violation text + comment>" until next num;
    # the code token must contain a digit (5-205.8, 44:02:07:55, 1(a))
    # so wrapped words like "6 inches" can't open a phantom row
    code = r"[0-9A-Za-z.:()\-/]*\d[0-9A-Za-z.:()\-/]*"
    rows = re.findall(
        r"(?:^|\s)(\d{1,2})\s+(" + code + r")\s+"
        r"(.*?)(?=\s+\d{1,2}\s+" + code + r"\s|$)",
        body)
    out = []
    for num, code, txt in rows:
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append({"num": int(num), "code": code, "text": txt})
    return out


VIEWER_URL = re.compile(
    r"window\.open\('(/Common/ExternalFileViewer\.aspx[^']+)'")


if __name__ == "__main__":
    import json
    import sys
    for fname in sys.argv[1:]:
        with open(fname, encoding="utf-8", errors="replace") as f:
            page = parse_results_page(f.read())
        print(json.dumps(page, indent=1)[:4000])
