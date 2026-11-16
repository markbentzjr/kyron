# Texas (TX) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-tx.manifest.json
- **Pipeline:** harvest/socrata_cities/ — austin source (Austin only)
- **Summary:** Austin pack published to the data-packs release, artifact sha256-verified 2026-11-16 (6,448 places, 0-100 scores); no statewide results search.

## Official sources

### Austin Public Health (tx-austin)

| field | value |
|---|---|
| coverage | Austin |
| access | api |
| website | https://data.austintexas.gov/resource/ecmv-9xxi.json |
| violations | partial |
| history | full-history |
| result model | SCORE_100_HIGH |
| status | pack-built |
| verified | 2026-10-22 |
| last refresh | 2026-11-16 |
| refresh | Harvest pipeline harvest/socrata_cities (austin) |
| notes | Socrata API (fetched 200 JSON): numeric 0-100 with color bands. Pack BUILT locally 2026-11-16 (6,448 places — full dataset). |

### Texas DSHS Retail Food Safety Unit (tx-dshs)

| field | value |
|---|---|
| coverage | Where no local program exists |
| access | official-link-only |
| website | https://www.dshs.texas.gov/retail-food-establishments |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| verified | 2026-10-22 |
| restrictions | DSHS inspects only where no local program exists; Houston/Dallas/San Antonio/El Paso publish their own (Dallas/SOCRATA unverified-cited). |
| notes | DSHS (fetched 200) publishes no public results search — only an ArcGIS jurisdiction map and open-records requests. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
