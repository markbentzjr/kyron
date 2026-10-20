# South Carolina Food Grades (SCDA) → Kyron field mapping — SC adapter prototype v0.1

The program (facilities permitted under SC Regulation 61-25) moved from
SC DHEC to the SC Department of Agriculture on 2024-07-01; the public
endpoints still live on `dhec.sc.gov` domains. Output mirrors
`places_tn.json`'s shape. Every raw response is in `raw/` with its URL,
UTC timestamp, status, bytes, and SHA-256 in `fetch_log.tsv`
(84 GIS files + 170 rate.aspx leaves, 254 log lines, exact match).

## Endpoints used

| Source | URL | Role |
|---|---|---|
| AGOL layer 0 "Restaurants" | `services5.arcgis.com/G4BLIH7rTQoIjCFv/arcgis/rest/services/Restaurants/FeatureServer/0/query` | establishment enrichment: fuller (150-char) name/address for 24,288 permits; legacy point geometry — **not** the place spine (stale, see quirks) |
| AGOL table 4 "Restaurants_Steton" | same service, `/4/query` | inspection spine 2023-10-17 → present: permit, county, grade, type; 137,087 rows |
| Advanced Search | `apps.dhec.sc.gov/Environment/FoodGrades/rate.aspx?fn=&pg=&ft=&aa=&ci=&cy=<CC>&sd=<MM/DD/YYYY>&ed=<MM/DD/YYYY>` | deep inspection archive to 2021-08-21 (213,359 rows) + place name/street/city per inspection; carries the shared `AuditResultGlobalID` in each row's PDF link |
| Inspection PDF | `https://pubdoc.dhec.sc.gov/Inspection/<GUID>.pdf` | per-inspection official report (numeric score + violations live only here); referenced as `du`, **not harvested** (host unreachable over HTTPS from the build sandbox — curl exit 52, python proxy-disconnect, wget timeout; three stacks, all fail) |

Joins are by `AuditResultGlobalID` (GUID). QA verified the GIS table
is an exact subset of the rate archive: 137,087/137,087 GUIDs present
in both, zero GIS-only, and dates and grades agree on 137,087/137,087.

## Place → Kyron fields

