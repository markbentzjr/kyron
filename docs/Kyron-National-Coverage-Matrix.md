# Kyron National Coverage Matrix

Generated from `tools/coverage/coverage_pipeline.py` on 2026-10-25.

**Status vocabulary (distinct, do not conflate):**
- **integrated** — data ships in the app (bundled seed and/or live sync).
- **pack-built** — verified ingestion + validated pack built; publication
  state tracked separately.
- **source-verified** — official endpoint DIRECTLY verified reachable with
  real content; no ingestion yet. Still not user-facing data.
- **official-link-only** — official portal known; NOT integrated and never
  counted as restaurant data.
- **blocked** — a named blocker prevents integration.

**Pack download vocabulary:** `downloadable-verified` (manifest + artifact
fetched and hash-checked) is the ONLY state in which the app may offer a
download. `declared-only` = publication claimed but the artifact could not
be verified (e.g. host 404). `staged-local` = built locally, not published.

Each of the 50 states is assigned to EXACTLY ONE primary tier below
(first matching rule: integrated → pack downloadable → pack built/declared
→ source verified → link-only/blocked); D.C. is reported as its own
federal-district row and is not folded into the 50-state tallies.

## Alabama (AL) — `us-al`

**Primary tier:** Integrated (live in app) · **Result model:** SCORE_100_HIGH · **Pack:** bundled (bundled)

Shipped bundled in the APK; three live sync sources.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| al-jcdh | Jefferson County Department of Health | Jefferson County | live-sync | full | full-history | integrated | 2026-10-13 | Scores plus full violation detail and per-place inspection history. |
| al-adph | Alabama Department of Public Health | Statewide (65 counties) | html | none | latest-only | integrated | 2026-10-13 | ASP.NET statewide search; latest score + inspection date only. Tallapoosa County upstream HTTP 500 (README caveat). |
| al-mchd | Mobile County Health Department | Mobile County | html | none | some-history | integrated | 2026-10-13 | Up to 4 dated inspections per establishment; no violation detail. |

## Florida (FL) — `us-fl`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** DISPOSITION · **Pack:** published (declared-only) · **Pack host:** unreachable-404 (checked 2026-10-22)

Pack built and registered in-app; the PUBLICATION is declared but the pack host returned HTTP 404 on 2026-10-22 — the download is NOT verified available until it is republished (declared-only).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| fl-dbpr | Florida Department of Business & Professional Regulation (DBPR), Hotels & Restaurants | Statewide | bulk-csv | full | latest-only | pack-built | 2026-10-13 | No numeric score: outcomes are dispositions (met standards, warning, closure…). District CSV extracts + inspection detail pages. Pack built and app-verified (70,051 places). |

## Georgia (GA) — `us-ga`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** SCORE_100_HIGH · **Pack:** published (declared-only) · **Pack host:** unreachable-404 (checked 2026-10-22)

Pack verified end-to-end in the rig and registered in-app; the publication is declared but the host returned HTTP 404 on 2026-10-22 (declared-only, not verified downloadable).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ga-dph | Georgia Department of Public Health | Statewide (excl. Gwinnett/Newton/Rockdale) | html | full | some-history | pack-built | 2026-10-13 | 100-point scale with A/B/C/U grades; full inspector notes. |

## Tennessee (TN) — `us-tn`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** SCORE_100_HIGH · **Pack:** built (staged-local)

Ingestion verified (138 MB place dataset, QA crosscheck pass); pack staged locally — blocked on publishing infrastructure.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| tn-tdh | Tennessee Department of Health | Statewide | html | full | some-history | pack-built | 2026-10-13 | Statewide scores with per-violation observation text (HealthSpace platform). Place dataset built (122,091 detail pages); pack staged, not yet published. |

## South Carolina (SC) — `us-sc`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** SCORE_100_HIGH · **Pack:** built (staged-local)

