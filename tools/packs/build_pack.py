#!/usr/bin/env python3
"""
Kyron region-pack builder (LF-4).

Builds a versioned, integrity-manifested region pack from a normalized
jurisdiction dataset, per the Free/LocalFirst gameplan §2.2:

  <region>-<datasetVersion>.db.gz   prebuilt SQLite DB (catalog v2 schema
                                    + pack_meta), gzip-compressed
  <region>.manifest.json            regionId, datasetVersion, placeCount,
                                    schemaVersion, full{file,bytes,sha256}

The app verifies the SHA-256, the pack's own pack_meta, and the exact
place count against the manifest before it swaps a single row in — a
corrupt pack can never reach the catalog.

First proof region: Florida, from the FL DBPR prototype's normalized
output (~/kyron-build/harvest/fl_dbpr/OUTPUT/places_fl.json). Florida
publishes NO numeric score: every place/inspection is written with the
NO_SCORE sentinel (-1) and its native DBPR disposition preserved
verbatim in result_text. Nothing is converted, estimated, or invented.

Second region: Georgia (Workstream C3), from the GA DPH prototype's
geocoded output (~/kyron-build/harvest/ga/OUTPUT/places_ga_geocoded.json).
Georgia publishes a native 0-100 score with state grade bands
A 90-100 / B 80-89 / C 70-79 / U <70: the score ships in `score`, the
band verbatim in `result_text` (place and per-inspection), and the
violation narratives ship in violations_json in the app's {p, c, r}
shape (see convert_ga_place). Nothing is converted or invented there
either — the band is the state's own, copied from the source record.

Third region: Tennessee (Workstream C6), from the TN DOH prototype's
geocoded output (~/kyron-build/harvest/tn/OUTPUT/places_tn_geocoded.json).
Tennessee publishes a native 0-100 score and NO letter grade (the
portal's grade element ships hidden and empty): the score ships in
`score`, `result_text` stays empty at place and inspection level —
never derived from the score — and the itemized violations ship in
{p, c, r} rows (see convert_tn_place). Scoreless source records (155
inspections; 24 places whose newest visit is scoreless) ship as the
NO_SCORE sentinel (-1) for that record only, never estimated.

Fourth region: South Carolina (Workstream C7), from the SCDA prototype's
geocoded output (~/kyron-build/harvest/sc/OUTPUT/places_sc_geocoded.json).
South Carolina is the mirror image of Tennessee: it publishes a posted
letter grade (A/B/C/N/A/S) and its 100-point score exists ONLY inside
the per-inspection PDF reports — the GIS SCORE column is null on every
row and the search portal shows the grade only. So the grade ships
verbatim in `result_text` (place and per-inspection, like GA's band)
and every score ships as the NO_SCORE sentinel (-1): a score is NEVER
derived from the grade, even though the program publishes band edges.
Violations likewise exist only inside the PDFs, so violations ship
empty and each inspection's official PDF rides in detail_url — the
app's no-score detail path opens it externally ("View official
record"); the app's HTML detail fetch is unreachable for sentinel-score
places (see the C7 report for the code evidence). SC therefore uses
the DISPOSITION score model, Florida's shape exactly.

Usage:
  python3 build_pack.py --source ~/kyron-build/harvest/fl_dbpr/OUTPUT/places_fl.json \
      --region us-fl --state FL --name Florida --limit 0
  python3 build_pack.py --source ~/kyron-build/harvest/ga/OUTPUT/places_ga_geocoded.json \
      --region us-ga --state GA --name Georgia --limit 0
  python3 build_pack.py --source ~/kyron-build/harvest/tn/OUTPUT/places_tn_geocoded.json \
      --region us-tn --state TN --name Tennessee --limit 0
  python3 build_pack.py --source ~/kyron-build/harvest/sc/OUTPUT/places_sc_geocoded.json \
      --region us-sc --state SC --name "South Carolina" --limit 0
  --limit N builds a development subset pack (separate output dir).
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = 2

PLACES_DDL = """CREATE TABLE places(
    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_lc TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
    zip TEXT NOT NULL DEFAULT '', county TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
    date_key INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    lat REAL, lng REAL,
    geo_status TEXT NOT NULL DEFAULT 'LEGACY',
    geo_acc TEXT NOT NULL DEFAULT 'NONE',
    geo_prov TEXT NOT NULL DEFAULT '',
    geo_match TEXT NOT NULL DEFAULT '',
    detail_url TEXT,
    state TEXT NOT NULL DEFAULT 'AL',
    jurisdiction TEXT NOT NULL DEFAULT '',
    region_id TEXT NOT NULL DEFAULT 'us-al',
    result_text TEXT NOT NULL DEFAULT '')"""

INSPECTIONS_DDL = """CREATE TABLE inspections(
    place_id TEXT NOT NULL, idx INTEGER NOT NULL,
    score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '', violations_json TEXT NOT NULL DEFAULT '[]',
    result_text TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(place_id, idx))"""

EPOCH = datetime(1970, 1, 1)


def date_key(mdy: str) -> int:
    """Epoch-day key for an M/d/yyyy date (0 when unparseable), matching
    the app's CatalogDb.dateKey closely enough for same-region sorting
    (pack rows are only ever sorted against other pack rows)."""
    if not mdy:
        return 0
    try:
        dt = datetime.strptime(mdy.strip(), "%m/%d/%Y")
        return (dt - EPOCH).days
    except ValueError:
        return 0


def normalize_date(mdy: str) -> str:
    """'10/08/2026' -> '10/8/2026' (the display format used across Kyron)."""
    if not mdy:
        return ""
    try:
        dt = datetime.strptime(mdy.strip(), "%m/%d/%Y")
        return f"{dt.month}/{dt.day}/{dt.year}"
    except ValueError:
        return mdy


def convert_fl_place(raw: dict) -> dict:
    """FL DBPR normalized record -> canonical Kyron place row.

    The conversion changes FORMAT only. Scores stay absent (-1 sentinel);
    dispositions are carried verbatim; violation categories keep the
    department's own wording (prefixed with its DBPR code, the way AL
    rows carry their code prefix)."""
    inspections = []
    for insp in raw.get("insp") or []:
        viols = []
        for v in insp.get("v") or []:
            r = f"{v.get('code', '')} {v.get('r', '')}".strip()
            cnt = v.get("cnt") or 1
            if cnt and cnt > 1:
                r += f" ({cnt} findings)"
            viols.append({"p": 0, "c": False, "r": r})
        inspections.append({
            "score": -1,
            "date": normalize_date(insp.get("draw") or insp.get("d") or ""),
            "type": insp.get("t") or "",
            "violations": viols,
            "result_text": insp.get("disp") or "",
        })
    return {
        "id": raw["id"],
        "name": raw.get("n") or "",
        "address": raw.get("a") or "",
        "city": raw.get("c") or "",
        "zip": raw.get("z") or "",
        "county": raw.get("ct") or "",
        "score": -1,
        "date": normalize_date(raw.get("d") or ""),
        "source": "FL-DBPR",
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "detail_url": raw.get("du"),
        "geo_status": raw.get("gs") or "UNRESOLVED",
        "geo_acc": raw.get("ga") or "NONE",
        "geo_prov": raw.get("gp") or "",
        "geo_match": raw.get("gm") or "",
        "state": "FL",
        "jurisdiction": raw.get("jur") or "FL-DBPR",
        "region_id": "us-fl",
        "result_text": raw.get("disp") or "",
        "inspections": inspections,
    }


def iso_to_mdy(iso: str) -> str:
    """'2026-06-04' -> '6/4/2026' (the display format used across Kyron)."""
    if not iso:
        return ""
    try:
        dt = datetime.strptime(iso.strip(), "%Y-%m-%d")
        return f"{dt.month}/{dt.day}/{dt.year}"
    except ValueError:
        return iso


def _ga_critical(v: dict) -> bool:
    """Map a GA violation to the app's `critical` flag.

    Georgia prints the FDA Food Code designation in every rule citation's
    trailing marker group: (p) = Priority, (pf) = Priority foundation,
    (c) = Core. Priority items are the FDA scheme's critical class —
    the direct analog of JCDH's native critical flag for Alabama. The
    flag is read from the source's own marker only; nothing is inferred
    from the item code or the narrative."""
    import re as _re
    m = _re.search(r"\(([^()]*)\)\s*$", v.get("rule") or "")
    if not m:
        return False
    toks = {t.strip() for t in m.group(1).replace(",", " ").split()}
    return "p" in toks


def convert_ga_place(raw: dict) -> dict:
    """GA DPH normalized record -> canonical Kyron place row.

    Format-only conversion, mirroring convert_fl_place's discipline:
      * place/inspection scores are Georgia's native 0-100, verbatim;
        the 8 source inspections with a blank Score column ship as the
        NO_SCORE sentinel (-1) for that visit only — never guessed;
      * the state grade band (A/B/C/U) ships verbatim in result_text,
        at place level (latest) and per inspection;
      * violations become the app's {p, c, r} rows: p = the state's own
        points deducted; c = FDA Priority designation from the citation
        (see _ga_critical); r = "<item> <title> — <rule citation>" plus
        the source's corrected/repeat flags, then "// " + the
        inspector's narrative notes verbatim (the AL remarks shape the
        app's Violation.ruleText / inspectorNote split on).
    """
    inspections = []
    for insp in raw.get("insp") or []:
        viols = []
        for v in insp.get("v") or []:
            head = f"{v.get('item', '')} {v.get('title', '')}".strip()
            rule = (v.get("rule") or "").strip()
            if rule:
                head = f"{head} — {rule}" if head else rule
            if v.get("corrected"):
                head += " · corrected on site"
            if v.get("repeat"):
                head += " · repeat violation"
            notes = (v.get("notes") or "").strip()
            r = head + (f" // {notes}" if notes else "")
            viols.append({"p": v.get("points") or 0, "c": _ga_critical(v), "r": r})
        s = insp.get("s")
        inspections.append({
            "score": s if s is not None else -1,
            "date": iso_to_mdy(insp.get("d") or ""),
            "type": insp.get("t") or "",
            "violations": viols,
            "result_text": insp.get("grade") or "",
        })
    return {
        "id": raw["id"],
        "name": raw.get("n") or "",
        "address": raw.get("a") or "",
        "city": raw.get("c") or "",
        "zip": raw.get("z") or "",
        "county": raw.get("ct") or "",
        "score": raw["s"],
        "date": normalize_date(raw.get("d") or ""),
        "source": "GA-DPH",
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "detail_url": raw.get("du"),
        "geo_status": raw.get("gs") or "UNRESOLVED",
        "geo_acc": raw.get("ga") or "NONE",
        "geo_prov": raw.get("gp") or "",
        "geo_match": raw.get("gm") or "",
        "state": "GA",
        "jurisdiction": raw.get("jur") or "GA-DPH",
        "region_id": "us-ga",
        "result_text": raw.get("grade") or "",
        "inspections": inspections,
    }


def convert_tn_place(raw: dict) -> dict:
    """TN DOH normalized record -> canonical Kyron place row.

    Format-only conversion, mirroring convert_ga_place's discipline:
      * place/inspection scores are Tennessee's native 0-100, verbatim;
        the 155 source inspections with no published score — and the 24
        places whose newest inspection is scoreless — ship as the
        NO_SCORE sentinel (-1) for that record only, never estimated;
      * Tennessee publishes NO letter grade, so result_text stays
        EMPTY at place and inspection level — never derived from the
        score (the deliberate divergence from GA, where the state
        itself publishes the band);
      * violations become the app's {p, c, r} rows: p = 0 (TN
        publishes no per-violation points); c = False (TN marks no
        critical/priority flag in its published data — the flag is set
        only where a source itself marks it, cf. GA's (p) citations and
        JCDH's native flag, and is never inferred from the item
        number); r = "<item> <title> — <rule citation>" plus
        "// " + the inspector's narrative verbatim where the portal
        prints one (blank narratives ship absent, never paraphrased).
        The checklist `status` is the outcome that selected the row
        into the source's violation list; per the GA precedent it is
        selection metadata and is not duplicated into r.
      * dates arrive ISO (yyyy-mm-dd) and are normalized to the
        M/d/yyyy display format every other region ships.
    """
    inspections = []
    for insp in raw.get("insp") or []:
        viols = []
        for v in insp.get("v") or []:
            head = f"{v.get('item', '')} {v.get('title', '')}".strip()
            rule = (v.get("rule") or "").strip()
            if rule:
                head = f"{head} — {rule}" if head else rule
            notes = (v.get("notes") or "").strip()
            r = head + (f" // {notes}" if notes else "")
            viols.append({"p": 0, "c": False, "r": r})
        s = insp.get("s")
        inspections.append({
            "score": s if s is not None else -1,
            "date": iso_to_mdy(insp.get("d") or ""),
            "type": insp.get("t") or "",
            "violations": viols,
            "result_text": "",
        })
    s = raw.get("s")
    return {
        "id": raw["id"],
        "name": raw.get("n") or "",
        "address": raw.get("a") or "",
        "city": raw.get("c") or "",
        "zip": raw.get("z") or "",
        "county": raw.get("ct") or "",
        "score": s if s is not None else -1,
        "date": iso_to_mdy(raw.get("d") or ""),
        "source": "TN-DOH",
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "detail_url": raw.get("du"),
        "geo_status": raw.get("gs") or "UNRESOLVED",
        "geo_acc": raw.get("ga") or "NONE",
        "geo_prov": raw.get("gp") or "",
        "geo_match": raw.get("gm") or "",
        "state": "TN",
        "jurisdiction": raw.get("jur") or "TN-DOH",
        "region_id": "us-tn",
        "result_text": "",
        "inspections": inspections,
    }


def convert_sc_place(raw: dict) -> dict:
    """SCDA normalized record -> canonical Kyron place row.

    Format-only conversion, mirroring convert_fl_place's discipline
    (South Carolina is a DISPOSITION-model region, Florida's shape):
      * the posted letter grade (A/B/C/N/A/S) ships verbatim in
        result_text, at place level (newest) and per inspection;
      * every score ships as the NO_SCORE sentinel (-1): SC's numeric
        score exists only inside the per-inspection PDF reports (the
        GIS SCORE column is null on all 137,087 spine rows; the portal
        shows grade only). A score is NEVER derived from the grade,
        even though the program publishes the band edges — a band is
        not a score;
      * violations ship empty ([]): itemized violations likewise exist
        only inside the PDFs. Each inspection's official PDF URL is
        the source's own `du`; the place-level detail_url carries the
        newest inspection's PDF, which the app's no-score detail path
        opens externally ("View official record") — the app's HTML
        detail fetch is unreachable for sentinel-score places (the
        fetch requires a numeric score and an empty inspection list;
        SC places always carry inspections). Nothing is fetched or
        parsed in-app;
      * the ZIP is normalized to its 5-digit form (the same value the
        Census pipeline submits): the prototype output carries 2,043
        records in a 9-character zero-suffixed / ZIP+4-concatenated
        form and a handful zero-padded — every other region ships
        5-digit ZIPs, and no other address field changes;
      * dates arrive ISO (yyyy-mm-dd) and are normalized to the
        M/d/yyyy display format every other region ships.
    """
    import re as _re
    m = _re.search(r"\d{5}", raw.get("z") or "")
    inspections = []
    for insp in raw.get("insp") or []:
        inspections.append({
            "score": -1,
            "date": iso_to_mdy(insp.get("d") or ""),
            "type": insp.get("t") or "",
            "violations": [],
            "result_text": insp.get("grade") or "",
        })
    return {
        "id": raw["id"],
        "name": raw.get("n") or "",
        "address": raw.get("a") or "",
        "city": raw.get("c") or "",
        "zip": m.group(0) if m else "",
        "county": raw.get("ct") or "",
        "score": -1,
        "date": iso_to_mdy(raw.get("d") or ""),
        "source": "SCDA",
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "detail_url": raw.get("du"),
        "geo_status": raw.get("gs") or "UNRESOLVED",
        "geo_acc": raw.get("ga") or "NONE",
        "geo_prov": raw.get("gp") or "",
        "geo_match": raw.get("gm") or "",
        "state": "SC",
        "jurisdiction": raw.get("jur") or "SCDA",
        "region_id": "us-sc",
        "result_text": raw.get("grade") or "",
        "inspections": inspections,
    }


CONVERTERS = {"us-fl": convert_fl_place, "us-ga": convert_ga_place,
              "us-tn": convert_tn_place, "us-sc": convert_sc_place}
SCORE_MODELS = {"us-fl": "DISPOSITION", "us-ga": "SCORE_100",
                "us-tn": "SCORE_100", "us-sc": "DISPOSITION"}
JURISDICTIONS = {
    "us-fl": [{"jurisdictionId": "FL-DBPR", "name": "Florida DBPR (statewide)"}],
    "us-ga": [{"jurisdictionId": "GA-DPH", "name": "Georgia DPH (statewide)"}],
    "us-tn": [{"jurisdictionId": "TN-DOH", "name": "Tennessee Dept. of Health (statewide)"}],
    "us-sc": [{"jurisdictionId": "SCDA", "name": "South Carolina Dept. of Agriculture (statewide)"}],
}
SOURCE_DEFAULTS = {"us-fl": "Florida DBPR", "us-ga": "Georgia DPH",
                   "us-tn": "Tennessee Dept. of Health",
                   "us-sc": "South Carolina Dept. of Agriculture"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--limit", type=int, default=0, help="dev subset size (0 = full)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.source) as f:
        raw_places = json.load(f)
    src_manifest_path = os.path.join(os.path.dirname(args.source), "manifest.json")
    src_manifest = {}
    if os.path.exists(src_manifest_path):
        with open(src_manifest_path) as f:
            src_manifest = json.load(f)

    converter = CONVERTERS.get(args.region)
    if converter is None:
        print(f"error: converter for {args.region} not implemented "
              f"(have: {', '.join(sorted(CONVERTERS))})", file=sys.stderr)
        return 2

    places = [converter(p) for p in raw_places]
    if args.limit:
        places = places[: args.limit]

    # ---- validation: the honesty invariants of each dataset
    if args.region == "us-fl":
        assert all(p["score"] == -1 for p in places), "FL place carries a numeric score!"
        assert all(i["score"] == -1 for p in places for i in p["inspections"]), "FL inspection carries a score!"
    if args.region == "us-ga":
        assert all(isinstance(p["score"], int) and 0 <= p["score"] <= 100 for p in places), \
            "GA place score missing or outside Georgia's native 0-100!"
        assert all(i["score"] == -1 or 0 <= i["score"] <= 100
                   for p in places for i in p["inspections"]), \
            "GA inspection score outside native 0-100 / NO_SCORE!"
        assert all(p["result_text"] in ("A", "B", "C", "U") for p in places), \
            "GA place missing its state grade band!"
    if args.region == "us-tn":
        assert all(p["score"] == -1 or 0 <= p["score"] <= 100 for p in places), \
            "TN place score outside native 0-100 / NO_SCORE!"
        assert all(i["score"] == -1 or 0 <= i["score"] <= 100
                   for p in places for i in p["inspections"]), \
            "TN inspection score outside native 0-100 / NO_SCORE!"
        assert all(p["result_text"] == "" for p in places), \
            "TN place carries a result_text — Tennessee publishes no grade; one was invented!"
        assert all(i["result_text"] == "" for p in places for i in p["inspections"]), \
            "TN inspection carries a result_text — Tennessee publishes no grade; one was invented!"
    if args.region == "us-sc":
        assert all(p["score"] == -1 for p in places), \
            "SC place carries a numeric score — SC publishes grades only; a score was derived!"
        assert all(i["score"] == -1 for p in places for i in p["inspections"]), \
            "SC inspection carries a numeric score — SC publishes grades only; a score was derived!"
        assert all(p["result_text"] in ("A", "B", "C", "N/A", "S") for p in places), \
            "SC place missing its posted grade (or carrying an unpublished one)!"
        assert all(i["result_text"] in ("A", "B", "C", "N/A", "S")
                   for p in places for i in p["inspections"]), \
            "SC inspection missing its posted grade (or carrying an unpublished one)!"
        assert all(not i["violations"] for p in places for i in p["inspections"]), \
            "SC inspection carries violations — they exist only inside the source PDFs!"
    assert all(p["state"] == args.state and p["region_id"] == args.region for p in places)
    assert all(
        (p["lat"] is None and p["lng"] is None)
        or (p["geo_status"] == "ACCEPTED" and p["geo_prov"] == "CENSUS"
            and p["geo_acc"] == "ADDRESS_RANGE" and p["geo_match"] in ("EXACT", "NON_EXACT"))
        for p in places
    ), f"{args.state} place carries coordinates without accepted Census provenance!"
    n_insp = sum(len(p["inspections"]) for p in places)
    n_with = sum(1 for p in places if p["inspections"])
    n_disp = sum(1 for p in places if p["result_text"])

    generated_at = src_manifest.get("generated_at") or datetime.now(timezone.utc).isoformat()
    day = generated_at[:10]
    version = f"{day}.1" if not args.limit else f"{day}.dev{args.limit}"

    out_dir = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out",
        args.region + ("-subset" if args.limit else ""),
    )
    os.makedirs(out_dir, exist_ok=True)
    db_name = f"{args.region}-{version}.db"
    db_path = os.path.join(out_dir, db_name)
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("CREATE TABLE pack_meta(k TEXT PRIMARY KEY, v TEXT)")
    cur.execute(PLACES_DDL)
    cur.execute(INSPECTIONS_DDL)
    meta = {
        "region_id": args.region,
        "state": args.state,
        "dataset_version": version,
        "generated_at": generated_at,
        "place_count": str(len(places)),
        "schema_version": str(SCHEMA_VERSION),
        "score_model": SCORE_MODELS[args.region],
        "source": src_manifest.get("source", SOURCE_DEFAULTS[args.region]),
    }
    cur.executemany("INSERT INTO pack_meta VALUES (?,?)", list(meta.items()))
    cols = ("id,name,name_lc,address,city,zip,county,score,date,date_key,source,"
            "lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url,"
            "state,jurisdiction,region_id,result_text")
    ph = ",".join("?" * 22)
    for p in places:
        cur.execute(f"INSERT INTO places ({cols}) VALUES ({ph})", (
            p["id"], p["name"], p["name"].lower(), p["address"], p["city"], p["zip"],
            p["county"], p["score"], p["date"], date_key(p["date"]), p["source"],
            p["lat"], p["lng"], p["geo_status"], p["geo_acc"], p["geo_prov"],
            p["geo_match"], p["detail_url"], p["state"], p["jurisdiction"],
            p["region_id"], p["result_text"],
        ))
        for idx, insp in enumerate(p["inspections"]):
            cur.execute(
                "INSERT INTO inspections (place_id,idx,score,date,type,violations_json,result_text)"
                " VALUES (?,?,?,?,?,?,?)",
                (p["id"], idx, insp["score"], insp["date"], insp["type"],
                 json.dumps(insp["violations"]), insp["result_text"]),
            )
    con.commit()
    con.close()

    gz_name = db_name + ".gz"
    gz_path = os.path.join(out_dir, gz_name)
    with open(db_path, "rb") as f_in, gzip.GzipFile(filename="", mode="wb", fileobj=open(gz_path, "wb"), mtime=0) as gz:
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
        "full": {"file": gz_name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
        "delta": None,
        "jurisdictions": JURISDICTIONS[args.region],
    }
    manifest_path = os.path.join(out_dir, f"{args.region}.manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=1)

    print(f"pack: {gz_path} ({len(raw):,} bytes, sha256 {manifest['full']['sha256'][:16]}…)")
    print(f"manifest: {manifest_path}")
    print(f"places={len(places):,} with_inspections={n_with:,} inspections={n_insp:,} "
          f"with_disposition={n_disp:,} scores_invented=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
