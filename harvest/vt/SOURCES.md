# Vermont (VT) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Pipeline:** harvest/sfi/ — SafeFoodInspection adapter
- **Summary:** Single-state agency; numeric score + violations; same platform family as SD/WY/PA.

## Official sources

### Vermont Department of Health — Food & Lodging Program (vt-vdh)

| field | value |
|---|---|
| coverage | Statewide |
| access | html |
| website | https://vtdoh.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx |
| violations | full |
| history | full-history |
| result model | SCORE_100_HIGH |
| status | source-verified |
| verified | 2026-10-22 |
| notes | 'Food Safety 5.5' platform; numeric inspection score (44-item checklist) + critical flags since May 2016. ASP.NET POST needed. SFI adapter (harvest/sfi) validated end-to-end 2026-11-16 — bounded proof pack: 20 places / 112 inspections / 231 violations incl. report-PDF extraction; full-history harvest pending. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
