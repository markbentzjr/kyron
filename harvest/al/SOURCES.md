# Alabama (AL) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** bundled in the APK
- **Availability:** bundled
- **Pipeline:** harvest/ root (adph_*.py, jcdh_*.py, mchd_harvest.py) — bundled seed
- **Summary:** Shipped bundled in the APK; three live sync sources.

## Official sources

### Jefferson County Department of Health (al-jcdh)

| field | value |
|---|---|
| coverage | Jefferson County |
| access | live-sync |
| website | https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/Food/FoodServScores.aspx |
| violations | full |
| history | full-history |
| result model | SCORE_100_HIGH |
| status | integrated |
| verified | 2026-10-13 |
| refresh | In-app live adapter (every ~12 h) + bundled seed |
| notes | Scores plus full violation detail and per-place inspection history. |

### Alabama Department of Public Health (al-adph)

| field | value |
|---|---|
| coverage | Statewide (65 counties) |
| access | html |
| website | https://foodscores.state.al.us/default.aspx |
| violations | none |
| history | latest-only |
| result model | SCORE_100_HIGH |
| status | integrated |
| verified | 2026-10-13 |
| refresh | In-app live adapter (county re-checks ~20 h) + bundled seed |
| restrictions | Jefferson and Mobile are NOT served by ADPH — separate agencies. |
| notes | ASP.NET statewide search; latest score + inspection date only. Tallapoosa County upstream HTTP 500 (README caveat). |

### Mobile County Health Department (al-mchd)

| field | value |
|---|---|
| coverage | Mobile County |
| access | html |
| website | https://mchd.org/ |
| violations | none |
| history | some-history |
| result model | SCORE_100_HIGH |
| status | integrated |
| verified | 2026-10-13 |
| refresh | In-app live adapter (admin-ajax table) |
| notes | Up to 4 dated inspections per establishment; no violation detail. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
