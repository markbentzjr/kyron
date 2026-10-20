# Kyron — South Carolina Pack Wave (Workstream C7)

**Date:** October 15–16, 2026 · **Status:** ✅ **COMPLETE** — SC is pack-ready: gate-confirmed,
geocoded, packed, independently audited, staged, and live-verified twice in the rig.
Nothing published; production tree untouched.

South Carolina is the mirror image of Tennessee: SCDA publishes a **posted letter grade**
(A/B/C/N/A/S) statewide, and the numeric 100-point score exists **only inside the
per-inspection PDF reports** — the AGOL `SCORE` column is null on all 137,087 spine rows and
the search portal shows the grade only. So the pack ships the grade verbatim and **no score
anywhere**: every place and inspection carries the `NO_SCORE` sentinel (−1). A score was never
derived from a grade, even though the program publishes the band edges — a band is not a score.

## Headline numbers

| | |
|---|---|
| Places / inspections | **35,862 / 213,358** (46/46 counties) |
| Pinned (verified Census address-level) | **29,479 — 82.20%** (EXACT 25,949 · NON_EXACT 3,530) |
| Places carrying a numeric score | **0** (sentinel −1 on all 35,862 places + 213,358 inspections) |
| Place grades (verbatim) | A 35,312 · B 285 · C 130 · N/A 133 · S 2 |
| Pack | `us-sc-2026-10-16.1.db.gz` — **8,419,300 bytes**, sha256 `0166b6ea7064023fa27b3f087f10016e58138532e0c32ed23d6a524948301347` |
| datasetVersion | `2026-10-16.1` (derived from the source manifest `generated_at` 2026-10-16T03:54:38Z, the builder's standing derivation) |
| Independent audit | **ALL CHECKS PASS** (full-table equality vs source) |
| ScLiveTest | **OK ×2** (install, native grades, band sanity, honest why, map, isolation, removal) |
| Non-regression | FL/GA/TN packs rebuild **byte-identical** under the edited builder |
| Staged at | `~/kyron-build/fl-publish/` (`us-sc.manifest.json` + pack) |

## Design point 1 — score model: SC fits MODEL_DISPOSITION exactly (Florida's shape)

**Decision: pack `us-sc` as `DISPOSITION` — grade verbatim in `result_text` at place and
inspection level, `score = −1` (NO_SCORE sentinel) everywhere.** Evidence from the app code:

- `data/Models.kt`: `hasNumericScore = score >= 0`. For a no-score place, `bandLabel` returns
  `nativeResult` (the grade) verbatim and `badgeText` returns `shortResultLabel(nativeResult)`,
  which passes "A"/"B"/"C"/"N/A"/"S" through unchanged — **the grade letter itself is the
  badge**. This is exactly how Florida's dispositions already render (FlLiveTest asserts
  badgeText == the native result verbatim).
- FL precedent (C1): `scoreModel = MODEL_DISPOSITION` for FL in both `Regions.kt` and the
  pack's `pack_meta`; GA's letter band rides the same `result_text` field (C3), so grades in
  `result_text` are an established, twice-proven pattern — the app does not distinguish
  models anywhere in a way that would mislabel a grade as a score.
- `data/Regions.kt`: `RegionInfo.scoreModel` distinguishes `MODEL_SCORE` vs
  `MODEL_DISPOSITION`; the SC registration uses `MODEL_DISPOSITION`, same as FLORIDA.
- The *only* seam found is cosmetic, same class as C3's GA band-display note:
  `resultToneOf()` (`Models.kt`) has no grade vocabulary, so every SC grade gets tone **2
  (warn/amber)** — used for pin color (`MapFragment.kt`), badge background
  (`PlaceAdapter.kt`) and detail tone (`DetailActivity.kt`). Nothing is mislabeled — the
  letter is correct everywhere — but an A and a C pin share the amber tone until a future
  wave teaches `resultToneOf` the grade letters (A → good, B → ok, C → bad). Not this wave's
  change to make; flagged for the CSDM.

## Design point 2 — detailUrl: KEPT (the official PDF links are safe)

**Decision: ship `detail_url` = the source's `du` (the newest inspection's official SCDA PDF).**
The brief's worry was the AL path parsing a PDF as HTML. The code says that path is
unreachable for SC:

- **Detail screen** (`ui/DetailActivity.kt`): for a place with `!hasNumericScore` (the only
  branch an SC place can ever reach — score is the sentinel) the screen shows a **"View
  official record"** button that fires `Intent.ACTION_VIEW` on `place.detailUrl` — the PDF
  opens in the system browser/viewer. **Nothing in-app fetches or parses it.** Florida's pack
  ships `detail_url` and uses this identical path.
