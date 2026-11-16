# Rhode Island (RI) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/dhd/ — healthinspections.us adapter
- **Summary:** Statewide; reachable but JS-postback heavy.

## Official sources

### Rhode Island Department of Health — Center for Food Protection (ri-ridoh)

| field | value |
|---|---|
| coverage | Statewide |
| access | html |
| website | https://ri.healthinspections.us/ri/ |
| violations | full |
| history | some-history |
| result model | VIOLATIONS_ONLY |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Official portal (linked from health.ri.gov/food-safety, fetched 200); Tyler-hosted JS/postback app — parsing needs the postback, not plain links. DHD adapter (harvest/dhd) validated end-to-end 2026-11-16 — bounded proof: 20 facilities / 51 inspections / 188 violations via paged search + inspectionsData API; full statewide fetch pending (~2k pages). |

<!-- KEEP: freeform notes below this line are preserved across regens -->
