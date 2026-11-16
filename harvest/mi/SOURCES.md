# Michigan (MI) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** no pack
- **Availability:** none
- **Summary:** State portal covers groceries only; restaurants are local agencies.

## Official sources

### Michigan Dept. of Agriculture & Rural Development — MiSafe (mi-mdard)

| field | value |
|---|---|
| coverage | Grocery/processor facilities ONLY (NOT restaurants) |
| access | html |
| website | https://www2.mda.state.mi.us/MiSafe/Default |
| violations | full |
| history | full-history |
| result model | VIOLATIONS_ONLY |
| status | blocked |
| verified | 2026-10-22 |
| blocker | MiSafe (fetched 200 OK) explicitly EXCLUDES restaurants — those are inspected by ~45 local health agencies with their own portals. |
| notes | Do not count MiSafe as restaurant data; Kent County et al. are the real restaurant publishers. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
