# Kyron Workstream B — The 2 Orphan Scores: Hunt, Root Cause, Fixes, Gate

**Date:** Oct 15, 2026 · **Scope:** shipped Alabama seed (`manual/src/main/assets/places_seed_geocoded.json`, 23,526 places) + presentation path + Florida dataset census
**Trigger:** Mark, in the running FIX3 app: *"There are also 2 scores that are not to any restaurant."*

---

## 1. Verdict

Two distinct defect classes ship scores that are not properly attached to a named restaurant at an address:

- **Class A — score with NO street address (exactly 2 records, dataset-wide).** These are the best-supported identification of the 2 scores Mark saw (§2).
- **Class B — fused name/street splits (58 records, all JCDH).** A parser regex truncated any establishment name containing a number and glued the rest of the name onto the street address. Two of these records are reduced to a single non-name word — **"The"** (score 99) and **"Home"** (score 98) — and are the second candidate pair (§3).

Everything else hunted came back clean: **zero** blank names, **zero** orphaned inspection rows, **zero** duplicate place ids, **zero** placeholder/header names outside Class B in Alabama. The app-side presentation path (`Place.fromJson` → `CatalogDb.importSeed`) stores and renders names/addresses verbatim — the defects are 100% in the data, created at harvest time.

All 60 defective records have remediation entries (`~/kyron-build/orphan-b/out/remediation.jsonl`: 58 fixes, 2 drops). The shipped seed was **not** overwritten. A validation gate now exists (`manual/tools/validate_seed.py`): the shipped seed **FAILS** it (88 violations); a remediated copy **PASSES**.

---

## 2. The exact 2 — Class A: score shipped with no street address

This is the **only class in the entire 23,526-record dataset with exactly 2 members** matching "a score that cannot be attached to a restaurant at an address." Both are ADPH records whose **source listing itself carries an empty address** (verified in the raw harvest files — the parser faithfully copied a source gap; no address may be invented for them):

### Record 1 — `adph_65187bf70f`

```json
{"id": "adph_65187bf70f", "n": "Dipped By Lisha Marie, LLC", "a": "", "c": "Greensboro",
 "z": "36744", "ct": "Hale", "s": 99, "d": "8/28/2026", "src": "ADPH",
 "lat": null, "lng": null, "du": null, "insp": [],
 "gs": "INSUFFICIENT_ADDRESS", "ga": "NONE", "gp": "", "gm": ""}
```
Raw source (`harvest/adph/33.json`): identical — `"address": ""`. A home-based LLC permit with a 99 score and no street address anywhere in the pipeline. In the app it renders as a 99 attached to a name and a town, with no establishment address — and it can never be mapped (`gs: INSUFFICIENT_ADDRESS`).

### Record 2 — `adph_6e37094e45`

```json
{"id": "adph_6e37094e45", "n": "El Mariachi Garibaldi", "a": "", "c": "Demopolis",
 "z": "36732", "ct": "Marengo", "s": 95, "d": "6/24/2026", "src": "ADPH",
 "lat": null, "lng": null, "du": null, "insp": [],
 "gs": "INSUFFICIENT_ADDRESS", "ga": "NONE", "gp": "", "gm": ""}
```
Raw source (`harvest/adph/46.json`): identical — `"address": ""`. Aggravating factor: a **different, fully-addressed** El Mariachi Garibaldi exists in the same dataset (`adph_121435bc92`, 508 State Street, Greensboro, score 93). The Demopolis record therefore reads as a phantom twin — a 95 floating next to a real listing of the same name, attached to no address of its own.

**Remediation: DROP both** (reason recorded per record in `remediation.jsonl`). Dropping is the only honest action: the CSDM gate is "zero scores ship unattached to a named place with an address," and fabricating an address would violate the data-accuracy rules.

---

## 3. Second candidate pair — the worst of Class B

If what Mark saw was garbage rows rather than address-less ones, it was these two — the only records in the dataset whose entire displayed "name" is a single word that is not a name at all:

### `jcdh_28783` — displayed name **"The"**, score **99**
Shipped: `n="The"`, `a="3 DELIGHTS 1420 31ST ST SW"`, Birmingham 35221, Jefferson.
Raw JCDH blob: `THE 3 DELIGHTS 1420 31ST ST SW BIRMINGHAM 35221 Smoke Free: Y …`
True record: **The 3 Delights**, 1420 31st St SW.