Ingestion verified (35,862 places, QA all-pass); pack staged locally — blocked on publishing infrastructure.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| sc-dhec | South Carolina DHEC — Food Grades | Statewide | html | full | some-history | pack-built | 2026-10-13 | Points-based (A >87); full inspection report as PDF. 35,862 places harvested; pack staged, not yet published. |

## North Carolina (NC) — `us-nc`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

Statewide web front-end over county inspections.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nc-dhhs | North Carolina DHHS — Environmental Health Inspections | Statewide (county-run inspections, statewide front-end) | html | full | latest-only | source-verified | 2026-10-13 | 100-pt scores with A/B/C grade cards; violations as written by the inspector. Harvest adapters exist (harvest/nc) but no pack yet. |

## Mississippi (MS) — `us-ms`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** LETTER_GRADE · **Pack:** none (none)

Letter grades only — the registry's Kyron model is LETTER_GRADE; numeric Alabama bands do NOT apply.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ms-msdh | Mississippi State Department of Health | Statewide | html | partial | full-history | source-verified | 2026-10-13 | Letter grades A/B/C only (no numeric score); full inspection history per facility (apps.msdh.ms.gov/food/FacilityRecord.aspx). |

## Virginia (VA) — `us-va`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Violations-only jurisdiction — alerts are new-result notices, never threshold violations.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| va-vdh | Virginia Department of Health | Statewide (health districts) | html | full | some-history | source-verified | 2026-10-13 | Violations with critical/non-critical flags and corrective actions; no score or grade of any kind. |

## Arkansas (AR) — `us-ar`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

In/out-of-compliance model.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ar-adh | Arkansas Department of Health | Statewide | html | full | some-history | source-verified | 2026-10-13 | In/out-of-compliance model with per-report observation detail. |

## Louisiana (LA) — `us-la`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Violation-based; icon ratings are jurisdiction presentation, not a numeric Kyron score.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| la-ldh | Louisiana Department of Health (EatSafe) | Statewide | html | full | some-history | source-verified | 2026-10-13 | Updated daily; violations (critical vs non-critical) + corrective actions; historically pelican-icon ratings rather than numbers. |

## Pennsylvania (PA) — `us-pa`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Pass/fail with published violation reports.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| pa-pda | Pennsylvania Department of Agriculture | Statewide (excl. some city/county programs) | html | full | some-history | source-verified | 2026-10-13 | Violations + inspector comments in full report view. |

## New York (NY) — `us-ny`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** PENALTY_LOW · **Pack:** built (staged-local) · **Artifact verified:** 2026-10-25

NYC pack built + validated locally (penalty points + letter grade); upstate is county-fragmented.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ny-nyc-dohmh | NYC Department of Health & Mental Hygiene | New York City | api | full | full-history | pack-built | 2026-10-25 | Socrata API (resource/43nn-pn8j.json): one row per violation citation; score = violation points (LOWER is better; A=0-13, B=14-27, C=28+), letter grade carried as result text. Pack BUILT locally 2026-10-25 (31,368 places / 92,713 inspections / 287,206 violations). Attribution: NYC DOHMH via NYC Open Data. |
| ny-statewide | Rest of New York State (county health departments) | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No statewide public portal verified; county-level publication. |

## Illinois (IL) — `us-il`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** PASS_FAIL · **Pack:** built (staged-local) · **Artifact verified:** 2026-10-25

Chicago pack built + validated locally (pass/fail); statewide coverage is county-by-county.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| il-chicago | Chicago Department of Public Health | Chicago | api | full | some-history | pack-built | 2026-10-25 | Socrata (SODA) API; pass / pass-with-conditions / fail; violations field with codes and inspector comments. Pack BUILT locally 2026-10-25 over a 2-year window (14,823 places / 36,070 inspections). Attribution: City of Chicago Data Portal. |
| il-statewide | Rest of Illinois (local health departments) | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No statewide results portal verified. |

## California (CA) — `us-ca`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

