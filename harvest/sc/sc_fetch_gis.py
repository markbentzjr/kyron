#!/usr/bin/env python3
"""Kyron SC adapter — AGOL FeatureServer fetcher (prototype v0.1).

Pulls the complete SC Food Grades GIS backend (the same public service
the official dataviz app at dataviz.dph.sc.gov/foodgrades/ queries):

  layer 0  "Restaurants"          establishment points (permit universe,
                                  addresses, legacy geocode snapshot)
  table 4  "Restaurants_Steton"   inspection rows: PERMIT_ID, POSTED_GRADE,
                                  AC_CODE, INSP_DATE, AuditResultGlobalID

Paging contract (measured 2026-10-15): maxRecordCount = 2000, standard
resultOffset/resultRecordCount paging with orderByFields=OBJECTID is
stable. Every page response is saved raw and logged with SHA-256 in
fetch_log.tsv. Resumable: existing complete pages are skipped.

No account, no key, $0. Public ArcGIS REST query endpoint.
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = ("https://services5.arcgis.com/G4BLIH7rTQoIjCFv/arcgis/rest/"
        "services/Restaurants/FeatureServer")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
LOG = os.path.join(HERE, "fetch_log.tsv")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
PAGE = 2000


def log(url, path, status, body):
    sha = hashlib.sha256(body).hexdigest()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rel = os.path.relpath(path, HERE)
    with open(LOG, "a") as fh:
        fh.write(f"{rel}\t{url}\t{ts}\t{status}\t{len(body)}\t{sha}\n")


def fetch(url, path, retries=5):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as fh:
            body = fh.read()
        try:
            d = json.loads(body)
            if "error" not in d:
                return d
        except Exception:
            pass
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                status = resp.status
            d = json.loads(body)
            if "error" in d:
                raise RuntimeError(f"arcgis error: {d['error']}")
            with open(path, "wb") as fh:
                fh.write(body)
            log(url, path, status, body)
            return d
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed after {retries} tries: {url}: {last}")


def pull(layer_id, subdir, out_fields, geometry):
    outdir = os.path.join(RAW, subdir)
    os.makedirs(outdir, exist_ok=True)
    q = urllib.parse.urlencode({
        "where": "1=1", "returnCountOnly": "true", "f": "json"})
    cnt = fetch(f"{BASE}/{layer_id}/query?{q}",
                os.path.join(outdir, "_count.json"))["count"]
    print(f"layer {layer_id}: {cnt} rows", flush=True)
    offset = 0
    seen = 0
    while offset < cnt:
        params = {
            "where": "1=1", "outFields": out_fields,
            "orderByFields": "OBJECTID", "resultOffset": offset,
            "resultRecordCount": PAGE, "returnGeometry": str(geometry).lower(),
            "outSR": "4326", "f": "json",
        }
        url = f"{BASE}/{layer_id}/query?{urllib.parse.urlencode(params)}"
        d = fetch(url, os.path.join(outdir, f"page_{offset:07d}.json"))
        feats = d.get("features", [])
        if not feats:
            raise RuntimeError(f"layer {layer_id}: empty page at {offset}")
        seen += len(feats)
        offset += len(feats)
        print(f"  {subdir}: {seen}/{cnt}", flush=True)
    if seen != cnt:
        raise RuntimeError(f"layer {layer_id}: got {seen}, expected {cnt}")
    return cnt


def main():
    if not os.path.exists(LOG):
        with open(LOG, "w") as fh:
            fh.write("file\turl\tfetched_utc\thttp_status\tbytes\tsha256\n")
    pull(0, "gis_layer0",
         "OBJECTID,PROG_CODE,ZIPCODE,PERMIT_ID,FACILITY,ADDRESS,CITY,STATE,"
         "INSP_DATE,MAX_DATE,Loc_name", True)
    pull(4, "gis_steton",
         "OBJECTID,PROG_CODE,PERMIT_ID,COUNTY,ADDRESS,CITY,STATE,ZIPCODE,"
         "SCORE,POSTED_GRADE,FACILITY,AC_CODE,INSP_DATE,AuditResultGlobalID,"
         "AuditTypeName,Insp_Num,CountyName,Active", False)
    print("GIS fetch complete.")


if __name__ == "__main__":
    sys.exit(main())