| Kyron | Source | Rule |
|---|---|---|
| `id` | PERMIT_ID / hash | `scda_<PERMIT_ID>`; rate-only places `scda_rate-<sha1(county\|name\|street\|city)[:12]>` |
| `fid`, `permit` | Steton PERMIT_ID (whitespace-stripped — 22 rows carry trailing `\r\n`) | null for rate-only places; never invented |
| `n` | layer-0 FACILITY → newest rate name → longest Steton FACILITY | verbatim modulo whitespace collapsing; Steton FACILITY is 30-char-capped, so it is the last resort |
| `a` | layer-0 ADDRESS → newest rate street → longest Steton ADDRESS | same precedence; Steton ADDRESS is 30-char-capped (1,558 rows at cap) |
| `c` | layer-0 CITY → rate city → Steton CITY | verbatim |
| `z` | layer-0 ZIPCODE → Steton ZIPCODE | verbatim (ZIP+4 kept); rate has no ZIP |
| `addr_state` | Steton STATE | verbatim (60 rows say NC/KY/DC/lowercase — border/legacy rows, kept as published) |
| `ct`, `ct_raw`, `search_county`, `county_code` | **operating county** of the newest inspection: Steton COUNTY, else rate query county | NOT the permit prefix — prefix `50` is the statewide mobile-food-unit series (4,842 rows, 2,321 places) whose COUNTY field holds the real county. County vocabulary = the search form's 46 codes |
| `st` | constant | `SC` |
| `jur`, `src` | constant | `SCDA` (program owner since 2024-07-01) |
| `ptype` | PROG_CODE | `206` Retail Food Establishments · `211` Grocery Stores · `204` Mobile Food Units · `208` Institutions (form labels verbatim); null for rate-only places |
| `prog_code` | PROG_CODE | verbatim |
| `s` | — | **null always** (see score model) |
| `grade`, `d`, `du` | newest inspection under the ordering below | verbatim |
| `lat`, `lng` | — | null (prototype rule: no geocoding; layer-0 geometry preserved in raw for the pack wave's decision) |
| `origin` | provenance | `gis` (permit-keyed) / `rate` (rate-only place) |
| `insp` | union by GUID | newest-first under the ordering below |

**"Newest inspection" ordering (documented tie-break):** date desc;
on a date tie, a record with a posted grade (A/B/C/S) outranks an
ungraded one (`N/A`); then Steton OBJECTID desc (the source table's own
insertion order). 726 places have >1 inspection on their newest date —
same-day paired audits are a real feature of this source.

**Rate-only attachment rule:** a rate inspection with no GIS row joins
a permit only when its (county, normalized name, street, city) key
matches exactly one permit; ambiguous keys (1,815 rows) and unmatched
rows form rate-only places. Never fuzzy-merged (62,213 attached;
1,303 rate-only places share (county, name, city) with a permit place
but differ on street — kept separate, counted in QA B10).

## Inspection → `insp[]` entry

| Kyron | Source | Rule |
|---|---|---|
| `id` | GUID | `scda_insp_<guid>` |
| `vid` | AuditResultGlobalID | verbatim, lowercased |
| `d` | rate date, else Steton INSP_DATE (epoch ms → UTC date) | the two agree on all 137,087 joined rows |
| `t` | Steton AuditTypeName, else rate Type | verbatim (AuditTypeName mixes legacy text values `Routine`/`Follow Up`/`COMPL`/`COO` with coded `10_Routine Inspection`, `15_Follow-Up Inspection`, `11_...`, `01_...`; AC_CODE keeps both "Follow Up"/"Follow-Up" spellings upstream) |
| `tcode` | Steton AC_CODE | verbatim; null for rate-only |
| `s` | — | **null always** (see score model) |
| `grade` | Steton POSTED_GRADE (space-padded in source, trimmed), else rate Grade | verbatim: `A` 194,603 · `B` 12,579 · `C` 4,527 · `N/A` 1,632 · `S` 17 (shipped census) |
| `v` | — | `[]` — violations exist only inside the PDF reports |
| `inspector`, `comments` | — | null — not published outside the PDFs |
| `du` | GUID | `https://pubdoc.dhec.sc.gov/Inspection/<GUID>.pdf` (the canonical form both apps link) |
| `origin` | provenance | `gis+rate` / `gis` / `rate` |

## Score model — native, nothing invented

SC publishes **both** a 100-point score and a posted letter grade per
inspection (program literature: A = more than 87 points, B = 78–87,
C = below 78 — context only). But the numeric score is **not
machine-readable anywhere public**: the GIS table's `SCORE` column is
null on all 137,087 rows (counted), rate.aspx shows the grade only,
and scores exist solely inside the per-inspection PDFs. Output
therefore carries `grade` verbatim and `s: null` on every record. The
grade is never converted to a score and a score is never inferred
from a grade. `S` (17 rows, all AC_CODE=COMPL) is carried verbatim
as published.

## Source quirks the normalizer handles (all counted in qa_report.json)

1. rate.aspx caps display at **2,000 rows** and prints the true matched
   count ("N records matched your search") — the enumeration oracle.
   Defeated by county × adaptive date partitioning until displayed ==
   matched on every leaf; sum of leaf oracles == parsed rows (213,359).
2. Zero-match rate windows return a bare "No records found with that
   search criteria." page (282 bytes, no count line).
3. Rate result rows are never closed with `</tr>` (a 616-row page
   contains one `</tr>`) — parsers must split on `<tr valign='top'>`.
4. Layer 0 lags the inspection table ~8 months (its MAX_DATE tops out
   2026-02-20) and covers only 24,288 of 29,940 permit places — never
   a spine, enrichment only. Its `Loc_name` mix (AddressPoints,
   street-centerline, ZIP-centroid, Google) is legacy geocode quality
   from the original load — coordinates deliberately not adopted.
5. Steton `CountyName` is null on all rows; county names come from the
   code vocabulary. Steton `ADDRESS`/`FACILITY` are 30-char fields.
6. Permit prefix ≠ county for the `50-` mobile series and for 20 rows
   across 13 ordinary permits (moved establishments); in every case
   Steton COUNTY == rate.aspx filing county (137,087/137,087), so
   COUNTY is authoritative.
7. 28 permits were inspected in more than one county over time; place
   county follows the newest inspection.
8. INSP_DATE carries time-of-day (entry timestamps); where-clauses
   need `DATE 'YYYY-MM-DD'` literals (epoch-ms comparisons return 400).
9. `Active` mixes `True`/`true` casings; not used as a filter.

## Exclusions (documented, by design)

- **1 place / 1 inspection withheld** (`OUTPUT/exclusions.json`):
  permit `32-204-06297` "CASEY'S BBQ BARK MOBILE" (mobile unit, West
  Columbia) — no street address in any source (G2-class); its grade-A
  inspection of 2025-03-07 is accounted, not shipped.
- The 1 layer-0 permit with no inspections in either inspection
  source is not a place (nothing published to show).
- Everything else ships: gate G1–G4, G6 = 0; the 13 G5 flags are
  proven source-verbatim pairs in `OUTPUT/gate_adjudication.json`.
