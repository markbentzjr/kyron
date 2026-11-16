# Arizona (AZ) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Summary:** County-run; Maricopa letter grades verified; no statewide search.

## Official sources

### Maricopa County Environmental Health (az-maricopa)

| field | value |
|---|---|
| coverage | Maricopa County (~4.6M, incl. Phoenix) |
| access | html |
| website | https://envapp.maricopa.gov/EnvironmentalHealth/FoodInspections |
| violations | full |
| history | some-history |
| result model | LETTER_GRADE |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Fetched 200 OK; letter grade cards ('A' for Food Safety) + full reports — NOT a numeric-score jurisdiction. |

### Pima County Health (az-pima)

| field | value |
|---|---|
| coverage | Pima County (Tucson) |
| access | html |
| website | https://healthinspect.pima.gov/portal/ |
| violations | unverified |
| history | unverified |
| result model | PASS_FAIL |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Fetched 200 OK; JS portal app. |

### Arizona ADHS + smaller counties (az-rest)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://www.azdhs.gov/preparedness/epidemiology-disease-control/food-safety-environmental-services/index.php |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | ADHS (fetched 200) has NO statewide results search — records requests only; ~15 county/city departments publish separately (Coconino, Yavapai, …). |

<!-- KEEP: freeform notes below this line are preserved across regens -->
