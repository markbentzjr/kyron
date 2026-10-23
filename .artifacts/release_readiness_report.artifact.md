# Kyron v2.0.1 — Production Release Readiness & Compliance Report

**Commit SHA:** tagged `v2.0.1` (branch: `release-preparation`, base `0cee7c3` / v1.05)
**Tag:** `v2.0.1`
**Application ID:** `com.kyronapp.kyron`
**Version Code:** `11`
**Version Name:** `2.0.1`
**Min SDK:** `29` (Android 10)
**Target SDK:** `36` (Android 16 / Play target requirements update effective August 31, 2026)

---

## 1. Google Play Target SDK Compliance & Policy Audit
- **Requirement:** Effective August 31, 2026, Google Play requires all new apps and app updates to target API level 36 (Android 16) or higher.
- **Official Reference:** [Google Play Target SDK Requirements](https://developer.android.com/google/play/requirements/target-sdk) (Checked: March 2026).
- **Compliance Status:** All three build entry points now link `targetSdk 36` from `app/version.properties` (VERIFIED in produced APK + AAB badging: `targetSdkVersion:'36'`) while maintaining backward compatibility down to `minSdk 29` (Android 10).

---

## 2. Artifact Inventory & Signing Status (VERIFIED, Oct 23 2026)

| Artifact | Filename | Size (bytes) | SHA-256 Checksum | Signing Status | Certificate Fingerprint / Identity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Release APK** | `app/Kyron-2.0.1-release.apk` | 8,984,911 | `82837547DA416EC2CE0F726529658852BE67C996FDCDED21E6F927C67D08204B` | Signed (Release, verified via `apksigner verify`) | `CN=Kyron, OU=Kyron, O=Kyron, C=US` — SHA-256 `5114fb03f5b896a212cbf5ce22ae534d0e6056edf30f4020b8d4601f6953ec1c` |
| **Android App Bundle (AAB)** | `app/Kyron-2.0.1.aab` | 8,008,259 | `8C41FA480A8B6B61CDEC51CD37F062661A05E3DAD96F2431FD5D3C25B1B3513D` | Unsigned / Upload-Ready | Protected Play App Signing (Managed via Google Play Console); upload key = the `kyron-release` keystore |

### Signing Identity & Channel Compatibility:
- **Local/GitHub Builds:** Signed with the owner-owned `kyron-release` keystore, kept outside the repo at `C:\Users\Mark\kyron-build\release\` (never committed; password held in `release/secret/`).
- **Google Play Distribution:** Signed with Google Play's App Signing key; the `kyron-release` key serves as the upload key.
- **Distribution Compatibility Note:** Due to Android package signature verification rules, users who install the GitHub release APK (local key) cannot perform in-place updates from builds installed via Google Play (Play App Signing key) unless uninstalled first.

---

## 3. Automated Tests & Data Validation Results (re-run Oct 23, 2026)

| Test / Gate | Command / Environment | Result | Evidence / Notes |
| :--- | :--- | :--- | :--- |
| **Vector PathData Gate** | `python tools/validate_pathdata.py app/src/main/res` (Python, Win11) | **PASS** | 23 files, 25 paths validated — 0 malformed paths. |
| **Seed Dataset Gate** | `python tools/validate_seed.py app/src/main/assets/places_seed_geocoded.json` | **PASS** | 134 records validated against G1–G6 rules — 0 violations. |
| **Canary Completeness Gate** | `python tools/canary_gate.py` (default paths repaired) | **PASS** | 134 canaries (128 pinned + 6 accounted) + 6 search canaries verified under FTS4 semantics. |
| **APK Dex Audit** | `python app/audit_apk.py app/Kyron-2.0.1-release.apk` (in-pipeline, mandatory) | **PASS** | 9,601 defined classes; 10,198 referenced types; 0 missing non-platform. Prevents the v1.04-class `NoClassDefFoundError` launch crash. |
| **Badging Check** | `aapt2 dump badging` (APK) + `bundletool dump manifest` (AAB) | **PASS** | Both artifacts: versionCode 11 / versionName 2.0.1 / minSdk 29 / targetSdk 36 — exact match. |
| **Bundle Build Check** | `bundletool build-apks --mode=universal` | **PASS** | Bundle parses fully; 8.5 MB universal APK set generated. |
| **Host / Unit Tests** | Robolectric test suite | **PASS** | JVM runtime boots cleanly, schema migrations and SQLite FTS reconcile successfully. |

---

## 4. Region-Pack & Data Verification
- **Bundled Seed:** Validated against Workstream B/D rules (`places_seed_geocoded.json`).
- **Region Packs:** Alabama bundled; Florida + Georgia published (declared-only until hosted), Tennessee, South Carolina, Delaware built and staged-local. Unreleased/staged regions are marked with honest unavailable/coming-soon states.

---

## 5. Privacy, Data Safety & Store Listing
- **Privacy Policy:** Compliant with local-first processing, zero data exfiltration, and on-device SQLite FTS storage.
- **Data Safety:** Declares zero collection of personal data, no third-party tracking, and local-only location usage.
- **Store Materials:** Complete title, short description, full description, and release notes prepared in [.artifacts/store_listing.artifact.md](file:///C:/Users/Mark/Documents/Kyron/kyron/.artifacts/store_listing.artifact.md).

---

## 6. Release Status Summary

| Milestone | Status | Details |
| :--- | :--- | :--- |
| **A. Work Completed** | **COMPLETED** | Build pipelines (single-sourced version metadata, targetSdk 36), data validation gates, canary checks, dex audit in both pipelines, and store/privacy materials. |
| **B. Artifacts & Hashes** | **VERIFIED** | Release APK built, release-signed, verified; real AAB (bundletool 1.18.3) built and bundle/tool-verified. |
| **C. Tests Executed** | **PASSED** | All data quality gates, dex audit, badging, and bundle checks passed with exit code 0. |
| **D. GitHub Release** | **READY** | Release notes, SHA256SUMS, and tag `v2.0.1` ready for publication upon approval. |
| **E. Play Technical Readiness** | **READY** | Target SDK 36 compliant, minSdk 29, AAB built and verified, upload key established. |
| **F. Play Console Readiness** | **OWNER ACTION** | Requires owner login to Google Play Console, store listing setup, Data safety questionnaire, and Play App Signing enrollment. |
| **G. Blockers** | **NONE TECHNICAL** | Only owner-only Play Console publication and account verification remain. |
