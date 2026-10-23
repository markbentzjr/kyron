# Kyron — Nationwide Restaurant Health Scores

Kyron is a free Android app that makes public restaurant health-inspection
results easy to browse and worth paying attention to. **Alabama ships with
the app** (23,526 establishments, live-synced), and **every U.S. state —
plus Washington, D.C. — is registered** in the built-in national coverage
registry (`app/src/main/assets/coverage/us_national_registry.json`,
generated from `tools/coverage/coverage_pipeline.py`; see
`docs/Kyron-National-Coverage-Matrix.md`).

"Covers every state" means the nationwide FRAMEWORK is in place: each state
lists its official source(s), status, access method, verification date and
result model — honestly distinguishing integrated data, built-but-
unpublished packs, verified-but-not-ingested sources, and official-link-only
fallbacks. It does NOT mean every jurisdiction's data is integrated yet.
Today's integrated data:

| Source | Coverage | What it publishes |
|---|---|---|
| **JCDH** — Jefferson County Dept. of Health | Jefferson County, AL | Scores **plus full violation detail** and inspection history |
| **ADPH** — Alabama Dept. of Public Health | 65 AL counties | Latest score + inspection date |
| **MCHD** — Mobile County Health Dept. | Mobile County, AL | Scores + up to 4 dated inspections per place |

Plus region packs (built, app-registered): **Florida DBPR** (dispositions,
70,051 places) and **Georgia DPH** (100-pt A/B/C/U). Packs for **Tennessee**
and **South Carolina** are built and staged — blocked only on publishing
infrastructure. 28 further states have official sources directly
fetch-verified (HTTP 200 with real content) as of 2026-10-22; the matrix
documents every state's concrete next step.

## Features

- **Browse & search** the statewide catalog, filter by county and score band
- **Map view** (OpenStreetMap, no API key) with score-colored pins
- **"Why this score?"** — for Jefferson County, a plain-language summary of
  the actual violations behind the number, with the inspector's own notes
- **Favorites** — star places and get alerted whenever they receive a *new*
  inspection score
- **Area alerts** — pick counties (or a radius around a center point) and a
  threshold; get alerted when a new score lands below it
- **Background sync** about every 12 hours. Merging is failure-safe: if a
  source is down, existing data is never wiped
- Alerts land as **notifications** and in an in-app **alert inbox**

Accounts, favorites and alert rules live on the device in this release;
cloud-synced accounts are on the roadmap (see `docs/Kyron-2.0-Blueprint.md`).

## Installation

### Installing from GitHub Releases

Kyron is distributed as an APK file that you can download and install directly from GitHub releases.

**Quick install:**
1. Go to the [Releases page](https://github.com/markbentzjr/kyron/releases)
2. Download the latest `Kyron-2.0.apk`
3. Install the APK on your Android device
4. Open Kyron and start browsing

For detailed installation instructions, troubleshooting, and system requirements, see [INSTALL.md](INSTALL.md).

**System requirements:**
- Android 9.0 (API level 29) or later
- 20-30 MB free storage space
- Internet connection for initial sync and updates

**Note:** You may need to enable "Install from unknown sources" in your phone's settings to install the APK. This is a standard Android security feature for apps not from the Play Store. See [INSTALL.md](INSTALL.md) for detailed instructions.

## Why one adapter per source?

The US has **no national restaurant-inspection database** — every state and
county publishes its own, in its own format, on its own scoring scale. Kyron
is built as a federation of small per-jurisdiction adapters
(`app/src/main/java/com/kyronapp/kyron/source/Sources.kt`): adding a state
means adding one adapter, nothing else changes. Research on which
jurisdictions to add next is in `docs/Kyron-USA-Source-Registry.md`.

## Known data caveat

ADPH's own search for **Tallapoosa County** currently returns a server error
(HTTP 500) on the state's site, so only a couple of its establishments could
be included in the bundled snapshot. The app re-checks counties during sync,
so Tallapoosa backfills automatically once ADPH fixes their page.

## How nationwide coverage works

- **Result models differ by jurisdiction** and Kyron never converts them
  into one fabricated 0–100 number: 0–100 scores where higher is better
  (AL, GA, TN…), penalty/demerit scales where LOWER is better, letter
  grades (MS), pass/fail and compliance (PA, WI…), violations-only (VA,
  AR, DC…), and dispositions (FL, HI placards…). Missing scores are never
  rendered, banded, or averaged as 0.
- **Region packs** add states on demand — a verified, checksummed SQLite
  pack per region, never bundled nationwide data in the APK. Favorites,
  alerts and preferences live in a separate user store and survive pack
  install/update/rollback/remove.
- **Adding a state** = harvest pipeline under `harvest/<state>/` →
  `tools/packs/build_pack.py` → publish the manifest at the pack host →
  register the pack region. See CONTRIBUTING.md and the matrix doc.

## Repository layout

- `app/` — the Android app (Kotlin). Note on the build: Kyron is currently
  built with a **manual single-process pipeline** (`app/build_manual.sh`):
  `aapt2` + `kotlinc` + R8/D8 + `apksigner`, with library manifests merged by
  `app/merge_manifest.py` and dependencies fetched by `app/fetch_deps.sh`.
  It exists because the development sandbox blocks the inter-process TCP the
  Gradle daemon needs; the source layout under `app/src/main` is a standard
  Android project layout, and porting back to a Gradle build is
  straightforward.
- `harvest/` — Python tooling that builds the bundled statewide snapshot
  (`app/src/main/assets/places_seed.json`): ADPH county harvester, JCDH
  catalog enumerator, MCHD harvester, and the seed builder that merges them.
- `tools/` — Validation gates (pathData, seed dataset, canary completeness),
  geocoding tools, region pack tools, and Robolectric test suite.
- `docs/` — The 1.x audit, the 2.0 product blueprint, the Alabama / USA
  source research, and detailed dev update reports.
- `CONTRIBUTING.md` — Build instructions, development guidelines, and how to
  add new data sources.
- `CHANGELOG.md` — Version history and release notes.
- `SECURITY.md` — Security policy and vulnerability reporting guidelines.

## Data

All scores are public health-department records, republished as-is.
Inspection data belongs to the publishing agencies; Kyron's code is what
this repository licenses.

## License

MIT — see [LICENSE](LICENSE). (The bundled dataset is a build artifact
generated by `harvest/` from the public sources above and is not committed;
it ships inside the release APK.)
