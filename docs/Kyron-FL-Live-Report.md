# Kyron Workstream C1 — Florida Goes Live: Report

**Date:** October 15, 2026 · **Workstream:** C1 (P1) — Florida pack: remediate, geocode, rebuild, publish, verify
**Status:** Steps 1–3 and 5 complete and verified. Step 4 (publish) is **staged, not live** — one infrastructure blocker, documented in §5. Nothing was improvised around it.

## Headline numbers

| | Before C1 | After C1 |
|---|---|---|
| FL places shipping | 70,051 (proof pack, unpublished) | **70,033** (18 nameless records excluded by the gate) |
| FL inspections | 44,664 | **44,660** (4 dropped with their nameless places) |
| Verified map pins | **0** | **59,288 of 70,033 places (84.66%)** — every one an adjudicated US Census address-level match |
| Pack | `us-fl-2026-10-13.1` (proof, 0 coords) | `us-fl-2026-10-15.1` — 7,900,234 bytes, sha256 below |
| Invented scores | 0 | **0** (native DBPR dispositions verbatim, NO_SCORE sentinel everywhere) |

## 1. Remediation + gate (Workstream B's validator is law)

Gate: `~/kyron-build/manual/tools/validate_seed.py` against `~/kyron-build/harvest/fl_dbpr/OUTPUT/places_fl.json`.

**Baseline (prototype dataset, 70,051 places):** G1 = 2, G4 = 18, G5 = 488, G2/G3/G6 = 0.

**Fix, at the normalizer level** (`harvest/fl_dbpr/fl_dbpr_build.py`): a new Pass 2.5 name-completeness reject that mirrors the gate's G4 predicate exactly (same placeholder set + names ending in a bare "#"). Records without a real establishment name never become places; every rejection is logged to `OUTPUT/fl_name_rejects.json` and printed loudly during the build. Legal-entity `licensee_name` values were deliberately **not** promoted to storefront names — no names were invented.

**Exactly 18 records excluded** — 14 blank names + 4 placeholder names:

| ID | Name in source | City | Result-bearing | Inspections dropped |
|---|---|---|---|---|
| fldbpr_NOS5815165 | *(blank)* | Orlando | **yes** | 1 |
| fldbpr_SEA2326635 | *(blank)* | Miami Beach | **yes** | 1 |
| fldbpr_VEN3900319 | "N/A" | Tampa | **yes** | 1 |
| fldbpr_SEA6000500 | "RESTAURANT" | Palm Beach | **yes** | 1 |
| fldbpr_SEA2320336 | *(blank)* | Miami | no | 0 |
| fldbpr_MFD2357374 | *(blank)* | Miami | no | 0 |
| fldbpr_SEA2327585 | *(blank)* | Miami Beach | no | 0 |
| fldbpr_VEN2324190 | *(blank)* | Miami | no | 0 |
| fldbpr_MFD1653468 | *(blank)* | Lauderhill | no | 0 |
| fldbpr_CAT1621398 | *(blank)* | Pompano Beach | no | 0 |
| fldbpr_MFD3952796 | *(blank)* | Tampa | no | 0 |
| fldbpr_SEA6218814 | *(blank)* | Largo | no | 0 |
| fldbpr_MFD3954552 | *(blank)* | Tampa | no | 0 |
| fldbpr_CAT6307452 | "N/A" | Winter Haven | no | 0 |
| fldbpr_SEA5810719 | *(blank)* | Orlando | no | 0 |
| fldbpr_MFD4150064 | *(blank)* | Sebastian | no | 0 |
| fldbpr_MFD5856406 | *(blank)* | Orlando | no | 0 |
| fldbpr_SEA2706562 | "ESTABLISHMENT" | Pensacola | no | 0 |

The 4 dropped inspections all carried the disposition "Inspection Completed - No Further Action". These are exactly the 4 result-bearing nameless records Workstream B's census flagged. A surgical diff against the pre-remediation backup (`harvest/fl_dbpr/work/backup_pre_live/`) proved: removed = exactly these 18 IDs, added = 0, changed-kept = 0.

**Post-remediation dataset:** 70,033 places (69,891 licensee + 160 inspection-only − 18), 44,660 inspections, 36,031 places with inspections, name completeness 100.0%.

