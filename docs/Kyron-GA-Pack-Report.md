# Kyron — Workstream C3 Report: Georgia pack-ready

**Date:** October 15, 2026 · **Wave:** C3 (mirrors C1/Florida) · **Spend:** $0 · **GitHub pushes:** none · **Production app changes:** none

## Headline

Georgia is **pack-ready and rig-verified**: gate confirmed, Census-geocoded
(**28,104 of 33,514 places pinned, 83.86%**, verified address-level only),
packed (**33,514 places / 138,922 inspections / 238,110 violation narratives**),
independently audited (full-table, zero mismatches), staged beside Florida's
pair in `~/kyron-build/fl-publish/`, and verified end-to-end in the rig
**twice** (install → scores/bands → why-summary narrative → Atlanta map →
AL/FL/GA co-residence → clean removal).

**One blocker stands between this pack and users, and it is an app change —
reported, not made (per the C3 brief). See Finding 1.**

---

## Finding 1 (BLOCKER, for CSDM decision): the shipped app cannot install the GA pack — Georgia is not registered

`PackManager.installFullPack` refuses any region missing from
`Regions.KNOWN`, which in the shipped FIX-line tree registers only Alabama
(bundled) and Florida. Coverage, RegionManager, and install all resolve
through that one table.

**Evidence (unmodified production build, `GaProbeTest`, run Oct 15):**

```
KYRONTEST Regions.KNOWN = [us-al, us-fl]
KYRONTEST refusal = Unknown region us-ga        (PackException, thrown before any file check)
KYRONTEST PROBE OK — OK (1 test)
```

