# Illinois (IL) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** built locally, not published
- **Availability:** STAGED-LOCAL (pack exists on disk, not published)
- **Pipeline:** harvest/socrata_cities/ — chicago source
- **Summary:** Chicago pack built + validated locally (pass/fail); statewide coverage is county-by-county.

## Official sources

### Chicago Department of Public Health (il-chicago)

| field | value |
|---|---|
| coverage | Chicago |
| access | api |
| website | https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5 |
| violations | full |
| history | some-history |
| result model | PASS_FAIL |
| status | pack-built |
| verified | 2026-10-25 |
| last refresh | 2026-10-25 |
| refresh | Harvest pipeline harvest/socrata_cities (chicago) |
| restrictions | Chicago only; the rest of Illinois is fragmented. |
| notes | Socrata (SODA) API; pass / pass-with-conditions / fail; violations field with codes and inspector comments. Pack BUILT locally 2026-10-25 over a 2-year window (14,823 places / 36,070 inspections). Attribution: City of Chicago Data Portal. |

### Rest of Illinois (local health departments) (il-statewide)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://dph.illinois.gov/topics-services/food-safety.html |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | No statewide results portal verified. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
