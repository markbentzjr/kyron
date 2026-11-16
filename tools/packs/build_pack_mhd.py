#!/usr/bin/env python3
"""Region-pack builder for harvest/mhd states (va, wi, co, mt, hi, …).

Same pack schema/manifest as build_pack_socrata.py; reuses the shared
builder's DDL + date helpers. Every covered jurisdiction's model is
non-numeric (VIOLATIONS_ONLY / PASS_FAIL per the registry), so all
scores ship as the NO_SCORE sentinel (-1) and the jurisdiction's own
result text rides in result_text — never converted, never invented.

Usage: python tools/packs/build_pack_mhd.py <va|wi|co|mt|hi|...> [--limit N]
Reads harvest/mhd/out/<key>/places.json, writes
<region>-<version>.db.gz + <region>.manifest.json next to it.
"""
import argparse, gzip, hashlib, json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "harvest", "mhd"))
import build_pack as bp  # noqa: E402
from states import STATES  # noqa: E402


def convert(raw, cfg):
    """MHD normalized record -> canonical Kyron place row.

    Violations arrive in the TN dict shape ({item,title,rule,notes,
    status}) and become the app's {p, c, r} rows exactly as
    convert_tn_place renders them: p = 0 (no per-violation points
    published), c = False (no critical flag published), r =
    "<item> <title> — <rule> // <narrative verbatim>".
    """
    insps = []
    for i in raw.get("insp") or []:
        viols = []
        for v in i.get("v") or []:
            if isinstance(v, dict) and "item" in v:
                head = f"{v.get('item', '')} {v.get('title', '')}".strip()
                rule = (v.get("rule") or "").strip()
                if rule:
                    head = f"{head} — {rule}" if head else rule
                notes = (v.get("notes") or "").strip()
                r = head + (f" // {notes}" if notes else "")
                viols.append({"p": 0, "c": False, "r": r or v.get("notes") or ""})
            else:
                viols.append({"p": 0, "c": False,
                              "r": v.get("r", "") if isinstance(v, dict) else str(v)})
        insps.append({"score": -1,
                      "date": bp.iso_to_mdy(i["d"]),
                      "type": i.get("t") or "",
                      "violations": viols,
                      "result_text": i.get("disp") or ""})
    return {"id": raw["id"], "name": raw["n"], "address": raw["a"],
            "city": raw["c"], "zip": raw["z"], "county": raw["ct"],
            "score": -1,
            "date": bp.iso_to_mdy(raw["d"]), "source": cfg["source_id"],
            "lat": raw["lat"], "lng": raw["lng"], "detail_url": raw["du"],
            "geo_status": raw["gs"], "geo_acc": raw["ga"],
            "geo_prov": raw["gp"], "geo_match": raw["gm"],
            "state": cfg["state"], "jurisdiction": cfg["jur"],
            "region_id": cfg["region"],
            "result_text": raw.get("disp") or "", "inspections": insps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(STATES))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = STATES[a.source]
    out = os.path.join(REPO, "harvest", "mhd", "out", a.source)
    places = [convert(p, cfg) for p in
              json.load(open(os.path.join(out, "places.json"),
                             encoding="utf-8"))]
    if a.limit:
        places = places[:a.limit]
    src_m = json.load(open(os.path.join(out, "manifest.json"),
                           encoding="utf-8"))
    # invariants — these jurisdictions publish no numeric score
    assert all(p["state"] == cfg["state"] and
               p["region_id"] == cfg["region"] for p in places)
    assert all(p["score"] == -1 for p in places), "score invented"
    assert all(i["score"] == -1 for p in places
               for i in p["inspections"]), "inspection score invented"
    for p in places:
        assert (p["lat"] is not None) == (
            p["geo_status"] == "ACCEPTED" and bool(p["geo_prov"]))
    gen = src_m["generated_at"]
    version = f"{gen[:10]}.1" if not a.limit else f"{gen[:10]}.dev{a.limit}"
    db_name = f"{cfg['region']}-{version}.db"
    db = os.path.join(out, db_name)
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("CREATE TABLE pack_meta(k TEXT PRIMARY KEY, v TEXT)")
    cur.execute(bp.PLACES_DDL)
    cur.execute(bp.INSPECTIONS_DDL)
    meta = {"region_id": cfg["region"], "state": cfg["state"],
            "dataset_version": version, "generated_at": gen,
            "place_count": str(len(places)),
            "schema_version": str(bp.SCHEMA_VERSION),
            "score_model": cfg["model"], "source": cfg["agency"]}
    cur.executemany("INSERT INTO pack_meta VALUES (?,?)",
                    list(meta.items()))
    for p in places:
        cur.execute("INSERT INTO places (id,name,name_lc,address,city,zip,county,score,date,"
                    "date_key,source,lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url,"
                    "state,jurisdiction,region_id,result_text) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["name"], p["name"].lower(), p["address"], p["city"], p["zip"],
                     p["county"], p["score"], p["date"], bp.date_key(p["date"]), p["source"],
                     p["lat"], p["lng"], p["geo_status"], p["geo_acc"], p["geo_prov"],
                     p["geo_match"], p["detail_url"], p["state"], p["jurisdiction"],
                     p["region_id"], p["result_text"]))
        for idx, i in enumerate(p["inspections"]):
            cur.execute("INSERT INTO inspections (place_id,idx,score,date,type,violations_json,"
                        "result_text) VALUES (?,?,?,?,?,?,?)",
                        (p["id"], idx, i["score"], i["date"], i["type"],
                         json.dumps(i["violations"], ensure_ascii=False), i["result_text"]))
    con.commit()
    con.close()
    gz = db + ".gz"
    with open(db, "rb") as fi, open(gz, "wb") as fo, \
            gzip.GzipFile(filename="", mode="wb", fileobj=fo, mtime=0) as g:
        g.write(fi.read())
    os.remove(db)
    raw = open(gz, "rb").read()
    man = {"regionId": cfg["region"], "displayName": cfg["name"],
           "state": cfg["state"], "status": "available",
           "datasetVersion": version, "generatedAt": gen,
           "placeCount": len(places), "schemaVersion": bp.SCHEMA_VERSION,
           "minAppVersion": "2.0",
           "full": {"file": os.path.basename(gz), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()},
           "delta": None, "attribution": cfg["agency"],
           "jurisdictions": [{"jurisdictionId": cfg["jur"],
                              "name": cfg["agency"]}]}
    json.dump(man, open(os.path.join(out, f"{cfg['region']}.manifest.json"),
                        "w", encoding="utf-8"), indent=1)
    print(f"pack {gz} {len(raw):,} bytes places={len(places):,} "
          f"sha256={man['full']['sha256'][:16]}")


if __name__ == "__main__":
    main()
