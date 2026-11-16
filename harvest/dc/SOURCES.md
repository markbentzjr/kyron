# District of Columbia (DC) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Summary:** Registered as a jurisdiction, explicitly NOT one of the 50 states.

## Official sources

### DC Health — Food Safety & Hygiene Inspection Services Division (dc-dchealth)

| field | value |
|---|---|
| coverage | District of Columbia (all inspections state-run) |
| access | html |
| website | https://dc.healthinspections.us/?a=Inspections |
| violations | full |
| history | full-history |
| result model | VIOLATIONS_ONLY |
| status | source-verified |
| verified | 2026-10-22 |
| notes | DC-run healthinspections.us instance fetched 200 OK: name/inspection-type search, FDA Food Code citation-level detail, history stated to cover 2007→current. Help page dchealth.dc.gov/service/understanding-food-establishment-inspections confirmed 200. DHD adapter (harvest/dhd) configured but DISABLED — tried /dc, /stateofdc and /districtofcolumbia deployments without finding the API root; the verified entry point is dc.healthinspections.us/?a=Inspections. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