- **The HTML fetch** (`SourceRegistry.jcdh.fetchDetail`, `source/Sources.kt` — Jsoup over a
  JCDH page) has exactly two callers, both gated away from SC:
  - `DetailActivity.kt` (~line 288): inside the branch that requires
    `place.hasNumericScore && cur == null` — SC places are never numeric-scored;
  - `SyncEngine.kt` (~line 119) favorites enrichment: gated on
    `p.detailUrl != null && p.inspections.isEmpty()` for places loaded via `repo.byId`, and
    `CatalogDb.placeById` always loads inspections (`inspectionsFor`) — **every SC place has
    ≥1 inspection**, so the gate can never fire for SC either.
- The sync-time fetch (`PlaceRepository.fetchAlDetail`) is AL-source-only.
- Keeping the PDF links also preserves the C5 GUID spine: if a sandbox-reachable PDF route
  ever opens, scores + violations unlock per-inspection with **zero re-harvest**.

## 1. Gate confirm — PASS (with the prototype's adjudication)

`validate_seed.py` over `OUTPUT/places_sc.json`: **G1 = 0 · G2 = 0 · G3 = 0 · G4 = 0 · G6 = 0 ·
G5 = 13**. The 13 G5 flags were set-compared against `OUTPUT/gate_adjudication.json`:
**identical set**, all 13 already proven source-verbatim FALSE POSITIVEs by the C5 prototype
(extraordinary-value name/grade pairs shipped identically by three independent source
systems — permit JOIN, rate feed, Steton pull). No new violation class appeared. Prototype
file unmodified.

## 2. Geocoding — 29,479 / 35,862 pinned (82.20%)

Same discipline as C1/C3/C6 (`harvest/sc/work/geocode_sc.py`, cloned from the TN pipeline):
25,723 unique addresses (dedupe by normalized address, never by name), Census batch
≤10,000/file, benchmark `Public_AR_Current`, the Workstream-A normalization ladder incl.
zip_drop + recanon acceptance rules, provenance (`ACCEPTED / ADDRESS_RANGE / CENSUS /
EXACT|NON_EXACT`) per place, PO Boxes/intersections never submitted, ties never auto-resolved.

Address-level adjudication ladder:

| Stage | Accepted | Δ |
|---|---|---|
| Production batches | 19,768 | — |
| + Repair 1 (full-word suffixes) | 19,774 | +6 |
| + Repair 2 (suffix dropped) | 19,848 | +74 |
| + Repair 3 (zip_drop) | 20,657 | +809 |
| + Repair 4 (recanon) | **20,675 / 25,723 (80.4%)** | +18 |

**Below TN's 87.74% — investigated, and the gap is source structure, not pipeline:**
places **with** a ZIP pin at **84.4%** (25,271/29,940 — the permit/GIS cohort, right in the
FL 84.66% / GA 83.86% band), while the 5,922 **ZIP-less rate-only places** pin at **71.1%**
(4,208/5,922): with no ZIP submitted, adjudication can only accept on Exact + house-number +
city (Non_Exact acceptance requires ZIP agreement by design), so the cohort's evidence is
structurally weaker. The blend of the two cohorts is the whole story. Secondary drag inside
the permit cohort: the 30-character truncated Steton street strings the prototype counted
(1,558 rows at cap).

Residual by reason (places, of 6,383 unpinned): NO_MATCH 3,090 · NEEDS_REVIEW 2,505 ·
TIE 761 · REJECTED 15 · PO_BOX 7 · INTERSECTION 5. Every unpinned place ships with an
explicit `gs` reason — browsable and searchable, just not on the map. No centroid, town-center
or jitter pin exists anywhere in the pack.

Outputs: `harvest/sc/OUTPUT/places_sc_geocoded.json` (new file; the prototype's
`places_sc.json` is untouched), `work/geo/` carries batches/results/adjudication artifacts.

## 3. Pack build

`convert_sc_place` added to `tools/packs/build_pack.py` (+ `us-sc` entries in `CONVERTERS`,
`SCORE_MODELS` = DISPOSITION, `JURISDICTIONS`, `SOURCE_DEFAULTS`), FL/GA/TN conversion paths
untouched. Format-only conversion rules: grade → `result_text` verbatim (place + inspection);
score → −1 everywhere; violations → `[]` everywhere (PDF-only at source); dates ISO →
M/d/yyyy (same normalization GA/TN ship); ZIP normalized to its 5-digit form — the same value
the Census pipeline submits (the prototype output carries 2,043 records in a 9-character
zero-suffixed/concatenated form and a handful zero-padded; every other region ships 5-digit
ZIPs; no other address field changes). Builder honesty asserts for `us-sc` (all scores
sentinel; all result_text ∈ {A, B, C, N/A, S}; zero violations) **passed**, alongside the
standing provenance assert.

