# Oregon (OR) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/mhd/ — MyHealthDepartment adapter
- **Summary:** Statewide, scored, full history — top integration candidate; MHD adapter staged but disabled pending district-GUID discovery.

## Official sources

### Oregon Health Authority (statewide, county-run inspections) (or-oha)

| field | value |
|---|---|
| coverage | Statewide |
| access | html |
| website | https://inspections.myhealthdepartment.com/oregon |
| violations | full |
| history | full-history |
| result model | SCORE_100_HIGH |
| status | source-verified |
| verified | 2026-10-22 |
| refresh | HealthSpace/MyHealthDepartment statewide search (fetched 200 OK) |
| notes | Restaurant 100-pt scale: priority items deduct 5, priority-foundation 3; < 70 fails. One of the cleanest candidate integrations in the country. Generic MHD adapter (harvest/mhd) configured but DISABLED — the statewide path answers [] so a county/district GUID map must be discovered before ingestion (states.py enabled=False). |

<!-- KEEP: freeform notes below this line are preserved across regens -->
