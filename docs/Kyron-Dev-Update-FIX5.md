# Kyron — Dev Update: FIX5 (pass 1)

**Date:** October 15–16, 2026 · **Wave:** FIX5 build (CSDM-confirmed scope; inputs staged by Workstream D) · **Spend:** $0 · **GitHub pushes:** none · **Deliveries to Mark:** none (`~/workspace/your_files/` untouched; staged only, awaiting pass-2 QA + CSDM review → device gate)

## Staged candidate

- **File:** `~/kyron-build/manual/Kyron-2.0-FIX5.apk` (== build output `Kyron-2.0.apk`)
- **md5:** `12637dd2a14152fe0a3a3fc1f1de597f` · **size:** 6,763,982 bytes
- **Badging:** package `com.kyronapp.kyron`, **versionCode 9**, versionName "2.0", minSdk 29 / targetSdk 34 — same debug cert as FIX3/FIX4 (SHA-256 `cb932a51…f24f56`)
- **Manifest delta vs FIX4:** exactly one line — versionCode 8 → 9 (permissions identical; INTERNET only)

## What FIX5 is

Three CSDM-confirmed items, all from Workstream D's staged inputs (`~/kyron-build/wsd/out/`, index `README-FIX5-INPUTS.md`):

1. **Catalog-refresh fix (the Chelsea McDonald's fix).** `PlaceRepository.load()` now fingerprints the bundled seed (SHA-256 in catalog meta); a changed/absent fingerprint swaps the bundled region wholesale in one transaction — DEVICE-prov coordinates, downloaded regions, favorites, and the sacred user store preserved — and reconciles the FTS index on every load. Aged catalogs (every pre-FIX5 install, incl. Mark's frozen pre-geocode catalog) heal on first FIX5 launch.
2. **Search fixes.** Apostrophe-alias FTS index + query normalization (both apostrophe forms), LIKE fallback on zero FTS hits (was: only when FTS unavailable), Explore map-filter apostrophe-insensitivity. Source names stay verbatim.
3. **us-ga registration** (C3's one-entry snippet) — Georgia's staged pack becomes installable by the shipped app.

Plus the data: the bundled AL seed is WS-D's remediated seed (below).

## Patch application

`patch -p1` inside `~/kyron-build/manual/` from `wsd/out/fix5.patch`: **clean apply, exit 0**, all five files, no fuzz, no offsets, no hand-rebasing:

- `data/db/CatalogDb.kt` — FTS alias helpers (`stripApostrophes`/`ftsName`/`FTS_NAME_SQL`), `ftsRowCount` + `reconcileFts`, `deviceCoords` snapshot helper
- `data/PlaceRepository.kt` — seed-fingerprint refresh in `load()`, FTS reconcile per load, LIKE fallback on zero FTS hits
- `data/PackManager.kt` — pack FTS rebuild uses the same alias expression
- `data/Regions.kt` — GEORGIA registration (`KNOWN = [ALABAMA, FLORIDA, GEORGIA]`) + GA-DPH display name
- `ui/MapFragment.kt` — apostrophe-insensitive Explore filter matching

Pre-patch sources, the FIX4 seed asset, and the pre-edit build script are backed up at `~/kyron-build/fix5-backup/`. The optional query-hygiene patch was **not** applied (outside the confirmed FIX5 scope; CSDM take-or-leave, per WS-D §5).

## Seed replacement

Bundled asset `places_seed_geocoded.json` replaced with `wsd/out/places_seed_wsd_remediated.json`, byte-identical (md5 `c8d6f25bcdd9ece9368689656e3fdd92` on both the staged file and the installed asset). Independent re-diff vs the FIX4 asset before install: **23,524 → 23,527 places; added exactly the 3 WS-D F-1 JCDH establishments** (`jcdh_21625` Panda Express #2631 Hoover, `jcdh_22231` Crestwood Pharmacy Birmingham, `jcdh_22419` Los Diaz Bessemer — all list-only in the source, no coordinates, nothing invented); **removed: none; changed: exactly 13** (the F-3 stale score/date corrections); pinned count unchanged at **18,712** (79.5%); list-only 4,815.

## Gates (all in the build log `manual/build_fix5_wave.log`, in order)

| Gate | Result |
|---|---|
| Vector pathData validator | 23 files, 25 paths, **0 malformed** — PASS |
| Seed gate (`validate_seed.py`) over the new asset | 23,527 places, G1–G6 all **0** — PASS |
| Canary gate (`canary_gate.py`) | 134 canaries (128 pinned, 6 accounted) + 6 search canaries over 23,527 — PASS |

The same two data gates were also run **standalone on the remediated file before install** (both PASS) and **again on the seed extracted from the finished FIX5 APK** (byte-identical to the remediated file; both PASS).

## Acceptance evidence — the CSDM case, in-tree on the production build

`AgedDbAcceptanceTest` (staged by WS-D, copied into the rig) constructs Mark's aged state byte-for-byte as the pre-fix code leaves it (23,526 legacy AL rows, McDonald's present **unpinned**, 2 DEVICE coords, 1 us-fl witness row, a favorite on the record, stale `bundled-2026-10` meta, no fingerprint) and runs one FIX5 `load()`. **OK (1 test)**:

- Catalog refreshes: 23,526 legacy → **23,528 total** (23,527 remediated AL + FL witness)
- `adph_750e13236c` returns with its **exact** Census pin (33.348118663136, −86.633388069144; CENSUS / ACCEPTED) and is inside the Chelsea viewport result — **the pin renders**
- All **5 acceptance queries** find it: `McDonalds` (223 hits), `McDonald's` (223), `McDonald's` curly (223), `16758` (1), `280 Chelsea` (19)
- The whole data wave lands with it: both WS-B orphan drops gone, `jcdh_11035` name restored ("Regal Trussville Cinemas 16"), pinned total **18,714** (18,712 AL + 1 FL + 2 DEVICE − 1 overlap)
- Preservation: DEVICE-prov coords survive (still labeled DEVICE), FL witness row intact, favorite intact
- Idempotence: a sync-merged fresher copy (score 91) survives a second `load()` — no repeat swap
- FTS self-heal: deleting the record's FTS row, then loading, restores findability

`SearchCanaryTest` **OK (2 tests)** on a fresh FIX5 catalog: all 13 real-user queries surface the McDonald's (5 of 13 failed pre-fix); fresh Chelsea box = 41 places incl. the pin; Browse → Shelby lists it.

## Suite results (production tree/build, this wave's runs)

| Test | Result |
|---|---|
| AgedDbAcceptanceTest | **OK (1)** — acceptance case above |
| SearchCanaryTest | **OK (2)** |
| DbTest | OK (3) |
| GeoTest | OK (1) — 23,527 loaded; 18,712 real pins (79.5%), all address-range; 0 centroid, 0 out-of-state, 0 missing geo status |
| Lf4Test | OK (9) — incl. full FL pack proof on FIX5 |
| FlLiveTest | OK (1) — FL install/browse/map/switch/removal vs `fl-publish` staged bytes |
| GaLiveTest | OK (1) — **against the production build** (no scratch tree): GA pack installs through PackManager, co-residence 23,527 + 70,033 + 33,514 = **127,074**, Kimchi II 76/band C, why-summary narrative, Atlanta viewport 4,108 pins, clean removal |
| StartupUpgradeTest | OK (3) — incl. MainActivity create on upgrade state |
| Qa2UpgradeTest | OK (2) |
| Qa2PackAttackTest | OK (2) |
| PerfTest | OK (1) — first-load import 27.5 s (one-time, 8.06 MB seed); steady load 1.1 s; search 38 ms; bounds 46 ms |
| UpgradeChainTest | **Fails by design** — defect record: flips at `UpgradeChainTest.kt:129` (`assertFalse`: "McDonalds" must NOT find it on the aged catalog — post-fix it returns 223 hits). No edits made to this test. |
| FtsDesyncTest | **1/2 pass + 1 by-design flip** — `importSeedIsAtomic` PASSES (single-transaction import preserved post-patch); the desync test constructs the desync correctly (23,527 places / 23,526 FTS rows; search misses the record pre-heal) then flips at line 88's "nothing heals it" assertion — `reconcileFts` now heals at load. |
| LaunchTest | Fails with the **pre-existing rig artifact** — `Resources$NotFoundException` on AppCompat's own `abc_vector_test` drawable (0x7f07004e), byte-identical failure in the Oct 13 `launch_run.log` from the original 2.0 build; the resource maps identically in FIX4/FIX5 arsc, and FIX5 touches no resources. The operative Activity-create gate is `StartupUpgradeTest.mainActivityCreateAttempt`, which passes and excuses exactly this named artifact (any non-rig exception would fail it). |

**Environment note (not a product defect):** FlLiveTest's first run failed with `No space left on device` inside `PackManager.ungzipTo` — the sandbox's 512 MB `/tmp` tmpfs (the same artifact class C3 and the data-wave QA hit; the limit does not exist on-device). Re-run with a disk-backed `java.io.tmpdir` passed cleanly; GaLive/Lf4/Qa2/Perf runs used the disk-backed tmpdir from the start.

## Test-expectation changes (all count-only, all for one data reason)

**Data reason for every change below:** the FIX5 bundled seed is WS-D's remediated seed — AL goes 23,524 → 23,527 (3 JCDH establishments restored, 13 stale scores corrected, 0 removed, pins unchanged at 18,712).

- `AgedDbAcceptanceTest.kt` (WS-D staged): post-refresh totals 23,525 → **23,528** (2 assertions + comments) — 23,527 AL + 1 FL witness (the aged-state precondition 23,527 = 23,526 legacy + witness is a different sum and unchanged).
- `SearchCanaryTest.kt` (WS-D staged): docstring only (FIX4 seed → FIX5 seed, 23,524 → 23,527). No assertion changes.
- `FtsDesyncTest.kt` (WS-D staged): asset-count literals 23,524 → 23,527 (×2) and post-deletion FTS count 23,523 → 23,526 (×1). Behavioral assertions untouched — with literals corrected, the atomicity half passes and the no-heal half flips by design (above).
- `DbTest.kt`: 23,524 → 23,527 + comment. `GeoTest.kt`: 23,524 → 23,527.
- `Lf4Test.kt`: 23,524 → 23,527 (×3: two `regionPlaceCount("us-al")`, one co-resident total) + comments.
- `FlLiveTest.kt` / `GaLiveTest.kt`: `alCount` 23,524 → 23,527 (GaLive's co-resident total is computed from it: 127,071 → 127,074).
- `PerfTest.kt`: 23,526 → 23,527. Disclosure: this literal was **already stale** — it predates the data wave (the FIX4-era harness ran a bytecode-patched class, per the data-wave changelog); FIX5 runs PerfTest from source with the true count.

No other test logic was changed. `UpgradeChainTest` was deliberately **not** edited.

## Audits

- **Zip delta FIX4 → FIX5:** 498 entries both; changed = exactly 6 (binary `AndroidManifest.xml`, seed asset, `classes2.dex`, 3 signature files); **492 entries byte-identical, including `resources.arsc` and `classes.dex`**.
- **R ↔ arsc:** arsc byte-identical to FIX4's audited state; R classes 595 in both (audit_apk.py), app R present; no R class appears in the added/changed lists. FIX4's R↔arsc consistency carries over unchanged.
- **Dex audit (audit_apk.py):** defined classes 7,845 → **7,847**; referenced types 8,689 → 8,691; the undefined-reference list is **identical to FIX4's** (the known-benign platform/optional-provider family — bouncycastle/conscrypt/xmlpull/sun-misc/room-compiler artifacts; no new undefined references from the patch). Coroutines `META-INF/services` present (both factories).
- **Class-level delta (dexdump structural compare, string-pool indices normalized):** added = exactly 2 — `PlaceRepository$Companion` (holds the seed-fingerprint meta key) and `PlaceRepository$$ExternalSyntheticLambda0`, both from the patch's PlaceRepository changes. Removed = 0. Changed = exactly **21 classes, 0 of them library classes**, every one defined in the five patched files: CatalogDb + Companion; PlaceRepository + its 10 coroutine continuation classes; PackManager + Companion; PackManifest (defined in PackManager.kt); Regions; RegionManager + Companion (defined in Regions.kt); MapFragment + MapFragment$Cluster.
- **PathData:** build gate (above) — 23 files / 25 paths / 0 malformed.
- **Production-policy sweep of the FIX5 APK:** no `kyronfoodsafety` (0 hits); **no `geocodio`** (0 hits — the only "geocod" string anywhere is the seed asset's filename, `places_seed_geocoded.json`, also in MANIFEST/SF listings); no `AIza` Google keys; no private-key material; the single `api_key`/`apikey` string is byte-identical to FIX4's known valueless osmdroid literal. Guest-first intact: no auth/sign-in code in the patch, no new permissions, catalog/search/pack flows all local.

## Known residuals (unchanged from WS-D, not FIX5 scope)

- Tallapoosa County remains under-covered (2 listings) until ADPH's county search recovers server-side (F-6).
- Optional query-hygiene patch (natural "<name> in <city>" phrasing + standalone-punctuation tokens) staged separately at `wsd/out/fix5-optional-query-hygiene.patch` — CSDM take-or-leave.
- Route-designator synonyms (US/Hwy/Highway 280) + Ste/Suite query normalization: quantified fast-follow (WS-D §3).
- FL + GA packs remain staged unpublished in `~/kyron-build/fl-publish/` pending the CSDM's publish-route decision; FIX5 registers us-ga, so the GA pack installs the moment it is published — no further app change needed.

## Build provenance

Built by `build_manual.sh` on the production tree (log: `manual/build_fix5_wave.log` — all three gates visible in order: pathData → seed → canary, then compile/link/dex/sign), Kotlin compile of 59 sources with **0 warnings**, output signed with the lineage debug cert and staged as `Kyron-2.0-FIX5.apk` (md5 above). Test logs: `~/kyron-build/test/fix5_*.log`.
