# Alaska (AK) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/sfi/ — SafeFoodInspection adapter
- **Summary:** State portal verified (safefood platform); Anchorage excluded.

## Official sources

### Alaska DEC — Food Safety & Sanitation (ak-dec)

| field | value |
|---|---|
| coverage | Statewide (excl. Anchorage) |
| access | html |
| website | https://adec.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx |
| violations | full |
| history | some-history |
| result model | VIOLATIONS_ONLY |
| status | source-verified |
| verified | 2026-10-22 |
| restrictions | Municipality of Anchorage runs its own program and is NOT in the state portal. |
| notes | DEC-run ASP.NET portal fetched 200 OK; FDA Food Code citations, no score/grade. dec.alaska.gov program page 403s automated fetches. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
