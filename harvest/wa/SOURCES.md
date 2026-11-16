# Washington (WA) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** built locally, not published
- **Availability:** STAGED-LOCAL (pack exists on disk, not published)
- **Pipeline:** harvest/socrata_cities/ — kingco source (King County only)
- **Summary:** King County pack built + validated locally (penalty points + rating); statewide is fragmented.

## Official sources

### Public Health — Seattle & King County (wa-kingcounty)

| field | value |
|---|---|
| coverage | King County (incl. Seattle) |
| access | api |
| website | https://data.kingcounty.gov/Health-Wellness/Food-Establishment-Inspection-Data/r878-4sxa |
| violations | full |
| history | some-history |
| result model | PENALTY_LOW |
| status | pack-built |
| verified | 2026-10-25 |
| last refresh | 2026-10-25 |
| refresh | Harvest pipeline harvest/socrata_cities (kingco) |
| restrictions | King County only; other counties publish separately. |
| notes | Socrata r878-4sxa (old gkhn-e8mn now requires login): one row per violation, red (critical)/blue points; score = inspection points (LOWER is better); result + Excellent/Good/Okay/Needs to Improve rating as result text. No coordinates published. Pack BUILT locally 2026-10-25 (12,167 places / 32,971 inspections, 2-year window). |

### Washington State DOH + county health departments (wa-statewide)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://doh.wa.gov/you-and-your-family/food-safety |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | No statewide results portal verified. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
