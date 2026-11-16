#!/usr/bin/env python3
"""Region-pack builder for harvest/sfi states (vt, ia, sd, wy, ak, ar, pa).

Convert + family invariants; the write tail lives in the shared engine
(build_pack.write_pack). SFI deployments may publish real numeric scores
(VT/SD publish 0-100) — scores ship as published; Compliance-column
deployments (PA) ship their In/Out text in result_text with the
NO_SCORE sentinel.

Usage: python tools/packs/build_pack_sfi.py <vt|ia|sd|wy|ak|ar|pa> [--limit N]
"""
import argparse, json, os, sys

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
    return bp.pack_place(
        raw,
        score=raw["s"], date=bp.iso_to_mdy(raw["d"]),
        source=cfg["source_id"], state=cfg["state"],
        jurisdiction=cfg["jur"], region_id=cfg["region"],
        inspections=insps)


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
    bp.write_pack(
        region=cfg["region"], state=cfg["state"], name=cfg["name"],
        model=cfg["model"], source_label=cfg["agency"],
        places=places, generated_at=src_m["generated_at"], out_dir=out,
        limit=a.limit, attribution=cfg["agency"],
        jurisdictions=[{"jurisdictionId": cfg["jur"],
                        "name": cfg["agency"]}])


if __name__ == "__main__":
    main()
