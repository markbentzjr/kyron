# Georgia (GA) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DECLARED-ONLY (publication declared, artifact not verified)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-ga.manifest.json
- **Pipeline:** harvest/ga/ — pack built, NOT yet published
- **Summary:** Pack verified end-to-end in the rig and registered in-app; the publication is declared but the host returned HTTP 404 on 2026-10-22 (declared-only, not verified downloadable).

## Official sources

### Georgia Department of Public Health (ga-dph)

| field | value |
|---|---|
| coverage | Statewide (excl. Gwinnett/Newton/Rockdale) |
| access | html |
| website | https://ga.healthinspections.us/stateofgeorgia/ |
| violations | full |
| history | some-history |
| result model | SCORE_100_HIGH |
| status | pack-built |
| verified | 2026-10-13 |
| refresh | Harvest pipeline harvest/ga -> tools/packs/build_pack.py |
| restrictions | Gwinnett, Newton and Rockdale counties are NOT in the statewide search. |
| notes | 100-point scale with A/B/C/U grades; full inspector notes. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
