#!/usr/bin/env python3
"""Build a per-region delta pack between two full pack versions.

The app-side contract (data/PackManager.kt applyDelta): the delta is a
JSON file — gzip-compressed for transport — carrying

    {"regionId": ..., "fromVersion": ..., "toVersion": ...,
     "upserts": [<compact Place JSON>], "deletions": [<place id>]}

that applies ONLY on top of its exact base dataset version. Upserts are
the app's compact Place.toJson() shape (id,n,a,c,z,ct,s,d,src,lat,lng,
du,gs,ga,gp,gm,st,jur,disp,insp) — a whole place plus its full
inspection list, because catalog.upsertPlace replaces the row and all
its inspections wholesale. The delta file is deterministic (gzip
mtime=0), then the new manifest's `delta` block is patched with
{fromVersion, file, bytes, sha256}, and publish_index.py propagates
that block into the signed index so the app can verify the delta
before downloading it.

The diff runs against the two pack SQLite files themselves — the
authoritative contents of what phones would install — so a place is
upserted when ANY of its 22 columns or any inspection row changed.
After emitting, the tool self-verifies: it applies the delta ops to a
copy of the base DB with the same semantics as catalog.upsertPlace /
deletePlace and requires the result to equal the new pack row-for-row.

Usage:
  python3 build_delta.py --base us-nv-2026-11-16.2.db.gz \
      --new us-nv-2026-11-16.3.db.gz \
      --manifest us-nv.manifest.json --out-dir .
"""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import tempfile

PLACE_COLS = ("id", "name", "name_lc", "address", "city", "zip", "county",
              "score", "date", "date_key", "source", "lat", "lng",
              "geo_status", "geo_acc", "geo_prov", "geo_match",
              "detail_url", "state", "jurisdiction", "region_id",
              "result_text")
INSP_COLS = ("score", "date", "type", "violations_json", "result_text")


def _read_pack(gz_path):
    """Decompress a .db.gz pack and return (pack_meta dict,
    {place_id: (place tuple, [inspection tuples in idx order])})."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "pack.db")
        with open(db_path, "wb") as f:
            f.write(gzip.open(gz_path, "rb").read())
        con = sqlite3.connect(db_path)
        meta = dict(con.execute("SELECT k,v FROM pack_meta").fetchall())
        places = {}
        for row in con.execute(f"SELECT {','.join(PLACE_COLS)} FROM places"):
            pid = row[0]
            insps = con.execute(
                f"SELECT {','.join(INSP_COLS)} FROM inspections"
                " WHERE place_id=? ORDER BY idx", (pid,)).fetchall()
            places[pid] = (row, insps)
        con.close()
        return meta, places


def _place_json(row, insps):
    """Pack place row + inspection tuples -> the app's compact
    Place.toJson() shape (see data/Models.kt)."""
    (pid, name, name_lc, address, city, zipc, county, score, date,
     date_key_, source, lat, lng, geo_status, geo_acc, geo_prov,
     geo_match, detail_url, state, jurisdiction, region_id,
     result_text) = row
    return {
        "id": pid, "n": name, "a": address, "c": city, "z": zipc,
        "ct": county, "s": score, "d": date, "src": source,
        "lat": lat, "lng": lng, "du": detail_url,
        "gs": geo_status, "ga": geo_acc, "gp": geo_prov, "gm": geo_match,
        "st": state, "jur": jurisdiction, "disp": result_text,
        "insp": [{"s": s, "d": d, "t": t, "disp": rt,
                  "v": json.loads(vj)}
                 for s, d, t, vj, rt in insps]}


def _apply_and_verify(base_gz, delta, new_gz):
    """Replay the delta onto the base pack with the app's semantics
    (deletePlace = place + its inspections; upsertPlace = replace row +
    all inspections) and require row-for-row equality with the new pack.
    This is the load-bearing check that a published delta transforms an
    installed base into exactly the advertised target."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "applied.db")
        with open(db_path, "wb") as f:
            f.write(gzip.open(base_gz, "rb").read())
        con = sqlite3.connect(db_path)
        ph = ",".join("?" * len(PLACE_COLS))
        for pid in delta["deletions"]:
            con.execute("DELETE FROM inspections WHERE place_id=?", (pid,))
            con.execute("DELETE FROM places WHERE id=?", (pid,))
        for u in delta["upserts"]:
            row = _json_to_row(u)
            con.execute(f"INSERT OR REPLACE INTO places"
                        f" ({','.join(PLACE_COLS)}) VALUES ({ph})", row)
            con.execute("DELETE FROM inspections WHERE place_id=?", (u["id"],))
            for i, insp in enumerate(u["insp"]):
                con.execute(
                    "INSERT INTO inspections"
                    " (place_id,idx,score,date,type,violations_json,result_text)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (u["id"], i, insp["s"], insp["d"], insp["t"],
                     json.dumps(insp["v"], ensure_ascii=False),
                     insp["disp"]))
        con.commit()
        con.close()

        _, expected = _read_pack(new_gz)
        with tempfile.TemporaryDirectory() as td2:
            # _read_pack expects .gz; wrap the applied db.
            agz = os.path.join(td2, "applied.db.gz")
            with open(agz, "wb") as fo, gzip.GzipFile(
                    filename="", mode="wb", fileobj=fo, mtime=0) as gz:
                gz.write(open(db_path, "rb").read())
            _, actual = _read_pack(agz)
        return actual == expected


