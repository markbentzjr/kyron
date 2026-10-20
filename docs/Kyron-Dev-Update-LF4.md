# Kyron dev update — LF-4: region packs + state selection (board task K-05)

**Recovery note.** The first LF-4 builder died mid-work on Oct 13, 2026
(~6:23 PM CDT) in a runtime restart — not a code failure. It left source
edits on disk and an unverified build-output APK (md5 `97c63014…`) that
was **never trusted and never delivered**. This changelog is from the
recovery pass: the inherited tree was audited line-by-line against the
K-05 scope, the gaps below were finished, everything was rebuilt from
source, and the full battery was re-run. **Delivered APK:
`~/workspace/your_files/kyron-improvement/Kyron-2.0.apk`, md5
`33a54a0e2a892f220398763e66691223` — identical to the build output of the
same name in `~/kyron-build/manual/` (both checksums stated, verified
after copy).** It replaces the QA-fixed LF-0→LF-3 build (md5
`9f2eab88…`). Badging: package `com.kyronapp.kyron`, versionCode 3 /
versionName "2.1" (see the conflict flag in the coordination answers —
that versioning was already in the shared tree's build script; LF-4 did
not set it). Same debug signing cert as every prior build, so it
installs over the old one and existing on-device data migrates (proven
by the migration test below).

---

## 1. Audit of the inherited tree — what the dead agent had done

Verified by reading the code, not by trusting it:

| K-05 scope item | State found |
|---|---|
| (a) State/jurisdiction in the model + safe DB migration | **Done.** `Place` carries `state`, `jurisdiction`, `nativeResult`; `CatalogDb` is schema v2 — `onUpgrade` adds `state`/`jurisdiction`/`region_id`/`result_text` columns with `AL`/`us-al` defaults (every v1 row *is* Alabama, so the defaults are the migration; no row is moved or rewritten). The user store is a separate DB file and is never touched by catalog migrations or pack operations. |
| (b) Hard-coded "AL" out of addresses | **Done.** `fullAddress()` composes from the place's own `state`. The remaining `AL` literals are legacy-data defaults (pre-LF-4 JSON with no state field *is* Alabama data) and the Alabama sources' own display labels in `Sources.kt` — both correct. |
| (c) State/coverage picker UI | **Done.** `ui/CoverageActivity.kt` (registered in the manifest, launched from MainActivity's region chip): searchable 50-state list with truthful per-state status (Included / Downloaded · data version · place count / Available / Not covered yet), Material card + button components per the coordination agreement, GPS *proposal* with an explicit confirmation dialog (an uncovered state is named as uncovered, never shown as an empty region), and a persisted manual-override flag that nothing automatic overrides. |
| (d) Region-pack format + loader | **Done.** `data/PackManager.kt` + offline builder `tools/packs/build_pack.py`. Manifest carries region, dataset version, place count, schema version, and SHA-256 of the pack file. Install discipline: size + SHA-256 verified **before** the file is opened; the pack's own `pack_meta` must agree with the manifest (region, schema ≤ what the app understands, exact place count); the previous artifact rotates to N−1 (`<region>.prev.db.gz` + prev manifest) before the swap; rows swap inside **one** catalog transaction (delete region → copy → rebuild that region's FTS rows), so a failed install leaves the old region byte-identical. Deltas are JSON change sets that apply only on their exact base version and are parsed fully before any write (the QA BUG-2 lesson). Rollback reinstalls the N−1 artifact (rolling back twice toggles). Region removal deletes rows + artifacts and refuses for bundled regions. |
| (e) Alabama bundled default | **Done.** The bundled seed imports as region `us-al` and is recorded under the same pack bookkeeping keys (`pack_version:us-al`); AL works fully offline with no download. |
| (f) Florida pack proof case | **Done.** `tools/packs/out/us-fl/us-fl-2026-10-13.1.db.gz` (6.86 MB) + `us-fl.manifest.json`, built by `build_pack.py` from the K-02 prototype output (`~/kyron-build/harvest/fl_dbpr/OUTPUT/places_fl.json`): **70,051 places**, every one written with the `NO_SCORE` sentinel (−1) and its native DBPR disposition verbatim in `result_text`. No score is converted, estimated, or invented — in the data, in `WhySummary.dispositionExplainer`, or in `DetailActivity`, which renders the native result with its own tone/badge and never a number. Browse hides the score-band chips and score sorts for disposition regions; catalog band filters hard-exclude `score < 0` so the sentinel can never fall into "Below 85". |

