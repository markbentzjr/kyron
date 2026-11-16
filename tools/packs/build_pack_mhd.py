#!/usr/bin/env python3
"""Region-pack builder for harvest/mhd states (va, wi, co, mt, hi, …).

Convert + family invariants; the write tail lives in the shared engine
(build_pack.write_pack). Every covered jurisdiction's model is
non-numeric (VIOLATIONS_ONLY / PASS_FAIL per the registry), so all
scores ship as the NO_SCORE sentinel (-1) and the jurisdiction's own
result text rides in result_text — never converted, never invented.

Usage: python tools/packs/build_pack_mhd.py <va|wi|co|mt|hi|...> [--limit N]
Reads harvest/mhd/out/<key>/places.json, writes
<region>-<version>.db.gz + <region>.manifest.json next to it.
"""
import argparse, json, os, sys

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
    return bp.pack_place(
        raw,
        score=-1, date=bp.iso_to_mdy(raw["d"]), source=cfg["source_id"],
        state=cfg["state"], jurisdiction=cfg["jur"],
        region_id=cfg["region"], inspections=insps)


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
    bp.write_pack(
        region=cfg["region"], state=cfg["state"], name=cfg["name"],
        model=cfg["model"], source_label=cfg["agency"],
        places=places, generated_at=src_m["generated_at"], out_dir=out,
        limit=a.limit, attribution=cfg["agency"],
        jurisdictions=[{"jurisdictionId": cfg["jur"],
                        "name": cfg["agency"]}])


if __name__ == "__main__":
    main()
