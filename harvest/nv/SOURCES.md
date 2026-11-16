# Nevada (NV) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-nv.manifest.json
- **Pipeline:** harvest/snhd/ — published pack (Clark County only)
- **Summary:** SNHD's nightly CSV is best-in-class bulk data; pack published to the data-packs release, artifact sha256-verified 2026-11-16 (19,755 places, Clark County ~73% of NV population).

## Official sources

### Southern Nevada Health District (Clark County / Las Vegas) (nv-snhd)

| field | value |
|---|---|
| coverage | Southern Nevada |
| access | bulk-csv |
| website | https://www.southernnevadahealthdistrict.org/permits-and-regulations/restaurant-inspections/restaurant-inspection-search/ |
| violations | full |
| history | full-history |
| result model | PENALTY_LOW |
| status | pack-built |
| verified | 2026-10-22 |
| last refresh | 2026-11-16 |
| refresh | Harvest pipeline harvest/snhd (snhd_harvest) |
| restrictions | Southern Nevada only; Washoe County (Reno) and rural DPBH counties are separate. |
| notes | Nightly developer CSV download (restaurants.zip + SQL schema; both pages fetched 200) — ~5-day posting lag. Pack BUILT locally 2026-11-16 (19,755 active-permit places / 238,876 inspections / 425,909 violations, 96.8% geocoded): A/B/C-grade text carried natively with demerit points as the score (lower is better; closures land ~44+). Lat/lng columns are swapped at source — adapter un-swaps; legacy stanford-file violations resolve via query_insp_violations codebook; closed (record_status 02/04/05) permits and their ~95k inspections excluded by convention. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