County-fragmented by design (CalCode). LA County + SF datasets cover a big population share.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ca-lacounty | Los Angeles County Department of Public Health | Los Angeles County (excl. Pasadena/Long Beach/Vernon) | api | full | full-history | source-verified | 2026-10-13 | Inspections + separate violations dataset (8jyd-4pv9); numeric score + letter grade. |
| ca-sf | San Francisco Department of Public Health | San Francisco | api | full | some-history | source-verified | 2026-10-13 | Numeric 0-100 score plus dedicated violations dataset (f29f-c3np). |
| ca-statewide | California Department of Public Health (Retail Food Program) | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | CalCode makes 60+ county EHDs the publishers; no statewide portal, bulk download, or API (AFDO index lists counties only; CDPH page fetch-blocked on 2026-10-22). |

## Massachusetts (MA) — `us-ma`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Boston has a strong open dataset; the rest is municipal.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ma-boston | City of Boston Inspectional Services | Boston | bulk-csv | full | full-history | source-verified | 2026-10-22 | Analyze Boston CKAN, daily refresh, per-violation rows with inspector comments (fetched 200 with data 2026-10-22). |
| ma-dph | Massachusetts DPH Food Protection Program | State-inspected facilities | html | unverified | unverified | blocked | 2026-10-22 | ~350 municipal health boards are the real publishers. — BLOCKER: Cognos JS report serves an empty body to non-browser fetches; municipal boards inpublish independently. |

## Washington (WA) — `us-wa`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** PENALTY_LOW · **Pack:** built (staged-local) · **Artifact verified:** 2026-10-25

King County pack built + validated locally (penalty points + rating); statewide is fragmented.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| wa-kingcounty | Public Health — Seattle & King County | King County (incl. Seattle) | api | full | some-history | pack-built | 2026-10-25 | Socrata r878-4sxa (old gkhn-e8mn now requires login): one row per violation, red (critical)/blue points; score = inspection points (LOWER is better); result + Excellent/Good/Okay/Needs to Improve rating as result text. No coordinates published. Pack BUILT locally 2026-10-25 (12,167 places / 32,971 inspections, 2-year window). |
| wa-statewide | Washington State DOH + county health departments | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No statewide results portal verified. |

## Oregon (OR) — `us-or`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

Statewide, scored, full history — top integration candidate.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| or-oha | Oregon Health Authority (statewide, county-run inspections) | Statewide | html | full | full-history | source-verified | 2026-10-22 | Restaurant 100-pt scale: priority items deduct 5, priority-foundation 3; < 70 fails. One of the cleanest candidate integrations in the country. |

## Wisconsin (WI) — `us-wi`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Dual-vendor state (DATCP + HealthSpace local agencies).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| wi-datcp | Wisconsin DATCP (state-inspected facilities) | Statewide (state-inspected) | html | full | some-history | source-verified | 2026-10-22 | DATCP publishes directly (fetched 200 OK); ~130 agency-managed local health departments publish separately in HealthSpace. |

## Oklahoma (OK) — `us-ok`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Statewide form-based search on a legacy ASP.NET site.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ok-phin | Oklahoma State Department of Health — Consumer Protection | Statewide (77 counties) | html | unverified | unverified | source-verified | 2026-10-22 | Legacy ASP.NET form (fetched 200 OK), county+name search; report records are form-post downloads. Tulsa and OKC-County also publish their own. |

## Vermont (VT) — `us-vt`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

Single-state agency; numeric score + violations; same platform family as SD/WY/PA.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| vt-vdh | Vermont Department of Health — Food & Lodging Program | Statewide | html | full | full-history | source-verified | 2026-10-22 | 'Food Safety 5.5' platform; numeric inspection score (44-item checklist) + critical flags since May 2016. ASP.NET POST needed. |

