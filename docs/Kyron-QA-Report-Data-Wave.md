# Kyron QA Report — Data Wave (Workstreams A + B integration), INDEPENDENT RECOUNT

**Date:** Oct 15, 2026. **Candidate under audit:** `~/kyron-build/manual/Kyron-2.0-FIX4.apk`
**Verdict: SHIP** — for CSDM review. Mark's Z Fold7 device gate on this exact md5
remains the final closer, as always. `~/workspace/your_files/` untouched; nothing
delivered to Mark by this pass.

Every number below was measured by this QA pass from the extracted APK artifact
or by re-running the source system (Census API), not taken from the builder's
changelog (`Kyron-Dev-Update-Data-Wave.md`).

## 0. Candidate identity — verified before and after all work

| Check | Claimed | Measured |
|---|---|---|
| APK md5 | `e5ddb2db797ab962c133659639a1c381` | `e5ddb2db797ab962c133659639a1c381` ✓ |
| versionCode / versionName | 8 / "2.0" | 8 / "2.0" (aapt2 badging) ✓ |
| Package | `com.kyronapp.kyron` | `com.kyronapp.kyron` ✓ |
| Signing cert SHA-256 | `cb932a51…f24f56` | `cb932a5158d51ff577be2ac5e40b3c30760aeb10248a31d26e2fe7db6af24f56` — identical on FIX3 and FIX4 ✓ |
| Baked seed md5 | `099a5ff71232506ba5178d539282773c` | `099a5ff7…` from the APK; byte-identical to the tree asset ✓ |

## 1. Counts (claim 1) — ALL CONFIRMED from the extracted FIX4 seed

| Metric | Claimed | Measured (this pass) |
|---|---:|---:|
| Total places | 23,524 | **23,524** |
| With verified coords | 18,712 (79.54%) | **18,712 (79.54%)** |
| List-only | 4,812 | **4,812** |
| FIX3 baseline | 23,526 / 17,613 (74.87%) / 5,913 | **23,526 / 17,613 (74.87%) / 5,913** |
| Duplicate place ids | 0 | **0** |
| Coords outside Alabama envelope (30.1–35.05, −88.5…−84.85) | 0 | **0** (lat range 30.234–34.996, lng −88.437…−84.888) |

**Provenance census of all 18,712 coordinates (measured):**
`gp` = CENSUS 17,610 · CENSUS-RETRY 1,099 · HARVEST 3 — and nothing else.
Every coord carries `gs=ACCEPTED`, `ga=ADDRESS_RANGE`; `gm` = EXACT 13,499 /
NON_EXACT 5,210 / (blank, the 3 HARVEST keeps) 3. **No centroid, jitter, or
city-center provenance exists anywhere in the file.**