Also found in place: region scoping through Browse (per-region county
list, filters reset on region bind), Map (viewport queries scoped to
the active region, recenter-on-switch, cross-region filter guard),
Favorites (cross-region by design — a favorite survives its region's
removal), Alerts (county sync stays explicitly Alabama's ADPH with the
reason documented in code; FL has no on-device sync source until K-06),
and `ExploreState` shared-query behavior from LF-3.

## 2. What the recovery pass finished

1. **BUG (real, user-facing) — FTS silently dead on every reopened
   database.** `CatalogDb.ftsAvailable` was set only in `onCreate`, so
   on any existing database (every returning user; any second
   `CatalogDb` instance) it stayed `false`: text search silently fell
   back to LIKE, and pack swaps skipped FTS inserts entirely — an
   installed region was **unsearchable by text**. Found when the FL
   proof test failed on a name search that the pack data provably
   contains. *Fix:* `onOpen` now probes `sqlite_master` for
   `places_fts` (creating it if a legacy DB somehow lacks it).
   Regression test added: `Lf4Test.ftsAvailableOnReopenedDatabase`.
2. **Latent alert-copy bug for scoreless places.** `SyncEngine`'s
   alert text assumed a numeric score ("New score for ★ X: −1",
   threshold comparisons against the `NO_SCORE` sentinel). Unreachable
   today (no FL sync source exists yet) but guaranteed to misfire the
   day pack deltas start feeding alert events. *Fix:* favorite alerts
   for disposition places use the native result verbatim ("New
   inspection for ★ X — result: …"), are never flagged "low", and the
   area rule now requires `hasNumericScore`. Alabama behavior unchanged.
3. **Binary-compat shim.** LF-4 added a `regionId` parameter to
   `CatalogDb.search`, which broke linkage for the pre-compiled QA
   harness classes (`QaAdvTest` calls the old 8-arg signature; its
   sources were not in the tree — see backlog item 25). *Fix:* the
   pre-LF-4 8-arg signature restored as a delegating overload; QA suite
   links and passes again (below).
4. **Verification, this changelog, GOAL/backlog updates, delivery** —
   none of which the dead agent reached. (Its own `Lf4Test.kt` suite
   existed but had evidently never been run to green: the FL proof test
   is what exposed bug 1.)

## 3. Verification — pass 1 (Mark's test-at-least-twice discipline)

All runs are against the delivered build (md5 `33a54a0e…`) unless noted;
the Robolectric rig is the same JVM harness as every prior wave.

- **Lf4Test — 7/7 PASS, run twice** (plus twice more on the immediately
  prior build during diagnosis): catalog v1→v2 migration preserves
  every row + the user store snapshot is byte-identical across it;
  pack install with region-scoped search/bounds/counties and
  `fullAddress()` state correctness ("100 Main St, GAINESVILLE, FL
  32608"); native results preserved with **no numeric score ever
  surfacing for Florida through any band**; bit-flipped pack rejected
  on checksum, truncated pack rejected, place-count-lying pack
  rejected — working region intact after each; delta applies on its
  exact base only, stale-base refused, poisoned delta applies nothing;
  rollback restores N−1 exactly; region removal deletes rows but the
  user store (favorites incl. one pointing at the removed region,
  counties, rules, inbox, outbox) is provably untouched; **full Florida
  proof: the real 70,051-place pack installs end-to-end (2.8–3.6 s rig
  time), AL↔FL switching returns each state's own data (23,526 +
  70,051 = 93,577 places co-resident), counties stay region-separated.**
- **GeoTest — PASS.** 23,526 AL places; 17,613 real coordinates
  (74.9%); 0 centroid-sourced; 0 out-of-state; Birmingham bounds 1,746.
- **DbTest — 3/3 PASS.** v2.0-fixture migration lossless, backup
  round-trip exact + idempotent, row-level merge.
- **PerfTest — PASS** (same rig timings class as LF-0→LF-3).
- **QaAdvTest + QaLikeTest — 8/8 PASS** (the independent QA wave's own
  adversarial suites, re-run against this build after the shim fix:
  duplicate-UUID favorites, malformed-backup atomicity, unicode/500-
  favorite round trips, timestamp attacks, literal-wildcard search).
- **Dex audit — zero NEW missing classes.** 9,958 defined classes, 6
  dex files, 802 R classes; the referenced-but-undefined set is the
  identical 13 known-benign entries as the QA-fixed build (platform
  Conscrypt/BouncyCastle/OpenJSSE TLS providers, framework XmlPull,
  one CLASS-retention annotation).
- **LaunchTest / UiTest — rig limitation only, signature identified.**
  All 5 fail inside Robolectric's binary-resource loader on resource
  `0x7f070076`, which `aapt2 dump resources` proves is
  `drawable/abc_vector_test` — the same AppCompat test drawable as
  every prior build (its ID moved because the resource table grew).
  The drawable is present and correctly referenced in the APK; no test
  reaches app logic. As with every wave, **Mark's Z Fold7 device gate
  remains the real launch check.**
- **Build reproducibility note:** of four builds in this pass, one
  failed at kotlinc with spurious "unresolved R" errors across all UI
  files while a parallel build was sharing `work/` (generated R.java
  verified complete on disk; the immediate retry built clean). Treat
  builds as serialized until the pipeline gets per-builder work dirs
  (backlog item 28).

## 4. Production-policy audit (binding, Mark — Oct 13, 2026)

**Embedded keys / tokens / test-account references — CLEAN.**
- Source sweep (`src/main/java`, `res`, `AndroidManifest.xml`,
  `build_manual.sh`): no API keys, no tokens, no `kyronfoodsafety`
  string anywhere. Geocodio appears **nowhere** in source or APK — it
  remains pipeline-only (its residual queue lives in
  `tools/geocode/out/`, outside the app).
- Final-APK sweep (all 6 dexes + assets + resources, 953 files): no
  `kyronfoodsafety`, no `geocodio`, no credential-shaped strings. The
  single pattern hit, a bare `apikey=` literal in `classes6.dex`,
  traces to the **osmdroid library's own classes.jar** (an empty query
  fragment in its API client) — no key value exists.