## South Dakota (SD) — `us-sd`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Statewide report platform; Sioux Falls separate.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| sd-doh | South Dakota Department of Health | Statewide (excl. Sioux Falls) | html | full | some-history | source-verified | 2026-10-22 | 'Food Safety 5.5' platform (fetched 200 OK); each inspection is a report/PDF; Sioux Falls inspects separately. |

## Wyoming (WY) — `us-wy`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Statewide compliance platform minus a handful of local jurisdictions.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| wy-wda | Wyoming Department of Agriculture — Consumer Health Services | Statewide (excl. 5 local jurisdictions) | html | full | some-history | source-verified | 2026-10-22 | 'Food Safety 5.5' platform (fetched 200 OK); in/out-of-compliance with violation explanation; excludes Laramie, Natrona, Sublette, Sweetwater, Teton + City of Laramie. |

## Rhode Island (RI) — `us-ri`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Statewide; reachable but JS-postback heavy.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ri-ridoh | Rhode Island Department of Health — Center for Food Protection | Statewide | html | full | some-history | source-verified | 2026-10-22 | Official portal (linked from health.ri.gov/food-safety, fetched 200); Tyler-hosted JS/postback app — parsing needs the postback, not plain links. |

## New Jersey (NJ) — `us-nj`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** DISPOSITION · **Pack:** none (none)

Fragmented into local agencies; dispositions are the common currency.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nj-burlington | Burlington County Health Department (HDGov pattern) | Burlington County | html | partial | some-history | source-verified | 2026-10-22 | Satisfactory / Conditionally Satisfactory / Unsatisfactory dispositions; XLSX export; the HDGov 'Views/HealthInspections' app recurs across NJ counties (Camden, Cape May, Gloucester, Ocean). |
| nj-statewide | New Jersey Department of Health (local agencies) | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | ~110 delegated local agencies publish in their own formats; no statewide public database. |

## Nevada (NV) — `us-nv`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** DISPOSITION · **Pack:** none (none)

SNHD's nightly CSV is best-in-class bulk data.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nv-snhd | Southern Nevada Health District (Clark County / Las Vegas) | Southern Nevada | bulk-csv | full | full-history | source-verified | 2026-10-22 | Nightly developer CSV download (restaurants.zip + SQL schema; both pages fetched 200) — ~5-day posting lag. Also demerit-style detail; no portal 0-100 number. |

## Texas (TX) — `us-tx`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

Big-city open-data APIs (Austin verified); no statewide results search.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| tx-austin | Austin Public Health | Austin | api | partial | full-history | source-verified | 2026-10-22 | Socrata API (fetched 200 JSON): numeric 0-100 with color bands. |
| tx-dshs | Texas DSHS Retail Food Safety Unit | Where no local program exists | official-link-only | unverified | unverified | official-link-only | 2026-10-22 | DSHS (fetched 200) publishes no public results search — only an ArcGIS jurisdiction map and open-records requests. |

## Utah (UT) — `us-ut`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

13 local districts; Salt Lake County portal verified.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ut-slco | Salt Lake County Health Department | Salt Lake County | html | full | some-history | source-verified | 2026-10-22 | Live ASP.NET search incl. closures (fetched 200 OK). |
| ut-statewide | Utah's 13 local health districts | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No statewide public search; Utah, Davis, Weber, Cache counties are separate integrations. |

## Michigan (MI) — `us-mi`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

State portal covers groceries only; restaurants are local agencies.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| mi-mdard | Michigan Dept. of Agriculture & Rural Development — MiSafe | Grocery/processor facilities ONLY (NOT restaurants) | html | full | full-history | blocked | 2026-10-22 | Do not count MiSafe as restaurant data; Kent County et al. are the real restaurant publishers. — BLOCKER: MiSafe (fetched 200 OK) explicitly EXCLUDES restaurants — those are inspected by ~45 local health agencies with their own portals. |

## Maryland (MD) — `us-md`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

