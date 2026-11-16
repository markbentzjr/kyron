#!/usr/bin/env python3
"""Generate harvest/<st>/SOURCES.md for every jurisdiction in the national
registry. Each folder is that state's pipeline home; the file records what
is verifiably known about the official source(s) — agency, portal URL,
access type, pack status — and which existing family adapter applies.

Generated from app/src/main/assets/coverage/us_national_registry.json —
rerun tools/coverage/gen_state_harvest_dirs.py after registry changes.
Do not hand-edit the generated SOURCE tables (the pipeline owns them);
state-specific freeform notes go at the bottom in the KEEP block.
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(ROOT, "app/src/main/assets/coverage/us_national_registry.json")
HARVEST = os.path.join(ROOT, "harvest")

# Where each state's working pipeline actually lives today.
PIPELINE = {
    "AL": "harvest/ root (adph_*.py, jcdh_*.py, mchd_harvest.py) — bundled seed",
    "AK": "harvest/sfi/ — SafeFoodInspection adapter",
    "AR": "harvest/sfi/ — SafeFoodInspection adapter",
    "CA": "harvest/socrata_cities/ — sf source (San Francisco only)",
    "CO": "harvest/mhd/ — MyHealthDepartment adapter (proof pack only)",
    "DE": "harvest/de_socrata/ — published pack",
    "FL": "harvest/fl_dbpr/ — published pack",
    "GA": "harvest/ga/ — pack built, NOT yet published",
    "HI": "harvest/mhd/ — MyHealthDepartment adapter",
    "IA": "harvest/sfi/ — SafeFoodInspection adapter",
    "IL": "harvest/socrata_cities/ — chicago source",
    "MD": "harvest/socrata_cities/ — montgomery source",
    "MT": "harvest/mhd/ — MyHealthDepartment adapter",
    "NC": "harvest/nc/ — pipeline exists; blocked on cdpehs_lib helper",
    "NV": "harvest/snhd/ — published pack (Clark County only)",
    "NY": "harvest/socrata_cities/ — nyc source",
    "OR": "harvest/mhd/ — MyHealthDepartment adapter",
    "PA": "harvest/sfi/ — SafeFoodInspection adapter",
    "RI": "harvest/dhd/ — healthinspections.us adapter",
    "SC": "harvest/sc/ — published pack",
    "SD": "harvest/sfi/ — SafeFoodInspection adapter",
    "TN": "harvest/tn/ — published pack",
    "TX": "harvest/socrata_cities/ — austin source (Austin only)",
    "VA": "harvest/mhd/ — MyHealthDepartment adapter",
    "VT": "harvest/sfi/ — SafeFoodInspection adapter",
    "WA": "harvest/socrata_cities/ — kingco source (King County only)",
    "WI": "harvest/mhd/ — MyHealthDepartment adapter (proof pack only)",
    "WY": "harvest/sfi/ — SafeFoodInspection adapter",
}

PACK_LABEL = {
    "bundled": "bundled in the APK",
    "published": "published to the data-packs release",
    "built": "built locally, not published",
    "none": "no pack",
}
AVAIL_LABEL = {
    "downloadable-verified": "DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)",
    "declared-only": "DECLARED-ONLY (publication declared, artifact not verified)",
    "staged-local": "STAGED-LOCAL (pack exists on disk, not published)",
    "none": "none",
}

def slug(state):
    return state.lower()

def render(j, registry_gen):
    st = j["state"]
    lines = []
    lines.append(f"# {j['name']} ({st}) — harvest folder")
    lines.append("")
    lines.append(f"_Generated {registry_gen} from `us_national_registry.json` — rerun "
                 "`tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._")
    lines.append("")
    lines.append(f"- **Pack status:** {PACK_LABEL.get(j['pack_status'], j['pack_status'])}")
    lines.append(f"- **Availability:** {AVAIL_LABEL.get(j['pack_availability'], j['pack_availability'])}")
    if j.get("pack_manifest_url"):
        lines.append(f"- **Manifest:** {j['pack_manifest_url']}")
    pipe = PIPELINE.get(st)
    if pipe:
        lines.append(f"- **Pipeline:** {pipe}")
    if j.get("summary"):
        lines.append(f"- **Summary:** {j['summary']}")
    lines.append("")
    lines.append("## Official sources")
    lines.append("")
    for s in j["sources"]:
        lines.append(f"### {s['agency']} ({s['id']})")
        lines.append("")
        lines.append("| field | value |")
        lines.append("|---|---|")
        lines.append(f"| coverage | {s.get('coverage','')} |")
        lines.append(f"| access | {s.get('access','')} |")
        lines.append(f"| website | {s.get('website','')} |")
        lines.append(f"| violations | {s.get('violations','')} |")
        lines.append(f"| history | {s.get('history','')} |")
        lines.append(f"| result model | {s.get('result_model','')} |")
        lines.append(f"| status | {s.get('status','')} |")
        if s.get("verified"):
            lines.append(f"| verified | {s['verified']} |")
        if s.get("last_refresh"):
            lines.append(f"| last refresh | {s['last_refresh']} |")
        if s.get("refresh"):
            lines.append(f"| refresh | {s['refresh']} |")
        for k in ("blocker", "restrictions", "notes"):
            if s.get(k):
                lines.append(f"| {k} | {s[k]} |")
        lines.append("")
    # Preserve any hand-written notes appended under the marker.
    lines.append("<!-- KEEP: freeform notes below this line are preserved across regens -->")
    return "\n".join(lines) + "\n"

def main():
    d = json.load(open(REGISTRY, encoding="utf-8"))
    gen = d.get("generated", "unknown")
    made = []
    idx = ["# Kyron harvest folders — all 50 states + D.C.", "",
           f"_Generated {gen} — rerun `tools/coverage/gen_state_harvest_dirs.py`._", "",
           "One folder per jurisdiction (`harvest/<st>/SOURCES.md`) records the",
           "official source(s), access type and pack status — the registry is the",
           "source of truth. Family adapters (sfi, mhd, dhd, socrata_cities) are",
           "shared pipelines that serve many states; state folders point at them.", "",
           "| state | pack | availability | pipeline |",
           "|---|---|---|---|"]
    for j in d["jurisdictions"]:
        st = j["state"]
        folder = os.path.join(HARVEST, slug(st))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "SOURCES.md")
        keep = ""
        if os.path.exists(path):
            old = open(path, encoding="utf-8").read()
            m = re.search(r"<!-- KEEP: freeform notes.*-->(.*)", old, re.S)
            if m and m.group(1).strip():
                keep = m.group(1)
        body = render(j, gen)
        if keep:
            body = body.rstrip() + "\n" + keep
        open(path, "w", encoding="utf-8").write(body)
        made.append(st)
        pipe = PIPELINE.get(st, "—")
        idx.append(f"| [{st}]({slug(st)}/SOURCES.md) | {j['pack_status']} | "
                   f"{j['pack_availability']} | {pipe} |")
    idx += ["",
            "Legacy family folders kept where they are: `de_socrata/`, `fl_dbpr/`,",
            "`ga/`, `nc/`, `sc/`, `snhd/`, `tn/` (state pipelines) and `dhd/`,",
            "`mhd/`, `sfi/`, `socrata_cities/` (multi-state adapters). Alabama's",
            "seed pipeline lives at this directory's root (`adph_*.py`, `jcdh_*.py`).",
            ""]
    open(os.path.join(HARVEST, "README.md"), "w", encoding="utf-8").write("\n".join(idx))
    print(f"generated {len(made)} SOURCES.md + harvest/README.md")

if __name__ == "__main__":
    main()
