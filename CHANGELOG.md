# Changelog

All notable changes to Kyron will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI workflow for data validation gates; CONTRIBUTING.md,
  SECURITY.md, INSTALL.md (earlier 2026-10-22 improvements, preserved).
- **Nationwide coverage framework (LF-N)**: a data-driven registry covering
  all 50 US states PLUS Washington, D.C. as a separate federal-district
  jurisdiction (`assets/coverage/us_national_registry.json`, generated and
  gated by `tools/coverage/coverage_pipeline.py`). Per state: official
  sources with access method, coverage scope, exclusions, verification
  date, result model, and honestly-distinct statuses (integrated /
  pack-built / source-verified / official-link-only / blocked).
- Coverage screen now renders every state + D.C. from the registry with
  pack-host health probes (a 404 pack host is reported, not hidden), an
  "Official sources" dialog for every state with links to the agency's
  own sites, and generated coverage matrix doc
  (`docs/Kyron-National-Coverage-Matrix.md`).
- Result-model generalization: penalty/demerit scales, letter grades,
  pass/fail, violations-only, and dispositions all keep their NATIVE
  presentation; score bands/chips/sorts adapt per region (e.g. penalty
  ranges "0–9 / 10–19 / 20+"). Alabama thresholds never apply to other scales.
- Antimeridian-safe map viewport queries (western Aleutians no longer vanish).
- CI gate + local Python gate for the registry (exactly 50 states + D.C.,
  unique sources, status vocabularies).
- **Registry schema 2** (2026-10-22): per-jurisdiction `pack_availability`
  (`bundled | downloadable-verified | declared-only | staged-local | none`),
  `artifact_verified` date, and map `center` — so "a pack was published"
  can never be confused with "a verified download exists". The gate
  enforces the consistency laws (declared-only requires a failing host;
  downloadable-verified requires manifest + verified artifact date;
  staged-local requires a built pack). Flow map assigns ONE primary tier
  per state; the 50-state tally is a hard SystemExit guard.
- **First verified national expansion slice — Delaware (us-de)**: SODA
  dataset `384s-wygj` (33,519 rows) harvested, normalized (3,731 places,
  9,202 inspections, 32,570 violations), pack built and validated locally
  (`us-de-2026-10-23.1.db.gz`, sha256 recorded in the registry). Pack is
  STAGED-LOCAL only — not published, no download offered.
- Source-level result models: `NationalCoverage.modelForPlace/modelForSource`
  resolve per registry SOURCE (a state may mix scales); explicit
  `MODEL_UNKNOWN` degrades to neutral (no bands, no score sorts, no
  threshold alerts) instead of defaulting to Alabama's 0–100.
- `AlertEvaluator`: pure decision core separating initial baseline,
  duplicates/retries, newly listed establishments (informational),
  corrected records (same date), and genuinely new inspections;
  per-place event keys + per-region baseline markers persist in catalog
  meta and are removed with the region.
- Deterministic test suites (31 tests, runnable via
  `tools/robolectric-test/run_national_windows.sh`): `SortingModelTest`
  (higher-is-better 60/80/95; penalty 25/10/2; NO SCORE never banded),
  `AlertLogicTest` (alert case matrix, dedupe, no date cutoffs), and an
  expanded `NationalCoverageTest` (schema-2 fields, DE staged-local
  semantics).

### Changed
- Sync alerts: first-sightings (backfill / reinstall) no longer fire
  duplicates; threshold semantics applied only to higher-is-better scales.
  Baseline/backfill is now marker-based (`alerts_baseline:<region>` +
  per-place `alerts_evt:<placeId>`), not date-based.
- Cross-region search degrades honestly: mixed scales get neutral sorting
  and no numeric band (no fake nationwide best/worst ranking).
- Detail "why" text is now jurisdiction-aware (no Alabama band language for
  non-AL scores).
- Welcome text and Coverage messaging generalized beyond Alabama.

### Known Issues
- **All published pack manifest URLs currently return HTTP 404** (verified
  2026-10-22: us-fl, us-ga, us-tn, us-sc) — remote pack downloads are
  unavailable until the host is republished; TN/SC packs additionally
  remain staged-not-published.
- Kotlin build toolchain unavailable in the 2026-10-22 working environment
  (no kotlinc/JDK/WSL) — the app build and Robolectric suite (incl. the new
  `run_national.sh`) could not be executed there; Python gates were run.

## [2.0] - October 2026

### Added
- Multi-state region support (LF-4): Alabama (bundled), Florida, Georgia (via region packs)
- Region pack system with install/update/rollback capability
- State selection UI in CoverageActivity
- Native result display for non-score jurisdictions (e.g., Florida DBPR dispositions)
- SQLite catalog database replacing JSON file storage (LF-2)
- FTS4 full-text search with apostrophe-insensitive matching
- Address-level geocoding with provenance tracking (geoStatus, geoAccuracy, geoProvider)
- Map viewport query with real coordinate filtering
- Material 3 UI overhaul (2.1): real vector icons, labeled bottom navigation, redesigned alerts

### Fixed
- FIX5: Catalog refresh mechanism to heal aged databases when bundled seed changes
- FIX5: Search apostrophe handling (McDonald's vs McDonalds)
- FIX5: FTS index self-heal on load
- FIX4: Region model and multi-state data support
- FIX3: Inspection history persistence
- Earlier fixes: Removal of mock scraper, Google Maps placeholder API key, data-safe sync merging

### Security
- No hardcoded API keys in production
- Guest-first mode (no sign-up required for core features)
- Local-first architecture with optional cloud sync planned

### Known Issues
- Tallapoosa County under-covered due to ADPH server error (HTTP 500)
- Robolectric tests have known limitations with large resource tables

## [1.0] - Earlier

### Added
- Initial Alabama restaurant health score browser
- Jefferson County (JCDH) integration with violation detail
- Alabama statewide (ADPH) integration
- Mobile County (MCHD) integration
- Map view with OpenStreetMap (osmdroid)
- Favorites and alerts system
- Background sync every 12 hours
- Manual build pipeline (no Gradle)

### Known Issues (from initial audit)
- Mock scraper injected fake restaurants (fixed in later versions)
- Google Maps placeholder API key (replaced with osmdroid)
- Data wipe on source failure (fixed with failure-safe merging)
- Inspection history not persisted (fixed)
- Debug build shipped (release build added later)

---

## Version Policy

- **Major version (X.0.0):** Breaking changes, major new features, architecture changes
- **Minor version (x.Y.0):** New features, backward-compatible changes
- **Patch version (x.y.Z):** Bug fixes, data improvements, documentation

The manual build pipeline tracks version in `app/build_manual.sh`:
- `--version-code`: Integer incremented for each release
- `--version-name`: Human-readable version string

## Data Versioning

The bundled seed dataset has its own versioning tracked in the database meta table:
- Key: `bundled_seed_sha:us-al` (or other region ID)
- Value: SHA-256 hash of the seed JSON
- When the hash changes, the app refreshes the region from the new seed

Region packs have their own schema version in `PackManifest.schema_version`.
Current supported pack schema: `SUPPORTED_PACK_SCHEMA = 2` (in CatalogDb.kt)