County APIs verified (Montgomery); statewide portal at present unreachable.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| md-montgomery | Montgomery County | Montgomery County | api | partial | some-history | source-verified | 2026-10-22 | Socrata (fetched 200 with data): per-item In/Out of Compliance rows. |
| md-statewide | Maryland DHMH Office of Food Protection (24 LHDs) | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | Statewide search vsi.maryland.gov was unreachable on 2026-10-22 (3 attempts); many counties publish by records request. |

## Missouri (MO) — `us-mo`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** DISPOSITION · **Pack:** none (none)

City-level sources (St. Louis verified); state publishes nothing centrally.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| mo-stl | City of St. Louis Department of Health | City of St. Louis | html | partial | some-history | source-verified | 2026-10-22 | Lookup runs on HealthSpace (fetched 200). Kansas City (Socrata, dataset unconfirmed), Springfield-Greene, Joplin also publish. |
| mo-statewide | Missouri DHSS | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No statewide public restaurant-inspection portal. |

## Minnesota (MN) — `us-mn`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

State page verified absent of portal; Minneapolis open data recommended next.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| mn-mdh | Minnesota Department of Health (FPLS) | Statewide-program page only | official-link-only | none | unverified | official-link-only | 2026-10-22 | Page fetched 200 but confirms: no online inspection portal; reports by request. Minneapolis open-data lookup is the big-population coverage (dashboard fetch failed 2026-10-22). |

## Montana (MT) — `us-mt`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

State-endorsed vendor dashboard plus ~26 independent counties.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| mt-dphhs | Montana DPHHS Environmental Health & Food Safety | ~30 counties | html | partial | some-history | source-verified | 2026-10-22 | DPHHS page (fetched 200) links the state-endorsed myhealthdepartment.com/montana dashboard; ~26 other counties run their own. |

## Nebraska (NE) — `us-ne`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

JS-only state app; can't be confirmed without a browser session.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ne-nda | Nebraska Department of Agriculture | Statewide | html | unverified | unverified | blocked | 2026-10-22 | Lincoln-Lancaster and Douglas/Omaha (biggest populations) publish separately. — BLOCKER: Portal fetched 200 but renders a JS-only search app; result model and history could not be confirmed by plain HTTP GET. |

## New Hampshire (NH) — `us-nh`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

No public online database; records by email request.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nh-dhhs | NH DHHS Food Protection Section | Statewide | official-link-only | none | latest-only | blocked | 2026-10-22 | Do not present NH as covered; official email-request path only. — BLOCKER: DHHS page 403s automated fetches and confirms there is NO online inspection database — records by email request; a few cities (Keene) publish their own lookups. |

## New Mexico (NM) — `us-nm`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Records-on-request at state level; city of Albuquerque has a lookup.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nm-nmed | New Mexico Environment Department — Food Program | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | NMED states inspection records are public but publishes no searchable portal (AFDO-cited; not fetched this session) — records custodian path; Albuquerque has its own lookup. |

## North Dakota (ND) — `us-nd`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Unverified in this pass; platform-family membership suspected only.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| nd-doh | North Dakota Department of Health & Human Services (local food programs) | Statewide | official-link-only | unverified | unverified | official-link-only | — | Not fetch-verified in the LF-N research pass; ND is expected to ride the 'Food Safety 5.5' platform family alongside SD/VT/WY/IL/IA but that is UNCONFIRMED — verify before integration work. |

## West Virginia (WV) — `us-wv`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

~50 separate county publishers; no statewide portal.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| wv-oehs | WV Bureau for Public Health — Office of Environmental Health Services | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | No consolidated portal; ~50 county/subcounty departments publish in their own formats (AFDO lists no state entry) — highest integration burden in the batch. |

## Arizona (AZ) — `us-az`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** LETTER_GRADE · **Pack:** none (none)

