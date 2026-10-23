#!/usr/bin/env python3
"""Delaware pack validator — asserts the built us-de SQLite pack
(harvest/de_socrata/out/us-de-*.db.gz) against every invariant the
slice promised, then prints an honest QA summary. Nothing is uploaded.

Checks (hard asserts; any failure aborts with a message):
  1. pack_meta: region_id == "us-de"; schema_version == the app's
     SUPPORTED_PACK_SCHEMA (2, from
     app/src/main/java/com/kyronapp/kyron/data/db/CatalogDb.kt — value
     pinned here because this script must not import app code);
     dataset_version matches the manifest's datasetVersion
     exactly; place_count == manifest.placeCount == actual row count.
  2. every places row: region_id "us-de", state "DE", source "de-dph".
  3. no invented numeric scores: rows with score >= 0 == 0 in places
     AND inspections (NO_SCORE sentinel is -1 everywhere), and no
     result_text anywhere (violations-only region).
  4. no orphans: every inspections.place_id exists in places.
  5. violations_json rows: every violation is {p:0, c:false,
     r:<non-empty>} — the app's Violation shape with nothing invented.
  6. coordinates: count of places with lat/lng != null (verified,
     source-provided) and without — reported, not hidden. Plus a loose
     Delaware bounding-box sanity range for the verified coordinates.

Printed QA summary: total places, total inspections, total violations,
places with/without coords, inspection date min/max (converted to
ISO from the pack's M/d/yyyy display format), the source window
(from out/fetch_log.json), and the top-12 cities by place count.
"""

import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")

# The pack schema this app build can install. CatalogDb.kt:
#   const val SUPPORTED_PACK_SCHEMA = 2
# (value pinned; this script must not read or import app code)
SUPPORTED_PACK_SCHEMA = 2


