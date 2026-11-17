#!/usr/bin/env python3
"""Generic SafeFoodInspection (Food Safety 5.x) fetcher.

Resumable WebForms walker per deployment in sfi_states.py:

  session   GET PublicInspectionSearch.aspx -> cookies + ViewState
  window    POST btnSearch with a date range (default 1-year windows
            back to cfg['start_year'], or --from <date>)
  pages     __doPostBack('ctl00$MainContent$gvInspections','Page$N')
            -> raw/<st>/search/<from>_<to>/pNNN.html, fetch_log.tsv
  details   per inspection row: 'Violation(s) N' lnkViolations ->
            postback __EVENTTARGET=uid (+ hfRebindGridOnPostBack,
            hfInspectionSequenceKeysToExpand=<row seq keys>) -> the
            re-rendered page with the populated violations panel ->
            raw/<st>/viol/<estabKey>_<yyyymmdd>.html
            OR (VT-class) btnInspectionReport <uid>.x/.y postback ->
            window.open('/Common/ExternalFileViewer.aspx?...') -> GET
            -> raw/<st>/pdf/<estabKey>_<yyyymmdd>.pdf

Details dedupe by (estab_key, date) filename across overlapping
windows — an establishment appears in every window where it was
inspected, and identical inspection rows re-render with identical
identity, so overlap never double-fetches.

POST pacing is single-threaded (WebForms sessions serialize anyway);
DELAY between posts. Resume re-walks the earliest incomplete window:
saved page files are skipped but the Page$N posts must replay to keep
the session consistent — cheap relative to detail fetches.

Usage:
  python sfi_fetch.py vt [sd wy ...] [--from YYYY-MM-DD] [--nodetails]
"""

import datetime
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import hashlib
import html as htmlmod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfi_states import STATES  # noqa: E402
from sfi_parse import parse_results_page, VIEWER_URL  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
      "KyronResearch/0.1 (SFI generic adapter)")
DELAY = 0.35
MAX_PAGES_PER_WINDOW = 500


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hid(html_text, name):
    m = re.search(r'id="' + re.escape(name) + r'"[^>]*value="([^"]*)"',
                  html_text)
    return m.group(1) if m else ""


class Session:
    def __init__(self, base_url):
        self.base = base_url
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last_html = ""

    def get(self, url, retries=4):
        last = None
        for a in range(retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA, "Referer": self.base})
                with self.opener.open(req, timeout=120) as r:
                    return r.read()
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5 * (2 ** a))
        raise last

    def post(self, fields, retries=4):
        data = urllib.parse.urlencode(fields).encode()
        last = None
        for a in range(retries):
            try:
                req = urllib.request.Request(
                    self.base, data=data,
                    headers={"User-Agent": UA,
                             "Content-Type":
                                 "application/x-www-form-urlencoded",
                             "Referer": self.base})
                with self.opener.open(req, timeout=180) as r:
                    body = r.read()
                self.last_html = body.decode("utf-8", "replace")
                time.sleep(DELAY)
                return self.last_html
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5 * (2 ** a))
        raise last