County-run; Maricopa letter grades verified; no statewide search.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| az-maricopa | Maricopa County Environmental Health | Maricopa County (~4.6M, incl. Phoenix) | html | full | some-history | source-verified | 2026-10-22 | Fetched 200 OK; letter grade cards ('A' for Food Safety) + full reports — NOT a numeric-score jurisdiction. |
| az-pima | Pima County Health | Pima County (Tucson) | html | unverified | unverified | source-verified | 2026-10-22 | Fetched 200 OK; JS portal app. |
| az-rest | Arizona ADHS + smaller counties | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | ADHS (fetched 200) has NO statewide results search — records requests only; ~15 county/city departments publish separately (Coconino, Yavapai, …). |

## Colorado (CO) — `us-co`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Shared state platform + Denver's own program; risk-index points, no 0–100 score.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| co-cdphe | Colorado CDPHE + delegated counties (shared platform) | Statewide (some counties opt out) | html | full | some-history | source-verified | 2026-10-22 | Fetched 200 OK (linked from CDPHE page; CDPHE plain fetch is 403). Results are Pass / Re-Inspection Required / Closed with risk-index points (Pass 0–49; Re-inspect 50–109; Closed 110+) — NOT a 0–100 score or letter grade. |
| co-denver | Denver Department of Public Health & Environment | City & County of Denver | html | full | some-history | source-verified | 2026-10-22 | Fetched 200 OK. Inspections after 9/6/24 moved to Accela (aca-prod.accela.com/DENVER); Denver self-inspects. |

## Alaska (AK) — `us-ak`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

State portal verified (safefood platform); Anchorage excluded.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ak-dec | Alaska DEC — Food Safety & Sanitation | Statewide (excl. Anchorage) | html | full | some-history | source-verified | 2026-10-22 | DEC-run ASP.NET portal fetched 200 OK; FDA Food Code citations, no score/grade. dec.alaska.gov program page 403s automated fetches. |

## Hawaii (HI) — `us-hi`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** PASS_FAIL · **Pack:** none (none)

Statewide placard system; no numeric score.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| hi-doh | Hawaii DOH — Food Safety Branch (Sanitation) | Statewide (all islands) | html | full | some-history | source-verified | 2026-10-22 | DOH-branded portal fetched 200 (linked from health.hawaii.gov/san, 200). Results are condition placards: green pass / yellow conditional / red closure, with cited violations in reports — there is NO numeric score; Alabama bands do NOT apply. |

## Connecticut (CT) — `us-ct`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

No statewide portal (verified negative finding); town-by-town.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ct-dph | Connecticut DPH Food Protection Program | Statewide program page | official-link-only | none | unverified | official-link-only | 2026-10-22 | Page fetched 200 contains only the blank inspection form — NO statewide results portal; consumers go town-by-town. ~60 local departments; some towns (e.g. Farmington Valley HD) publish 0–100 scores higher-is-better. |

## Delaware (DE) — `us-de`

**Primary tier:** Pack built/declared — NOT verified downloadable · **Result model:** VIOLATIONS_ONLY · **Pack:** built (staged-local) · **Artifact verified:** 2026-10-22

Pack built + validated locally (datasetVersion 2026-10-23.1; window 2024-10-14..2026-12-03); staged — blocked on publishing infrastructure. No scores exist in this data (violations-only model).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| de-dph | Delaware Division of Public Health — Office of Food Protection | Statewide | api | full | some-history | pack-built | 2026-10-22 | Socrata open-data API (resource 384s-wygj): one row per violation, geocoded, ~2-year rolling window. Pack BUILT and validated locally (3,731 places / 9,202 inspections / 32,570 violations; sha256 536e54a6…92835); staged, NOT published. Violations-ONLY extract: zero-violation establishments are absent from the source dataset. |

## Idaho (ID) — `us-id`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

7 independent district portals; state page verified without results.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| id-dhw | Idaho DHW + 7 Public Health Districts | Statewide via 7 districts | official-link-only | none | unverified | official-link-only | 2026-10-22 | State page (fetched 200) has no results tool; the 7 independent district portals are the publishers — pages verified: phd5.idaho.gov/inspections (200), eiph.id.gov program page (200), cdh.idaho.gov program page (fetch 200, portal 403 Cloudflare); the underlying search apps are cited, not fetch-verified. ~7 integrations. |

