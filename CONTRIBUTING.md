# Contributing to Kyron

Thank you for your interest in contributing to Kyron! This document provides guidance for developers who want to build, test, and improve the project.

## Build Overview

Kyron uses a **manual build pipeline** (`app/build_manual.sh`) rather than Gradle. This design choice exists because the development sandbox blocks the inter-process TCP that the Gradle daemon requires. The source layout under `app/src/main` is a standard Android project layout, and porting back to a Gradle build is straightforward if needed.

### Prerequisites

- **JDK 17** - Required for Kotlin compilation
- **Android SDK** - Build tools 34.0.0, platform android-34
- **Kotlin compiler** - kotlinc (version 2.0.20)
- **Python 3** - For data validation gates and harvest tools
- **bash** - The build scripts are written for Unix-like shells

### First-Time Setup

1. **Set up the build directory structure:**
   ```bash
   export KB=$HOME/kyron-build
   mkdir -p $KB/manual/{work,deps} $KB/tmp
   ```

2. **Download Android SDK:**
   ```bash
   # Install SDK via command-line tools or Android Studio
   # Ensure platform android-34 and build-tools 34.0.0 are installed
   export SDK=$KB/android-sdk
   ```

3. **Download Kotlin compiler:**
   ```bash
   cd $KB
   curl -L -o kotlin-compiler.zip https://github.com/JetBrains/kotlin/releases/download/v2.0.20/kotlin-compiler-2.0.20.zip
   unzip kotlin-compiler.zip
   mv kotlinc $KB/
   ```

4. **Fetch dependencies:**
   ```bash
   cd $KYRON_REPO/app
   ./fetch_deps.sh
   ```

5. **Download Robolectric for testing (optional):**
   ```bash
   cd $KYRON_REPO/tools/robolectric-test
   ./fetch_robolectric.py
   ```

### Building the APK

Run the manual build pipeline:

```bash
cd $KYRON_REPO/app
./build_manual.sh
```

The build process includes several automated gates:

1. **Manifest merging** - Combines app and library manifests
2. **Vector pathData validation** - Ensures vector drawables have valid path data
3. **Seed dataset validation** - Validates the bundled places dataset for completeness
4. **Canary completeness gate** - Ensures known establishments are present
5. **Resource compilation** - aapt2 compile
6. **Kotlin compilation** - kotlinc with generated R classes
7. **Dex conversion** - d8/R8
8. **APK assembly and signing** - zipalign and apksigner

The output APK will be at `app/Kyron-2.0.apk`.

### Running Tests

Kyron has a Robolectric test suite for JVM-level testing:

```bash
cd tools/robolectric-test
./run_host_test.sh  # Runs HostTest (fragment and layout tests)
./run_test.sh      # Runs LaunchTest (MainActivity boot test)
```

**Note:** Robolectric tests in this project have known limitations due to the large Material 3 resource table. Some tests may be limited by binary resource parsing in the Robolectric runtime. On-device testing is recommended for full verification.

### CI Workflows and the Android SDK emulator

`.github/workflows/` carries the automation; nothing needs to be run by
hand:

- **`ci.yml`** — data-validation gates on every PR: pathData, the
  50-state coverage registry gate (`coverage_pipeline.py gate`, incl. its
  cross-check that `Regions.kt`'s hand-maintained `US_STATES` /
  `STATE_BOUNDS` lists stay in lockstep), seed gates when a seed exists,
  license check and a security scan.
- **`emulator-smoke.yml`** — boots an Android SDK emulator (API 34,
  x86_64), installs the debug APK, opens the Coverage screen and filters
  by every one of the 50 state codes **plus D.C.**, requiring each state's
  card to render from the bundled national registry (screenshots + a
  per-state report are uploaded as artifacts). This is how "a state can be
  selected in the app" is verified across all 50 states, since the
  registry is data-driven and the Coverage screen renders it.
- **`publish-state-packs.yml`** — weekly / on-dispatch harvest + build +
  publish of region packs for FL, GA, TN, SC, NC, DE and the Socrata
  city/county packs NY (NYC), IL (Chicago), WA (King County) to the
  rolling `data-packs` GitHub Release, ending with a signed `index.json`.
- **`android-release.yml`** — tag-driven signed APK/AAB release build.

Required repository secrets (owner action, set once in repo settings):

| Secret | Used by | Purpose |
|---|---|---|
| `PACK_SIGNING_KEY` | publish-state-packs | EC P-256 private key (PEM) that signs `index.json`; if absent the index is left unsigned and the app refuses release-hosted pack installs |
| `KYRON_KEYSTORE_B64` / `KYRON_KEYSTORE_PASSWORD` / `KYRON_KEY_ALIAS` / `KYRON_KEY_PASSWORD` | android-release | upload keystore for signed releases |

## Data Validation Gates

The build includes three critical data validation gates that protect data quality:

### 1. Vector PathData Gate (`tools/validate_pathdata.py`)
Validates that all vector drawable `pathData` attributes are syntactically correct. Malformed paths compile cleanly but crash the app at runtime during inflation.

### 2. Seed Dataset Gate (`tools/validate_seed.py`)
Validates the bundled `places_seed_geocoded.json` to ensure:
- Every score is attached to a named place at an address
- No placeholder or truncated names
- No fused name/street splits

### 3. Canary Completeness Gate (`tools/canary_gate.py`)
Ensures the dataset is complete by checking for 134 curated "canary" establishments (2+ well-known places per county). This catches accidental deletions or normalizer regressions.

**Important:** Never edit `tools/canaries.json` to make a build pass. Fix the dataset or normalizer instead.

## Project Structure

```
kyron/
├── app/                      # Android application
│   ├── src/main/
│   │   ├── java/com/kyronapp/kyron/
│   │   │   ├── data/        # Data models, repository, database
│   │   │   ├── source/      # Health department scrapers
│   │   │   ├── ui/          # Fragments and activities
│   │   │   ├── worker/      # Background sync and notifications
│   │   │   └── *.kt         # Application and main activity
│   │   ├── res/             # Android resources
│   │   └── assets/          # Bundled seed dataset
│   ├── build_manual.sh      # Main build pipeline
│   ├── fetch_deps.sh        # Dependency fetcher
│   └── tools/               # Build validation tools
├── harvest/                  # Data ingestion tools
│   ├── adph_*.py            # Alabama state harvester
│   ├── jcdh_*.py            # Jefferson County harvester
│   ├── mchd_*.py            # Mobile County harvester
│   └── build_seed.py        # Seed merger
├── tools/
│   ├── robolectric-test/    # JVM test suite
│   ├── geocode/             # Geocoding tools
│   ├── packs/               # Region pack tools
│   └── *.py                 # Validation gates
└── docs/                     # Documentation and reports
```

## Adding a New Data Source

Kyron is designed as a federation of per-jurisdiction adapters. To add a new state or county:

1. **Create a new source adapter** in `app/src/main/java/com/kyronapp/kyron/source/Sources.kt`:
   - Implement the `PlaceSource` interface
   - Implement scraping logic specific to that jurisdiction
   - Respect rate limits (current implementation uses 2 requests/second)

2. **Register the source** in `SourceRegistry`:
   ```kotlin
   object SourceRegistry {
       val yourSource = YourSource()
       val all: List<PlaceSource> = listOf(jcdh, adph, mchd, yourSource)
   }
   ```

3. **Add to SyncEngine** if needed for background sync

4. **Test the parser** using `tools/parser-harness/` to verify against live pages

## Code Style

- Follow Kotlin idiomatic conventions
- Use existing patterns for similar functionality
- The project uses Material 3 design components
- Avoid adding emoji as functional icons; use Material vector icons instead
- All user-facing text should be plain language with 48dp minimum touch targets

## Testing Before Submitting

1. **Run the full build:** `./app/build_manual.sh`
2. **Verify all gates pass:** pathData, seed validation, canary gate
3. **Run Robolectric tests:** `./tools/robolectric-test/run_host_test.sh`
4. **Check for regressions:** Verify the APK size and dex count are reasonable
5. **Test on device:** Ideally verify on a physical Android device

## Data Quality Requirements

- **No fake data:** Never add mock or test data to production scrapers
- **Provenance tracking:** All coordinates must carry `geoStatus`, `geoAccuracy`, and `geoProvider`
- **No centroid approximations:** Only address-level coordinates should be stored as place locations
- **Native results preserved:** For jurisdictions that don't publish numeric scores (e.g., Florida DBPR), always show the native disposition text. Never invent a score.

## Free/Open-Source Requirements

Kyron's default experience must remain:
- **Free to use** - No subscriptions, paid API keys, or trial credits required
- **Open source** - Prefer local-first, self-hostable components
- **Usable without paid services** - Core workflows work offline or with free public APIs
- **No mandatory accounts** - All features work without sign-up
- **No telemetry** - Do not add tracking or data collection without explicit user consent

When adding features:
- If external computing resources are needed, provide a local or self-hosted option
- Document any network requirements clearly
- Keep proprietary integrations as clearly labeled, optional additions

## Security

- **Never commit credentials** - API keys, passwords, or tokens
- **Redact sensitive logs** - Don't log user data or secrets
- **Validate all input** - Especially data from external sources
- **Use HTTPS** - All network requests should use secure connections
- **Review dependency licenses** - Ensure new dependencies have compatible licenses

## License

By contributing to Kyron, you agree that your contributions will be licensed under the MIT License, as per the existing LICENSE file.

## Getting Help

- Review the documentation in the `docs/` directory
- Check existing issues and pull requests on GitHub
- Review the audit reports and dev updates for context on recent changes