Centroid-signature cross-check: the most-shared coordinates are legitimately
co-located establishments at one street address (e.g. 75 places at
"4217 9TH AVE SW STE/SUITE/UNIT 39, Huntsville" — spelling variants of a single
address, all receiving Census's one interpolated point for that address).
Jittered centroid pins would show the opposite signature (unique fake points);
none present.

## 2. Workstream B remediation (claim 2) — CONFIRMED

- **Drops absent:** `adph_65187bf70f` and `adph_6e37094e45` are present in the
  FIX3 seed and **absent** in FIX4. The full id-set difference FIX3→FIX4 is
  exactly those 2 removals and **zero additions**.
- **Fix sample vs raw source:** 20 of the 58 fixes sampled deterministically
  (every 3rd); for each, the restored name+street in the FIX4 seed exactly
  equals the remediation file's fields, and the concatenation
  `name + " " + street` is the literal prefix of the raw JCDH source blob in
  `harvest/jcdh_enum.json` (e.g. `jcdh_11035`: blob "REGAL TRUSSVILLE CINEMAS
  16 5895 TRUSSVILLE CROSSINGS PKWY…" → restored "Regal Trussville Cinemas 16"
  / "5895 TRUSSVILLE CROSSINGS PKWY"; FIX3 had shipped "Regal Trussville
  Cinemas" / "16 5895 …"). **20/20 verified — restorations come from the
  source, not invention.**

## 3. Workstream A coordinates (claim 3) — CONFIRMED, 30/30

Deterministic random sample (seed 20261015) of **30 of the 1,099** CENSUS-RETRY
pins, re-geocoded independently against the US Census API:

- **27/30:** submitting the seed's own raw address (batch API) returned Census
  coordinates **identical to the shipped pin (< 0.5 m)**.
- **2/30** (highway/suffix variant classes): the raw form no-matches by design;
  submitting Workstream A's recorded verbatim matched address returned the pin
  at **0.00 m**.
- **1/30** (`adph_4196732391`, "4154 HWY 47, Shelby"): the batch API returns a
  bare Tie. The single-address API shows the tie is between "4154 HWY 47"
  (state highway — **the shipped pin, exact coordinate match**) and
  "4154 CO RD 47" (a different road ~800 m away). The pin is Census's own
  coordinate for the candidate whose street form matches the source record —
  correct, evidence-based disambiguation, not a guess between equals.

**Total: 30/30 pins are Census-produced coordinates for the place's own
address. Zero mismatches, zero findings.**

## 4. Merge discipline (claim 4) — CONFIRMED, exact

Record-by-record diff of the FIX4 APK seed vs the FIX3 APK seed:

- Changed records: **exactly 1,157** — 1,099 with only
  `{lat, lng, gs, ga, gp, gm}` changed (Workstream A; all `gp=CENSUS-RETRY`,
  all had `lat=null` in FIX3, seed coords byte-equal to `new_coords.jsonl` for
  all 1,099), and 58 with only `{n, a}` (57) or `{a}` (1) changed
  (Workstream B). **Zero other changes.**
- The 58 changed B ids are **set-identical** to `remediation.jsonl`'s fix ids;
  the 2 removed ids are set-identical to its drop ids; A∩B overlap = 0.

## 5. Seed gate (claim 5) — CONFIRMED, including negative control and wiring

- `validate_seed.py` on the extracted FIX4 seed: **PASS — 0 violations**
  (G1–G6 all 0), exit 0.
- Same tool on the FIX3 seed: **FAIL — 88 violations**, exit 1 (negative
  control reproduces Workstream B's census to the digit).
- **Wiring, re-proven by this pass in its own scratch tree** (production tree
  untouched): the real `build_manual.sh` with the OLD seed swapped in passes
  manifest merge and the pathData gate, then **exits 1 at the seed gate,
  naming `adph_65187bf70f` et al. — "3/8 aapt2 compile" never runs.**
  With the merged seed the production build proceeded (FIX4 exists and its
  seed passes, above).

## 6. Standard audits on FIX4 (claim 6) — CONFIRMED

- **Zip diff FIX3→FIX4:** 498 entries, identical name sets; exactly **5**
  CRC-differing entries — `AndroidManifest.xml` (vc7→vc8),
  `assets/places_seed_geocoded.json`, and the 3 signature files.
- **Dexes:** `classes.dex` CRC `0x487f7147` and `classes2.dex` CRC
  `0xcb9b6a65` — **byte-identical to FIX3**; `resources.arsc` byte-identical.
- **Dex audit (own run of `tools/dex_audit.py`):** 7,845 defined classes;
  referenced-but-undefined = **exactly the 13 known-benign** (BouncyCastle
  JSSE ×3, Conscrypt ×3, OpenJSSE ×3, framework XmlPull ×3, JSpecify
  `@NullMarked` ×1); 599 R classes.
- **pathData validator (own run):** 23 files / 25 paths / **0 malformed**.
  (FIX3 pass-2's binary-level audit of the compiled APK carries over: the
  compiled resources are byte-identical.)
- **Production-policy sweep (own scan of every zip entry):** 0 hits for
  `kyronfoodsafety`, Geocodio, credential shapes, private keys, `CrashDiag`,
  breadcrumb/diag artifacts, or diag version names. The single bare `apikey=`
  occurrence sits in a dex byte-identical to policy-clean FIX3 (osmdroid's
  known valueless literal).

## 7. Suite spot-runs (claim 7) — PASS on this pass's own runs

- **GeoTest: OK (1 test)** — asserts the new counts (23,524 places /
  18,712 real / 0 centroid) from the shipped seed.
- **Lf4Test: OK (9 tests)** — pack install/attack/rollback and the
  AL 23,524 + FL 70,051 co-residency flow.

*Environmental note, with evidence:* this pass's first two GeoTest attempts
failed during Robolectric's database import with an SQLite-open error while
/tmp (512 MB tmpfs) had only ~136 MB free — 311 MB of it was this pass's own
scratch tree. After removing the scratch copy (446 MB free), GeoTest passed,
and Lf4Test passed after it. Same artifact class recorded in the LF-4 and
FIX2 passes; not a product defect.

## 8. Bookkeeping reconciliation — 4,814 vs 4,812 (authoritative figures)

Workstream A's residual export (`residual_for_geocodio.csv`, measured by this
pass: **4,105 rows, place_count summing to 4,814**) was computed against the
**pre-merge** dataset. Two of its rows are blank-street entries
("Malformed source address (no street field)") whose only places are
`adph_65187bf70f` and `adph_6e37094e45` — the exact 2 records Workstream B
deleted from the dataset. Therefore, for the Geocodio API-key ask:

- **Authoritative places still needing pins: 4,812** (the shipped list-only
  count; every one carries a street address — measured 0 blank in the
  shipped list-only set).
- **Authoritative credit figure: 4,103 submittable unique addresses** — the
  export's 4,105 rows minus its 2 dead blank-street rows, which correspond to
  deleted places and must be filtered before submission. (This pass's raw
  (street, city, ZIP) tuple count over the shipped list-only set is 4,229;
  the export's lower figure is its normalization dedup of spelling variants
  of the same address, which is the correct basis for credit planning.)
- "4,814 places / 4,105 unique addresses" remains accurate **only** as a
  description of the pre-merge export file, not of the shipped data.

## Verdict

**SHIP** for CSDM review. Every builder claim reproduced independently:
counts, provenance, remediation fidelity (20/20 against raw harvest),
coordinate truth (30/30 against live Census), merge exactness (1,157 + 2,
nothing else), the gate (passes the new seed, fails the old at exactly 88,
and blocks the real build before aapt2), and the standard audits
(dex/arsc byte-identity, 13 known-benign, policy clean). No P1/P2 findings.
The one correction this pass makes is bookkeeping-only (§8): quote
**4,812 places / 4,103 submittable unique addresses** to Mark for the
Geocodio key, not 4,814 / 4,105.

*Residual, stated plainly: no sandbox executes a real-device first frame;
Mark's Z Fold7 device gate on md5 `e5ddb2db797ab962c133659639a1c381`
remains the final closer under the binding release gate.*
