# Colorado (CO) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/mhd/ — MyHealthDepartment adapter (proof pack only)
- **Summary:** Shared state platform + Denver's own program; risk-index points, no 0–100 score.

## Official sources

### Colorado CDPHE + delegated counties (shared platform) (co-cdphe)

| field | value |
|---|---|
| coverage | Statewide (some counties opt out) |
| access | html |
| website | https://inspections.myhealthdepartment.com/colorado/ |
| violations | full |
| history | some-history |
| result model | PASS_FAIL |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Fetched 200 OK (linked from CDPHE page; CDPHE plain fetch is 403). Results are Pass / Re-Inspection Required / Closed with risk-index points (Pass 0–49; Re-inspect 50–109; Closed 110+) — NOT a 0–100 score or letter grade. Generic MHD adapter (harvest/mhd) validated end-to-end 2026-11-16 — bounded proof pack: 151 places / 518 violations with native result text; full-history harvest pending. |

### Denver Department of Public Health & Environment (co-denver)

| field | value |
|---|---|
| coverage | City & County of Denver |
| access | html |
| website | https://www.denvergov.org/restaurantinspections |
| violations | full |
| history | some-history |
| result model | PASS_FAIL |
| status | source-verified |
| verified | 2026-10-22 |
| notes | Fetched 200 OK. Inspections after 9/6/24 moved to Accela (aca-prod.accela.com/DENVER); Denver self-inspects. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
