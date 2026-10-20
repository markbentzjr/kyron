#!/usr/bin/env python3
"""Mechanical G5 adjudication for the SC output.

For every place the gate flags under G5, prove (or refute) that the
shipped name/street pair is verbatim-identical to a source pair:
  - the layer-0 (FACILITY, ADDRESS) pair for the permit, or
  - any rate.aspx (name, street) pair among the place's inspections, or
  - any Steton (FACILITY, ADDRESS) pair among the place's inspections.
If a shipped pair equals a source pair exactly (modulo the build's
documented whitespace collapsing), the G5 hit is a false positive of
the AL-tuned fused-split heuristic against SC's separate-field data.
Output: OUTPUT/gate_adjudication.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sc_parse import load_gis, load_rate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGGED = [
    "scda_02-206-03263", "scda_02-206-03325", "scda_24-206-03118",
    "scda_26-206-10512", "scda_26-206-13788", "scda_26-211-00586",
    "scda_39-206-02411", "scda_46-206-05192", "scda_rate-3bee5fade7df",
    "scda_rate-5583ab69a2e9", "scda_rate-93245efa5105",
    "scda_rate-9b116930af28", "scda_rate-daa06d2b8c2b",
]


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def main():
    places = {p["id"]: p for p in json.load(
        open(os.path.join(HERE, "OUTPUT", "places_sc.json")))}
    l0 = {}
    for f in load_gis("gis_layer0"):
        a = f["attributes"]
        pid = clean(a.get("PERMIT_ID"))
        if pid:
            l0[pid] = (clean(a.get("FACILITY")), clean(a.get("ADDRESS")))
    st_pairs = {}
    for f in load_gis("gis_steton"):
        a = f["attributes"]
        g = (a.get("AuditResultGlobalID") or "").lower()
        st_pairs[g] = (clean(a.get("FACILITY")), clean(a.get("ADDRESS")))
    rate_pairs = {}
    for r in load_rate():
        rate_pairs[r["guid"]] = (clean(r["name"]), clean(r["street"]))

    verdicts = []
    for pid_ in FLAGGED:
        p = places[pid_]
        shipped = (clean(p["n"]), clean(p["a"]))
        evidence = []
        if p["fid"] and p["fid"] in l0 and l0[p["fid"]] == shipped:
            evidence.append("layer0 pair identical")
        for i in p["insp"]:
            if rate_pairs.get(i["vid"]) == shipped:
                evidence.append(f"rate pair identical (insp {i['vid']})")
                break
        for i in p["insp"]:
            if st_pairs.get(i["vid"]) == shipped:
                evidence.append(f"steton pair identical (insp {i['vid']})")
                break
        verdicts.append({
            "place": pid_, "name": p["n"], "street": p["a"],
            "verdict": ("FALSE POSITIVE — shipped pair is source-verbatim"
                        if evidence else "UNPROVEN — needs manual review"),
            "evidence": evidence,
        })
        print(pid_, verdicts[-1]["verdict"], evidence[:1])
    with open(os.path.join(HERE, "OUTPUT", "gate_adjudication.json"),
              "w") as fh:
        json.dump(verdicts, fh, ensure_ascii=False, indent=1)
    bad = [v for v in verdicts if not v["evidence"]]
    print(f"{len(verdicts) - len(bad)}/{len(verdicts)} proven source-verbatim")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
