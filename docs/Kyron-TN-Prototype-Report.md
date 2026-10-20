# Kyron — Tennessee Adapter Prototype Report (Workstream C4)

**Date:** October 15, 2026 · **Adapter:** `tn_doh` prototype v0.1, in `~/kyron-build/harvest/tn/`
**Spend:** $0 · no accounts · no app changes · no geocoding run (readiness measured only)

## Headline numbers

| Metric | Value |
|---|---|
| Establishments (Commercial Food permits) | **33,262** |
| Inspections | **122,079** |
| Violations (itemized, with narratives where published) | **343,776** |
| Inspection date range | **2023-09-16 → 2026-10-15** (≈3.1 years — the portal's archive floor) |
| Counties covered | **95 of 95** (**100.0%** of Tennessee's 2020 Census population, 6,910,786) |
| Places with ≥1 inspection | 33,262 (100%) |
| Latest-score profile | mean 97.4 · median 98 · 90–100: 32,582 (98.0%) · 80–89: 497 · 70–79: 100 · <70: 59 · scoreless: 24 |
| Validation gate (Workstream B) | **PASS — G1–G6 all 0 violations**, no adjudication needed |
| Independent QA crosscheck | **ALL PASS** (B1–B9) |
| Geocode-readiness | **99.41%** of street addresses start with a house number; 99.23% carry house number + city + ZIP |

## 1. Source verdict

Tennessee's statewide source is the **Tennessee Department of Health** inspection portal on the **MyHealthDepartment** platform — `inspections.myhealthdepartment.com/tennessee/`. (This is the same vendor platform GA's GNR Health District uses; see §7.) A single statewide system covers all 95 counties: there are no per-county portals to chase. There is **no bulk download**, but the portal is fully machine-readable through its own public surface, with **no login, no API key, and no CAPTCHA on the flows used**:

- `POST /` with `{"task":"searchInspections", …}` — the JSON backend the portal's own landing page calls; enumerates inspection stubs (name, address, permit, score, date, purpose) per county + date range. The landing page's *keyword* search is gated client-side by reCAPTCHA; this adapter never uses keyword search — enumeration uses the ungated county/date filter flow the landing page itself issues.
- `GET /tennessee/inspection/?inspectionID=<GUID>` — the official inspection report as a server-rendered HTML page: score, the 58-item FDA-style checklist, itemized violations with TN rule citations and inspector narratives, and comments. Detail pages refuse cookieless/non-browser agents (403/hang); a primed cookie session with a browser UA answers in ~0.7 s.

Every response was saved raw (**3.9 GB**) with a SHA-256 fetch log (`fetch_log.tsv`, 147,851 rows including probes and reference files): 25,756 search-page fetches and 122,093 detail fetches. Only **Commercial Food** permits were harvested (see §6 for the rest of the portal's permit universe).

## 2. Score model — native, nothing invented

Tennessee scores food-service inspections on a **native 0–100 scale**, stored verbatim (`s`). The portal's report template contains a "Grade:" element but ships it hidden and empty — **Tennessee publishes no letter grade**, so `grade` is `null` everywhere and is never derived from the score (a deliberate divergence from GA, where the state itself publishes bands). Inspection purposes are preserved verbatim: Routine 79,106 · Follow-Up 42,712 · Complaint 239 · Complete 22. **155 inspections (0.13%) publish no score** (stub and detail agree on blank); they ship with `s: null`, never estimated. 24 places have a scoreless *newest* inspection and therefore a null place-level score with full history beneath it.

**Violations are itemized checklist outcomes with narratives where the portal prints them** — 343,776 entries keyed by FDA-style item number, each with the checklist title and status; 235,929 (68.6%) carry the inspector's narrative/corrective-action text and 59,566 (17.3%) a TN rule citation (e.g. `1200-23-01-.03(5)(a)7`). On many inspections — follow-ups especially — the portal lists the out-of-compliance item numbers with **blank** narrative text; those ship with `notes: null`, never paraphrased. 78.7% of inspections have ≥1 violation entry.

History depth is what the portal exposes: a uniform floor of **2023-09-16** (the system's migration cutover; a handful of pre-2023 reports the portal once served to search engines are no longer returned by search). Inspections per place run 1–15, median 3.

## 3. The 225-row window — the hazard that defines this adapter

The search API's paging rules, measured by direct probing (evidence in `work/probe_*`), are unlike anything in FL/GA:

- Page size is **fixed at 25 rows** — the `count` parameter is ignored.
- `start` must be a multiple of 25 and **≤ 200**; beyond that the API answers `{"err":true,"msg":"bad request"}`. One query can therefore expose **at most the newest 225 rows** of its result set, and it fails *silently* if you only look at HTTP status (the error arrives as HTTP 200).

A naive pager would harvest the newest 225 inspections per county and stop — for Davidson that's 1.0% of its 23,492 food inspections, with no error anywhere. The first fetcher version hit exactly this on 6 counties. The shipped fetcher (`tn_fetch.py` v0.3) enumerates by **adaptive date partitioning**: any range whose start=200 page returns full is split in half recursively until every leaf range ends on a short page (provably exhausted); at the 1-day floor it partitions by inspection purpose. A global 8-worker range queue keeps sibling subtrees and small counties from queueing behind the metros. The cost is duplication — 616,896 stub rows fetched for 235,486 unique inspections (all permit types) — deduplicated exactly by inspectionID downstream (`qa_report.json` records zero stub conflicts: no inspectionID ever appeared with two different payloads).

## 4. Verification — the GA crossed-payload lesson, applied and answered

Every one of the **122,091** detail pages was **stub-verified at fetch time** (permit GUID, establishment name, date, and score must agree with the search stub; the page's own PDF link must carry the requested inspectionID), then re-verified in the build, then independently re-verified a third time by QA pass B with separate extraction code. Result: **zero crossed payloads and zero score/date disagreements across the entire harvest** — MyHealthDepartment's detail serving stayed consistent under 8-worker parallel load where GA's Tyler portal did not. Verification stays mandatory for refreshes regardless; it is what makes the next sentence provable.

The only 2 failures (0.0016%) are **hollow legacy records** (Putnam + Sullivan Cos., both dated 2023-09-16, the archive floor): the search index carries full stub data, but the detail pages render the report template with every field empty — records whose detail bodies never migrated. Sequential re-fetch (`tn_mopup.py`, fresh sessions) confirmed the hollowness is in the source. Both inspections are excluded as unverified; their permits ship on their remaining verified inspections (Habibi's Mexican Kitchen Mobile ships 7 of its 8).

## 5. Validation gate + independent QA

`validate_seed.py` over `OUTPUT/places_tn.json` (33,262 places): **G1–G6 = 0, GATE PASS.** No G5 adjudication was needed — TN names and streets are separate source fields end-to-end (the fusion failure mode cannot occur), and no street form tripped the heuristic. Zero scores ship unattached to a named place with an address.

**3 exclusions**, logged with full provenance in `OUTPUT/exclusions.json`: permits whose published names end in a bare `#` — "Subway #" (Fentress), "McD's Famous Hot Dogs MT#" and "Weenie Fever Mobile Cart #" (Davidson) — the portal itself truncated a unit/store number at the `#`, and the names trip G4. Their detail pages carry the same truncated names, so nothing fuller exists in the source to restore. The 10 verified inspections belonging to these permits are withheld with them (accounted explicitly in the crosscheck).

Independent QA pass B (`qa_crosscheck.py`, own extraction code, streams raw): **ALL PASS (B1–B9)** — permit accounting exact (33,265 = 33,262 shipped + 3 excluded), inspection accounting exact (122,091 stubs = 122,079 shipped + 10 on excluded permits + 2 hollow), every place's newest score/date re-derived from raw, zero invented scores, county attribution and unique-id invariants hold, violation total independently recounted to the entry (343,776).

## 6. Coverage notes and TN-specific hazards for the pack wave

- **The portal's permit universe is mixed.** One search returns pools, hotels/motels, tattoo & body-piercing studios, and child-care facilities alongside food (235,486 total inspections vs 122,091 food). Only `Commercial Food*` permits with food-service inspections ship (TN child-care *kitchens* receive food-service inspections under child-care permits; they are excluded by permit type, the FL/GA precedent — one filter change away if Kyron ever wants them). The county filter's 96th entry is an out-of-state body-art pseudo-county, skipped.
- **Refresh economics.** A full re-harvest is ~7 hours of polite fetching, dominated by partition overhead on search and 122k detail GETs. The pack wave should refresh incrementally: re-query only recent date ranges per county (the leaf-range map from this snapshot is in `raw/search_pages/`), and re-verify totals against the snapshot census. Do not re-run the 2015-rooted tree blindly.
- **Session handling is load-bearing.** Detail GETs require the primed-cookie + browser-UA pattern in `tn_fetch_details.py`; a plain HTTP client gets 403s and hangs that look like missing data.
- **Cold-start latency.** The first-ever query took ~193 s; uncached range queries run 10–20 s. Timeouts sized for anything less will manufacture false "empty county" results.
- **Score skew.** TN scores run high (98.0% of newest scores are 90–100; mean 97.4). Presentation should treat the state's meaningful line — below 70 — with care; band-style displays tuned for GA's spread will look flat here. TN publishes no bands, and none were invented.
- **Stub quirks.** `timein` carries a legacy `1899-12-30` date artifact (time-only encoding) — unused by the model. A few border permits publish out-of-state or free-text `state` values (`GA`, `MS`, `Tennessee`, blank); `addr_state` keeps them verbatim, `st` stays `TN`. 51 places publish PO Box streets — list-only candidates for the map, per the honesty rules.
- **Output size.** `places_tn.json` is 138 MB uncompressed, almost all violation text — the pack build should trim per the GA precedent (the checklist-derived titles/statuses are the compressible part).

## 7. The GNR dividend

This adapter doubles as the reference implementation for closing GA's known gap: **Gwinnett, Newton and Rockdale counties publish on this same MyHealthDepartment platform** (`…/gwinnett`). The TN fetcher, parser, and verification discipline transfer directly — only the jurisdiction path and county vocabulary change.

## 8. Deliverables in `~/kyron-build/harvest/tn/`

`tn_fetch.py` (partitioned search fetcher, resumable) · `tn_fetch_details.py` (session-based detail fetcher with stub verification) · `tn_mopup.py` (sequential repair) · `tn_parse.py` (detail-page parser) · `tn_build.py` (normalizer + QA pass A) · `qa_crosscheck.py` (independent QA pass B) · `FIELD_MAPPING.md` · `fetch_log.tsv` (147,851 rows, SHA-256 per response) · `raw/` (3.9 GB: partitioned search pages + 122,091 detail pages + Census reference) · `OUTPUT/` (`places_tn.json` 138 MB, `manifest.json`, `qa_report.json`, `qa_crosscheck.json`, `exclusions.json`).

## 9. Next per the revised order: SC → NC

With TN complete, the adapter order from the GA report stands: **SC next** (SC Food Grades — one statewide tool, GIS-backed, ~22k establishments, 100-point scores with published A/B/C bands), **then NC** (county-administered mini-wave: CDPEHS platform counties plus separate Wake/Mecklenburg/Durham portals). The Socrata city wave (K-07) follows. Every adapter inherits this one's rules: the 225-window lesson generalized — *measure the source's paging contract before trusting it* — plus Workstream B's gate, stub-vs-detail verification on every record, and sequential mop-up for anything that disagrees.
