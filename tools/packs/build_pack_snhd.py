#!/usr/bin/env python3
"""Region-pack builder for the harvest/snhd adapter (Southern Nevada
Health District — Clark County / Las Vegas).

Convert + family invariants; the write tail lives in the shared engine
(build_pack.write_pack). SNHD's model is PENALTY_LOW:
`inspection_demerits` are penalty points (lower is better) and the
letter grade / result text rides verbatim in result_text — never
converted, never invented.

Usage: python tools/packs/build_pack_snhd.py snhd [--limit N]
Reads harvest/snhd/out/snhd/places.json, writes
us-nv-<version>.db.gz + us-nv.manifest.json next to it.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import build_pack as bp  # noqa: E402

CFG = {
    "region": "us-nv", "state": "NV", "name": "Nevada (SNHD / Clark Co.)",
    "source_id": "nv-snhd", "jurisdiction": "NV-SNHD",
    "model": "PENALTY_LOW",
    "attribution": ("Southern Nevada Health District — restaurant "
                    "inspections nightly developer extract "
                    "(southernnevadahealthdistrict.org)"),
}


def convert(raw, cfg):
    return bp.pack_place(
        raw,
        score=raw["s"], date=bp.iso_to_mdy(raw["d"]),
        source=cfg["source_id"], state=cfg["state"],
        jurisdiction=cfg["jurisdiction"], region_id=cfg["region"],
        inspections=[{"score": i["s"], "date": bp.iso_to_mdy(i["d"]),
                      "type": i["t"], "violations": i["v"],
                      "result_text": i.get("disp", "")}
                     for i in raw["insp"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["snhd"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--version-seq", type=int, default=0,
                    help="override dataset version suffix (e.g. 2 -> <day>.2)")
    a = ap.parse_args()
    cfg = CFG
    out = os.path.join(REPO, "harvest", "snhd", "out", a.source)
    places = [convert(p, cfg) for p in
              json.load(open(os.path.join(out, "places.json"),
                             encoding="utf-8"))]
    if a.limit:
        places = places[:a.limit]
    src_m = json.load(open(os.path.join(out, "manifest.json"),
                           encoding="utf-8"))
    assert all(p["state"] == cfg["state"] and
               p["region_id"] == cfg["region"] for p in places)
    for p in places:
        assert (p["lat"] is not None) == (
            p["geo_status"] == "ACCEPTED" and bool(p["geo_prov"]))
    bp.write_pack(
        region=cfg["region"], state=cfg["state"], name=cfg["name"],
        model=cfg["model"], source_label=cfg["attribution"],
        places=places, generated_at=src_m["generated_at"], out_dir=out,
        limit=a.limit,
        version=(f"{src_m['generated_at'][:10]}.{a.version_seq}"
                 if a.version_seq else None),
        # SNHD keeps ~18y of history per place (max depth 58); 30 bounds
        # the outliers while retaining ~98% of all inspections.
        max_inspections=30,
        attribution=cfg["attribution"],
        jurisdictions=[{"jurisdictionId": cfg["jurisdiction"],
                        "name": cfg["attribution"]}])


if __name__ == "__main__":
    main()
