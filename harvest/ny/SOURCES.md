# New York (NY) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** built locally, not published
- **Availability:** STAGED-LOCAL (pack exists on disk, not published)
- **Pipeline:** harvest/socrata_cities/ — nyc source
- **Summary:** NYC pack built + validated locally (penalty points + letter grade); upstate is county-fragmented.

## Official sources

### NYC Department of Health & Mental Hygiene (ny-nyc-dohmh)

| field | value |
|---|---|
| coverage | New York City |
| access | api |
| website | https://data.cityofnewyork.us/Health/DOHMH-New-York-City-Restaurant-Inspection-Results/43nn-pn8j |
| violations | full |
| history | full-history |
| result model | PENALTY_LOW |
| status | pack-built |
| verified | 2026-10-25 |
| last refresh | 2026-10-25 |
| refresh | Harvest pipeline harvest/socrata_cities (nyc) |
| restrictions | NYC only — the rest of New York State is fragmented by county. |
| notes | Socrata API (resource/43nn-pn8j.json): one row per violation citation; score = violation points (LOWER is better; A=0-13, B=14-27, C=28+), letter grade carried as result text. Pack BUILT locally 2026-10-25 (31,368 places / 92,713 inspections / 287,206 violations). Attribution: NYC DOHMH via NYC Open Data. |

### Rest of New York State (county health departments) (ny-statewide)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://www.health.ny.gov/food_safety/ |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | No statewide public portal verified; county-level publication. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
