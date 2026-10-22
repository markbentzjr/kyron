# Changelog

All notable changes to Kyron will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub Actions CI workflow template for data validation gates
- CONTRIBUTING.md with build instructions and development guidelines
- SECURITY.md policy document
- CHANGELOG.md for release tracking

### Changed
- Documentation improvements for developer onboarding

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
