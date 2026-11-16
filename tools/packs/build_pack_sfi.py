#!/usr/bin/env python3
"""Region-pack builder for harvest/sfi states (vt, ia, sd, wy, ak, ar, pa).

Same pack schema/manifest as the other builders; reuses the shared
DDL + date helpers. SFI deployments may publish real numeric scores
(VT/SD publish 0-100) — scores ship as published; Compliance-column
deployments (PA) ship their In/Out text in result_text with the
NO_SCORE sentinel.

Usage: python tools/packs/build_pack_sfi.py <vt|ia|sd|wy|ak|ar|pa> [--limit N]
"""
import argparse, gzip, hashlib, json, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "harvest", "sfi"))
import build_pack as bp  # noqa: E402
from sfi_states import STATES  # noqa: E402


def convert(raw, cfg):
    insps = []
    for i in raw.get("insp") or []:
        viols = [{"p": v.get("p", 0), "c": bool(v.get("c", False)),
                  "r": v.get("r", "")} for v in (i.get("v") or [])]
        insps.append({"score": i.get("s", -1),
                      "date": bp.iso_to_mdy(i["d"]),
                      "type": i.get("t") or "",
                      "violations": viols,
                      "result_text": i.get("disp") or ""})
    return {"id": raw["id"], "name": raw["n"], "address": raw["a"],
            "city": raw["c"], "zip": raw["z"], "county": raw["ct"],
            "score": raw["s"],
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
    out = os.path.join(REPO, "harvest", "sfi", "out", a.source)
    places = [convert(p, cfg) for p in
              json.load(open(os.path.join(out, "places.json"),
                             encoding="utf-8"))]
    if a.limit:
        places = places[:a.limit]
    src_m = json.load(open(os.path.join(out, "manifest.json"),
                           encoding="utf-8"))
    assert all(p["state"] == cfg["state"] and
               p["region_id"] == cfg["region"] for p in places)
    # numeric scores only where the portal publishes them (0-100)
    for p in places:
        assert p["score"] == -1 or 0 <= p["score"] <= 100, \
            f"score out of range: {p['score']}"
        for i in p["inspections"]:
            assert i["score"] == -1 or 0 <= i["score"] <= 100
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
