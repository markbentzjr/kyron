# Kyron — South Carolina Adapter Prototype Report (Workstream C5)

*Harvest + normalize + gate + independent QA completed Oct 15–16, 2026. All figures below are measured from the harvested raw files and re-derived by the independent crosscheck — not copied from agency literature.*

## Headline numbers

| | |
|---|---|
| Establishments (places) | **35,862** (29,940 permit-keyed + 5,922 rate-only) + **1 excluded** (below) |
| Inspections shipped | **213,358** (union 213,359 − 1 excluded) |
| Inspection date range | **2021-08-21 → 2026-10-13** |
| Counties | **46 of 46 = 100%** of SC population (2020 Census total 5,118,425) |
| Native result | Posted letter grade verbatim (A/B/C/N/A/S); **numeric score exists only inside the PDF reports → `s: null` everywhere, never derived from the grade** |
| Violations carried | **0** — itemized violations exist only inside the PDFs; every inspection's `du` links the official PDF |
| History depth | mean 5.95 inspections/place, median 5, p90 12, max 41 |
| Seed gate | **PASS with adjudication** — G1–G4, G6 = 0; 13 G5 flags, 13/13 proven source-verbatim |
| Independent QA crosscheck | **ALL PASS** (B1–B9; B6/B10/B11 adjudicated/informational as noted) |
| Geocode-readiness | **99.84%** of places have a house-numbered street (35,803/35,862); 83.35% have house+city+ZIP; 7 PO Box streets |
| Spend | $0 — public endpoints, no accounts, no keys |

## 1. Source verdict

SC runs a single statewide Food Grades system for Regulation 61-25 facilities. The program moved from DHEC to the **SC Department of Agriculture** on July 1, 2024; the public endpoints still live on `dhec.sc.gov` domains. Three public routes were verified fetchable, and they interlock by one shared key (`AuditResultGlobalID`):

1. **ArcGIS FeatureServer (preferred spine)** — the GIS app behind `dataviz.dph.sc.gov/foodgrades/` exposes `Restaurants` on SC DPH's ArcGIS Online org: layer 0 (24,295 establishment points) + table 4 "Restaurants_Steton" (**137,087 inspections**, 2023-10-17 → present). Standard offset paging, maxRecordCount 2000, stable.
2. **Advanced Search (`rate.aspx`)** — the classic search is the *deeper* archive: county-by-county enumeration yields **213,359 inspections back to 2021-08-21**, each row carrying name/street/city/grade/date/type and the same GUID in its PDF link. It completely contains the GIS table (QA B3b: 137,087/137,087 GIS GUIDs present, zero GIS-only), and on every joined row the two systems agree exactly — dates 137,087/137,087, grades 137,087/137,087, filing county 137,087/137,087. Each system cross-verifies the other.
3. **Per-inspection PDFs** (`pubdoc.dhec.sc.gov/Inspection/<GUID>.pdf`) — the only place numeric scores and itemized violations exist. **Unreachable from the build sandbox**: HTTPS fails on three independent stacks (curl exit 52 empty-reply, python requests proxy-disconnect, wget timeout), plain HTTP only 301-redirects to the same HTTPS. The URLs are live for the public (both state apps link them); this is a sandbox egress block, documented with evidence — the prototype ships grades + PDF links and leaves score/violation enrichment as a GUID-keyed join whenever a PDF route opens (no re-harvest of the spine needed).

No vendor portal, no account, no key, no terms friction: plain GETs against the state's own public query/search endpoints at polite rates (GIS paging sequential-ish; rate enumeration 4 county workers).

## 2. Native result model — grades verbatim, scores honestly absent

SC publishes **both** a 100-point score and a posted letter grade for each inspection (program literature: A = more than 87 points, B = 78–87, C = below 78). Machine-readably, only the grade survives: the GIS `SCORE` column is **null on all 137,087 rows** (counted, QA B5), and rate.aspx displays grade only. So the adapter carries:

- `grade` — the published POSTED_GRADE verbatim (source pads it with spaces; trimmed only). Shipped inspection census: **A 194,603 · B 12,579 · C 4,527 · N/A 1,632 · S 17**. (`N/A` is the source's own value for audits with no posted grade; `S` appears on 17 compliance-coded rows — both carried exactly as published.)
- `s` — **null on every place and inspection**. Never derived from the grade (the band edges are published, but a band is not a score).
- Place headline = newest inspection under a documented ordering (below): A 35,312 · B 285 · C 130 · S 2 · N/A 133.

Facility types (all in scope, form labels verbatim): Retail Food Establishments 23,224 places · Mobile Food Units 4,344 · Institutions 1,362 · Grocery Stores 1,010 · rate-only places (no program code published) 5,922.

## 3. The hazards that define this adapter

1. **rate.aspx's silent 2,000-row display cap** — the TN 225-row lesson in a new costume. A naive query for Greenville County returns 2,000 rows and quietly omits 13,020 more. The page *prints* the true matched count, which becomes the exhaustiveness oracle: partition county × date-window adaptively until displayed == matched on every leaf. Verified end-to-end: leaf oracles sum to 213,359 == parsed rows == distinct GUIDs (QA B2). Zero-match windows return a bare "No records found" page with no count line (measured; handled). Rows are never closed with `</tr>` — a parser written against well-formed HTML silently reads zero rows (this bit the first build run; the matched==rows assertion caught it).
2. **The GIS layer 0 is a stale snapshot, not a spine.** Its newest activity date is 2026-02-20 (~8 months behind) and it holds only 24,288 of 29,940 permits. Used as enrichment only (fuller 150-char names/addresses vs the table's 30-char caps). Its legacy point geometry mixes AddressPoints, centerline, ZIP-centroid and Google geocodes — deliberately **not adopted** (Kyron's verified-address-level-only rule; the pack wave re-geocodes via Census like every other state).
3. **Permit prefix ≠ county.** Prefix `50` is a statewide mobile-food-unit series (4,842 inspection rows, 2,321 places) whose real operating county lives in the COUNTY field; 20 further rows across 13 ordinary permits have prefix ≠ COUNTY (moved establishments — e.g. a Charleston-permitted restaurant the state files under Berkeley in *both* systems). Rule: county = Steton COUNTY / rate filing county, which agree on 137,087/137,087 rows; place county follows the newest inspection (28 permits were inspected in >1 county over time).
4. **Same-day paired audits.** 726 places have more than one inspection on their newest date (e.g. a graded follow-up paired with a same-day A). "Newest" is defined deterministically: date desc → graded (A/B/C/S) before ungraded (`N/A`) → Steton OBJECTID desc. QA B4 re-derives every place's headline under this rule: 0 mismatches.
5. **Rate-only identity discipline.** 76,272 inspections predate the GIS table. 62,213 attached to a permit by an exact, unique (county, name, street, city) key; 1,815 rows sat under ambiguous keys and 1,303 places are near-misses (same county/name/city as a permit place, different street) — all kept as separate rate-only places under the never-guess rule rather than merged on fuzzy evidence.
6. **Field-level traps**, all counted in `qa_report.json`: Steton `SCORE` and `CountyName` null on 100% of rows; `ADDRESS`/`FACILITY` capped at 30 chars (1,558 address rows at cap); PERMIT_IDs with trailing `\r\n` (22 rows); 1,271 permits with multiple name spellings across rows (case variants + truncations — layer-0/newest/longest precedence resolves); `Active` in mixed case; INSP_DATE carries time-of-day and rejects epoch-ms where-clauses (use `DATE` literals).

## 4. Verification — gate and independent QA

- **Workstream B gate** (`validate_seed.py`) over `OUTPUT/places_sc.json`: G1 blank name 0 · G2 blank street 0 · G3 orphan inspections 0 · G4 placeholder names 0 · G6 duplicate ids 0 · G5 **13 flags, all 13 proven false positives** — each shipped name/street pair is byte-identical (modulo documented whitespace collapsing) to a source pair from layer 0 or rate.aspx (`OUTPUT/gate_adjudication.json`). SC keeps name and street in separate fields end-to-end, so the AL-tuned fused-split heuristic has nothing real to catch here. **Substantive verdict: PASS with adjudication** (the FL precedent).
- **Exclusion**: exactly 1 place withheld — permit `32-204-06297` ("CASEY'S BBQ BARK MOBILE", a mobile unit) with no street address in any source; its 1 inspection is accounted in `OUTPUT/exclusions.json`, not shipped (G2-class; no address invented).
- **Independent QA crosscheck** (`qa_crosscheck.py`, separate HTMLParser-based extraction): **ALL PASS** — fetch oracles (137,087 GIS rows; 213,359 rate rows), GUID uniqueness both sources, union accounting exact to the row (213,359 = 213,358 shipped + 1 excluded), GIS ⊆ rate, every place's newest (date, grade, county) re-derived from raw (0 wrong), zero non-null scores, 46 counties present with per-county sums reconciling, unique ids throughout.

## 5. Coverage notes + refresh strategy for the pack wave

- **Depth asymmetry is the archive's shape, not a gap**: inspections before 2023-10-17 exist only in rate.aspx; the enumeration floor found nothing before 2021-08-21 (windows back to 2015 return the same counts as 2020 starts in test counties). Coverage is complete for what the state publishes in these systems.
- **Refresh (publishable strategy)**: incremental and GUID-keyed. (a) GIS table: re-page with an `INSP_DATE` floor at the last harvest (DATE literals; ~35 min full re-page is also affordable as a periodic audit). (b) rate.aspx: re-run each county's *recent* windows only (e.g. trailing 120 days) — the printed matched count is the completeness oracle per window, and any drift vs the GUID set alarms. (c) Upsert by GUID; re-run the rate-attachment pass for new rate-only rows against the updated permit index. (d) The two systems cross-check each other every refresh (dates/grades/county agreement is currently perfect — treat any break as a source-change alarm, not noise).
- **PDF unlock path**: if any future environment can reach `pubdoc.dhec.sc.gov`, scores + violations enrich by GUID join with zero spine changes — 213k PDF fetches is a big but mechanical wave; sample-verify the PDF score against the published grade bands first (never backfill a score from a band).
- **Geocoding**: 99.84% house-numbered is the best readiness yet (TN 99.41%, GA 99.24%). Layer-0 points stay unadopted; Census batch at pack time, per standing policy. 5,922 rate-only places have no ZIP (rate publishes none) — their Census match rate will run lower; that's expected and honest.
- **Pack shape note**: `places_sc.json` is 107.9 MB uncompressed, dominated by inspection history depth (mean 5.95/place). The TN pack builder's SQLite path will compress this substantially; no truncation of history is proposed.

## 6. Deliverables in `~/kyron-build/harvest/sc/`

- `sc_fetch_gis.py`, `sc_fetch_rate.py` — fetchers (resumable; `fetch_log.tsv` = 254 lines covering all 254 raw files with URL/UTC/status/bytes/SHA-256)
- `sc_parse.py`, `sc_build.py` — parser + normalizer; `g5_adjudicate.py`, `qa_crosscheck.py` — adjudication + independent QA
- `FIELD_MAPPING.md` — full field-level mapping, precedence rules, quirk log
- `OUTPUT/places_sc.json` (35,862 places, 213,358 inspections), `OUTPUT/manifest.json`, `OUTPUT/qa_report.json`, `OUTPUT/qa_crosscheck.json` (ALL PASS), `OUTPUT/exclusions.json` (1), `OUTPUT/gate_adjudication.json` (13/13)
- `raw/` — 84 GIS JSON files + 170 rate.aspx leaf pages

## 7. Next per the revised order: NC → Socrata city wave
