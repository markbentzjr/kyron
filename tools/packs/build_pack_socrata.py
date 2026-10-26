#!/usr/bin/env python3
"""Region-pack builder for harvest/socrata_cities sources (nyc, chicago,
kingco). Same pack schema/manifest as build_pack_de.py; reuses the shared
builder's DDL + date helpers (build_pack.py is not modified).

Usage: python tools/packs/build_pack_socrata.py <nyc|chicago|kingco> [--limit N]
Reads harvest/socrata_cities/out/<key>/places.json, writes
<region>-<version>.db.gz + <region>.manifest.json next to it.
"""
import argparse, gzip, hashlib, json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "harvest", "socrata_cities"))
import build_pack as bp  # noqa: E402
from sources import SOURCES  # noqa: E402


def convert(raw, cfg):
    numeric = cfg["model"] != "PASS_FAIL"
    insps = [{"score": i["s"] if numeric else -1,
              "date": bp.iso_to_mdy(i["d"]), "type": i["t"],
              "violations": i["v"], "result_text": i.get("disp", "")}
             for i in raw["insp"]]
    return {"id": raw["id"], "name": raw["n"], "address": raw["a"],
            "city": raw["c"], "zip": raw["z"], "county": raw["ct"],
            "score": raw["s"] if numeric else -1,
            "date": bp.iso_to_mdy(raw["d"]), "source": cfg["source_id"],
            "lat": raw["lat"], "lng": raw["lng"], "detail_url": raw["du"],
            "geo_status": raw["gs"], "geo_acc": raw["ga"], "geo_prov": raw["gp"],
            "geo_match": raw["gm"], "state": cfg["state"],
            "jurisdiction": cfg["jurisdiction"], "region_id": cfg["region"],
            "result_text": raw.get("disp", ""), "inspections": insps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cfg = SOURCES[a.source]
    out = os.path.join(REPO, "harvest", "socrata_cities", "out", a.source)
    places = [convert(p, cfg) for p in json.load(open(os.path.join(out, "places.json")))]
    if a.limit:
        places = places[:a.limit]
    src_m = json.load(open(os.path.join(out, "manifest.json")))
    # invariants
    assert all(p["state"] == cfg["state"] and p["region_id"] == cfg["region"] for p in places)
    if cfg["model"] == "PASS_FAIL":
        assert all(p["score"] == -1 for p in places), "PASS_FAIL score invented"
    for p in places:
        assert (p["lat"] is not None) == (p["geo_status"] == "ACCEPTED" and bool(p["geo_prov"]))
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
    meta = {"region_id": cfg["region"], "state": cfg["state"], "dataset_version": version,
            "generated_at": gen, "place_count": str(len(places)),
            "schema_version": str(bp.SCHEMA_VERSION), "score_model": cfg["model"],
            "source": cfg["attribution"]}
    cur.executemany("INSERT INTO pack_meta VALUES (?,?)", list(meta.items()))
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
    man = {"regionId": cfg["region"], "displayName": cfg["name"], "state": cfg["state"],
           "status": "available", "datasetVersion": version, "generatedAt": gen,
           "placeCount": len(places), "schemaVersion": bp.SCHEMA_VERSION,
           "minAppVersion": "2.0",
           "full": {"file": os.path.basename(gz), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()},
           "delta": None, "attribution": cfg["attribution"],
           "jurisdictions": [{"jurisdictionId": cfg["jurisdiction"], "name": cfg["jur_name"]}]}
    json.dump(man, open(os.path.join(out, f"{cfg['region']}.manifest.json"), "w"), indent=1)
    print(f"pack {gz} {len(raw):,} bytes places={len(places):,} sha256={man['full']['sha256'][:16]}")


if __name__ == "__main__":
    main()