def _json_to_row(u):
    """Compact Place JSON -> canonical places-table row tuple."""
    return (u["id"], u["n"], u["n"].lower(), u["a"], u["c"], u["z"],
            u["ct"], u["s"], u["d"], _date_key(u["d"]), u["src"],
            u["lat"], u["lng"], u["gs"], u["ga"], u["gp"], u["gm"],
            u["du"], u["st"], u["jur"], "us-" + u["st"].lower(),
            u["disp"])


def _date_key(mdy):
    from datetime import datetime
    try:
        return (datetime.strptime(mdy.strip(), "%m/%d/%Y")
                - datetime(1970, 1, 1)).days
    except (ValueError, AttributeError):
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base .db.gz pack")
    ap.add_argument("--new", required=True, help="new .db.gz pack")
    ap.add_argument("--manifest", required=True,
                    help="new pack's .manifest.json (patched in place)")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    bmeta, base = _read_pack(a.base)
    nmeta, new = _read_pack(a.new)
    region = nmeta["region_id"]
    assert bmeta["region_id"] == region, "region mismatch base vs new"
    assert bmeta["dataset_version"] != nmeta["dataset_version"], \
        "delta needs distinct versions"

    deletions, upserts = [], []
    for pid in base:
        if pid not in new:
            deletions.append(pid)
    for pid, (row, insps) in new.items():
        if pid not in base or base[pid] != (row, insps):
            upserts.append(_place_json(row, insps))
    deletions.sort()

    delta = {"regionId": region,
             "fromVersion": bmeta["dataset_version"],
             "toVersion": nmeta["dataset_version"],
             "upserts": upserts, "deletions": deletions}
    name = f"{region}-delta-{bmeta['dataset_version']}" \
           f"-to-{nmeta['dataset_version']}.json.gz"
    out_path = os.path.join(a.out_dir, name)
    payload = json.dumps(delta, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    with open(out_path, "wb") as fo, gzip.GzipFile(
            filename="", mode="wb", fileobj=fo, mtime=0) as gz:
        gz.write(payload)
    raw = open(out_path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()

    print(f"delta {name} {len(raw):,} bytes "
          f"upserts={len(upserts):,} deletions={len(deletions):,}")
    print("verifying: applying delta to base ...")
    if not _apply_and_verify(a.base, delta, a.new):
        raise SystemExit("VERIFY FAIL: applied delta != new pack")
    print("verify ok: base + delta == new pack")

    man_path = a.manifest
    m = json.load(open(man_path, encoding="utf-8"))
    assert m["regionId"] == region and \
        m["datasetVersion"] == nmeta["dataset_version"]
    m["delta"] = {"fromVersion": bmeta["dataset_version"], "file": name,
                  "bytes": len(raw), "sha256": sha}
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    print(f"manifest {man_path} delta -> {bmeta['dataset_version']}")


if __name__ == "__main__":
    main()