## Iowa (IA) — `us-ia`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Statewide agency; two live portals in an Oct 2026 transition.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ia-dial | Iowa Department of Inspections, Appeals & Licensing (DIAL) | Statewide | html | full | some-history | source-verified | 2026-10-22 | BOTH portals fetched 200: legacy USFS search (reports through Oct 14, 2026) and the going-forward SAFHER SPA (safher-portal.dial.iowa.gov/safher-portal). MID-TRANSITION Oct 2026 — archive coverage must be confirmed before relying on history. |

## Kansas (KS) — `us-ks`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Statewide nightly-updated public record search (new portal).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ks-kda | Kansas Department of Agriculture — Food Safety & Lodging | Statewide | html | full | full-history | source-verified | 2026-10-22 | New portal fetched 200 (launched ~Jul 2026): 'updated nightly, free & no sign-in'; In/Out-of-compliance + cited violations, date-range filters. Old foodsafety.kda.ks.gov retired July 2026 (fetched 500). |

## Maine (ME) — `us-me`

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Statewide search app; pass/fail via C/NC counts.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| me-hip | Maine DHHS / Maine CDC — Health Inspection Program | Statewide (incl. MUN municipal licenses) | html | full | some-history | source-verified | 2026-10-22 | Search app fetched 200 (linked from maine.gov HIP page, 200): name/city/county/ZIP/type/date-range. Pass/fail via critical (C) and non-critical (NC) counts (failed >3 C or >10 NC); ~3-year history. |

## Kentucky (KY) — `us-ky`

**Primary tier:** Official-link-only / blocked · **Result model:** SCORE_100_HIGH · **Pack:** none (none)

County-fragmented (registry doc research).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| ky-fragmented | Kentucky local health departments | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | Fragmented (verified in US registry doc 2026-10-13): Louisville, Lexington, Northern Kentucky, Jessamine and others publish their own scores/violations on different sites. |

## Indiana (IN) — `us-in`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

County-fragmented (registry doc research).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| in-fragmented | Indiana local health departments | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | Fragmented (registry doc 2026-10-13): counties use varied platforms; Marion County/Indianapolis publishes via hhcwebfood.hhcorp.org. |

## Ohio (OH) — `us-oh`

**Primary tier:** Official-link-only / blocked · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Local-district publication (registry doc research).

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| oh-odh | Ohio Department of Health + local health districts | Statewide (not verified) | official-link-only | unverified | unverified | official-link-only | — | Fragmented (registry doc 2026-10-13): a state database exists but public access is via ~local health districts, many on HealthSpace; many jurisdictions publish violations without an overall score. |

## District of Columbia (DC) — `us-dc`  (*federal district, not a state*)

**Primary tier:** Source verified (no ingestion yet) · **Result model:** VIOLATIONS_ONLY · **Pack:** none (none)

Registered as a jurisdiction, explicitly NOT one of the 50 states.

| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |
|---|---|---|---|---|---|---|---|---|
| dc-dchealth | DC Health — Food Safety & Hygiene Inspection Services Division | District of Columbia (all inspections state-run) | html | full | full-history | source-verified | 2026-10-22 | DC-run healthinspections.us instance fetched 200 OK: name/inspection-type search, FDA Food Code citation-level detail, history stated to cover 2007→current. Help page dchealth.dc.gov/service/understanding-food-establishment-inspections confirmed 200. |

## Tier tally (50 states, each assigned once)

- Integrated (live in app): **1**
- Pack built/declared — NOT verified downloadable: **8**
- Source verified (no ingestion yet): **29**
- Official-link-only / blocked: **12**
- **States total: 50** (must equal 50)

**Separate federal-district row:** District of Columbia (primary tier: Source verified (no ingestion yet)) — not counted above.
