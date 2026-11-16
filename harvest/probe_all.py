#!/usr/bin/env python3
"""Adapter health probe: one lightweight live request per configured
harvest source. Answers "can harvest still get data from this source
TODAY?" without running a full harvest.

Probes (read-only, minimal payloads):
  * socrata_cities sources   -> $select=count(*) on the dataset
  * mhd states               -> one searchInspections page, 7-day window
  * sfi states               -> GET the PublicInspectionSearch page
  * dhd states               -> GET <host>/<path>/API/index.cfm/clientData
  * bespoke (AL x3, GA, SC, TN, DE, FL, NC) -> portal landing/query

Usage: python harvest/probe_all.py
Exit 0 always; prints one line per source: OK/FAIL + evidence.
"""
import concurrent.futures
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "socrata_cities"))
sys.path.insert(0, os.path.join(ROOT, "mhd"))
sys.path.insert(0, os.path.join(ROOT, "sfi"))
sys.path.insert(0, os.path.join(ROOT, "dhd"))

from sources import SOURCES as SOCO  # noqa: E402
from states import STATES as MHD  # noqa: E402
from sfi_states import STATES as SFI  # noqa: E402
from dhd_states import STATES as DHD  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) KyronProbe/1.0")


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def post_json(url, payload, origin=None, timeout=180):
    hdrs = {"User-Agent": UA, "Content-Type": "application/json"}
    if origin:
        hdrs["Origin"] = origin
        hdrs["Referer"] = origin + "/"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 method="POST", headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def probe_socrata(key, cfg):
    base = f"https://{cfg['domain']}/resource/{cfg['dataset']}.json"
    st, body = get(base + "?$select=count(*)")
    n = int(json.loads(body)[0]["count"])
    return f"{n:,} rows in dataset"


def probe_mhd(key, cfg):
    d1 = datetime.date.today()
    d0 = d1 - datetime.timedelta(days=7)
    payload = {"task": "searchInspections", "data": {
        "path": cfg["path"], "programName": "",
        "filters": {"date": f"{d0.isoformat()} to {d1.isoformat()}",
                    "purpose": "", "county": ""},
        "start": 0, "count": 25, "searchStr": "",
        "lat": 0, "lng": 0, "sort": {}}}
    st, body = post_json("https://inspections.myhealthdepartment.com/",
                         payload,
                         origin="https://inspections.myhealthdepartment.com")
    parsed = json.loads(body)
    if isinstance(parsed, dict) and (parsed.get("err") or parsed.get("error")):
        raise RuntimeError(f"api err: {parsed.get('msg')}")
    if not isinstance(parsed, list):
        raise RuntimeError("response not a list")
    return f"{len(parsed)} rows in last-7d first page"


def probe_sfi(key, cfg):
    st, body = get(cfg["url"])
    text = body.decode("utf-8", "replace")
    if "__VIEWSTATE" not in text and "InspectionSearch" not in text:
        raise RuntimeError("search form fields not found in page")
    return "search form OK"


def probe_dhd(key, cfg):
    api = cfg["host"] + "/" + cfg["path"] + "/API/index.cfm"
    st, body = get(api + "/clientData")
    return f"clientData {len(body)} bytes"


def probe_get(url, marker=None, label=""):
    st, body = get(url)
    if marker and marker not in body.decode("utf-8", "replace"):
        raise RuntimeError(f"marker {marker!r} missing")
    return label or "200 OK"


BESPOKE = [
    ("al-jcdh", lambda: probe_get(
        "https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/"
        "Food/FoodServScores.aspx", label="list page 200")),
    ("al-adph", lambda: probe_get(
        "https://foodscores.state.al.us/default.aspx",
        marker="DrpCnty", label="search form + county select OK")),
    ("al-mchd", lambda: probe_get(
        "https://mchd.org/restaurant-ratings-mobile/",
        marker="geosearch_options", label="ratings page + nonce OK")),
    ("ga-dph", lambda: probe_dhd("ga", {
        "host": "https://ga.healthinspections.us", "path": "stateofgeorgia"})),
    ("sc-dhec", lambda: probe_get(
        "https://services5.arcgis.com/G4BLIH7rTQoIjCFv/arcgis/rest/"
        "services/Restaurants/FeatureServer/0/query"
        "?where=1%3D1&returnCountOnly=true&f=json",
        label="arcgis count query OK")),
    ("tn-tdh", lambda: probe_mhd("tn", {"path": "tennessee"})),
    ("de-dph", lambda: probe_socrata("de", {
        "domain": "data.delaware.gov", "dataset": "384s-wygj"})),
    ("fl-dbpr", lambda: probe_get(
        "https://www2.myfloridalicense.com/hotels-restaurants/"
        "public-records/", label="public-records page 200")),
    ("nc-dhhs", lambda: probe_get(
        "https://public.cdpehs.com/", label="CDPEHS portal 200")),
]


def run_probe(tag, fn):
    try:
        return tag, "OK", fn()
    except Exception as e:  # noqa: BLE001 - probe reports, never raises
        return tag, "FAIL", f"{type(e).__name__}: {str(e)[:140]}"


def main():
    jobs = []
    for key, cfg in SOCO.items():
        jobs.append((f"soco:{key}", lambda c=cfg: probe_socrata(key, c)))
    for key, cfg in MHD.items():
        if cfg.get("enabled"):
            jobs.append((f"mhd:{key}", lambda c=cfg: probe_mhd(key, c)))
    for key, cfg in SFI.items():
        if cfg.get("enabled"):
            jobs.append((f"sfi:{key}", lambda c=cfg: probe_sfi(key, c)))
    for key, cfg in DHD.items():
        if cfg.get("enabled"):
            jobs.append((f"dhd:{key}", lambda c=cfg: probe_dhd(key, c)))
    jobs.extend(BESPOKE)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_probe, tag, fn): tag for tag, fn in jobs}
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())

    ok = fail = 0
    for tag, status, info in sorted(results):
        mark = "OK  " if status == "OK" else "FAIL"
        if status == "OK":
            ok += 1
        else:
            fail += 1
        print(f"{mark} {tag:14s} {info}")
    print(f"\n{ok} sources OK, {fail} FAILED out of {len(results)}")


if __name__ == "__main__":
    main()