**The exact fix (one entry, same shape as FLORIDA's registration in LF-4):**

```kotlin
val GEORGIA = RegionInfo(
    regionId = "us-ga", state = "GA", displayName = "Georgia",
    scoreModel = MODEL_SCORE, bundled = false,
    centerLat = 32.96, centerLng = -83.11,
    manifestUrl = "https://markbentzjr.github.io/kyron/data/us-ga.manifest.json"
)
// KNOWN = listOf(ALABAMA, FLORIDA, GEORGIA)
// plus one cosmetic line: sourceDisplayName("GA-DPH") -> "Georgia Dept. of Public Health"
```

**How verification proceeded without touching production:** the pack was
verified in a scratch copy of the tree (`~/kyron-build/scratch-ga/`) carrying
**only** the registration above (diff vs production `Regions.kt` is exactly
those lines; production file md5 `54eff880461f0c520f91953d720778cc` before
and after this wave). Everything else in the verification path —
PackManager, CatalogDb, PlaceRepository, WhySummary — is unmodified
production code, and the installed bytes are the staged publish bytes.
Once the CSDM approves the registration into a future build, Georgia needs
**no further pack work**: publish the staged pair at `data/us-ga.manifest.json`
+ `data/us-ga-2026-10-15.1.db.gz` (same route decision pending for FL) and
the Coverage screen offers Georgia with no other change.

## Finding 2: the band model fits with NO app change (verified, not assumed)

The brief's stop-condition does not trigger. Georgia's native model maps
onto the existing schema exactly as directed:

- `places.score` / `inspections.score` = native 0–100, verbatim;
- `places.result_text` / `inspections.result_text` = the state grade band
  (A/B/C/U) verbatim; `pack_meta.score_model = "SCORE_100"`
  (`Regions.MODEL_SCORE`).

Because `result_text` surfaces in the model as `Place.nativeResult` — a
field whose doc convention is "empty for score jurisdictions" — every
consumer was audited for scored places: DetailActivity's tone badge,
MapFragment's pin/sheet badges, the share-text builder, and
`WhySummary.dispositionExplainer` all sit behind `hasNumericScore`
guards, so a band in `nativeResult` changes **no rendering** for GA
places today (badges stay score-colored; the band is carried in the data,
in `eventKey`, and available to any future UI). One honest caveat for a
future wave: the letter band is not yet *displayed* anywhere for scored
places (the detail meta line shows Kyron's own `bandLabel`); surfacing
"A/B/C/U" visually is a presentation decision for the CSDM, not a data gap.

**Violation shape (the C1 gap, closed):** FL's pack carried no narrative
text. GA ships all **238,110** violations in the app's `{p, c, r}` rows:
`p` = Georgia's own points deducted; `r` = `"<item> <title> — <rule
citation>"` + the source's corrected/repeat flags + `" // "` + the
inspector's narrative verbatim (the exact remarks shape
`Violation.ruleText`/`inspectorNote` and `WhySummary` already parse for
Alabama). `c` (critical) is read from the source's own FDA Food Code
designation printed in every citation's trailing marker — `(p)` Priority
→ critical, `(pf)`/`(c)` → not — the direct analog of JCDH's native
critical flag; **55,341** violations carry it. No values were inferred
from anything else. The 8 source inspections with a blank Score column
ship as the NO_SCORE sentinel (−1) for that visit only; every place has
a native latest score (range 46–100).

---

## 1. Gate confirm — PASS

`validate_seed.py` over the C2 output (`places_ga.json`, 33,514 places):

| Gate | Result |
|---|---|
| G1 result-bearing, blank name | 0 |
| G2 result-bearing, blank street | 0 |
| G3 inspection → nonexistent place | 0 |
| G4 placeholder/truncated name | 0 |
| G5 fused name/street split | **88 — ID set exactly equal to `gate_adjudication.json`'s adjudicated source-verbatim false positives** |
| G6 score with no inspection on file | 0 |

No new violation class. The same gate is now the pack's build-time
precondition discipline, mirroring AL/FL.

## 2. Census geocoding — 83.86% of places pinned

Pipeline: C1's `geocode_fl.py` discipline cloned as
`harvest/ga/work/geocode_ga.py` (dedupe by normalized address, never by
name; benchmark `Public_AR_Current`; ≤10,000 rows/file; adjudication
unchanged: Exact needs house-number + ZIP-or-city, Non_Exact needs all
three, ties never resolved, envelope enforced). 33,514 places →
**26,039 unique addresses**, 26,022 submittable (17 held back: 14 PO Box,
3 intersection).

Repair ladder (address-level ACCEPTED, of 26,039):

| Round | Variant | Accepted | Δ |
|---|---|---|---|
| prod | canonical | 21,084 | — |
| 1 | full-word suffixes | 21,096 | +12 |
| 2 | suffix dropped | 21,207 | +111 |
| 3 | **zip_drop** (A's class; acceptance tightened to Exact + number + city + street-core) | 21,850 | **+643** |
| 4 | recanon (A's class; restores the trailing directional LF-1's `canon_street` drops — "… ST NE" → "… ST") | 21,851 | +1 |

Place-level result: **28,104 / 33,514 pinned (83.86%)** — EXACT 20,854 ·
NON_EXACT 7,250, every pin with provenance
(`ACCEPTED / ADDRESS_RANGE / CENSUS / EXACT|NON_EXACT`).

**Residual 5,410 places (16.14%), by reason:** NO_MATCH 4,043 · TIE 839
(never auto-resolved) · NEEDS_REVIEW 510 · PO_BOX 15 · INTERSECTION 3.
Geography says reference-data limits, not pipeline error: lowest coverage
is rural/mountain counties (Colquitt 57.1%, Rabun 62.3%, Habersham 64.6%)
vs DeKalb 94.4% and metro-Atlanta counties 84.2%. This lands at FL's level
(84.66%) rather than above it despite 99.24% house-numbered addresses —
Census's Georgia address-range coverage is the binding constraint, the
same residual shape as FL. A future Geocodio residual pass (once the API
key exists) is the honest drain for these, exactly as queued for AL/FL.

Edge records, handled openly: the 3 source records whose state tail
disagrees with Georgia were submitted by ZIP coherence (GA ZIP → GA) —
Newnan ("TN" 30263) and Fayetteville ("CA" 30214) both pinned at correct
Georgia coordinates; the one genuine out-of-state address (Plainsboro,
NJ 08536, on a GA permit) was submitted as NJ, returned NO_MATCH, and
stays unpinned. Directional fidelity: 2,170 pinned places have
directional-ending streets; acceptance always required ZIP agreement
(Atlanta's quadrants are ZIP-separated; where Census itself found both
quadrants it returned Tie → unpinned).

Output: `harvest/ga/OUTPUT/places_ga_geocoded.json` (the C2 prototype
file is untouched), checkpoints in `harvest/ga/work/geo/`.

## 3. Pack build + independent audit — ALL CHECKS PASS

Built with `tools/packs/build_pack.py` (extended with a GA converter;
the FL path is behavior-preserving — an FL rebuild after the change is
**byte-identical**, sha256 `2c47c3d5…` before and after).

| | |
|---|---|
| Pack | `us-ga-2026-10-15.1.db.gz` |
| Bytes | 33,674,322 |
| SHA-256 | `478105036ef2e833e3f2f3ab7a199c3beef897c4989192136c45fca312ba68df` |
| datasetVersion | `2026-10-15.1` · schema 2 · minAppVersion 2.0 |
| pack_meta | region us-ga · state GA · place_count 33,514 · score_model **SCORE_100** |

Independent audit (`harvest/ga/work/audit_ga_pack.py`, direct SQLite
queries against the pack DB, no builder code): **every check passed** —
pack_meta ↔ manifest agreement; 33,514 places / 138,922 inspections /
0 orphans; **full-table comparison of all 33,514 places against source
(name, street, city, ZIP, county, score, band, region tags, coordinates):
zero mismatches**; 0 coordinates without complete provenance; 0
half-null coords; 0 coords outside the GA envelope; band census
A 28,817 / B 4,384 / C 296 / U 17 (places) and A 116,519 / B 18,347 /
C 3,164 / U 884 (inspections) both equal to source; exactly 8 NO_SCORE
inspection sentinels; 238,110 violations carried; per-place inspection
counts equal everywhere. The required 20-place byte-check sample (stride
sample, printed in the audit output) is 20/20 OK — e.g.
`gadph_12981545 POPEYES CONC B — pack[81 B 6/1/2026] = src[81 B 6/1/2026]`.

## 4. Staged for publishing (not published)

`~/kyron-build/fl-publish/` now holds both pairs:

- `us-fl.manifest.json` + `us-fl-2026-10-15.1.db.gz` (C1, unchanged)
- `us-ga.manifest.json` + `us-ga-2026-10-15.1.db.gz` (this wave)

No GitHub publish attempted — the route decision (browser-driven upload,
pack first / manifest last, per C1) is the CSDM's, and GA inherits
whatever route FL takes: the app reads
`https://markbentzjr.github.io/kyron/data/us-ga.manifest.json`.

## 5. Rig verification — GaLiveTest OK ×2

`test/src/GaLiveTest.kt`, run twice against the scratch build (Finding 1)
with the staged publish bytes (`GA_PACK_DIR=fl-publish`); identical
results both runs (`galive_run1b.log`, `galive_run2.log`):

- Install through PackManager (SHA-256 + pack_meta verified inside):
  33,514 places in ~7 s; `installedRegionVersion("us-ga") = 2026-10-15.1`.
- Co-residence: AL 23,524 + FL 70,033 + GA 33,514 = **127,071**; county
  isolation clean (Fulton only in GA; Alachua only in FL); RegionManager
  switches to us-ga.
- Browse: Kimchi II (gadph_1181797, Chatham Co.) — score **76**, band
  **"C"** verbatim in the native result; band filter "Below 85" includes
  it, "95+" excludes it; 1,000-place sample all GA + numeric + banded.
- Why-summary renders the GA narrative: *"Scored 76 · lost 25 points
  across 7 items. Biggest deduction: other violations (−9 pts): Observed
  raw shell eggs stored above Ready to eat foods and next to kimchi in
  reach in cooler…"* — violations carry item/rule/notes end-to-end.
- Map: Atlanta viewport (33.65–33.90, −84.55…−84.20) returns **4,108**
  pinned GA places, all with real locations; catalog coord count equals
  the pack's own count (28,104); 0 coords without accepted provenance.
- Removal: GA removed → AL + FL fully intact; FL removed → AL at 23,524.

**Known presentation refinement (data is complete; not a defect):**
`WhySummary`'s category regexes are tuned to Alabama/JCDH phrasing, so
many GA items bucket as "other violations" while their narratives still
render in full. The pack ships item code + title + rule + narrative for
every violation, so a future why-summary tuning pass can categorize GA
precisely without a data change.

**Rig environment note:** the first GaLiveTest attempt failed inside
`swapRegionRows` with a masked "cannot rollback" SQLite error — root
cause was the sandbox's 512 MB `/tmp` tmpfs (the GA swap's catalog +
journal + FTS outgrow it; FL's smaller pack fit). Re-running with a
disk-backed `java.io.tmpdir` passed twice with no code change. On-device
this limit does not exist; noted so the next big-pack wave uses the
disk-backed runner (`test/run_one_ga.sh`) from the start.

## 6. Production-policy audit for this wave

- No credentials anywhere: Census batch is keyless; no Geocodio key
  exists or was used; nothing test-account-tied entered the pack, the
  manifest, or any build (the pack is static data — names, addresses,
  scores, bands, narratives, coordinates, provenance).
- Guest-first untouched: packs install into the local catalog; no
  sign-in exists or is implied. Production tree byte-identical except
  the sanctioned tooling extension (`build_pack.py`, FL output proven
  byte-identical) and new pipeline/test files under `harvest/ga/work/`,
  `manual/tools/packs/out/us-ga/`, and `test/src/`.

## What the CSDM needs to decide

1. **Approve the one-entry Georgia registration** (Finding 1) into the
   next app build — until then the staged pack is verified but
   unreachable, exactly FL's pre-LF-4 position.
2. **Publish route** for the staged pairs (FL + GA together): the C1
   proposal (browser-driven GitHub Pages upload, pack first, manifest
   last) covers both files in one session.
3. Optional later waves: GA why-summary category tuning; Geocodio
   residual drain for GA's remainder (5,410 places at 4,188 unresolved
   unique addresses) once the API key exists.
