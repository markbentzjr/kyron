#!/usr/bin/env python3
"""Delaware region-pack builder (us-de) — THIN WRAPPER, does not modify
the shared builder.

Why this file exists (genuine shared-builder limitation, reported):
tools/packs/build_pack.py hard-codes every region-specific mapping —
CONVERTERS (line ~409), SCORE_MODELS, JURISDICTIONS, SOURCE_DEFAULTS —
to us-fl / us-ga / us-tn / us-sc, and resolves `--region us-de` to
`converter not implemented`, exiting 2. The four per-region dict
entries cannot be supplied through its CLI. Rather than editing the
shared file (out of scope for the DE slice), this wrapper imports the
shared builder's helpers — PLACES_DDL, INSPECTIONS_DDL, date_key,
normalize_date, iso_to_mdy, SCHEMA_VERSION — and reproduces its main()
flow for us-de with Delaware's own converter and score model.

Delaware's score model is VIOLATIONS_ONLY: dataset 384s-wygj carries
NO numeric score and NO disposition either — one row per violation
code + short description. So:
  * every place and inspection score is the NO_SCORE sentinel (-1)
    (Place.NO_SCORE in the app) and result_text stays EMPTY at every
    level — never derived, never invented;
  * violations ship as the app's {p, c, r} rows with p=0, c=false
    (the source publishes neither points nor a critical flag) and
    r = the normalizer's "CODE violation, DESC" remarks string;
  * coordinates are the source's OWN geocoded_column values. They are
    only shipped when present, with geo_status=ACCEPTED, geo_acc=
    ADDRESS_RANGE (address-level class per the app's Place contract)
    and geo_prov naming the Socrata geocoded column. The shared
    builder's Census-provenance invariant (`geo_prov == "CENSUS"`,
    `geo_match in EXACT/NON_EXACT`) asserts facts that are FALSE for
    Delaware — these coordinates are not Census-geocoded — so this
    wrapper's equivalent invariant is: coordinates present IFF
    geo_status is ACCEPTED with a named provenance provider. Nothing
    is geocoded here and nothing is invented.

Usage (same CLI shape as build_pack.py):
  python build_pack_de.py --source <...>/harvest/de_socrata/out/places.json \
      --region us-de --state DE --name Delaware --limit 0 \
      --out <...>/harvest/de_socrata/out
"""

import gzip
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pack as bp  # noqa: E402  (shared helpers; NOT modified)

SCHEMA_VERSION = bp.SCHEMA_VERSION
JURISDICTION_ID = "DE-DPH"
SOURCE_ID = "de-dph"   # places' `source` value (registry source id)


def convert_de_place(raw: dict) -> dict:
    """DE normalizer record -> canonical Kyron place row (FL/TN shape:
    sentinel scores, empty result_text, published violations intact)."""
    inspections = []
    for insp in raw.get("insp") or []:
        inspections.append({
            "score": -1,                       # NO_SCORE: no score exists
            "date": bp.iso_to_mdy(insp.get("d") or ""),
            "type": insp.get("t") or "",
            "violations": [{"p": v.get("p", 0), "c": v.get("c", False),
                            "r": v.get("r", "")} for v in insp.get("v") or []],
            "result_text": "",                 # violations-only region
        })
    s = raw.get("s")
    return {
        "id": raw["id"],
        "name": raw.get("n") or "",
        "address": raw.get("a") or "",
        "city": raw.get("c") or "",
        "zip": raw.get("z") or "",
        "county": raw.get("ct") or "",         # dataset has no county field
        "score": s if s is not None else -1,
        "date": bp.normalize_date(bp.iso_to_mdy(raw.get("d") or "")),
        "source": SOURCE_ID,
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "detail_url": raw.get("du"),
        "geo_status": raw.get("gs") or "UNRESOLVED",
        "geo_acc": raw.get("ga") or "NONE",
        "geo_prov": raw.get("gp") or "",
        "geo_match": raw.get("gm") or "",
        "state": "DE",
        "jurisdiction": raw.get("jur") or JURISDICTION_ID,
        "region_id": "us-de",
        "result_text": "",
        "inspections": inspections,
    }


