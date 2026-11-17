#!/usr/bin/env python3
"""Region-pack builder for harvest/ms (Mississippi MSDH).

Letter-grade deployment: the portal publishes A/B/C inspection
grades only — no numeric score. Grades ship verbatim in
result_text; score stays NO_SCORE (-1). Violations ship empty in
v1 (per-inspection detail pages exist but are unfetched — declared
in the source manifest's coverage_exclusions).

Usage: python tools/packs/build_pack_ms.py [--limit N]
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import build_pack as bp  # noqa: E402

CFG = {
    "region": "us-ms", "state": "MS", "name": "Mississippi",
    "jur": "MS-MSDH", "source_id": "ms-msdh",
    "agency": "Mississippi State Department of Health — Food "
              "Facility Inspections (apps.msdh.ms.gov/food)",
    "model": "LETTER_GRADE",
}


def convert(raw):
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
        raw, score=raw["s"], date=bp.iso_to_mdy(raw["d"]),
        source=CFG["source_id"], state=CFG["state"],
        jurisdiction=CFG["jur"], region_id=CFG["region"],
        inspections=insps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    out = os.path.join(REPO, "harvest", "ms", "out", "ms")
    places = [convert(p) for p in
              json.load(open(os.path.join(out, "places.json"),
                             encoding="utf-8"))]
    if a.limit:
        places = places[:a.limit]
    src_m = json.load(open(os.path.join(out, "manifest.json"),
                           encoding="utf-8"))
    assert all(p["state"] == "MS" and p["region_id"] == "us-ms"
               for p in places)
    # letter grades only — never a numeric score
    assert all(p["score"] == -1 for p in places)
    assert all(i["score"] == -1 for p in places
               for i in p["inspections"])
    assert all(p["result_text"] in ("", "A", "B", "C", "Pass",
                                    "Fail") for p in places), \
        "unexpected result_text in a LETTER_GRADE pack"
    assert all((p["lat"] is None) == (
        p["geo_status"] == "UNRESOLVED" and not p["geo_prov"])
        for p in places)
    bp.write_pack(
        region="us-ms", state="MS", name="Mississippi",
        model="LETTER_GRADE", source_label=CFG["agency"],
        places=places, generated_at=src_m["generated_at"],
        out_dir=out, limit=a.limit, attribution=CFG["agency"],
        jurisdictions=[{"jurisdictionId": "MS-MSDH",
                        "name": CFG["agency"]}])


if __name__ == "__main__":
    main()
