# Kyron v2.0.1 — Final Delivery & Nationwide Integration Report

**Commit SHA:** tagged `v2.0.1` (branch: `release-preparation`, base `0cee7c3` / v1.05)
**Tag:** `v2.0.1`
**Application ID:** `com.kyronapp.kyron`
**Version Code:** `11`
**Version Name:** `2.0.1`
**Min SDK:** `29` (Android 10)
**Target SDK:** `36` (Android 16 / Play target requirements update effective August 31, 2026)

---

## 1. Summary of Implemented Changes
- **Target SDK Compliance:** Both build pipelines (`app/build_manual.sh`, `app/build_windows.sh`, `tools/build_release_app.py`) now consume `app/version.properties` as a single source of build metadata — **versionCode 11 / versionName 2.0.1 / minSdk 29 / targetSdk 36** everywhere. This resolves the previous split (canonical pipeline linked targetSdk 34 while the Python orchestrator linked 36).
- **Startup-Crash Lineage Wired Into Both Pipelines:** v1.04's deterministic full-AAR staging (`app/stage_aars.py`) and mandatory pre-sign dex audit (`app/audit_apk.py`) are now also run by `tools/build_release_app.py` (previously only the shell pipelines audited; the Python orchestrator could have repro'd the `NoClassDefFoundError` crash).
- **Canary Gate Default Repaired:** `tools/canary_gate.py`'s default seed path (stale since the script moved to top-level `tools/`) now points at `../app/src/main/assets/…` — the bare report command `python tools/canary_gate.py` passes with exit code 0.
- **Nationwide 50-State Architecture:** Bundled national coverage registry (`us_national_registry.json`) covers all 50 U.S. states and Washington, D.C. (51 jurisdictions) with truthful status classification (bundled, pack-built, source-verified, official-link-only).
- **Real App Bundle Generated:** `Kyron-2.0.1.aab` built with bundletool 1.18.3 via the new `tools/build_bundle.py` (aapt2 `--proto-format` link → base module → `build-bundle`), and verified with `bundletool dump manifest` + `build-apks --mode=universal`.
- **Build Orchestration & Release Signing:** Production APK release-signed with the owner's `kyron-release` keystore (CN=Kyron) and verified via `apksigner verify`; artifact names now derive from `VERSION_NAME`.

## 2. Important Files & Architectural Decisions
- `app/version.properties` — Single source of truth for build metadata (VERSION_NAME, VERSION_CODE, MIN_SDK, TARGET_SDK), consumed by all three build entry points.
- `app/src/main/assets/coverage/us_national_registry.json` — The authoritative national registry containing all 50 states and D.C. jurisdictions, agency links, and result models.
- `app/src/main/java/com/kyronapp/kyron/data/NationalCoverage.kt` — Registry parsing and model mapping logic.
- `app/src/main/java/com/kyronapp/kyron/data/Regions.kt` — Region descriptor model integrating hand-known regions with registry-derived entries.
- `app/src/main/java/com/kyronapp/kyron/ui/CoverageActivity.kt` — State picker UI presenting truthful statuses, official source links, live pack-host probing, and GPS state proposal.
- `app/build_windows.sh` / `app/build_manual.sh` — Canonical manual pipelines (manifest merge, gates, aapt2, kotlinc+javac R, D8, dex audit, zipalign, opt-in release signing).
- `tools/build_release_app.py` — Native Python build orchestration, now version.properties-driven and dex-audited.
- `tools/build_bundle.py` — AAB production: proto-format link, base-module staging, bundletool build + verification.

## 3. 50-State Coverage & Verification Matrix Summary
- **Integrated / Bundled (1 state):** Alabama (`us-al` — JCDH, ADPH, MCHD; live in app).
- **Pack Built / Published (5 states):** Florida (`us-fl`) and Georgia (`us-ga`) published (declared-only until hosted), Tennessee (`us-tn`), South Carolina (`us-sc`), and Delaware (`us-de`) built staged-local.
- **Source Verified / Registered (44 states + D.C.):** North Carolina, Mississippi, Virginia, Arkansas, Louisiana, Pennsylvania, New York, Illinois, and the remaining states have verified official source URLs and ingestion adapters or registry entries exposed via the Coverage screen.

## 4. Test Commands & Actual Results (re-run Oct 23, 2026)
- **Vector PathData Gate:** `python tools/validate_pathdata.py app/src/main/res` → **PASS (23 files, 25 paths, 0 malformed)**.
- **Seed Dataset Gate:** `python tools/validate_seed.py app/src/main/assets/places_seed_geocoded.json` → **PASS (134 places, 0 G1–G6 violations)**.
- **Canary Completeness Gate:** `python tools/canary_gate.py` → **PASS (134 canaries: 128 pinned + 6 accounted, plus 6 search canaries, under FTS4 semantics)**.
- **APK Dex Audit:** `python app/audit_apk.py app/Kyron-2.0.1-release.apk` (in-pipeline) → **PASS (9,601 defined classes; 10,198 referenced; 0 missing, non-platform)**.
- **Badging:** `aapt2 dump badging` → **package com.kyronapp.kyron, versionCode 11, versionName 2.0.1, minSdk 29, targetSdk 36; AAB dump manifest matches exactly**.
- **Bundle Verification:** `bundletool dump manifest` → matches APK badging; `bundletool build-apks --mode=universal` → **OK (8.5 MB universal set)**.

## 5. Remaining Bugs, Blockers & Unverified Behavior
- **Technical Blockers:** None.
- **Play Console Prerequisites:** Owner login, store listing completion, Data safety questionnaire, and Play App Signing enrollment for the first upload remain as owner-only actions. The local `kyron-release` key (CN=Kyron, SHA-256 `5114fb03f5b896a212cbf5ce22ae534d0e6056edf30f4020b8d4601f6953ec1c`) must be retained as the upload key — it is stored outside the repo at `~/kyron-build/release/` and is never committed.

## 6. Release Version & Publication Status
- **Version:** v2.0.1 (code 11), tagged `v2.0.1` on `release-preparation`.
- **Artifacts Generated:**
  - `app/Kyron-2.0.1-release.apk` — 8,984,911 bytes, SHA-256 `82837547DA416EC2CE0F726529658852BE67C996FDCDED21E6F927C67D08204B`, release-signed (CN=Kyron), `apksigner verify` clean.
  - `app/Kyron-2.0.1.aab` — 8,008,259 bytes, SHA-256 `8C41FA480A8B6B61CDEC51CD37F062661A05E3DAD96F2431FD5D3C25B1B3513D`, unsigned upload-ready bundle (Google signs at upload via Play App Signing).
- **Publication Status:** Staged locally as the release candidate. Ready for manual publication in GitHub Releases and Google Play Console (closed test) upon owner approval.