### `jcdh_23218` — displayed name **"Home"**, score **98**
Shipped: `n="Home"`, `a="2 SUITES BY HILTON 3289 LOWERY PKWY"`, Fultondale 35068, Jefferson.
Raw JCDH blob: `HOME 2 SUITES BY HILTON 3289 LOWERY PKWY FULTONDALE 35068 Smoke Free: Y …`
True record: **Home 2 Suites by Hilton**, 3289 Lowery Pkwy.

Both are repaired by their Class B remediation entries (§5).

---

## 4. Class census — Alabama (whole shipped seed, scripted)

| # | Class | Count | Disposition |
|---|-------|------:|-------------|
| A | Score ≥ 0 with **blank street address** (name present) | **2** | DROP (§2) |
| B | **Fused name/street split** — name truncated at first digit, tail glued to street | **58** | FIX (§5) |
| B1 | …of which name ends with bare `#` (store number severed) | 27 | subset of B |
| B2 | …of which name reduced to a lone non-name word ("The", "Home") | 2 | subset of B |
| — | Blank / whitespace-only name with a score | 0 | — |
| — | Punctuation-only name | 0 | — |
| — | Placeholder/header name (outside Class B) | 0 | — |
| — | Inspections referencing a nonexistent place | 0 | impossible by construction (§6) |
| — | Duplicate place ids | 0 | — |
| — | Non-numeric / out-of-range scores | 0 | — |
| — | Blank city / county / date | 0 / 0 / 0 | — |
| — | Blank ZIP (address present; cosmetic) | 24 | noted, not an orphan class |
| — | Name == city (1: "Graysville" — is a Class B record via the prototype path) | 1 | in B |

Class B examples (shipped name + fused street → corrected):
`Abc` + `123 MAGICLAND 1518 4TH AVE N` → **Abc 123 Magicland**, 1518 4th Ave N ·
`Piggly Wiggly #` + `263 PRODUCE …` → **Piggly Wiggly # 263 Produce** ·
`Arbys#` + `7139 1668 GADSDEN HWY` → **Arbys# 7139**, 1668 Gadsden Hwy ·
`Cava` + `20 MIDTOWN 241 20TH ST S` → **Cava 20 Midtown** ·
`Sams Club #` + `8247 (CAFE) …` → **Sams Club # 8247 (Cafe)** ·
`Twelve` + `78 CATERING @ CHEFS WORKSHOP …` → **Twelve 78 Catering @ Chefs Workshop**.

One Class B record needed a hand-built fix: `jcdh_22521` (Soho Social – Standard) — the JCDH blob itself interleaves a suite range inside the street (`1830 29TH Ste . 150 -160 -175 AVE`); the name was never truncated. Remediation rebuilds the street from the source tokens only: `1830 29TH AVE STE 150-160-175`.

---

## 5. Root causes

### Class B — the fused-blob regex (58 records)
JCDH's list page yields **one fused text blob** per permit: `NAME STREET CITY ZIP Smoke Free: …`. `harvest/build_seed.py` split it with:

```python
blob_re = re.compile(r'^(.*?)\s+(\d+\s+.+?)\s+Smoke Free:.*$', re.S)
name = group(1)          # everything before the FIRST digit token
street = group(2)        # starts at the first digit token
```

Any name containing a number — store numbers (`#263`, `#8247`, `2355`), brand numbers (`Home 2 Suites`, `AMC Summit 16`, `Twelve 78 Catering`), or a leading article + number (`The 3 Delights`, `ABC 123 Magicland`) — was cut at that digit, and the remainder of the name was prepended to the street. Two entry points, one root cause:

- **56 records** via the enum path above (`harvest/jcdh_enum.json` blobs, re-verified one by one).
- **2 records** (`jcdh_14824` Dollar General #, `jcdh_29433` Graysville) via the prototype path: `kyron-prototype/data.json` was built earlier with the same split and already contains the fused fields; `build_seed.py` copied them verbatim.

A secondary cosmetic defect rides along: `title_case()` destroys intentional capitalization (`BJCC` → `Bjcc`, `AMC` → `Amc`). Left as-is (faithful re-casing would require source data we don't hold), noted for the record.

### Class A — source-data gap, parser had no guard (2 records)
ADPH's county listings genuinely publish no street address for these two permits (raw harvest rows carry `"address": ""`). `build_seed.py`'s ADPH section inserted records unconditionally — there was **no completeness guard anywhere in the pipeline**: not in the ADPH merge, not in `build_seed.py`, not at pack build. The MCHD section, by contrast, already skipped blank-name rows.

### Why the app shows them faithfully (presentation path audit)
`Place.fromJson` reads `n`/`a` with `optString` (present in every seed record), and `CatalogDb.importSeed` binds name/address verbatim into `places` and writes inspections from the same record object under its own id (`INSERT OR REPLACE INTO inspections(place_id, idx, …)`). No field is dropped, renamed, or re-keyed on device. **Embedded inspections cannot orphan in this design** — an inspection exists only inside its place record end-to-end.

---

## 6. Parser / harvest fixes applied (`harvest/build_seed.py`)

1. **Street-anchored splitter** (`split_name_street` + `_complete_street` + `_tail_clean`): the enum path now strips city/ZIP from the blob tail, then splits NAME/STREET where the remainder is a *complete street* (house number + street-name token + suffix), preferring the last clean anchor — names keep their numbers; streets lose the debris. Suite-interleaved sources (`1830 29TH Ste . …`) are protected by a tail-cleanliness rule (a name tail may not contain ordinal street names or suite markers). Legacy first-digit fallback retained for suffix-less streets (`800 LAKESHORE`).
2. **Build-time rejection:** enum records whose produced name is still a fragment (ends with `#`, lone article) or whose street still carries a name tail (`street_has_fused_tail`) are counted `n_bad` and **skipped with a printed permit id** instead of shipping.
3. **Prototype-path guard:** if a prototype record's street carries a fused tail, the recombined string is re-split at the street anchor before use (verified: reproduces both known records' corrections exactly).
4. **ADPH completeness guard:** score rows with a blank name **or** blank street address are excluded and written to `harvest/adph_rejects.json` with a loud build log line. **MCHD** gained the same blank-address guard (it already had the blank-name one).

**Verification of the patched splitter** over all 2,274 enum blobs vs. the shipped seed: reproduces the shipped name/street for **2,162** clean records exactly (plus 43 more identical modulo whitespace collapsing — the old code preserved the blobs' double spaces; the new one normalizes them), reproduces the remediation corrections for **55 of 56** enum-path Class B records (the exception is the hand-built Soho fix), and would reject **0** records. Zero enum blobs lack a ZIP tail.

**Remediation list:** `~/kyron-build/orphan-b/out/remediation.jsonl` — 60 entries (`place_id`, `action`, `reason`, corrected `fields` for fixes): **58 fixes** (JCDH fused splits; corrected name = shipped name + recovered tail, corrected street = the true street suffix) + **2 drops** (Class A). The shipped seed was not modified; the integration wave applies the list.

---

## 7. The gate — `manual/tools/validate_seed.py`

Fails a dataset (exit 1) on any of:

- **G1** result-bearing place with a blank name
- **G2** result-bearing place with a blank street address
- **G3** an inspection referencing a nonexistent (or wrong) place
- **G4** a name matching the placeholder/header blocklist, or ending in a bare `#`
- **G5** a fused name/street split (street field = name fragment + complete street; a `<house#> <directional>` prefix such as `1842 EAST 3 NOTCH STREET` is explicitly *not* flagged — that candidate was investigated and cleared as a genuine Andalusia street)
- **G6** duplicate place ids

**Results:**

| Dataset | Result | Detail |
|---|---|---|
| Shipped AL seed (pre-remediation) | **FAIL — 88 violations** | G1 0 · **G2 2** (exactly the Class A pair) · G3 0 · **G4 28** (27 `#`-names + "The") · **G5 58** (exactly Class B) · G6 0 |
| Remediated copy (58 fixes + 2 drops applied → 23,524 places) | **PASS** | all checks 0 |
| Florida `places_fl.json` | **FAIL — substantive subset below** | §8 |

Gate counts cross-check the hand census exactly (G5's 58 = Class B's 58; the one detector false positive found during development — David's Catfish House, Andalusia — is excluded by the directional-prefix rule and documented in the gate).

---

## 8. Florida census (`harvest/fl_dbpr/OUTPUT/places_fl.json`, 70,051 places)

FL carries DBPR **dispositions**, not numeric scores; "result-bearing" = a disposition or ≥1 inspection (36,035 places; 44,664 inspections). FL fixes are a later wave — this is the census:

| Class | Count | Notes |
|---|---:|---|
| Blank name, total | **14** | DBPR licensee rows with no DBA name; every one has a `licensee_name` (legal entity) on file — a fallback path exists for the FL wave |
| …of which **result-bearing** (inspections/disposition attached to no name) | **2** | `fldbpr_NOS5815165` (18 N Dollins Ave K31, Orlando — insp. 2026-09-25, "No Further Action") · `fldbpr_SEA2326635` (1418 Ocean Dr, Miami Beach — insp. 2026-09-17, "No Further Action") |
| Placeholder name | **3** | `N/A` ×2 (`fldbpr_CAT6307452` Winter Haven, no insp. · `fldbpr_VEN3900319` Tampa, **has inspection + disposition**) · `ESTABLISHMENT` ×1 (`fldbpr_SEA2706562` Pensacola, no insp.) |
| Placeholder name, result-bearing | **2** | `fldbpr_VEN3900319` ("N/A") · `fldbpr_SEA6000500` ("**RESTAURANT**", 155 Hammon Ave, Palm Beach, lic. CH OPCO LLC — insp. 2026-09-24, "No Further Action") |
| **Total FL results attached to no real restaurant name** | **4** | the 2 blank + 2 placeholder above |
| Blank street address | 0 | — |
| PO-Box (mailing) address in the street field | 29 | data-quality note for the FL geocoding pass |
| Duplicate ids / orphan inspections | 0 / 0 | inspections are embedded, as in AL |
| Gate G5 raw hits | 488 | **detector artifacts, sampled 12/12**: structured DBPR addresses of the form `<house#> <ordinal street> <STE/UNIT/LOT/#>` (e.g. `737 8 AVE W STE 118`). FL name/address are separate source columns — fusion is impossible by construction; G5 is calibrated for fused-string sources (AL JCDH) |

Gate verdict on FL as-is: **FAIL** (G1 2, G4 18 = 14 blank + 3 placeholder + 1 "RESTAURANT"). Recommendation for the FL wave: drop or `licensee_name`-fallback the 18 G4 records before pack build, and treat the 12 non-result-bearing blank-name license rows the same way (the ordered gate only blocks result-bearing records, but a nameless place should not ship at all).

---

## 9. Adjacent findings (not orphans; for the integration wave)

- **Dual-permit duplicates:** 5 matchKey groups hold two JCDH permits for the same name+address with *different* scores (La Oaxaquena 91/100, Roll Cajun Boudin 96/91, Snapper Grabbers 90/92, Taqueria La Juanita 98/95, Sam's Club grocery/café 100/96 — the last is plausibly two genuinely distinct permits). Both rows render; a merge/dedup decision is a product call, so no remediation entries were written.
- **ADPH raw matchKey overwrites:** 19,057 raw rows → 18,999 keys (53 collision groups, 42 with differing score/date — repeat inspections of one permit listed as separate rows). `build_seed.py`'s dict keeps the last row per key wholesale — no cross-record contamination, but the choice is silent and order-dependent. Worth an explicit newest-date rule in a future harvest pass.
- **MCHD matchKey collisions:** 2 groups (Marathon Snow Rd, Springhill Seafood) collapse two raw rows into one seed record each.
- **Investigated and cleared:** `adph_0a670e2202` named **"1856"** (205 S. College St., Auburn, 95) — the name is numeric but genuine: ADPH's own listing says "1856" (a real Auburn restaurant). 65 ADPH addresses not starting with a digit are legitimate (shopping centers, "One Grand Boulevard", intersections). `title_case` capitalization damage (`Bjcc`, `Amc`) is cosmetic and dataset-wide, not an attachment defect.

---

## 10. Files

- Gate: `~/kyron-build/manual/tools/validate_seed.py` (exit 0 PASS / 1 FAIL, per-check violation lists)
- Remediation: `~/kyron-build/orphan-b/out/remediation.jsonl` (60 entries; **not applied** to the shipped seed)
- Parser fixes: `~/kyron-build/harvest/build_seed.py` (street-anchored splitter, enum + prototype guards, ADPH/MCHD completeness guards; compiles clean, splitter verified against all 2,274 source blobs)
- This report: `files/Kyron-Orphan-Scores-Report.md`
