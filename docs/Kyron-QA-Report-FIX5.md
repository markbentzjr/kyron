# Kyron FIX5 — Independent Pass-2 QA Report (bug-hunt)

**Date:** October 15–16, 2026 · **Pass:** 2 (independent; builder's claims distrusted and re-measured) · **Spend:** $0 · **Deliveries to Mark:** none

## Verdict: **SHIP — for CSDM review**

No P1 findings. One P2 process condition (test-tree hygiene, §4 — required before this tree becomes the repo baseline; it is **not** a device-gate blocker). The artifact itself passes every attack this pass mounted: user data survives the catalog refresh **byte-for-byte**, a mid-swap failure rolls back atomically, successive seed changes each refresh, a FIX4 downgrade stays fully compatible (search included), and the CSDM acceptance case passes on independent reruns.

Mark's device gate (FIX5 installed over FIX4 on his aged DB; Chelsea McDonald's pin + search as the case) remains the final closer, as always.

## Candidate identity (verified first and last)

| | Claimed | Measured |
|---|---|---|
| File | `~/kyron-build/manual/Kyron-2.0-FIX5.apk` | same |
| md5 | `12637dd2a14152fe0a3a3fc1f1de597f` | `12637dd2a14152fe0a3a3fc1f1de597f` (first **and** last check) |
| Badging | package `com.kyronapp.kyron`, **versionCode 9**, "2.0", minSdk 29 / targetSdk 34 | exact match (aapt2) |
| Cert | SHA-256 `cb932a51…f24f56` | `cb932a5158d51ff577be2ac5e40b3c30760aeb10248a31d26e2fe7db6af24f56` — identical on FIX4/FIX5 |
| Manifest delta vs FIX4 | versionCode only | badging diff = **exactly one line** (8→9); full manifest xmltree identical modulo versionCode — no new activities, no new permissions |

## 1. User-data preservation under refresh — HELD, byte-for-byte (my own test)

New QA test `QaFix5PreserveTest` (2 tests, **OK on my run**) builds its own aged states — not the builder's fixtures:

- **FIX4-lineage catalog** (imported from the pre-patch backup's FIX4 seed bytes; FTS name column degraded to FIX4's exact plain-name content; `pack_version` meta only, no fingerprint) carrying: SHA-256-canonical dumps of **all non-Alabama catalog rows** (places + inspections + FTS rows) and of the **entire sacred user store** (favorites incl. tombstones, monitored-county areas, both alert rules, an inbox item, profile, outbox count).
- **DEVICE-coords collision, decided empirically:** a DEVICE coordinate set on the Chelsea McDonald's itself (which has a bundled Census pin) **wins over the bundled pin** and keeps its `DEVICE` label — the patch's documented rule ("device data, not seed data"), now proven, not just commented. A DEVICE coordinate on a seed-unpinned place also survives exactly.
- After `load()`: both hashes **identical**; the F-3 correction lands (Beebe's Catering 99/8-6-2025 → 96/5-11-2026); the 3 restored establishments are present and list-only; all 4 favorites (2 AL + 1 FL pack + 1 GA pack) resolve through the refreshed catalog; `McDonalds` finds the record.
- **Dropped-place favorite:** on a legacy-lineage catalog, a favorite + inbox alert pointing at WS-B orphan `adph_65187bf70f` survive the refresh **byte-for-byte in the user store** while the place itself is correctly dropped; favorite resolution skips it gracefully (`mapNotNull` → 1 of 2), search returns empty, nothing crashes. User data is never silently deleted by a data refresh — the correct contract.

## 2. Refresh robustness — HELD (my own test)

New QA test `QaFix5RobustTest` (3 tests, **OK on my run**):

- **(a) Interruption / mid-swap failure (the kill case, at transaction level):** a staged seed whose element 100 is a bare string makes `importSeed` throw *after* `deleteRegionRows` and ~100 inserts, inside the swap. Result: `load()` surfaces the `JSONException` (fail-loud, not swallowed), the catalog is **byte-state untouched** (23,526 rows, McDonald's still the aged unpinned row, FTS still mirroring at 23,526, **no fingerprint recorded**), and a retry with the genuine seed heals completely. The nested-transaction stack rolls back as one — the catalog can never be left half-swapped by an exception at any depth of the swap.
- **(b) Two successive fingerprint changes:** fresh import (sha recorded = SHA-256 of the seed, verified) → doctored seed (one place removed, McDonald's score 98→55) refreshes (23,526; score 55; sha updated) → genuine seed again refreshes back (23,527; 98). The trigger tracks **every** change, not just the first.
- **(c) Downgrade (FIX4 code semantics on a FIX5-refreshed catalog):** catalog schema is **v2 in both builds** (no upgrade/downgrade path is even entered); FIX4's `load()` on a non-empty catalog is read-only (verified in the pre-patch source); `pack_version` is only ever compared as an opaque string / for null. Running FIX4's **verbatim** `ftsIds` query construction against the refreshed catalog's FTS table: `"McDonald's"` → 161 ids incl. the record; `"McDonalds"` → 223 ids incl. the record. **Bonus finding (positive):** because the apostrophe alias lives in the FTS *data*, even FIX4's unpatched query code finds the record both ways on a FIX5 catalog — a downgrade does not re-break headline search.
- **(d)** Dropped-place favorite grace: §1, second test.

## 3. Acceptance — independently rerun, PASSES

| Test (my runs) | Result |
|---|---|
| `AgedDbAcceptanceTest` | **OK (1)** — aged legacy catalog (23,526, McDonald's unpinned) → one FIX5 `load()` → 23,528; record back with its exact pin (33.348118663136, −86.633388069144, CENSUS/ACCEPTED) and inside the Chelsea viewport; all 5 acceptance queries find it; pinned total 18,714; DEVICE coords + FL witness + favorite preserved; second load idempotent; deleted FTS row self-heals |
| `SearchCanaryTest` | **OK (2)** — all 13 real-user queries surface the record on a fresh FIX5 catalog (5 failed pre-fix); fresh Chelsea box = 41 places incl. the pin |
| `QaFix5PreserveTest` (mine) | **OK (2)** — §1 |
| `QaFix5RobustTest` (mine) | **OK (3)** — §2 |
| `GaLiveTest` | **OK (1) — against the production FIX5 classes** (no scratch tree): GA pack installs through PackManager, co-residence 23,527 + 70,033 + 33,514 = **127,074**, Atlanta viewport 4,108 GA pins, clean removal |
| `FlLiveTest` | **OK (1)** — Orlando viewport 5,000 pinned (limit); 59,288/70,033 FL Census pins |
| `Lf4Test` | **OK (9)** — incl. full-FL-pack proof, pack validation, user-store isolation |
| `DbTest` | **OK (3)** |
| `GeoTest` | **OK (1)** |

§1's preserve test *is* the FIX4-lineage acceptance variant (catalog built by FIX4-vintage import from FIX4 seed bytes → FIX5 load → pin + corrections + all query forms land).

## 4. The two red tests — ADJUDICATED (P2, process)

Both flips reproduce on my runs at the exact disclosed lines:

- `UpgradeChainTest` — **1 failure at line 129** (`assertFalse`: "McDonalds must NOT find it") on the healed catalog.
- `FtsDesyncTest` — **2 run, 1 failure at line 88** ("nothing heals it"); the `importSeedIsAtomic` half **passes**.

**Ruling: a shippable tree may not carry knowingly-red tests in its runnable suite.** The flips are honest — each assertion encodes the *defect* the fix removes, and the builder disclosed both prominently and edited neither test's behavior assertions (verified: the rig's `UpgradeChainTest.kt` is **byte-identical** to WS-D's staged original; the other staged files' diffs are exactly the disclosed count literals/comments — §6). But a permanently-red suite is indistinguishable from a regressed one to any future runner, trains alert fatigue, and invites a future "fix" that reintroduces the defect to turn the suite green.

**Required disposition (before this tree becomes the repo baseline):** invert the two flipped assertions to assert the *fixed* behavior — `UpgradeChainTest.kt:129` → the record **is** found; `FtsDesyncTest.kt:88` → the desync **is** healed at load — keeping both tests' setups (they are excellent lineage/desync fixtures), **or** move both classes out of the runnable suite into a defect-records directory alongside their logs. Either is acceptable; leaving them red in `test/src` is not. This conditions the *tree*, not the APK: it does not block CSDM review or Mark's device gate.

## 5. Recount from the APK — exact (my own extraction)

From the seed extracted out of the FIX5 APK itself (not the tree asset):

- **23,527 places; 18,712 with coordinates (79.5%)**; provenance census of all 18,712 pins: CENSUS 17,610 + CENSUS-RETRY 1,099 + HARVEST 3 — **every pin ACCEPTED / ADDRESS_RANGE**, zero centroid-class provenance anywhere; 0 pins outside the Alabama envelope.
- vs the FIX4 APK's seed: adds = **exactly the 3** WS-D establishments (`jcdh_21625` Panda Express #2631, `jcdh_22231` Crestwood Pharmacy, `jcdh_22419` Los Diaz — all list-only, no coordinates invented); removals = **0**; changed = **exactly 13**, id-set identical to `remediation_delta.jsonl`'s `update-score-date` entries, and **every one of the 13 moves the inspection date strictly forward** (latest-score corrections, e.g. Beebe's Catering 8/6/2025 → 5/11/2026) — no silent edits.
- Gates run by me against the extracted seed: `validate_seed.py` → **PASS** (G1–G6 all 0); `canary_gate.py` → **PASS** (134 canaries + 6 search canaries over 23,527).
- McDonald's record in the extracted seed: pinned, CENSUS/ACCEPTED, 98 on 9/14/2026 — the acceptance record ships in the artifact.

## 6. Standard audits

- **Dex delta (my own parser, index-independent):** classes.dex byte-identical to FIX4. classes2.dex — added = **exactly the 2 claimed** (`PlaceRepository$Companion`, `PlaceRepository$$ExternalSyntheticLambda0`); removed = **0**; code-touched (field/method-set or instruction-count change) = **7 classes**, all in the patched files' families (PlaceRepository + `load$2` + `searchPlaces$2`, CatalogDb + Companion, Regions, MapFragment); PackManager's change is string-pool-only (the new FTS-rebuild SQL), visible in the pool diff. The builder's "21 changed" is the superset produced by their SMAP/debug-info comparison (recompiling the 5 files churns line tables for every co-defined class, incl. PackManifest/RegionManager, whose code is untouched) — **methodological difference, substance identical: 0 library classes, nothing outside the 5 patched files.** New-string census (86) is entirely patch-plausible (fingerprint key, GA registration, apostrophe-SQL fragments) — nothing unexpected. `audit_apk.py`: defined 7,845 → 7,847, undefined-reference list identical to FIX4's known-benign set, 595 R classes, coroutines services present.
- **Test-source diffs:** the 5 WS-D-staged files diff against their staged originals **exactly** as the changelog discloses (AgedDbAcceptanceTest: 1 comment + 2 count assertions 23,525→23,528; FtsDesyncTest: 3 count literals; SearchCanaryTest: docstring only; UpgradeChainTest: **zero diff**). No assertion was weakened, deleted, or softened in any staged file.
- **Policy sweep (my own, on the full APK):** 0 hits for `kyronfoodsafety`, `geocodio`, `AIza`, private-key material. **Guest-first:** the patch contains no auth/sign-in surface; the manifest is identical modulo versionCode (no new permissions, no new activities); the new dex strings contain no auth surface.
- **LaunchTest:** fails in the rig with `Resources$NotFoundException` on resource `0x7f07004e` — the **identical failure signature** (same resource id) appears in the Oct 13 log from the original 2.0 build, and `resources.arsc` is byte-identical FIX4→FIX5. Pre-existing rig artifact confirmed; not a FIX5 regression. The operative Activity-create gate (`StartupUpgradeTest`, builder-run OK) covers cold start.

## Findings register

| # | Grade | Finding | Disposition |
|---|---|---|---|
| F-1 | **P2** (process) | Two knowingly-red defect-record tests in the runnable suite (`UpgradeChainTest:129`, `FtsDesyncTest:88`) | **Required before repo merge:** invert the two assertions to assert fixed behavior, or retire both classes to a defect-records directory (§4). Does not block the APK/device gate |
| F-2 | P3 | `reconcileFts` heals on **count** mismatch only; a same-count content divergence would survive. No current writer can produce one (swap / pack install / upsert / deletePlace all maintain FTS transactionally — source-verified) | Latent limitation; note for future work |
| F-3 | P3 | `ftsRowCount`/`reconcileFts` gate on the instance's `ftsAvailable` flag (probed at `onOpen`): a cold `CatalogDb` instance that hasn't opened its DB reports 0 / no-ops. Production is safe (single opened instance in `PlaceRepository`); the API is a footgun for future callers (this QA tripped it once in test code) | Document; consider probing in the helpers |
| F-4 | P3 | A corrupt seed makes `load()` throw to its caller instead of degrading to the stale catalog. State stays consistent and the next good load heals (§2a). On-device this needs a corrupt staged sideload file — production never writes one; the bundled asset is gate-validated | Fail-loud + self-healing; acceptable, recorded |
| F-5 | P3 (process) | `fix5-backup/` snapshots production sources + the FIX4 seed but **not** the pre-FIX5 rig tests, so a literal FIX4→FIX5 diff of `DbTest/GeoTest/Lf4Test/FlLiveTest/GaLiveTest/PerfTest` isn't possible from disk. Mitigations applied (§6): staged-file diffs exact; those tests' count assertions are strict `assertEquals` literals matching this pass's independent APK recount; test counts on my reruns match the reported OK (N); the one historical baseline available (github-export GeoTest) shows the only assertion-form change in the lineage was a data-wave *strengthening* (bound → exact equality), predating FIX5 | Recommend future waves snapshot `test/src` into the wave backup |

**Positive findings worth recording:** DEVICE-provided coordinates beat bundled seed coordinates in a collision, with the label preserved (the device is authoritative for its own data); the FTS alias living in the *data* means even a downgrade to FIX4 keeps both search forms working (§2c); the refresh preserves sync-merged freshness semantics honestly (documented in the patch: AL sync freshness re-merges at next scheduled sync, same as after a pack full-install).

## What was NOT verified (residuals)

- On-device behavior (no AVD in this sandbox; native PathParser class of issues remains device-gate territory — the pathData gate passed in the build and FIX5 touches no resources).
- PerfTest was not rerun by this pass (builder reports OK (1); first-load import 27.5 s one-time is a PerfTest-internal measure, unchanged in kind from prior waves).
- The optional query-hygiene patch was **not** applied to this build (outside confirmed scope) and is not audited here.

## Tree hygiene (post-QA disposition of finding F-1, executed Oct 15, 2026)

The §4 ruling's inversion path was executed: both defect-record tests stay in the runnable suite with their setups (lineage/desync fixtures) intact, and every assertion that encoded the pre-FIX5 defect now asserts the fixed behavior. The hygiene pass first reproduced both flips in its own runs at the exact cited lines (`UpgradeChainTest.kt:129`; `FtsDesyncTest` 2 run / 1 failure), then inverted, then re-ran.

**One correction to §4's line attribution, established empirically:** `FtsDesyncTest`'s first flip is NOT the relaunch assertion. In every FIX5 run (builder's, QA's, and this pass's baseline) the run stops at the original line 88, which is the **house-number assertion** — the "desync after relaunch" print never appears in any log, because execution never reaches the relaunch block. Line 88 is:

- Before: `assertFalse(viaAddr.any { it.id == mcdId })` — searching the unique house number "16758" must miss, because "address lives only in FTS".
- After: `assertTrue(viaAddr.any { it.id == mcdId })`

Mechanism (production source, `PlaceRepository.searchPlaces`): with the record's FTS row deleted, "16758" returns **zero** FTS hits, and FIX5's search-defect-(a) fix turns a zero-hit FTS result into the LIKE scan over the places table, which finds the record by its address. The desync's search-invisibility survives exactly where the test's design intends: the "McDonald's" name query returns 222 non-empty FTS hits, so no fallback fires and the record is still missed until relaunch (that assertion is unchanged and still passes).

The relaunch assertion — masked behind line 88 in every run to date — was also inverted, as it encodes the same defect and independently flips (the heal is proven by `AgedDbAcceptanceTest`'s FTS self-heal section on the same code):

- Before: `assertFalse("no FTS reconciliation exists in load()", after.any { it.id == mcdId })`
- After: `assertTrue("FTS reconciliation in load() heals the desync", after.any { it.id == mcdId })`

`UpgradeChainTest.kt:129` inverted as ruled:

- Before: `assertFalse(byBareName.any { it.id == mcdId })`
- After: `assertTrue(byBareName.any { it.id == mcdId })`

Comments/docstrings that described the defect as the expected outcome were updated alongside (the chain test's apostrophe-less-search note; the desync test's class docstring and relaunch comment/final print), and the desync test method was renamed `ftsRowLossHidesPlaceFromSearchOnly_andNothingHealsIt` → `ftsRowLossHidesPlaceFromSearchOnly_untilLoadHealsIt` so the identifier no longer asserts the defect. No other assertions, setups, or files were changed; production sources were not touched, and the staged FIX5 APK is byte-identical before and after this pass (md5 `12637dd2a14152fe0a3a3fc1f1de597f`, re-verified).

**Post-hygiene suite run (all green):** UpgradeChainTest OK (1) · FtsDesyncTest OK (2) · AgedDbAcceptanceTest OK (1) · SearchCanaryTest OK (2) · DbTest OK (3) · GeoTest OK (1) · Lf4Test OK (9). Logs: `~/kyron-build/test/hygiene_*.log`.

**Baseline snapshot (per finding F-5's recommendation):** the full post-hygiene test tree is snapshotted at `~/kyron-build/fix5-backup/test-src-postfix5/` (24 files) as the baseline record for future waves.

**Environment note:** during this pass the shared 512 MB `/tmp` tmpfs reached 100% (a sibling wave's pack-rebuild staging plus completed FIX5-wave scratch), killing two baseline runs with SIGBUS before diagnosis. Completed-wave scratch in `/tmp` (the FIX5 QA's pack-DB dumps, dex scratch, and sweep trees — disposable by `/tmp` policy, all conclusions already recorded in this report) was cleared, restoring ~411 MB; all hygiene runs used a disk-backed `java.io.tmpdir`/`TMPDIR` under `~/kyron-build/test/tmpdisk`, the same workaround earlier waves used. The sibling wave's staging directories were not touched.
