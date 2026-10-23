# Kyron National Expansion — Progress Report & Resumable Checklist

**Date:** 2026-10-22 · **Workstream:** LF-N (nationwide framework, 50 states + D.C.)
This report states exactly what is implemented, what was verified live, what
could not be run in this environment, and what remains. Executable code was
treated as authoritative over docs where they conflicted.

---

## 1. Audit findings (start of this window)

| Finding | Evidence | Resolution in this window |
|---|---|---|
| All four published pack manifests return **HTTP 404** (`us-fl`, `us-ga`, `us-tn`, `us-sc`) | Direct fetch of each URL on 2026-10-22 | Coverage UI + registry now record `pack_host_status: unreachable-404`; downloads stay permitted (host may return) and failures surface clearly |
| Docs said FL/GA packs were "available" and TN/SC "staged" | Pack reports | Registry distinguishes `published` vs `built` vs host health; doc/matrix regenerated from data |
| No registry structure; 50-name list in `Regions.US_STATES` only | `Regions.kt` | Registry JSON + `NationalCoverage.kt` loader + gate |
| Alert dedupe gap: `SyncEngine` fired alerts when `e.old == null` (reinstall/backfill duplicates) | Code read of `SyncEngine.kt` step 5 | Fixed: first sighting never alerts |
| Numeric band/chip/sort + threshold semantics were 0–100-Alabama-only | `PlaceRepository`, `BrowseFragment`, `MapFragment`, `WhySummary` | Generalized via result models; NO_SCORE sentinel excluded everywhere |
| Map viewport query could not match across the antimeridian | `CatalogDb.inBounds` BETWEEN | Wrap-aware OR query |
| Alert threshold could compare a penalty scale to an Alabama threshold | Code read | Threshold applies only to `SCORE_100_HIGH` territories |

---

## 2. What is implemented NOW (working vertical slice)

1. **Registry** — `assets/coverage/us_national_registry.json` (schema 1,
   generated 2026-10-22): **51 jurisdictions = 50 unique states + D.C. as a
   separate federal-district entry**; **67 unique sources**, each with
   agency, coverage scope, access method, exclusions/restrictions, native
   result model, verification date, refresh notes, and one of five
   distinct statuses. Generated + validated by
   `tools/coverage/coverage_pipeline.py` (`build`, `gate`, `matrix`).
2. **App wiring** — `data/NationalCoverage.kt` (bounded parse-once loader);
   Coverage screen renders ALL states + D.C. from it (result-model legend
   per state, pack-host probes, honest `official-link-only` labeling, an
   "Official sources" dialog linking agency sites — never presented as data).
3. **Result-model generalization** — `MODEL_SCORE_100_HIGH` (higher better),
   `MODEL_PENALTY_LOW` (penalty, lower better), `LETTER_GRADE`,
   `PASS_FAIL`, `DISPOSITION`, `VIOLATIONS_ONLY`; shared `bandRange`/
   `bandMatches`; Browse chips/sorts and Map filtering adapt per region;
   SQL bands hard-exclude `score = -1`; area/fav alerts honor the model
   (`supportsThresholdAlerts`).
4. **Map correctness** — antimeridian-safe `inBounds`; same
   verified-geocode-only pinning (ungeocoded places stay in Browse, never
   faked as pins).
5. **Alerts & sync safety** — no fire on `e.old == null`; model-aware
   numeric alert paths.
6. **Tests** — `tools/robolectric-test/NationalCoverageTest.kt`
   (12 tests listed below) + `run_national.sh`; Python registry gate wired
   into `.github/workflows/ci.yml`.
7. **Docs** — `docs/Kyron-National-Coverage-Matrix.md` (generated),
   this report, README/CHANGELOG updates.

### Current honest coverage tiers (from the registry, machine-counted)

| Tier | States |
|---|---|
| **Integrated data in-app** (bundled + live sync) | 1 — Alabama |
| **Pack built, app-registered** (host or publication pending) | 2 — FL (published/404 host), GA (published/404 host), plus TN & SC (`built`, not published) → counted 4 pack states total, 5 including AL |
| **Official source fetch-verified (HTTP 200, real content), no ingestion** | 34 — NC MS VA AR LA PA NY IL CA MA WA OR WI OK VT SD WY RI NJ NV TX UT MD MO MT AZ CO AK HI DE IA KS ME DC |
| **Official-link-only / blocked (named blockers; NEVER counted as data)** | 12 — MI MN NE NH NM ND WV CT ID KY IN OH |

No endpoint, restaurant record, score, or violation was invented. Any
derived summary (band text, cluster shading) stays clearly labeled as
presentation, not an agency rating.

---

## 3. Commands ACTUALLY run + results in this window

