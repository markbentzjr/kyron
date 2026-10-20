# FL-DBPR Adapter — Field Mapping (prototype v0.1, 2026-10-13)

Source: Florida DBPR Division of Hotels & Restaurants public-records extracts
(https://www2.myfloridalicense.com/hotels-restaurants/public-records/).
Canonical model per Kyron-Gameplan-Draft §5.3; output shape follows the Alabama
seed's compact-key philosophy plus explicit `st`/`jur` fields.

## Files consumed

| Source file (per district N=1..7) | Content |
|---|---|
| `hrfood{N}.csv` | Licensee/establishment extract, 35 columns, header row present |
| `{N}fdinspi.csv` | Inspection extract, current fiscal year, 82 columns, header row present |

## Place (from `hrfood{N}.csv`)

| Source column | Canonical field | Notes |
|---|---|---|
| License Number | `lic`, `id` = `fldbpr_<License Number>` | Dedupe key. Unique per license type + location; embeds rank prefix (SEA/MFD/…). |
| Business Name | `n` | DBA name at location |
| Licensee Name | `licensee_name` | Legal owner; can differ from DBA |
| Location Street Address + Line 2 + Line 3 | `a` | Joined with single spaces, blanks skipped |
| Location City | `c` | |
| Location Zip Code | `z` | As published (5-digit, ZIP+4, or 9-digit unhyphenated) |
| Location County | `ct` | County name as published (e.g. "Dade") |
| — (constant) | `st` = `FL`, `jur` = `FL-DBPR`, `src` = `FL-DBPR` | |
| District | `dist` | DBPR district 1–7 (column value kept; 3 anomalous rows statewide) |
| License Type Code | `ltype` | 2010 permanent, 2013 caterer, 2014 mobile, 2015 vending, 2016 …, 2012 … |
| Rank Code | `rank` | SEAT / MFDV / NOST / CATR / VEND / HTDG / TEMP / PARK / … |
| Primary Status Code | `status_p` | Native code preserved verbatim (20 = 92.8% of rows; 45, 46 also occur). Code meanings per DBPR "Understanding DBPR Codes"; not reinterpreted here. |
| Secondary Status Code | `status_s` | Native code preserved |
| Base Risk Level | `risk` | e.g. "Risk Level 2" |
| Secondary Risk Level | `risk2` | Usually blank |
| Number of Seats or Rental Units | `seats` | Integer when parseable |
| Secondary Phone Number | `phone` | Location phone |
| License Expiry Date | `expiry` | Normalized to ISO `YYYY-MM-DD` |
| Last Inspection Date | `lic_last_insp` | ISO; from licensee snapshot (can lag the inspection extract by a day) |
| — (derived) | `d`, `disp` | Latest inspection date (Alabama-style M/D/YYYY) + native disposition, from the inspection list when present, else `lic_last_insp` with `disp` = null |
| — | `lat`, `lng` | Always null in this prototype — **no geocoding performed** |
| — (derived) | `du` | DBPR license-lookup URL pattern |

Unmapped licensee columns (kept in raw only): Board Code (constant 200), Modifier Code,
Mailing Name + full Mailing Address block + Mailing City/State/Zip + Mailing County Code
(owner mailing address — deliberately excluded from the place record: it is the owner's
postal address, often a home/corporate address, not the establishment location),
Primary Phone Number (mailing phone; location phone is mapped), Filler,
Location State (constant FL), Location County Code (numeric twin of `ct`),
Region (sub-district routing code), Application fields (not present in these extracts).

## Inspection (from `{N}fdinspi.csv`) → `insp[]` on the place

| Source column | Canonical field | Notes |
|---|---|---|
| Inspection Visit ID | `vid`, `id` = `fldbpr_insp_<vid>` | Unique per visit; the deterministic inspection key |
| Inspection Number | `insp_no` | Groups all visits (initial + callbacks) of one inspection event |
| Visit Number | `visit` | 1 = initial, >1 = callback |
| Inspection Date | `d` (ISO) + `draw` (verbatim) | |
| Inspection Type | `t` | Native string: "Routine - Food", "Complaint Full", "Food-Licensing Inspection", "Complaint Partial", … |
| Inspection Class | `class` | "Food" for 100% of rows in these files |
| Inspection Disposition | `disp` | **The native Florida result** — preserved verbatim. Florida publishes no numeric score; `raw_score_text`/`numeric_score` are null by design and no score is ever synthesized. |
| Number of Total Violations | `tot` | Native total (per DBPR docs, excludes "reporting" categories 45–49) |
| Number of High Priority Violations | `hp` | Native per-inspection tier total |
| Number of Intermediate Violations | `im` | Native |
| Number of Basic Violations | `ba` | Native |
| PDA Status | `pda` | Y/N — inspection captured on mobile device |
| Violation 01 … Violation 58 | `v[]` entries `{code, cnt, r}` | **Counts per violation category**, not narrative findings. `r` = the category's published short title (post-2013 FDA Food Code list, extracted from the DBPR public-records page). The extracts do NOT contain per-violation inspector observations — those exist only on DBPR's per-inspection web detail pages. |
| License Number | join key | Numeric only in this file (no rank prefix) — join is (digits, License Type Code); see report §Join |
| License Type Code | join key + place fallback | |
| Business (DBA) Name / Location Address / City / Zip / County Name | place stub fields | Used only for establishments absent from the licensee extracts (`origin = "inspections_only"`, id `fldbpr_insp_only_<digits>`) |
| District, County Number | — | District duplicated by file; county number is the numeric twin of County Name |

Unmapped inspection columns: Number of Critical Violations, Number of Noncritical
Violations (pre-2013 fields, blank in 100% of current rows), License ID (owner-level
ID — candidate future alias key, unused in v0.1).

## Violation category titles (post-2013, as published by DBPR)

01 Approved source · 02 Original container: properly labeled, date marking, consumer
advisory · 03 Time and Temperature Control – PH/TCS foods · 04 Facilities to maintain
PH/TCS at the proper temperature · 05 Food and food equipment thermometers provided
and accurate · 06 PH/TCS foods properly thawed · 07 Unwrapped or PH/TCS food not
re-served · 08 Food protection, cross-contamination · 09 Bare hand contact with RTE
food; AOP · 10 In-use food dispensing utensils properly stored · 11 Employee health
knowledge; ill/symptomatic employee present · 12 Hands washed and clean, good
hygienic practices · 13 Clean clothes; hair restraints; jewelry; fingernails ·
14 Food-contact and nonfood-contact surfaces designed/constructed/maintained ·
15 (no longer used) · 16 Dishwashing facilities; chemical test kit(s); gauges ·
17–20, 26, 30, 34, 37, 39, 44, 56–58 (no longer used) · 21 Wiping cloths; clean and
soiled linens; laundry · 22 Food-contact surfaces clean and sanitized · 23 Non-food
contact surfaces clean · 24 Storage/handling of clean equipment, utensils; air
drying · 25 Single-service and single-use items · 27 Water source safe, hot (100°F)
and cold under pressure · 28 Sewage and wastewater disposed properly · 29 Plumbing
installed and maintained; mop sink; water filters; backflow prevention ·
31 Hand wash sinks, supplies and sign · 32 Bathrooms · 33 Garbage and refuse;
premises maintained · 35 No presence/breeding of insects/rodents/pests; no live
animals · 36 Floors, walls, ceilings and attached equipment; venting · 38 Lighting
provided as required; fixtures shielded · 40 Employee personal belongings ·
41 Chemicals/toxic substances · 42 Cleaning and maintenance equipment ·
43 Complete separation from living/sleeping area; kitchen restricted ·
45 Fire extinguishing equipment (reporting only) · 46 Exits not blocked or locked
(reporting only) · 47 Electrical wiring/outlets in good repair (reporting only) ·
48 Gas appliances; boiler certificate (reporting only) · 49 Flammable/combustible
materials (reporting only) · 50 Current license properly displayed ·
51 Other conditions sanitary and safe operation · 52 Misrepresentation; misbranding ·
53 Food management certification valid / employee training verification ·
54 Florida Clean Indoor Air Act · 55 Automatic Gratuity Notice

Full machine-readable table: `work/violation_categories.json` (includes DBPR's
† risk-factor and * primary-concern markers).