**Pack:** `us-sc-2026-10-16.1.db.gz` — 8,419,300 bytes —
sha256 `0166b6ea7064023fa27b3f087f10016e58138532e0c32ed23d6a524948301347` —
schema 2 · 35,862 places · 213,358 inspections · `pack_meta.score_model = DISPOSITION`.

**Non-regression (required proof):** with the edited builder, FL rebuilds to
`2c47c3d53f0446e9330c9bb3af457fe1a8d9c8d4cee2f527d6ebe6c264523b8d` — **byte-for-byte the
staged artifact**. GA (`47810503…`) and TN (`40ef34ce…`) rebuild byte-identical too.

## 4. Independent audit — ALL CHECKS PASS

`harvest/sc/work/audit_sc_pack.py` — direct SQLite queries against the pack, expectation
re-implemented from the C7 spec (no builder code):

- pack_meta ↔ manifest ↔ source manifest agree (region, version, 35,862, schema 2, DISPOSITION);
- **full-table** place comparison vs source (id/name/street/city/ZIP5/county/date/source/
  coords/geo fields/detail_url/result_text): **0 mismatches**; place ID sets identical;
- **score == −1 on every one of the 35,862 places and 213,358 inspections** — 0 numeric
  scores, 0 derivations;
- grade censuses equal the source exactly at both levels (places A 35,312 · B 285 · C 130 ·
  N/A 133 · S 2; inspections A 194,603 · B 12,579 · C 4,527 · N/A 1,632 · S 17);
- per-place inspection counts equal everywhere; 0 orphan inspections;
  per-inspection date/type/grade equality: 0 mismatches; `violations_json == "[]"` on all;
- pinned 29,479 == source; match census EXACT 25,949 / NON_EXACT 3,530 == source;
  **0 coords without complete provenance · 0 half-null coords**;
- 20-place stride sample: **20/20 full-row equal**.

## 5. Scratch-tree verification — ScLiveTest OK ×2

Scratch tree: `~/kyron-build/scratch-sc/` = byte copy of production + **only** the SC
registration (§6) in `Regions.kt`; `diff -rq` over `src/` shows that one file differing, and
within it only the registration block + the one-line cosmetic `sourceDisplayName` entry.
Production `Regions.kt` md5 `943f704da72124018bd14a0786cbb4fe` **before and after the wave**
(unchanged since C6). Scratch build OK (all build gates green; signed with the standing
debug cert `cb932a51…`).

`~/kyron-build/test/src/ScLiveTest.kt` (new; runner `run_one_sc.sh`, staged bytes via
`SC_PACK_DIR`), run **twice, OK both times** (~2.7s/3.4s install):

- Staged manifest asserted in-test: 35,862 places · 8,419,300 bytes · sha256 `0166b6ea…`;
  install through `PackManager` (SHA-256 + pack_meta checked inside); version `2026-10-16.1`.
- **Browse shows grades natively, no numeric score anywhere**: KIM'S SOUL FOOD
  (scda_32-204-06634, Columbia) — `score=-1, nativeResult='A', badge='A'`, county Lexington;
  RUBY TUESDAY #4396 renders "C"; a DOMINO'S renders "N/A"; a 1,000-place sample is
  uniformly `score == NO_SCORE && !hasNumericScore && nativeResult ∈ {A,B,C,N/A,S}`;
  the fixture's `detailUrl` ends in `.pdf` (the official-record action).
- **Band filters behave sanely** (expected behavior derived from `CatalogDb.search`: the
  `score>=0` guard means a sentinel can never enter a band — the same guard FlLiveTest
  proved): "Below 85", "85–94" and "95+" each return **empty** for us-sc, with and without a
  text filter, while the same places are reachable under "All scores". (In the UI,
  `BrowseFragment` hides the band chip row entirely for DISPOSITION regions and restricts
  sorts to Most recent / Name A–Z.)