| Command | Result |
|---|---|
| `python tools/coverage/coverage_pipeline.py build` | **PASS** — "GATE PASS: 50 unique states + 1 D.C.; 67 unique sources; all vocabularies valid" (after catching & fixing: missing ND, non-namespaced source id, missing link-only limitation) |
| `python tools/coverage/coverage_pipeline.py gate` | **PASS** (twice) |
| `python tools/coverage/coverage_pipeline.py matrix` | **PASS** — regenerated `docs/Kyron-National-Coverage-Matrix.md` |
| `python tools/validate_pathdata.py app\src\main\res` | **PASS** — 23 files, 25 paths, 0 malformed |
| Live HTTP GETs of `us-fl/us-ga/us-tn/us-sc` manifests | **404 ×4** |
| `kotlinc` compile of app + tests | **NOT RUN — unavailable** (no kotlinc/JDK/bash/WSL on this Windows box; documented in CONTRIBUTING as Unix-only sandbox) |
| Robolectric suite (new `run_national.sh`, existing run_test/run_host_test) | **NOT RUN — cannot execute** here; written to run in the standard `$HOME/kyron-build` sandbox |
| Full APK build (`app/build_manual.sh`) | **NOT RUN — cannot execute** here |
| Benchmarks (search/map/install/memory) | **NOT RUN** — `tools/robolectric-test/PerfTest.kt` requires the Robolectric runtime |

The registry, matrix, and pathData gates are the checks this environment
could genuinely run; everything Kotlin-side is specified, reviewable, and
testable in the normal build sandbox but is honestly NOT verified here.

---

## 4. New/changed files this window

**New:** `app/src/main/assets/coverage/us_national_registry.json` (generated),
`app/src/main/java/com/kyronapp/kyron/data/NationalCoverage.kt`,
`tools/coverage/coverage_pipeline.py`,
`docs/Kyron-National-Coverage-Matrix.md` (generated),
`docs/Kyron-National-Expansion-Progress-2026-10-22.md` (this file),
`tools/robolectric-test/NationalCoverageTest.kt`,
`tools/robolectric-test/run_national.sh`.

**Modified:** `data/Regions.kt`, `data/Models.kt` (unchanged API), 
`data/PlaceRepository.kt`, `data/WhySummary.kt`, `data/db/CatalogDb.kt`,
`ui/CoverageActivity.kt`, `ui/BrowseFragment.kt`, `ui/MapFragment.kt`,
`ui/DetailActivity.kt`, `worker/SyncEngine.kt`, `MainActivity.kt`,
`README.md`, `CHANGELOG.md`, `.github/workflows/ci.yml`.

Preserved: manual build pipeline (`app/build_manual.sh` untouched), all AL
seed data, user-store/data-store separation, pack architecture and its
validation semantics, Places/Regions public APIs (added-to, not replaced).

---

## 5. Ingestion & pack-building (reproducible path, unchanged mechanics)

1. Research + fetch: write a harvester under `harvest/<state>/` following
   the existing field-mapped per-state tooling (`fl_dbpr/`, `ga/`, `tn/`,
   `sc/`, `nc/` are reference implementations — each has `FIELD_MAPPING.md`,
   fetchers with per-response SHA-256 logs, parsers, builder, independent
   QA cross-check).
2. Normalize to Kyron `Place` JSON (native results preserved verbatim;
   NO_SCORE sentinel for non-numeric; geocode provenance required).
3. Pack: `python tools/packs/build_pack.py <region> <places.json>` →
   gzip SQLite + `*.manifest.json` with schemaVersion ≤ 2, exact place
   counts and SHA-256s.
4. Verify in-app semantics via PackManager's existing gates; the
   registry's per-state entry is then updated (`pack_status`, verified
   dates) by editing `coverage_pipeline.py` and re-running `build`.

## 6. Migration / compatibility notes

- No schema change was needed: registry is an asset; models generalize the
  EXISTING `score`/`result_text`/`region_id` columns; every existing id,
  favorite, alert rule and pack version survives unchanged.
- New registry fields are additive; `Regions.KNOWN` remains the pack-
  capable set so PackManager cannot be tricked into installing a pack for a
  state with no verified pack.

## 7. Resumable checklist for the next window

1. [ ] Publish the pack artifacts (host choice per
      `docs/Kyron-Publish-Route-Decision-Brief-2026-10-17.md`) — needs
      maintainer approval (external infrastructure).
2. [ ] Verify FL/GA manifests 200 after republication; then re-check the
      app download path end-to-end in the rig.
3. [ ] Publish TN/SC staged packs.
4. [ ] Run `app/build_manual.sh` + `run_national.sh` in the sandbox; fix
      anything Kotlinc flags (this environment could not compile).
5. [ ] First new-state integration vertical slice — recommend **Oregon**
      (statewide, scored, full history) or **Delaware** (Socrata violation-
      row API, verified returning real rows) following §5.
6. [ ] Jurisdiction-level picker UI for fragmented states (registry schema
      already supports multiple sources per state).
7. [ ] Benchmarks (PerfTest) with a realistically large multi-region
      catalog; the registry itself is bounded and never loads place data.
8. [ ] Convert the remaining 12 link-only/blocked states: KY/IN/OH need
      per-county sourcing; NH/MN/ND are records-request states — document,
      don't simulate.
