# Massachusetts (MA) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Summary:** Boston has a strong open dataset; the rest is municipal.

## Official sources

### City of Boston Inspectional Services (ma-boston)

| field | value |
|---|---|
| coverage | Boston |
| access | bulk-csv |
| website | https://data.boston.gov/dataset/food-establishment-inspections |
| violations | full |
| history | full-history |
| result model | PASS_FAIL |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Analyze Boston CKAN, daily refresh, per-violation rows with inspector comments (fetched 200 with data 2026-10-22). |

### Massachusetts DPH Food Protection Program (ma-dph)

| field | value |
|---|---|
| coverage | State-inspected facilities |
| access | html |
| website | https://dphanalytics.hhs.mass.gov/ibmcognos/bi/?pathRef=MEPHTN/inspections/food-protection/food-protection-list |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | blocked |
| verified | 2026-10-22 |
| blocker | Cognos JS report serves an empty body to non-browser fetches; municipal boards inpublish independently. |
| notes | ~350 municipal health boards are the real publishers. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