- **Why-summary honesty** — for RUBY TUESDAY #4396 (newest inspection 9/28/2026, grade C,
  violations empty), `WhySummary.dispositionExplainer` renders **verbatim**:
  > "This jurisdiction publishes inspection outcomes, not numeric scores. The inspection of 9/28/2026 ended with: “C”."
  Nothing is appended (violations empty → no violation clause exists to add), and the string
  contains no "Scored". The other two why-surfaces are code-gated the same way: browse cards
  render "Latest result: C (9/28/2026)" and the map sheet "Latest result: C (9/28/2026) —
  this jurisdiction publishes outcomes, not scores."; `WhySummary.summarize` (the
  violation-narrative path) is reachable only behind `hasNumericScore` /
  non-empty-violations guards at every call site.
- **Map**: Columbia viewport (33.85–34.15, −81.25…−80.80) returns **3,482** pins — equal to
  the pack DB's own count for the same box and to an independent count from the geocoded
  source; catalog ACCEPTED/CENSUS coord count == pack count (29,479); 0 coords without
  provenance.
- **Co-residence**: AL 23,527 + SC 35,862 + FL 70,033 + GA 33,514 = **162,936**, region
  switching works, Richland County exists only under us-sc.
  ⚠️ **One deviation from the C7 brief, with cause**: the brief asked for 5-region
  co-residence including TN, but the scratch boundary ("only the SC registration added")
  forbids it — Tennessee's registration is *also* still a pending CSDM batch item, and this
  rig verified that production `PackManager` still refuses us-tn (`PackException: Unknown
  region us-tn`). TN's own wave (C6) proved TN co-resides with AL/FL/GA through the identical
  install path, and this wave proves SC co-resides with AL/FL/GA; when the CSDM batches both
  registrations into one build, the five-region total is 196,198 by the same code path.
- **Removal**: `removePack("us-sc")` leaves AL/FL/GA byte-exact; GA removal then leaves
  AL+FL exact.

## 6. Registration snippet for the CSDM's batch

Add to `Regions.kt` (alongside the pending TENNESSEE snippet from C6 — one build can carry
both; if both land, `KNOWN = listOf(ALABAMA, FLORIDA, GEORGIA, TENNESSEE, SOUTH_CAROLINA)`):

```kotlin
/** South Carolina (Workstream C7): grade-only state — SCDA publishes
 *  a posted letter grade (A/B/C/N/A/S); the numeric score exists only
 *  inside the per-inspection PDF reports and is never derived. The
 *  pack is DISPOSITION-shaped exactly like Florida's: grade verbatim
 *  in result_text, NO_SCORE sentinel everywhere else. */
val SOUTH_CAROLINA = RegionInfo(
    regionId = "us-sc", state = "SC", displayName = "South Carolina",
    scoreModel = MODEL_DISPOSITION, bundled = false,
    centerLat = 33.92, centerLng = -80.90,
    manifestUrl = "https://markbentzjr.github.io/kyron/data/us-sc.manifest.json"
)
// KNOWN = listOf(ALABAMA, FLORIDA, GEORGIA, SOUTH_CAROLINA)
// + cosmetic: sourceDisplayName "SCDA" -> "South Carolina Dept. of Agriculture"
```

## 7. Publish posture

Staged pair sits in `~/kyron-build/fl-publish/` beside FL/GA/TN. At 8.03 MiB the SC pack
**fits the 25 MB GitHub web-upload route** (like FL 7.9 MB and TN 18.4 MB; GA 33.7 MB still
does not). Nothing was published — the route decision remains the CSDM's, and it gates all
four packs. $0 spent; no Geocodio; no test-account dependency anywhere (packs are static
data; the app never sees a key).

## 8. File boundaries honored

Edited only: `tools/packs/build_pack.py` (SC converter + registries + asserts) and **added**
`~/kyron-build/test/src/ScLiveTest.kt`. Everything else is new files in the SC work area
(`geocode_sc.py`, `audit_sc_pack.py`, `geo/` artifacts, `places_sc_geocoded.json`,
`scratch-sc/`, `run_one_sc.sh`) or the staged publish pair. Production source, the FIX5 tree,
`Regions.kt`, and the C5 prototype outputs are untouched (md5/diff-verified above).

## 9. What's next (not this wave)

- CSDM: batch the TN + SC registrations into the next build; decide the publish route.
- Optional future wave: teach `resultToneOf` the grade letters so SC pins/badges tone by
  grade (cosmetic; §Design point 1).
- The 6,383 unpinned SC places (esp. 3,090 NO_MATCH) are Geocodio-mop-up candidates if the
  CSDM ever wants them — pipeline-only, per standing policy; not a gate.
- If a sandbox-reachable PDF route opens, the GUID spine unlocks SC scores + violations
  with zero re-harvest.