def main() -> int:
    ap_args = __import__("argparse").ArgumentParser()
    ap_args.add_argument("--source", required=True)
    ap_args.add_argument("--region", required=True)
    ap_args.add_argument("--state", required=True)
    ap_args.add_argument("--name", required=True)
    ap_args.add_argument("--limit", type=int, default=0,
                         help="dev subset size (0 = full)")
    ap_args.add_argument("--out", default=None)
    args = ap_args.parse_args()
    if args.region != "us-de":
        print("error: build_pack_de.py builds us-de only (shared "
              "build_pack.py owns the other regions)", file=sys.stderr)
        return 2

    with open(args.source, encoding="utf-8") as f:
        raw_places = json.load(f)
    src_manifest = {}
    src_manifest_path = os.path.join(os.path.dirname(args.source),
                                     "manifest.json")
    if os.path.exists(src_manifest_path):
        with open(src_manifest_path, encoding="utf-8") as f:
            src_manifest = json.load(f)

    places = [convert_de_place(p) for p in raw_places]
    if args.limit:
        places = places[: args.limit]

    # ---- validation: Delaware's honesty invariants ---------------------
    # 1. no score ever invented (NO_SCORE sentinel everywhere)
    assert all(p["score"] == -1 for p in places), \
        "DE place carries a numeric score — the dataset has none!"
    assert all(i["score"] == -1 for p in places for i in p["inspections"]), \
        "DE inspection carries a score — the dataset has none!"
    # 2. violations-only => empty result_text at every level
    assert all(p["result_text"] == "" for p in places), \
        "DE place carries a result_text — DE publishes neither a score " \
        "nor a disposition; one was invented!"
    assert all(i["result_text"] == "" for p in places
               for i in p["inspections"]), \
        "DE inspection carries a result_text — invented!"
    # 3. violation rows: p=0, c=false always; every remark non-empty
    assert all(v["p"] == 0 and v["c"] is False and v["r"]
               for p in places for i in p["inspections"]
               for v in i["violations"]), \
        "DE violation shape broken (points/critical/remark)!"
    # 4. state/region integrity
    assert all(p["state"] == args.state and p["region_id"] == args.region
               for p in places)
    # 5. geo invariant (DE-equivalent of the shared builder's Census
    #    assertion — see module docstring): coordinates exist IFF
    #    ACCEPTED with named provenance; never a bare coordinate.
    for p in places:
        has = p["lat"] is not None and p["lng"] is not None
        claimed = (p["geo_status"] == "ACCEPTED"
                   and bool(p["geo_prov"])
                   and p["geo_acc"] == "ADDRESS_RANGE")
        assert has == claimed, \
            f"DE geo/provenance mismatch for {p['id']}"

    n_insp = sum(len(p["inspections"]) for p in places)
    n_viol = sum(len(i["violations"]) for p in places
                 for i in p["inspections"])

    generated_at = (src_manifest.get("generated_at")
                    or datetime.now(timezone.utc).isoformat())
    day = generated_at[:10]
    version = f"{day}.1" if not args.limit else f"{day}.dev{args.limit}"

    out_dir = args.out or os.path.join(os.path.dirname(args.source),
                                       "out")
    os.makedirs(out_dir, exist_ok=True)
    db_name = f"{args.region}-{version}.db"
    db_path = os.path.join(out_dir, db_name)
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("CREATE TABLE pack_meta(k TEXT PRIMARY KEY, v TEXT)")
    cur.execute(bp.PLACES_DDL)
    cur.execute(bp.INSPECTIONS_DDL)
    meta = {
        "region_id": args.region,
        "state": args.state,
        "dataset_version": version,
        "generated_at": generated_at,
        "place_count": str(len(places)),
        "schema_version": str(SCHEMA_VERSION),
        "score_model": "VIOLATIONS_ONLY",
        "source": ("Delaware Division of Public Health — Food "
                   "Establishment Inspection Violations, Socrata "
                   "dataset 384s-wygj (data.delaware.gov)"),
    }
    cur.executemany("INSERT INTO pack_meta VALUES (?,?)",
                    list(meta.items()))
    cols = ("id,name,name_lc,address,city,zip,county,score,date,date_key,"
            "source,lat,lng,geo_status,geo_acc,geo_prov,geo_match,"
            "detail_url,state,jurisdiction,region_id,result_text")
    ph = ",".join("?" * 22)
    for p in places:
        cur.execute(f"INSERT INTO places ({cols}) VALUES ({ph})", (
            p["id"], p["name"], p["name"].lower(), p["address"],
            p["city"], p["zip"], p["county"], p["score"], p["date"],
            bp.date_key(p["date"]), p["source"], p["lat"], p["lng"],
            p["geo_status"], p["geo_acc"], p["geo_prov"], p["geo_match"],
            p["detail_url"], p["state"], p["jurisdiction"], p["region_id"],
            p["result_text"],
        ))
        for idx, insp in enumerate(p["inspections"]):
            cur.execute(
                "INSERT INTO inspections"
                " (place_id,idx,score,date,type,violations_json,result_text)"
                " VALUES (?,?,?,?,?,?,?)",
                (p["id"], idx, insp["score"], insp["date"], insp["type"],
                 json.dumps(insp["violations"], ensure_ascii=False),
                 insp["result_text"]),
            )
    con.commit()
    con.close()

    gz_name = db_name + ".gz"
    gz_path = os.path.join(out_dir, gz_name)
    with open(db_path, "rb") as f_in, gzip.GzipFile(
            filename="", mode="wb", fileobj=open(gz_path, "wb"), mtime=0
            ) as gz:
        gz.write(f_in.read())
    os.remove(db_path)

    raw = open(gz_path, "rb").read()
    manifest = {
        "regionId": args.region,
        "displayName": args.name,
        "state": args.state,
        "status": "available",
        "datasetVersion": version,
        "generatedAt": generated_at,
        "placeCount": len(places),
        "schemaVersion": SCHEMA_VERSION,
        "minAppVersion": "2.0",
        "full": {"file": gz_name, "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()},
        "delta": None,
        "jurisdictions": [{"jurisdictionId": JURISDICTION_ID,
                           "name": "Delaware Division of Public Health "
                                   "(statewide)"}],
    }
    manifest_path = os.path.join(out_dir,
                                 f"{args.region}.manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=1)

    print(f"pack: {gz_path} ({len(raw):,} bytes, "
          f"sha256 {manifest['full']['sha256'][:16]}…)")
    print(f"manifest: {manifest_path}")
    print(f"places={len(places):,} inspections={n_insp:,} "
          f"violations={n_viol:,} scores_invented=0 "
          f"score_model=VIOLATIONS_ONLY (nativeResult empty everywhere)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
