# NC FIELD_MAPPING — CDPEHS (North Carolina) → Kyron model

Jurisdiction: **NC-CDPEHS** — the North Carolina Public Health Inspections
portal (`public.cdpehs.com`, "NCENVPBL"), operated by CDPEHS for the NC
Department of Health and Human Services' environmental-health program and
the county health departments that perform the inspections. One system of
record covers **98 of North Carolina's 100 counties** (see "Coverage" —
Alexander and Buncombe return zero rows; Buncombe publishes through its own
Accela Citizen Access portal instead).

The output shape mirrors `places_tn.json` exactly (same key set, same
conventions) so the pack builder and app treat NC like every other state.

## Source records

Two portal artifacts per county, both produced by the portal itself:

1. **Enumeration stub** — the establishment/inspection grid
   (`ESTABLISHMENT/ShowESTABLISHMENTTablePage.aspx?ESTTST_CTY=<1..100>`)
   and its **CSV export** (the grid's own export button), one row per
   inspection: `Inspection Date, Grade, Final Score, Inspector ID,
   Premises Name, Premise Address 1, Premise Address 2, Premise City,
   Premise State, Premise ZIP, State ID#, ID`. The last column is headed
   "ID" but carries the **establishment type id** (verified against the
   grid's Establishment Type column and the detail pages' Premise Type).
   The grid header prints a matched-row count ("1 - 500 of N Items") that
   must equal the CSV row count for every county and every filtered
   slice — this is the enumeration oracle; no slice ships unless all
   three counts (grid, CSV, harvested details) agree exactly.
2. **Detail record** — the "Violation Details" page
   (`INSPECTION_VIOLATION/ShowVIOLATIONTable.aspx?ESTABLISHMENT=<id>&INSPECTION=<id>&ESTTST_CTY=<cty>`),
   reached by the grid row's Violation Details postback (the postback
   redirects to this URL, which is then also the inspection's `du`).
   Contains the premises block (name, address, city/state/ZIP, premise
   type, county), inspection date, **Final Score @ Grade**, general
   comments, and the full violation table (item #, demerits, violation
   description, CDI / R / VR flags, comment narrative). This view has no
   pagination — all violations render on one page.

## Place fields (`places_nc.json`)

| Kyron key | NC source | Notes |
|---|---|---|
| `id` | `"ncdpehs_" + State ID#` | State ID# is the portal's establishment key (`ESTAB_NUMBER`), stable across inspections. |
| `fid`, `fid_b64` | State ID# verbatim | |
| `permit` | State ID# | NC publishes the State ID# on every row (unlike TN, which publishes no permit number). Its digits embed county (3) + establishment type (2) + serial. |
| `n` | Premises Name from the newest inspection's detail page | Verified equal to the stub name for every inspection (build-time stub verification). |
| `a` | Premise Address 1 + Address 2 (joined `", "`) from the newest detail page | |
| `c` | Premise City (title-cased from the portal's upper case) | |
| `z` | Premise ZIP (5-digit as published) | |
| `addr_state` | `"NC"` | |
| `ct`, `ct_raw`, `search_county` | County name (portal county list) | The county whose grid served the record. |
| `st` | `"NC"` | |
| `jur`, `src` | `"NC-CDPEHS"` | |
| `phone`, `eh_phone` | `null` | Not published by the portal. Never invented. |
| `ptype` | Premise Type verbatim, e.g. `"1 - Restaurant"` | |
| `lat`, `lng` | `null` | No geocoding in the prototype wave. |
| `s`, `d`, `grade`, `du` | Newest inspection's Final Score / date / grade / detail URL | |
| `origin` | `"portal"` | |

## Inspection fields

| Kyron key | NC source | Notes |
|---|---|---|
| `id` | `"ncdpehs_insp_" + INSPECTION id` | |
| `vid` | INSPECTION id (from the detail URL) | |
| `d` | Inspection Date → ISO `YYYY-MM-DD` | |
| `draw` | Same date in written form (`October 15, 2026`) | |
| `t` | `null` | CDPEHS publishes **no visit-purpose field** on the grid, the CSV, or the detail page (verified by inspection of all three). Not derived. |
| `s` | Final Score **verbatim as a JSON number** | NC scores have **half-point granularity** (e.g. `95.5`). Whole values are emitted as integers (`98`), halves as decimals (`95.5`) — the value is never rounded. Blank in source → `null`. |
| `grade` | Grade verbatim (`A` / `B` / `C` / `N/A`) or `null` when the source leaves it blank | Both forms are published natively (A = 90+, B = 80–89.5, C = 70–79.5); **neither is ever derived from the other**. |
| `inspector` | Inspector ID from the stub (the portal publishes an inspector number, not a name) | |
| `comments` | General Comments verbatim, `null` when empty | The inspector's free-text summary, never paraphrased. |
| `v[]` | Violation table rows (below) | |
| `du` | The inspection's Violation Details URL (official record) | |

## Violation fields (`v[]`)

| Kyron key | NC source |
|---|---|
| `item` | Violation Item number (FDA/NC item #) as integer |
| `title` | Violation Description verbatim |
| `rule` | The FDA Food Code citation that prefixes the source comment (e.g. `2-301.15`), else `null` |
| `notes` | The remainder of the source comment verbatim — rule text plus the inspector's narrative, never paraphrased |
| `points` | Demerits verbatim as a JSON number (halves occur, e.g. `1.5`). By NC's published rule the Final Score equals 100 − Σ demerits; QA measures this identity on every scored inspection and reports the match rate — it is a check, never a computation used to fill data. |
| `corrected` | CDI flag (`Yes` → true) — corrected during inspection |
| `repeat` | R flag (`Yes` → true) — repeat violation |
| `vr` | VR flag (`Yes` → true) — verification required |

## Establishment-type cut (food only)

Mirroring TN's Commercial-Food-only rule, the adapter ships only the
food-service establishment types — the ones graded on the NC sanitation
score:

`1 Restaurant · 2 Food Stands · 3 Mobile Food · 4 Push Carts ·
5 Private Schools Lunchroom · 6 Edu. Food Service · 9 Elderly Nutrition ·
11 Public School Lunch · 12 Elderly Nutrition · 14 Limited Food ·
15 Commissary (Pushcarts/Mobile Foods) · 16 Institutional Food Service ·
30 Meat Market`

All other CDPEHS programs are enumerated in the county CSVs and counted in
`OUTPUT/qa_report.json`, but excluded from the output: lodging (20–23),
camps (22, 25, 26), rest/nursing homes (40), hospitals (41), child care
(42 — a demerit-classification program: Superior/Approved/Provisional/
Disapproved, not a sanitation score), residential care (43), school
buildings (44), local confinement (45), boarding schools/colleges (46),
orphanages (47), adult day care (48), swimming pools & spas (50–58) and
tattoo artists (61). For these programs the CSV's "Final Score" column is
a demerit count or classification value, **not** a 0–100 sanitation
score, and Kyron never re-labels one native result form as another.

## Verification discipline

Every shipped inspection passed stub verification at build time: the
detail page's name, date, Final Score, grade, premise type and county
must agree with the grid/CSV stub. Disagreements are excluded with
reasons (`OUTPUT/exclusions.json`, `OUTPUT/qa_report.json`) after a
sequential mopup re-fetch; nothing is shipped on a stub alone.
Enumeration is oracle-checked at three levels (county CSV vs grid
count; slice CSV vs filtered grid count; harvested detail multiset vs
slice stub multiset, exact to the row per county).

## Coverage

- **98 / 100 counties** on CDPEHS, including Wake, Mecklenburg, Durham,
  Guilford and Forsyth (prior research assumed the big counties ran
  separate systems for records; in fact their inspections of record are
  in CDPEHS — Wake's own open-data portal and Mecklenburg's pages are
  front doors onto the same underlying records).
- **Alexander (cty 2)** and **Buncombe (cty 11)**: the CDPEHS county
  pages render with their health-department headers but contain zero
  inspection rows (verified by grid count and CSV export, Oct 15–16,
  2026). Buncombe County publishes inspection reports through its own
  Accela Citizen Access portal (per the county's published how-to) —
  a separate adapter; documented as a gap, nothing fabricated.
- Archive depth is county-specific (counties migrated/backfilled at
  different times — e.g. Chatham reaches 2007, Wake's CDPEHS records
  begin Oct 2022, Johnston's reach 1991). Per-county date ranges are in
  the prototype report; the adapter takes everything the portal serves.
