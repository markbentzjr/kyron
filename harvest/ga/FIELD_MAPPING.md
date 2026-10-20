# Georgia DPH → Kyron field mapping — GA adapter prototype v0.1

Source: **Georgia Department of Public Health — "State of Georgia" Health
Inspection portal** (Tyler Technologies DHD), `ga.healthinspections.us/stateofgeorgia/`.
The portal is a search UI; its own public JSON backend
(`…/stateofgeorgia/API/index.cfm/…`) is what the adapter reads. No bulk
download exists. Every response is saved raw under `raw/` and logged in
`fetch_log.tsv` (URL, UTC timestamp, HTTP status, bytes, SHA-256).

Score model: **native GA 0–100 numeric score** (Georgia Rule 511-6-1),
with the state's published grade bands **A 90–100 · B 80–89 · C 70–79 ·
U <70**. Both are stored; nothing is converted or invented.

Violations: **narratives** — each violation carries the FDA-style item
code + short title, the Georgia rule citation, the points deducted,
corrected-on-site / repeat flags, and the inspector's full notes text.
(Unclear/none in FL terms: these are NOT category counts.)

## Endpoints used

| Endpoint | Use |
|---|---|
| `API/index.cfm/clientData` | portal configuration (saved raw) |
| `API/index.cfm/filters` | authoritative filter vocabularies: 159 counties, 567 cities, permit types (Food Service / Tourist Accommodation / Swimming Pool) |
| `API/index.cfm/search/<json>/<page>` | facility enumeration, 5/page, newest-inspection-first. Query used per county: `{"county": b64(COUNTY), "permitType": b64("Food Service"), "keyword": ""}` (values base64-encoded, as the portal's own client does) |
| `API/index.cfm/inspectionsData/<facilityId>` | a facility's full inspection history with violations as exposed by the portal (observed window 2023-10-16 → present; per-facility counts 0–29, mode ~5–6 at ~2 inspections/year) |

Facility detail HTML (`facilityData`) and CSV (`downloadCSV`) endpoints
exist in the portal client but were **not used**: `search` +
`inspectionsData` carry every field the CSV/detail views show.

## Facility (search record) → place

| Portal field | Example | Kyron field | Transform |
|---|---|---|---|
| `id` | `ODg0MDY4` | `fid_b64` | verbatim |
| `id` (base64-decoded) | `884068` | `id` = `gadph_884068`, `fid` = 884068 | base64-decode; portal DB id is the stable key |
| `name` | `DUNKIN'` | `n` | verbatim (trimmed) |
| `mapAddress` line 1 | `5265 HWY 20` | `a` (street) | split `mapAddress` on `\r\n` |
| `mapAddress` line 2 | `SUGAR HILL, GA 30518` | `c`, `z` | regex `CITY, GA ZIP(-4)` |
| search county | `GWINNETT`* | `ct`, `ct_raw` | permitting county from the query (authoritative; a facility's city can sit across a county line). *Gwinnett itself returns no results — see exclusions |
| — | — | `st` = `GA`, `jur` = `GA-DPH`, `src` = `GA-DPH` | constants |
| `columns["1"]` | `Phone Number: (404) …` | `phone` | prefix stripped; null if blank |
| `columns["2"]` | `Permit Type: Food Service` | `ptype` | prefix stripped (always "Food Service" in this harvest) |
| `columns["3"]` | `Permit Number: FSP-152-000021` | `permit` | prefix stripped; formats vary by county (e.g. `FS044-884984`, `103-…`) — kept verbatim |
| `columns["4"]` | `Last Inspection Score: 100` | fallback only | used for place-level `s`/`d` **only** when `inspectionsData` returns no rows (flagged `latest_from_stub_only`); never used to fabricate an inspection |
| `columns["5"]` | `Last Inspection Date: 07-01-2026` | fallback only | as above |
| `columns["6"]` | `For More Information Call: (229) 828-3223` | `eh_phone` | county environmental-health office phone — provenance/contact |
| newest inspection | — | `s`, `grade`, `d`, `du` | taken from the newest normalized inspection (score native; grade per state bands; `d` reformatted `M/D/YYYY`; `du` = that inspection's official report URL) |
| — | — | `lat`, `lng` | **null** — no geocoding in this prototype (Census-batch readiness is reported instead) |
| — | — | `origin` = `portal` | single-source adapter |

## Inspection (`inspectionsData` record) → `insp[]`

| Portal field | Kyron field | Transform |
|---|---|---|
| `inspectionId` | `vid`; `id` = `gadph_insp_<inspectionId>` | verbatim |
| `columns["0"]` `Date: MM-DD-YYYY` | `d` (ISO), `draw` (verbatim) | parsed `MM-DD-YYYY` → `YYYY-MM-DD` |
| `columns["1"]` `Inspection Purpose: Routine` | `t` | prefix stripped (Routine / Initial / Follow-up / Complaint etc., verbatim) |
| `columns["2"]` `Score: 97` | `s` | integer, native 0–100; null if the source has no numeric score for that visit |
| (derived) | `grade` | state bands A/B/C/U from `s` (the grade the state itself assigns from the same score) |
| `columns["3"]` `Inspector: Harold Carter` | `inspector` | prefix stripped |
| `printablePath` | `du` | `../../_templates/…` resolved against `https://ga.healthinspections.us/` → the official full report URL |
| `violations` (dict `"0".."n"`) | `v[]` | ordered by numeric key; each parsed below |

## Violation (array of 6 strings) → `v[]` entry

| Portal element | Example | Kyron field |
|---|---|---|
| `[0]` item line | `4-2B - food-contact surfaces: cleaned & sanitized` | `item` = `4-2B`, `title` = remainder (split on first ` - `) |
| `[1]` rule citation | `511-6-1.05(7)(a)1 - equipment, food-contact surfaces,& utensils (pf)` | `rule` verbatim |
| `[2]` | `Points: 4` | `points` = 4 |
| `[3]` | `Corrected during inspection?: Yes` | `corrected` (bool) + `corrected_raw` |
| `[4]` | `Repeat: No` | `repeat` (bool) + `repeat_raw` |
| `[5]` | `Inspector Notes: Observed …` | `notes` verbatim after prefix (full narrative + quoted rule text) |

If a violation array does not have exactly 6 elements, the raw array is
preserved in the entry (`raw`) and the shape is counted in
`qa_report.json` (`violation_shape_census`).

## Source quirks the normalizer handles (all logged in qa_report.json)

- **County prefix match**: the portal's county predicate is a prefix
  match — `county=CLAY` also returns CLAYTON facilities (the only
  prefix pair among GA's 159 counties; verified programmatically).
  Attribution rule: single sighting → that county; prefix-chain
  sightings → the longest name; other multi-county sightings (49
  facilities: metro-Atlanta county-line and mobile cases) → permit-code
  tie-break among the sighting counties, else search county + QA log.
  Permit codes alone never move a facility (health-district offices
  issue cross-county permits — e.g. an Alma, Bacon Co. facility holding
  a Coffee-coded permit stays in Bacon; verified against addresses).
- **Crossed inspection payloads**: under parallel fetch load the
  portal intermittently returned *another facility's* inspection
  payload (239 of 33,516 copies, 0.71%, detected because each copy's
  newest inspection contradicted the facility's own search-stub
  last-score/last-date). All 239 were re-fetched sequentially
  (`ga_mopup.py`); 236 verified consistent afterward. The 3 remaining
  are facilities whose detail endpoint literally returns a
  "No Inspections To Display" placeholder row — they keep stub-level
  latest score/date (`latest_from_stub_only`), no inspection rows are
  fabricated. **Future GA refreshes should fetch inspectionsData
  sequentially or verify every copy against its stub.**
- **Address shapes**: two-line (norm), single-line (`STREET CITY, GA
  ZIP`, e.g. Gordon Co.), and three records with a wrong state in the
  source tail (`NEWNAN, TN 30263`, `FAYETTEVILLE, CA 30214` — GA ZIPs;
  one `PLAINSBORO, NJ 08536`) — parsed generically, state kept verbatim
  in `addr_state`. One facility (Tybee Island) publishes no street at
  all and is excluded (see below).
- **Null/scoreless rows**: inspectionsData can contain JSON nulls
  (3), placeholder rows (3), unparseable-date rows (2), and inspections
  with a blank Score column (8) — nulls/placeholders/bad dates are
  dropped and counted; scoreless inspections are kept with `s: null`.

## Exclusions (documented, by design)

- **Permit types**: only **Food Service** harvested. Tourist
  Accommodation and Swimming Pool permits are not food-service
  establishments (mirrors FL excluding non-food license types).
- **Gwinnett, Newton, Rockdale counties**: the GNR Health District does
  not publish on the state portal (its county searches return zero
  results — the empty page-0 responses are kept in `raw/` as evidence).
  GNR publishes at `inspections.myhealthdepartment.com/gwinnett`
  (MyHealthDepartment) — a separate future adapter. 156/159 counties.
- **Closed/dropped facilities**: the portal search is the live permit
  universe as published; records the portal itself drops are out of
  scope for this snapshot (the fetch log timestamps the snapshot).
- **Gate exclusions** (`OUTPUT/exclusions.json`): 2 records —
  `gadph_3135799` (Fulton Co. permit published under the literal name
  "Establishment"; G4 placeholder) and `gadph_873437` ("Sweet Dreams
  Pavillion", Tybee Island; the source publishes no street address;
  G2-class). Both excluded with full provenance, per the Workstream B
  gate precedent — scores never ship attached to a non-name or an
  address-less record.
