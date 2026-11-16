# Wisconsin (WI) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/mhd/ — MyHealthDepartment adapter (proof pack only)
- **Summary:** Dual-vendor state (DATCP + HealthSpace local agencies).

## Official sources

### Wisconsin DATCP (state-inspected facilities) (wi-datcp)

| field | value |
|---|---|
| coverage | Statewide (state-inspected) |
| access | html |
| website | https://inspections.myhealthdepartment.com/wisconsin-datcp |
| violations | full |
| history | some-history |
| result model | PASS_FAIL |
| status | source-verified |
| verified | 2026-10-22 |
| restrictions | State-inspected jurisdictions only; agency-delegated ones are a second source. |
| notes | DATCP publishes directly (fetched 200 OK); ~130 agency-managed local health departments publish separately in HealthSpace. Generic MHD adapter (harvest/mhd) validated end-to-end 2026-11-16 — bounded proof pack: 196 places / 202 inspections / 495 violations, 0 unverified; full-history harvest pending. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