**Gate re-run (also re-run after geocoding — identical):** G1 = 0, G2 = 0, G3 = 0, G4 = 0, G6 = 0. G5 = 488 flags remain, and they are **proven false positives for this source**: a dedicated provenance check (`harvest/fl_dbpr/work/g5_provenance.py`) reconstructed name and address for all 488 from the raw DBPR columns exactly as the builder built them — 488/488 source-verbatim, 0 mismatches. The G5 fused-split detector is calibrated for fused-string sources (AL JCDH); FL name and address are separate source columns, so fusion is impossible by construction — the same verdict Workstream B reached. **Substantive gate verdict: PASS.**

## 2. Census geocoding (0 → 59,288 verified pins)

Pipeline: `harvest/fl_dbpr/work/geocode_fl.py`, reusing the LF-1 methodology (`geocode_common` normalization, Census batch geocoder, benchmark `Public_AR_Current`, free, no key). Dedupe by normalized address (street|city|FL|zip5), never by name: 70,033 places → **54,871 unique addresses**, 54,850 submittable in 11 batches of ≤5,000. One batch (flprod10) hit a Census HTTP 502 and recovered on retry; all batches checkpointed, none resubmitted. Two repair rounds (expanded suffixes; suffix dropped) resubmitted only NO_MATCH / NEEDS_REVIEW addresses; ties were never resubmitted.

Adjudication mirrors LF-1 exactly: Exact requires house-number + (ZIP or city) agreement; Non_Exact requires number + ZIP + city all to agree; Tie is never auto-resolved; coordinates outside the Florida envelope are rejected. A dedupe-suffix guard collapses doubled trailing suffixes (the AL `canon_street` lesson — 2,759 FL addresses needed it). Only adjudicated matches set coordinates, with per-place provenance (`gs/ga/gp/gm` = ACCEPTED / ADDRESS_RANGE / CENSUS / EXACT|NON_EXACT). **No centroids, no jitter, ever.**

**Address-level result (54,871):** ACCEPTED 46,053 (83.94%) · NO_MATCH 5,622 · NEEDS_REVIEW 2,028 · TIE 1,141 · REJECTED 6 · PO_BOX 15 · INTERSECTION 6.

**Place-level result (70,033) — the numbers that ship:**

| Outcome | Places |
|---|---|
| **ACCEPTED (pinned, Census provenance)** | **59,288 (84.66%)** |
| NO_MATCH | 7,119 |
| NEEDS_REVIEW (evidence disagreed) | 2,256 |
| TIE (never auto-resolved) | 1,324 |
| PO_BOX (unpinned by rule) | 32 |
| REJECTED (outside FL envelope / unparseable) | 8 |
| INTERSECTION (no single address) | 6 |

Quality spot checks: Orlando — 4,397 of 4,401 pinned places fall inside the Orlando bounding box; Miami Beach — 698 of 699. Random accepted samples land on their named cities (Coral Springs, Naples, Miami, Brandon, …). The residual is a future Geocodio/Census-retry candidate set; it ships honestly unpinned (list-only), exactly like Alabama's residual.

## 3. Pack rebuild

Builder fix first: `tools/packs/build_pack.py`'s FL converter previously hardcoded `geo_status="UNRESOLVED"` — it now carries each record's real `gs/ga/gp/gm`, and a new build-time assert refuses any place whose coordinates lack ACCEPTED + CENSUS + ADDRESS_RANGE provenance. Gate result for the pack input is §1 (PASS). Native DBPR dispositions verbatim; every place and inspection score is the NO_SCORE sentinel (−1).

**New pack** (in `tools/packs/out/us-fl/` and staged, §5):

- File: `us-fl-2026-10-15.1.db.gz`
- datasetVersion: **2026-10-15.1** · schemaVersion 2 · placeCount **70,033**
- Bytes: **7,900,234** · SHA-256: `2c47c3d53f0446e9330c9bb3af457fe1a8d9c8d4cee2f527d6ebe6c264523b8d`
- Manifest's own sha256 (of the staged manifest file): `11f7b1567faf3e8de5aa433225b8bfad19dd5bdbfb574d13371434bf13484d92`

Independent pack-DB audit (decompressed and queried directly): 70,033 places; 59,288 with ACCEPTED/CENSUS/ADDRESS_RANGE pins; **0 coordinates without provenance**; 0 non-sentinel scores among 70,033 places and 44,660 inspections; `pack_meta` agrees with the manifest on region, version, count, and DISPOSITION score model.

## 4. Verification — end-to-end on the rig (test-twice honored)

New test: `~/kyron-build/test/src/FlLiveTest.kt` (Lf4Test-style Robolectric harness; pack dir via `FL_PACK_DIR`, run against the **staged publish bytes** in `~/kyron-build/fl-publish/`). It walks the real user path:

1. **Coverage precondition** — `Regions.FLORIDA`: regionId `us-fl`, not bundled, score model DISPOSITION, manifestUrl exactly `https://markbentzjr.github.io/kyron/data/us-fl.manifest.json` — the state CoverageActivity renders as "Available — free region-pack download".
2. **Install** — the staged pack installs through PackManager (which verifies SHA-256, size, pack_meta, and place count before swapping a row): `KYRONTEST FL live pack install ms=5070`; region count = 70,033; catalog total = 23,524 AL + 70,033 FL.
3. **Browse** — text search returns FL places with native dispositions (HILLS BAR B QUE & CATERING → "Inspection Completed - No Further Action"), `score == NO_SCORE` on a 1,000-place sample, and both score-band searches ("Below 85", "95+") return empty — no phantom scores.
4. **Map** — Orlando viewport query returns pinned places only, all `hasRealLocation`: `KYRONTEST Orlando viewport pinned places=5000` (the 5,000 limit — the viewport is fully pinned); catalog verified-pin count equals the pack DB's own count exactly: `KYRONTEST FL verified Census pins=59288 of 70033`; 0 FL places carry coordinates without accepted Census provenance.
5. **Switching + removal** — AL Jefferson County search returns only scored AL places; county lists stay state-clean; removing the FL pack leaves Alabama untouched at 23,524 and FL search empty. `KYRONTEST FL live end-to-end OK` — **OK (1 test), run twice, both passes green.**

**Regression:** Lf4Test re-run against the rebuilt pack — **OK (9 tests)**, including the full-Florida-pack proof and F-1 pack-validation refusals.

**Disclosed test maintenance:** `Lf4Test.kt` hardcodes the FL place count; its five expectations were updated 70,051 → **70,033** (and the doc comment) to match the remediated dataset. No other test logic changed. (Its AL expectations already reflect the data wave's 23,524.)

## 5. Publish — STAGED, one blocker

The app fetches, hardcoded in `Regions.kt`:
- Manifest: `https://markbentzjr.github.io/kyron/data/us-fl.manifest.json`
- Pack (resolved relative to the manifest): `https://markbentzjr.github.io/kyron/data/us-fl-2026-10-15.1.db.gz`

**Live check (Oct 15, 2026): both URLs return HTTP 404 — nothing is published yet, and the manifest was deliberately NOT published alone** (the app would offer a download whose pack 404s).

**Blocker:** there is currently no working route to land a 7.9 MB binary at that host from this environment:
- The GitHub connector's write tools are file-content based with a ~90 KB per-call arguments cap and no release-asset upload — the pack cannot pass through it (the manifest alone could, but see above).
- Direct git egress is blocked: `git ls-remote https://github.com/markbentzjr/kyron.git` times out (proxy CONNECT aborted), re-verified this session.

**Staged, ready to publish** in `~/kyron-build/fl-publish/`:
- `us-fl.manifest.json` (511 bytes)
- `us-fl-2026-10-15.1.db.gz` (7,900,234 bytes, sha256 `2c47c3d5…523b8d`)

**To go live, either:** (a) someone with git access pushes both files to the repo path `data/` (pack first, manifest last) on the branch GitHub Pages serves for `markbentzjr.github.io/kyron`, or (b) a release-asset-capable route is provided and the app's manifest URL is repointed accordingly (an app change — CSDM call, not done here). No alternate host was improvised. The moment both files land, the already-shipped FIX3-line app offers Florida in Coverage with no app update — the rig test above ran against these exact bytes.

## 6. Production-policy audit

- Published/staged artifacts contain **public health records only** — no API keys, no account references, no credentials. The Census geocoder is a free public endpoint used offline in the pipeline; nothing is called at runtime.
- Guest-first untouched: Florida installs and browses with no sign-up, same as Alabama.
- Spend: **$0** (Census batch geocoder is free; GitHub Pages is the repo's free hosting).

## Artifacts

- Staged publish pair: `~/kyron-build/fl-publish/` (manifest + pack)
- Geocoding pipeline + checkpoints: `~/kyron-build/harvest/fl_dbpr/work/geocode_fl.py`, `work/geo/` (batches, results, `adjudicated_fl.json`, `adjudicate_fl_report.json`)
- Rejection log: `~/kyron-build/harvest/fl_dbpr/OUTPUT/fl_name_rejects.json`
- Pre-change backups: `~/kyron-build/harvest/fl_dbpr/work/backup_pre_live/`
- Test: `~/kyron-build/test/src/FlLiveTest.kt`; updated expectations in `Lf4Test.kt`
