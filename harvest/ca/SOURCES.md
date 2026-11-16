# California (CA) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-ca.manifest.json
- **Pipeline:** harvest/socrata_cities/ — sf source (San Francisco only)
- **Summary:** San Francisco pack published to the data-packs release, artifact sha256-verified 2026-11-16 (6,253 places, 0-100 scores); county-fragmented otherwise (CalCode).

## Official sources

### Los Angeles County Department of Public Health (ca-lacounty)

| field | value |
|---|---|
| coverage | Los Angeles County (excl. Pasadena/Long Beach/Vernon) |
| access | api |
| website | https://data.lacounty.gov/Health/LOS-ANGELES-COUNTY-RESTAURANT-AND-MARKET-INSPECTIO/6ni6-h5kp |
| violations | full |
| history | full-history |
| result model | SCORE_100_HIGH |
| status | source-verified |
| verified | 2026-10-13 |
| restrictions | Excludes Pasadena, Long Beach and Vernon (own health departments). |
| notes | Inspections + separate violations dataset (8jyd-4pv9); numeric score + letter grade. |

### San Francisco Department of Public Health (ca-sf)

| field | value |
|---|---|
| coverage | San Francisco |
| access | api |
| website | https://data.sfgov.org/resource/pyih-qa8i.json |
| violations | full |
| history | some-history |
| result model | SCORE_100_HIGH |
| status | pack-built |
| verified | 2026-10-13 |
| last refresh | 2026-11-16 |
| refresh | Harvest pipeline harvest/socrata_cities (sf) |
| notes | Numeric 0-100 score plus dedicated violations dataset (f29f-c3np). Pack BUILT locally 2026-11-16 (6,253 places / 890 inspections — full dataset, one inspection row per violation-bearing inspection). |

### California Department of Public Health (Retail Food Program) (ca-statewide)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/RetailFoodProgram.aspx |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | CalCode makes 60+ county EHDs the publishers; no statewide portal, bulk download, or API (AFDO index lists counties only; CDPH page fetch-blocked on 2026-10-22). |

<!-- KEEP: freeform notes below this line are preserved across regens -->
