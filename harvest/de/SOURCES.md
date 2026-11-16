# Delaware (DE) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-de.manifest.json
- **Pipeline:** harvest/de_socrata/ — published pack
- **Summary:** Pack published to the data-packs release, artifact sha256-verified 2026-11-16 (3,740 places, datasetVersion 2026-11-16.1). Violations-only model — no scores exist in this data.

## Official sources

### Delaware Division of Public Health — Office of Food Protection (de-dph)

| field | value |
|---|---|
| coverage | Statewide |
| access | api |
| website | https://data.delaware.gov/Health/Food-Establishment-Inspection-Violations/384s-wygj |
| violations | full |
| history | some-history |
| result model | VIOLATIONS_ONLY |
| status | pack-built |
| verified | 2026-10-22 |
| last refresh | 2026-10-22 |
| refresh | Harvest pipeline harvest/de_socrata |
| notes | Socrata open-data API (resource 384s-wygj): one row per violation, geocoded, ~2-year rolling window. Pack BUILT and validated locally (3,731 places / 9,202 inspections / 32,570 violations; sha256 536e54a6…92835); staged, NOT published. Violations-ONLY extract: zero-violation establishments are absent from the source dataset. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