def base_fields(html_text):
    return {
        "__EVENTTARGET": "", "__EVENTARGUMENT": "", "__LASTFOCUS": "",
        "__VIEWSTATE": hid(html_text, "__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": hid(html_text, "__VIEWSTATEGENERATOR"),
        "__SCROLLPOSITIONX": "0", "__SCROLLPOSITIONY": "0",
        "__EVENTVALIDATION": hid(html_text, "__EVENTVALIDATION"),
        "ctl00$MainContent$hfUseRadius": "",
        "ctl00$MainContent$hfLatitude": "",
        "ctl00$MainContent$hfLongitude": "",
        "ctl00$MainContent$hfRadiusMiles": "",
        "ctl00$MainContent$txtEstablistmentName": "",
        "ctl00$MainContent$txtStreetAddress": "",
        "ctl00$MainContent$txtCity": "",
        "ctl00$MainContent$txtZip": "",
        "ctl00$MainContent$dteInspectionBeginDate$txtDate": "",
        "ctl00$MainContent$dteInspectionEndDate$txtDate": "",
        "ctl00$MainContent$hfViolationInspectionKey": "",
        "ctl00$MainContent$hfRebindGridOnPostBack": "",
        "ctl00$MainContent$hfInspectionSequenceKeysToExpand": "",
    }


def log_fetch(log_path, rel, url, body):
    sha = hashlib.sha256(body).hexdigest()
    line = "\t".join([rel, url, utcnow(), "200",
                      str(len(body)), sha]) + "\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def mdy(d):
    return d.strftime("%m/%d/%Y")


def windows_for(cfg, date_from):
    """Windows from date_from to today. Default 1 year; cfg
    ['window_months'] shortens it for portals that 500 on large
    result sets (WDA cannot render a Wyoming year)."""
    months = cfg.get("window_months", 12)
    today = datetime.date.today()
    out = []
    cur = date_from
    while cur <= today:
        ny, nm = divmod(cur.month - 1 + months, 12)
        ny += cur.year
        nm += 1
        last = (datetime.date(ny + (nm == 12), nm % 12 + 1, 1)
                - datetime.timedelta(days=1)).day
        end = min(cur.replace(year=ny, month=nm,
                              day=min(cur.day, last))
                  - datetime.timedelta(days=1), today)
        out.append((cur, end))
        cur = end + datetime.timedelta(days=1)
    return out


def detail_targets(page):
    """Every fetchable per-inspection detail on a results page."""
    targets = []
    for row in page["rows"]:
        seq = row["seq_key"] or ""
        for ins in [row["latest"], *row["past"]]:
            if not ins["date"]:
                continue
            targets.append({
                "estab_key": row["estab_key"] or "x",
                "seq_key": seq,
                "date": ins["date"],
                "viol_uid": ins.get("viol_uid"),
                "report_uid": ins.get("report_uid"),
            })
    return targets


RECORDS_FOUND = re.compile(r"(\d+)\s+record\(s\)\s+found", re.I)
SERVER_CAP = 500


class WindowOverflow(Exception):
    """The portal hard-caps every query at 500 records (verified
    2026-11-17 across five states). A capped window must be split —
    shipping it as-is would silently drop every establishment past
    the cap."""


def fetch_window(sess, cfg, raw, work, log_path, wfrom, wto, do_details):
    wkey = f"{wfrom.isoformat()}_{wto.isoformat()}"
    wdir = os.path.join(raw, "search", wkey)
    os.makedirs(wdir, exist_ok=True)
    f = base_fields(sess.last_html)
    f.update({
        "ctl00$MainContent$dteInspectionBeginDate$txtDate": mdy(wfrom),
        "ctl00$MainContent$dteInspectionEndDate$txtDate": mdy(wto),
        "ctl00$MainContent$btnSearch": "Search"})
    page_html = sess.post(f)
    found = RECORDS_FOUND.search(page_html)
    if found and int(found.group(1)) >= SERVER_CAP and wto > wfrom:
        raise WindowOverflow(
            f"{wkey}: {found.group(1)} records hits the 500 cap")
    log_fetch(log_path, f"search/{wkey}/p001.html", sess.base,
              page_html.encode())
    with open(os.path.join(wdir, "p001.html"), "w",
              encoding="utf-8") as fh:
        fh.write(page_html)
    stats = {"window": wkey, "pages": 1, "rows": 0, "viol_pages": 0,
             "pdfs": 0, "detail_errors": 0}
    current = page_html
    for pno in range(1, MAX_PAGES_PER_WINDOW + 1):
        page = parse_results_page(current)
        stats["rows"] += len(page["rows"])
        if do_details:
            seq_keys = ",".join(
                sorted({r["seq_key"] for r in page["rows"]
                        if r["seq_key"]}))
            stats = fetch_details(sess, cfg, raw, log_path, wkey,
                                  page, seq_keys, stats, wfrom, wto)
        # next page?
        if f"Page${pno + 1}" not in current:
            break
        f = base_fields(current)
        f.update({
            "__EVENTTARGET": "ctl00$MainContent$gvInspections",
            "__EVENTARGUMENT": f"Page${pno + 1}",
            "ctl00$MainContent$dteInspectionBeginDate$txtDate":
                mdy(wfrom),
            "ctl00$MainContent$dteInspectionEndDate$txtDate": mdy(wto)})
        current = sess.post(f)
        rel = f"search/{wkey}/p{pno + 1:03d}.html"
        log_fetch(log_path, rel, sess.base, current.encode())
        with open(os.path.join(wdir, f"p{pno + 1:03d}.html"), "w",
                  encoding="utf-8") as fh:
            fh.write(current)
        stats["pages"] = pno + 1
    return stats


def fetch_details(sess, cfg, raw, log_path, wkey, page, seq_keys,
                  stats, wfrom, wto):
    host = re.match(r"(https?://[^/]+)", sess.base).group(1)
    # every postback rebinds the grid from the CURRENT form fields —
    # the window's date range must ride on detail clicks too or the
    # server searches with empty criteria and the clicked row's
    # control tree no longer matches
    date_fields = {
        "ctl00$MainContent$dteInspectionBeginDate$txtDate": mdy(wfrom),
        "ctl00$MainContent$dteInspectionEndDate$txtDate": mdy(wto)}
    for t in detail_targets(page):
        fname = t["estab_key"] + "_" + t["date"].replace("-", "")
        if t["viol_uid"]:
            dest = os.path.join(raw, "viol", fname + ".html")
            kind = "viol"
        elif t["report_uid"] and cfg["viols"] in ("pdf", "auto"):
            dest = os.path.join(raw, "pdf", fname + ".pdf")
            kind = "pdf"
        else:
            continue
        if os.path.exists(dest):
            continue
        f = base_fields(sess.last_html)
        f.update(date_fields)
        if kind == "viol":
            f.update({
                "__EVENTTARGET": t["viol_uid"],
                "ctl00$MainContent$hfRebindGridOnPostBack": "true",
                "ctl00$MainContent$"
                "hfInspectionSequenceKeysToExpand": t["seq_key"]})
            try:
                resp = sess.post(f)
            except Exception:
                stats["detail_errors"] += 1
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(resp)
            log_fetch(log_path, f"viol/{fname}.html", sess.base,
                      resp.encode())
            stats["viol_pages"] += 1
        else:
            btn = t["report_uid"]
            f.update({
                "ctl00$MainContent$"
                "hfInspectionSequenceKeysToExpand":
                    t["seq_key"] or seq_keys,
                btn + ".x": "5", btn + ".y": "5"})
            try:
                resp = sess.post(f)
            except Exception:
                stats["detail_errors"] += 1
                continue
            vm = VIEWER_URL.search(resp)
            if not vm:
                stats["detail_errors"] += 1
                continue
            vurl = host + htmlmod.unescape(vm.group(1))
            try:
                pdf = sess.get(vurl)
            except Exception:
                stats["detail_errors"] += 1
                continue
            if not pdf.startswith(b"%PDF"):
                stats["detail_errors"] += 1
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(pdf)
            log_fetch(log_path, f"pdf/{fname}.pdf", vurl, pdf)
            stats["pdfs"] += 1
    return stats


def main():
    args, date_from, i = [], None, 1
    nodetails = False
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--from" and i + 1 < len(sys.argv):
            date_from = datetime.date.fromisoformat(sys.argv[i + 1])
            i += 2
            continue
        if a == "--nodetails":
            nodetails = True
            i += 1
            continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    keys = args or [k for k, c in STATES.items() if c["enabled"]]
    for key in keys:
        cfg = STATES.get(key)
        if cfg is None or not cfg["enabled"]:
            print(f"[skip] {key}", flush=True)
            continue
        raw = os.path.join(ROOT, "raw", key)
        work = os.path.join(ROOT, "work", key)
        os.makedirs(raw, exist_ok=True)
        os.makedirs(work, exist_ok=True)
        log_path = os.path.join(work, "fetch_log.tsv")
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("file\turl\tfetched_utc\thttp_status\tbytes"
                        "\tsha256\n")
        sess = Session(cfg["url"])
        landing = sess.get(cfg["url"])
        sess.last_html = landing.decode("utf-8", "replace")
        d0 = date_from or datetime.date(cfg["start_year"], 1, 1)
        wstats = []
        queue = list(windows_for(cfg, d0))
        while queue:
            wfrom, wto = queue.pop(0)
            wkey = f"{wfrom.isoformat()}_{wto.isoformat()}"
            done_mark = os.path.join(work, f"window_{wkey}.done")
            if os.path.exists(done_mark):
                continue
            try:
                st = fetch_window(sess, cfg, raw, work, log_path,
                                  wfrom, wto, not nodetails)
            except WindowOverflow:
                mid = wfrom + (wto - wfrom) / 2
                queue.insert(0, (mid + datetime.timedelta(days=1), wto))
                queue.insert(0, (wfrom, mid))
                st = {"window": wkey, "split": True}
                print(f"[{key}] {wkey} hit 500-cap -> splitting",
                      flush=True)
            except Exception as e:  # noqa: BLE001
                st = {"window": wkey, "error": str(e)[:200]}
            wstats.append(st)
            if not st.get("split"):
                with open(done_mark, "w", encoding="utf-8") as f:
                    json.dump(st, f, indent=1)
            print(f"[{key}] {st}", flush=True)
        with open(os.path.join(work, "fetch_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"ts": utcnow(), "windows": wstats}, f, indent=1)
    print("SFI FETCH COMPLETE", flush=True)


if __name__ == "__main__":
    main()