def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    gz_files = sorted(f for f in os.listdir(OUT)
                      if re.match(r"^us-de-\d{4}-\d{2}-\d{2}"
                                  r"(\.dev\d+)?\.1\.db\.gz$", f))
    if len(gz_files) != 1:
        fail(f"expected exactly one us-de-*.db.gz in {OUT}, found "
             f"{gz_files}")
    gz_path = os.path.join(OUT, gz_files[0])
    manifest_path = os.path.join(OUT, "us-de.manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # ---- integrity re-verify (like the app: hash before touching rows)
    raw = open(gz_path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != manifest["full"]["sha256"]:
        fail("sha256 mismatch with manifest")
    if len(raw) != manifest["full"]["bytes"]:
        fail("byte length mismatch with manifest")

    # temp DB is a build artifact: keep it (and its deletion) under out/
    tmp_db = os.path.join(OUT, "_validate_tmp.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    with open(tmp_db, "wb") as f:
        f.write(gzip.decompress(raw))
    try:
        con = sqlite3.connect(tmp_db)
        cur = con.cursor()

        # ---- pack_meta -------------------------------------------------
        meta = dict(cur.execute("SELECT k, v FROM pack_meta"))
        if meta.get("region_id") != "us-de":
            fail(f"pack_meta.region_id = {meta.get('region_id')!r}")
        if int(meta.get("schema_version", -1)) != SUPPORTED_PACK_SCHEMA:
            fail(f"pack_meta.schema_version = {meta.get('schema_version')!r}"
                 f" != SUPPORTED_PACK_SCHEMA {SUPPORTED_PACK_SCHEMA}")
        if int(manifest.get("schemaVersion", -1)) != SUPPORTED_PACK_SCHEMA:
            fail("manifest.schemaVersion != app's SUPPORTED_PACK_SCHEMA")
        if meta.get("dataset_version") != manifest["datasetVersion"]:
            fail("pack_meta.dataset_version does not match manifest "
                 "datasetVersion")
        place_count_meta = int(meta.get("place_count", "-1"))
        n_places_actual = cur.execute("SELECT count(*) FROM places"
                                      ).fetchone()[0]
        if not (place_count_meta == manifest["placeCount"]
                == n_places_actual):
            fail(f"place_count mismatch: pack_meta={place_count_meta} "
                 f"manifest={manifest['placeCount']} "
                 f"actual={n_places_actual}")

        # ---- places rows ------------------------------------------------
        bad = cur.execute(
            "SELECT count(*) FROM places WHERE region_id != 'us-de' "
            "OR state != 'DE' OR source != 'de-dph'").fetchone()[0]
        if bad:
            fail(f"{bad} places rows with wrong region/state/source")
        if cur.execute(
                "SELECT count(*) FROM places WHERE score >= 0"
                ).fetchone()[0]:
            fail("places: numeric scores found — invented!")
        if cur.execute(
                "SELECT count(*) FROM inspections WHERE score >= 0"
                ).fetchone()[0]:
            fail("inspections: numeric scores found — invented!")
        if cur.execute(
                "SELECT count(*) FROM places WHERE result_text != ''"
                ).fetchone()[0] or cur.execute(
                "SELECT count(*) FROM inspections WHERE result_text != ''"
                ).fetchone()[0]:
            fail("result_text found — violations-only region carries no "
                 "native result; one was invented")

        # ---- orphans ---------------------------------------------------
        orphans = cur.execute(
            "SELECT count(*) FROM inspections i "
            "WHERE NOT EXISTS (SELECT 1 FROM places p "
            "WHERE p.id = i.place_id)").fetchone()[0]
        if orphans:
            fail(f"{orphans} orphan inspections rows")
        places_without_inspections = cur.execute(
            "SELECT count(*) FROM places p "
            "WHERE NOT EXISTS (SELECT 1 FROM inspections i "
            "WHERE i.place_id = p.id)").fetchone()[0]

        # ---- violation shape --------------------------------------------
        bad_v = 0
        for (vj,) in cur.execute(
                "SELECT violations_json FROM inspections"):
            for v in json.loads(vj):
                if not (v.get("p") == 0 and v.get("c") is False
                        and isinstance(v.get("r"), str) and v["r"]):
                    bad_v += 1
        if bad_v:
            fail(f"{bad_v} violation rows break the {p,c,r} shape / carry "
                 "an empty remark")
        total_viol = sum(
            len(json.loads(vj)) for (vj,) in cur.execute(
                "SELECT violations_json FROM inspections"))

        # ---- QA -------------------------------------------------------
        n_insp = cur.execute("SELECT count(*) FROM inspections"
                             ).fetchone()[0]
        with_coords = cur.execute(
            "SELECT count(*) FROM places WHERE lat IS NOT NULL "
            "AND lng IS NOT NULL").fetchone()[0]
        without_coords = n_places_actual - with_coords
        oob = cur.execute(
            "SELECT count(*) FROM places WHERE lat IS NOT NULL AND "
            "NOT (lat BETWEEN 37 AND 40 AND lng BETWEEN -76 AND -74)"
            ).fetchone()[0]
        dates = [d for (d,) in cur.execute(
            "SELECT date FROM inspections WHERE date != ''")]
        iso = []
        for d in dates:
            d_iso = None
            m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
            if not m and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                d_iso = d
            elif m:
                d_iso = (f"{m.group(3)}-{int(m.group(1)):02d}"
                         f"-{int(m.group(2)):02d}")
            if d_iso:
                iso.append(d_iso)
            else:
                fail(f"unparseable inspection date in pack: {d!r}")
        date_min, date_max = min(iso), max(iso)
        cities = Counter(row[0] for row in cur.execute(
            "SELECT city FROM places WHERE city != ''"))
        top12 = cities.most_common(12)
        fetch_log = json.load(open(os.path.join(OUT, "fetch_log.json"),
                                   encoding="utf-8"))
        qa_report = json.load(open(os.path.join(OUT, "qa_report.json"),
                                   encoding="utf-8"))
        con.close()
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    print("=" * 62)
    print("ALL CHECKS PASSED — us-de pack is internally consistent")
    print("=" * 62)
    print(f"pack file          : {gz_files[0]}")
    print(f"sha256             : {sha}")
    print(f"bytes              : {len(raw):,} (manifest match)")
    print(f"pack_meta                  : "
          f"region_id={meta['region_id']} "
          f"schema_version={meta['schema_version']} "
          f"dataset_version={meta['dataset_version']} "
          f"place_count={place_count_meta:,} "
          f"score_model={meta.get('score_model')}")
    print(f"places rows        : {n_places_actual:,} "
          f"(source de-dph, state DE, region us-de — all rows pass)")
    print(f"inspections rows   : {n_insp:,} (0 orphans)")
    print(f"places w/o any inspection recorded: "
          f"{places_without_inspections:,}")
    print(f"violations         : {total_viol:,} "
          f"(all p=0, c=false, non-empty remarks)")
    print(f"scores >= 0        : 0 in places, 0 in inspections "
          f"(NO_SCORE sentinel only; no invented scores)")
    print(f"result_text != ''  : 0 (violations-only region)")
    print(f"places WITH verified source coordinates     : "
          f"{with_coords:,} ({with_coords / n_places_actual:.1%})")
    print(f"places WITHOUT coordinates         (no source geocode): "
          f"{without_coords:,}")
    print(f"coords outside loose DE bbox (37-40 lat, -76..-74 lng): {oob}"
          f"  (0 expected; counts as source geocode sanity warning)")
    print(f"inspection date range       : {date_min} .. {date_max}")
    print(f"source window (fetch)       : "
          f"{qa_report['inspection_date_min']} .. "
          f"{qa_report['inspection_date_max']} "
          f"(rolling ~2y; {qa_report['inspections_dated_after_2026_10_22']}"
          f" pre-scheduled future-dated rows)")
    print(f"top-12 cities               : {top12}")
    cov_limit = ("captures Delaware DPH food inspections for rolling "
                 "~2-year window; zero-violation establishments are "
                 "ABSENT from the source dataset; NO scores — the DE "
                 "result model is violations-only")
    print(f"coverage limitation         : {cov_limit}")
    report = {
        "validated_at_datasetVersion": manifest["datasetVersion"],
        "checks": [
            "pack_meta region/schema/datasetVersion/place_count OK",
            "places all us-de/DE/de-dph OK",
            "no numeric scores (places+inspections) OK",
            "result_text empty everywhere OK",
            "0 orphan inspections OK",
            f"{total_viol:,} violations in app { '{p,c,r}' } shape OK",
        ],
        "totals": {"places": n_places_actual, "inspections": n_insp,
                   "violations": total_viol,
                   "places_with_coords": with_coords,
                   "places_without_coords": without_coords},
        "inspection_date_min": date_min, "inspection_date_max": date_max,
        "coverage_limitations": cov_limit,
        "sha256": sha, "bytes": len(raw),
    }
    with open(os.path.join(OUT, "validate_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