- The one URL LF-4 adds is the plan-sanctioned static pack-manifest
  location on the project's own public GitHub Pages
  (`markbentzjr.github.io/kyron/data/us-fl.manifest.json`, Free/
  LocalFirst gameplan §2.3): a public static file, no credential, no
  per-user account, no runtime dependency on the test inbox. Packs
  themselves are public health-department records.
- No analytics, no ads SDK, no account SDK added by LF-4.

**Guest-first — CONFIRMED.** There is no sign-up, login, or account
prompt anywhere in the app (the only "login" string in the tree is a
design comment in `Backup.kt` about the *future* claim-on-first-login
flow). Browse, Map, scores, Favorites, Alerts, and the Coverage/state
picker all work in the default local mode with no account; the state
picker never gates a feature, and denying location permission leaves
the manual list fully usable.

## 5. Coordination answers for the 2.1 team

1. **UI files LF-4 edited, and their status at this ship:** `ui/CoverageActivity.kt` (NEW — LF-4-owned), `ui/BrowseFragment.kt` (region binding, disposition-aware bands/sorts), `ui/MapFragment.kt` (region scoping, recenter-on-switch, cross-region filter guard), `ui/AlertsFragment.kt` (comment-level scoping note; county list stays AL by design), `ui/FavoritesFragment.kt`, `ui/DetailActivity.kt` (native-result rendering), `ui/PlaceAdapter.kt` (badge/tone for scoreless places), `MainActivity.kt` (region chip + Coverage entry point), `res/layout/activity_coverage.xml` (NEW). **All are final and stable as of this ship** — LF-4's data layer underneath them is frozen (item 2). Note the tree also carries 2.1-wave edits to several of the same files (bottom nav, county-picker dialog, Material restyling) that landed in the same shared tree during the parallel work; the shipped build passed the full battery with both waves' changes in. LF-4 pass 2 should file any nav/icon inconsistency it finds as 2.1 backlog rather than blocking, per the Oct 13 coordination agreement.
2. **Final data-layer API signatures (frozen for 2.1):**
   - `Prefs` (facade over `UserStore`): unchanged from the QA-fixed build — `favorites: Set<String>`, `store.setFavorite(placeId, Boolean)`, `monitoredCounties`, `profileName`, `threshold`, `alertsForFavorites/alertsForArea`, `addAlert(AlertItem)`, `store.allRules/allInbox(includeDeleted)`, `store.outboxCount()`.
   - `PlaceRepository`: `load()`, `places: StateFlow<List<Place>>`, `byId(id)`, `count()`, `counties(regionId: String? = null)` (null = all regions), `searchPlaces(PlaceQuery, regionId: String? = null)`, `placesInBounds(minLat, maxLat, minLng, maxLng, limit = 5000, regionId: String? = null)`, `mergeFresh(List<Place>): List<PlaceEvent>`, `updatePlace(Place)`, `setCoords(placeId, lat, lng)`, plus pack ops `installPack(File, PackManifest): PackInstallResult`, `applyPackDelta(File, PackManifest): PackInstallResult`, `rollbackPack(regionId): Boolean`, `removePack(regionId)`, `packHasRollback(regionId): Boolean`, `installedRegionVersion(regionId): String?`, `regionPlaceCount(regionId): Int`, and the public `packs: PackManager`.
   - `UserStore` basics: unchanged contract (UUID ids, created/updated, tombstones, version, `sync_outbox` written-never-drained).
   - `Regions` / `RegionManager`: `Regions.KNOWN`, `Regions.byId/byState/regionIdForState/stateForPoint/sourceDisplayName`, `Regions.MODEL_SCORE`/`MODEL_DISPOSITION`, `Regions.US_STATES`; `RegionManager.activeRegion: StateFlow<String>`, `activeRegionId()`, `activeInfo()`, `setActive(regionId, manual)`, `manualOverride`.
   - `PackManager` / `PackManifest`: `PackManifest.fromJson(JSONObject)`; `installFullPack(db, File, PackManifest)`, `applyDelta(db, File, PackManifest)`, `rollback(db, regionId)`, `removeRegion(db, regionId)`, `installedVersion/installedManifest(db, regionId)`, `hasRollback(regionId)`, `PackManager.sha256(File)`; refusals are `PackException` with the catalog untouched.
   - Model: `Place.state/jurisdiction/nativeResult`, `Place.regionId` (derived: `"us-" + state.lowercase()`), `Place.hasNumericScore`, `Place.NO_SCORE = -1`, `Place.badgeText/resultTone`, `Place.shortResultLabel/resultToneOf`, `Inspection.nativeResult`; `CatalogDb` schema v2, `SUPPORTED_PACK_SCHEMA = 2`.
3. **What CoverageActivity's redesign must preserve:** the truthful-status model (Included / Downloaded with data version + place count / Available / Not covered yet — never an empty-region pretense); GPS *proposes only* — a confirmation dialog before any switch, an honest "not covered" dialog for uncovered states, and the persisted manual-override semantics (a hand pick is never overridden); the action set per state (Use / Download / Roll back with confirm / Remove with
...[truncated 3389 chars]