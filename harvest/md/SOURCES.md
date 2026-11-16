# Maryland (MD) — harvest folder

_Generated 2026-11-16 from `us_national_registry.json` — rerun `tools/coverage/gen_state_harvest_dirs.py`; do not hand-edit the tables._

- **Pack status:** published to the data-packs release
- **Availability:** DOWNLOADABLE-VERIFIED (bytes sha256-checked against the signed index)
- **Manifest:** https://github.com/EMC-MB/kyron/releases/download/data-packs/us-md.manifest.json
- **Pipeline:** harvest/socrata_cities/ — montgomery source
- **Summary:** Montgomery County pack published to the data-packs release, artifact sha256-verified 2026-11-16 (4,160 places, compliance flags); statewide portal at present unreachable.

## Official sources

### Montgomery County (md-montgomery)

| field | value |
|---|---|
| coverage | Montgomery County |
| access | api |
| website | https://data.montgomerycountymd.gov/resource/5pue-gfbe.json |
| violations | partial |
| history | some-history |
| result model | VIOLATIONS_ONLY |
| status | pack-built |
| verified | 2026-10-22 |
| last refresh | 2026-11-16 |
| refresh | Harvest pipeline harvest/socrata_cities (montgomery) |
| notes | Socrata (fetched 200 with data): per-item In/Out of Compliance rows. Pack BUILT locally 2026-11-16 (4,160 places / 6,708 violations — full dataset). Data caveat: ~32 place names carry a literal U+FFFD where the county's own import mangled 'é' ('CAF�') — source-side corruption in older rows, unrecoverable (the 'organization' field is the legal entity, not the trade name); shipped verbatim. |

### Maryland DHMH Office of Food Protection (24 LHDs) (md-statewide)

| field | value |
|---|---|
| coverage | Statewide (not verified) |
| access | official-link-only |
| website | https://health.maryland.gov/phpa/pages/ofp.aspx |
| violations | unverified |
| history | unverified |
| result model | VIOLATIONS_ONLY |
| status | official-link-only |
| restrictions | No reproducible automated access verified; official link only — NOT integrated restaurant data. |
| notes | Statewide search vsi.maryland.gov was unreachable on 2026-10-22 (3 attempts); many counties publish by records request. |

<!-- KEEP: freeform notes below this line are preserved across regens -->
