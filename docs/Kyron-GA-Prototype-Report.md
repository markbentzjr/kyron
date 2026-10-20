# Kyron — Georgia Adapter Prototype Report (Workstream C2)

**Date:** October 15, 2026 · **Adapter:** `ga_dph` prototype v0.1, in `~/kyron-build/harvest/ga/`
**Spend:** $0 · no accounts · no app changes · no geocoding run (readiness measured only)

## Headline numbers

| Metric | Value |
|---|---|
| Establishments (Food Service permits) | **33,514** |
| Inspections | **138,922** |
| Violations (full narratives) | **238,110** |
| Inspection date range | **2023-10-16 → 2026-10-15** (3 full years) |
| Counties covered | **156 of 159** (≈ **89.1%** of Georgia's 2020 Census population) |
| Places with ≥1 inspection | 33,511 (99.99%) |
| Latest-score profile | mean 95.5 · A 28,817 (86.0%) · B 4,384 · C 296 · U 17 · lowest 46 |
| Validation gate (Workstream B) | **G1/G2/G3/G4/G6 = 0 violations**; G5's 88 flags 100% adjudicated false positives (see §4) |
| Independent QA crosscheck | **ALL PASS** (B1–B5, B8, B9) |
| Geocode-readiness | **99.24%** of street addresses start with a house number; 100% have city + ZIP |

## 1. Source verdict

Georgia's statewide source is the **Georgia Department of Public Health "State of Georgia" Health Inspection portal** — a Tyler Technologies *Digital Health Department* (DHD) system at `ga.healthinspections.us/stateofgeorgia/`, linked from the DPH Environmental Health page. There is **no bulk download** (consistent with the Oct 13 nationwide research), but the portal's own public JSON backend (`…/API/index.cfm/…`) — the same API its web UI calls — exposes everything in structured form:

- `filters` — the authoritative vocabularies (all 159 counties; permit types Food Service / Tourist Accommodation / Swimming Pool)
- `search/<json>/<page>` — facility enumeration, 5 per page, newest-inspection-first (query values base64-encoded, exactly as the portal's client does)
- `inspectionsData/<facilityId>` — full inspection history **with violation narratives**: FDA-style item codes, Georgia rule citations (Rule 511-6-1), points deducted, corrected-on-site / repeat flags, inspector name, and the inspector's full notes — plus a `printablePath` to the official full report PDF/HTML for every inspection.

No login, no API key, no CAPTCHA. Every response was saved raw (277 MB) with a SHA-256 fetch log: **41,776 requests, 100% HTTP 200** (`fetch_log.tsv`). Only **Food Service** permits were harvested; Tourist Accommodation and Swimming Pool permits are not food establishments.

**Coverage gap (by the source's own design):** Gwinnett, Newton and Rockdale counties publish through the **GNR Health District** (`inspections.myhealthdepartment.com/gwinnett`, a different vendor — MyHealthDepartment), not the state portal. Their county searches on the state portal return zero results (the empty responses are preserved in `raw/` as evidence). Those 3 counties held 1,163,115 of Georgia's 10,711,908 people in the 2020 Census (Gwinnett 957,062; Newton 112,483; Rockdale 93,570), so this dataset covers **156/159 counties ≈ 89.1% of the state population**. A small GNR adapter is the follow-up to close the gap.

## 2. Score model — native, nothing invented

Georgia scores food-service inspections on a **native 0–100 scale** with state-published grade bands **A 90–100 · B 80–89 · C 70–79 · U <70**. Both the numeric score and the band are stored (`s`, `grade`); no conversion of any kind was applied or needed. Inspection purposes are preserved verbatim (Routine ≈ 89.9%, Initial, Followup, Temporary, Issued Provisional Permit, …). **Violations are narratives** (unlike FL's category counts) — the richest "why" data Kyron has in any state so far. All 238,110 violation entries share one uniform 6-field shape (item, citation, points, corrected, repeat, notes). Eight inspections statewide have a blank Score column in the source; they are kept with `s: null`, never guessed.

History depth is what the portal exposes: inspections run from **2023-10-16** forward (no earlier records are published by this system), per-facility counts 0–29 (mode 5–6, consistent with ~2 inspections/year).

## 3. What the harvest surfaced (and how it was handled)

Three source behaviors matter for anyone refreshing this data — all are documented in `FIELD_MAPPING.md` and `OUTPUT/qa_report.json`:

1. **County prefix matching.** The portal's county predicate prefix-matches: `county=CLAY` also returns all 962 CLAYTON facilities (the only prefix pair among the 159 counties — verified programmatically). County attribution is adjudicated by rule (longest sighting wins on prefix chains; permit-code tie-break for the other 49 multi-county sightings — metro county-line and mobile facilities). Permit codes alone never move a facility: district offices issue cross-county permits (an Alma, Bacon Co. facility legitimately holds a Coffee-coded permit; it stays in Bacon — verified against its address).
2. **Crossed inspection payloads under parallel load.** 239 of 33,516 inspection responses (0.71%) contained *another facility's* history — caught because each response's newest inspection contradicted the facility's own search-stub last score/date. All 239 were re-fetched **sequentially** (`ga_mopup.py`); 236 then verified consistent. **Lesson baked into the adapter docs: fetch `inspectionsData` sequentially, or verify every copy against its stub.** The remaining 3 are facilities whose detail endpoint literally answers "No Inspections To Display" — they keep their stub-level latest score/date (flagged `latest_from_stub_only`); no inspection rows were fabricated for them.
3. **Address variety.** Two-line addresses (norm), single-line `STREET CITY, GA ZIP` (e.g. Gordon Co.), three records with a wrong state typed in the source (`NEWNAN, TN 30263`; `FAYETTEVILLE, CA 30214`; one genuine NJ address on a GA permit) — parsed generically, source state preserved in `addr_state`.

## 4. Validation gate (Workstream B's `validate_seed.py`)

Run over `OUTPUT/places_ga.json` (33,514 places):

- **G1** blank name · **G2** blank street · **G3** orphaned inspections · **G4** placeholder names · **G6** duplicate ids → **0 across the board.** Zero scores ship unattached to a named place with an address.
- **G5** (fused name/street) flagged 88 records. **All 88 are proven false positives** (`OUTPUT/gate_adjudication.json`, reproducible via `ga_adjudicate.py`): every flagged street is byte-identical to the street segment of the portal's own `mapAddress` and every name to the portal's separate name field — this adapter never splits a combined blob, so the JCDH fusion failure mode G5 guards against cannot occur here. The flags are legitimate Georgia address forms the AL-tuned heuristic doesn't know: numbered streets/highways (21), venue-prefixed street lines — 26 UGA Sanford Stadium concession stands whose source street line is literally "SANFORD STADIUM - 100 SANFORD DRIVE" (15+11 highway/intersection forms), Circle 75 Parkway (7), Old 41 Hwy-style named routes (6), ranges/multi-number/unit-first/intersection forms (9). The data was left verbatim rather than corrupted to appease the heuristic.
- **2 exclusions**, logged with full provenance in `OUTPUT/exclusions.json`, per Workstream B precedent: a Fulton permit the source itself publishes under the literal name **"Establishment"** (G4; 5 real inspections, 85–96 — dropped rather than shipped under a non-name), and a Tybee Island facility for which the source publishes **no street address at all** (G2-class).

Independent QA pass B (`qa_crosscheck.py`, different method — streams the raw layer and recomputes everything) is **ALL PASS**: stub↔place accounting exact (33,516 = 33,514 + 2 exclusions), inspection accounting exact (138,930 raw rows − 3 JSON nulls − 3 placeholder rows − 2 unparseable dates = 138,922), every place's latest score/grade/date re-derived from raw, zero invented scores, county-attribution invariants hold.

## 5. Geocode-readiness (no geocoding run)

**99.24%** of the 33,514 street addresses start with a house number (33,258); 100% carry city and ZIP; only 15 are PO Boxes (a further 241 are intersections/ranges/venue lines that Census may partially match). This is FL-grade readiness (FL was 98.96%) — the GA pack can go straight into the standard Census-batch → residual pipeline when the pack wave runs. Coordinates in this prototype are `null` by design; no centroid or jitter pins were created.

## 6. Deliverables in `~/kyron-build/harvest/ga/`

`ga_fetch.py` (resumable fetcher) · `ga_build.py` (normalizer + QA pass A) · `qa_crosscheck.py` (independent QA pass B) · `ga_mopup.py` (crossed-payload repair) · `ga_adjudicate.py` (G5 adjudication) · `FIELD_MAPPING.md` · `fetch_log.tsv` (41,776 rows, SHA-256 per response) · `raw/` (277 MB: search pages + inspection payloads + portal config) · `OUTPUT/` (`places_ga.json` 211 MB — size is the full violation narratives, a pack-build trimming decision for later — `manifest.json`, `qa_report.json`, `qa_crosscheck.json`, `exclusions.json`, `gate_adjudication.json`).

## 7. Recommended order for the remaining states: TN → SC → NC

The assigned order was GA → TN → NC → SC. After GA, I recommend **TN next (confirmed), then SC, then NC** — swapping the last two on adapter-efficiency evidence:

- **TN — next.** Tennessee Department of Health runs a single statewide system with native **0–100 scores** (below 70 = failed, mandatory follow-up) and publishes full inspection reports through its statewide search — one agency, one portal, the closest analog to GA. (Verify its machine-access pattern at build time; state newspapers already rebuild weekly databases from it, so the data demonstrably flows.)
- **SC — second.** One statewide tool, **SC Food Grades** (DHEC / SC Dept. of Agriculture retail-food program), ~22,000 establishments, 100-point scores with A >87 / B 78–87 / C <78. It is backed by a GIS web app (`gis.dhec.sc.gov/foodgrades`) — GIS-backed sources usually expose clean query endpoints, which should make SC the cheapest of the three to adapt.
- **NC — last of the three.** Inspections are **county-administered** under state rules: a state-hosted platform (CDPEHS) covers many counties, but Wake, Mecklenburg, Durham and others run separate portals — NC is a mini-wave, not one adapter. Its scores are numeric with half-point deductions (A ≥90, B 80–89.5, C 70–79.5, <70 = permit revoked), all preservable natively once the county sources are sequenced.

After those, the Socrata city wave (board task K-07) proceeds as planned. Every new adapter inherits this one's lessons: Workstream B's gate with per-record adjudication, stub-vs-detail consistency checks, and sequential (or verified) detail fetching.
