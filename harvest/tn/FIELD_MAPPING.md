# Tennessee DOH → Kyron field mapping — TN adapter prototype v0.1

Source: **Tennessee Department of Health — MyHealthDepartment inspection
portal**, `inspections.myhealthdepartment.com/tennessee/`. The portal is
an AngularJS SPA; its own public JSON backend (POST `searchInspections`
to the site root) is what the fetcher reads, and each inspection's
report is a server-rendered HTML page on the same host. No bulk
download, no account, no API key. Every response is saved raw under
`raw/` and logged in `fetch_log.tsv` (file, URL, UTC timestamp, HTTP
status, bytes, SHA-256).

Score model: **native TN 0–100 numeric score**. The portal's report
template has a "Grade:" element but ships it hidden and empty —
Tennessee publishes **no letter grade**, so `grade` is `null`
everywhere and is never derived from the score.

Violations: **itemized checklist outcomes with narratives where the
portal prints them** — each violation carries the FDA-style item number
and short title, the Tennessee rule citation (when printed), and the
inspector's narrative/corrective-action text (when printed). On many
inspections — follow-ups especially — the portal lists the out-of-
compliance item numbers with **blank** narrative text; those ship with
`notes: null`, never paraphrased or invented.

## Endpoints used

| Endpoint | Use |
|---|---|
| `GET /tennessee/` (landing HTML) | authoritative county filter vocabulary (95 counties + 1 out-of-state body-art pseudo-county, skipped) |
| `POST /` `{"task":"searchInspections", …}` | inspection enumeration per county + date range. **Server rules measured 2026-10-15: page size is fixed at 25 (`count` is ignored); `start` must be a multiple of 25 and ≤ 200, else `{"err":true,"msg":"bad request"}` — one query exposes at most the newest 225 rows.** `tn_fetch.py` therefore enumerates by adaptive date-range partitioning: a range whose start=200 page is full is split in half recursively until every leaf range ends on a short page (provably exhausted); at the 1-day floor it partitions by inspection purpose |
| `GET /tennessee/inspection/?inspectionID=<GUID>` | the official inspection report (server-rendered HTML): score, checklist, violations, comments. Requires a browser-like session (cookieless requests get 403/hang; a primed cookie jar + Chrome UA + Referer works and is fast, ~0.7 s) |
| `GET /tennessee/permit/?permitID=<GUID>` | exists in the portal UI; **not used** — the search stub + inspection reports carry every field the Kyron model needs |

The landing page's *keyword* search is gated client-side by
reCAPTCHA; this adapter never uses keyword search (enumeration uses
the ungated county/date filter flow the landing page itself issues),
so no CAPTCHA is encountered or bypassed.

## Search stub (per inspection row) → place / inspection

| Portal field | Example | Kyron field | Transform |
|---|---|---|---|
| `permitID` (GUID) | `7961BA9A-…` | place `id` = `tndh_<permitID>`, `fid` = permitID, `fid_b64` | verbatim; TN publishes no numeric facility id and no permit number, so the permit GUID is the stable key and `permit` = null |
| `establishmentName` | `Anatolia Turkish Restaurant` | `n` | verbatim (trimmed), from the permit's newest stub |
| `addressLine1` + `addressLine2` | `48 White Bridge Rd.` | `a` | joined with `", "` when line 2 is non-blank; verbatim, never split or fused (name and street are separate source fields) |
| `city` / `state` / `zip` | `Nashville` / `TN` / `37205` | `c` / `addr_state` / `z` | verbatim from the newest stub |
| search county | `Davidson` | `ct`, `ct_raw`, `search_county` | permitting county from the query (authoritative; a place's city can sit across a county line) |
| `permitType` | `Commercial Food 51+` | `ptype` | verbatim. Harvest keeps only `Commercial Food*` permits with `inspectionType` = "Food Service Establishment Inspection" |
| — | — | `st` = `TN`, `jur` = `TN-DOH`, `src` = `TN-DOH`, `origin` = `portal` | constants |
| — | — | `phone`, `eh_phone` | **null** — the portal publishes neither |
| newest verified inspection | — | `s`, `d`, `du` | from the newest normalized inspection (`d` ISO; `du` = that inspection's official report URL) |
| — | — | `grade` | **null** — TN publishes no grade |
| — | — | `lat`, `lng` | **null** — no geocoding in this prototype (geocode-readiness is reported instead) |

## Inspection (stub + detail page) → `insp[]`

| Source field | Kyron field | Transform |
|---|---|---|
| `inspectionID` (GUID) | `vid`; `id` = `tndh_insp_<inspectionID>` | verbatim |
| stub `inspectionDate` (ISO) | `d` (ISO) | date part; cross-verified against the detail page's written date |
| detail page written date | `draw` | verbatim, e.g. `October 15, 2026` |
| stub `purpose` | `t` | verbatim (Routine / Complete / Follow-Up / Complaint) |
| stub `score` / detail score | `s` | integer, native 0–100; **null when the portal shows no score** (seen on unscored visit types); both sources must agree or the inspection is dropped as unverified |
| — | `grade`, `inspector` | **null** — not published by this portal |
| detail "Additional Comments" | `comments` | verbatim; null when the page says "No comments" |
| detail page URL | `du` | `https://inspections.myhealthdepartment.com/tennessee/inspection/?inspectionID=<GUID>` (the page also links a printable PDF via `/tennessee/print/?task=getPrintable&path=tennessee&pKey=<inspectionID>,<inspectionID>`) |

## Violations → `v[]` entry

Built per inspection as the union, by item number, of:

1. the detail page's **"Observations & Corrective Actions"** entries —
   each is `NN: <citation>. <narrative>`; `item` = NN, `rule` = the TN
   rule citation (e.g. `1200-23-01-.03(5)(a)7`) when the entry starts
   with one, `notes` = the narrative text (null when the portal prints
   the item number with blank text);
2. the checklist's **OUT items** not already in (1) — `item`, `title`,
   `status: "OUT"`, `rule`/`notes` null.

`title` and `status` come from the page's 58-item FDA-style checklist
(statuses IN / OUT / NO / NA; a few items are Yes/No questions — e.g.
item 57, TN Non-Smoker Protection Act — which appear in (1) with their
checklist status when answered adversely).

## Stub verification (the GA crossed-payload lesson, applied)

Every detail page is verified against its search stub before use —
permit GUID, establishment name, inspection date, and score must all
agree, and the page's own PDF link must carry the requested
inspectionID. Verification runs in `tn_fetch_details.py` at fetch time
(4 workers) and again in `tn_build.py`; disagreements are logged to
`work/detail_mismatch.jsonl`, re-fetched **sequentially** by
`tn_mopup.py`, and any survivor is excluded from the output and
counted in `qa_report.json`. `qa_crosscheck.py` re-verifies every
detail independently with its own extraction code.

## Source quirks the normalizer handles (all logged in qa_report.json)

- **225-row query window**: the API's hard paging cap (above) means
  naive paging silently truncates every large county — the first
  fetcher version hit `{"err":true,"msg":"bad request"}` at start=225
  on 6 counties before the rule was measured. Enumeration is only
  complete because every leaf range ends on a short page.
- **Archive depth varies**: the portal's searchable history does not
  reach back uniformly (Davidson Co. returns nothing before 2023 in
  tests on 2026-10-15, although the portal once served a 2020 Sevier
  Co. report to search engines). The harvest queries 2015-01-01 →
  today for every county and takes whatever the portal returns;
  per-county min dates land in the report.
- **Mixed permit universe**: one search returns all TN DOH permit
  types — Commercial Food alongside swimming pools, hotels/motels,
  tattoo & body-piercing studios, and child-care facilities (child-care
  kitchens receive "Food Service Establishment Inspection" visits
  under a child-care permit). Only Commercial Food permits ship.
- **Scoreless inspections**: some food-service inspections publish no
  score (stub `score` null, detail score blank). They ship with
  `s: null` — counted in `qa_report.json` — never estimated.
- **Hollow legacy detail records**: 2 inspections (Putnam and
  Sullivan Cos., both dated 2023-09-16 — the archive's floor date)
  exist in the search index with complete stub data, but their detail
  pages render the report template with every field empty: legacy
  records whose detail bodies never migrated. Sequential re-fetch
  (`tn_mopup.py`) confirmed the hollowness is in the source, not the
  fetch. Both inspections are excluded as unverified; their permits
  ship on their remaining verified inspections.
- **Names truncated at '#'**: 3 permits publish names ending in a
  bare '#' (e.g. "Subway #") — the portal itself truncated a unit /
  store number at the '#'. Their detail pages carry the same
  truncated names (nothing fuller exists in the source), and the
  names trip the gate's G4 class, so the permits are excluded
  (`OUTPUT/exclusions.json`).
- **Cold-start latency**: the first-ever search query took ~193 s;
  uncached county/range queries run 10–20 s while warm ones answer in
  1–4 s. Timeouts and resumability are sized for the cold case.

## Exclusions (documented, by design)

- **Permit types**: only **Commercial Food** harvested (incl.
  `Commercial Food <51 (Mobile)`). Pools, hotels/motels, tattoo/body
  piercing, and child-care permits are not food-service
  establishments (mirrors FL/GA excluding non-food license types).
- **Out-of-state pseudo-county**: the county filter's 96th entry
  ("OOS - Out of State (Artists and Body Piercers Only)") is skipped.
- **Gate exclusions** (`OUTPUT/exclusions.json`): any permit whose
  newest stub publishes a blank name (G1-class), no street address
  (G2-class), or a placeholder name (G4-class), and any permit left
  with zero stub-verified inspections — excluded with full provenance,
  per the Workstream B gate precedent: scores never ship attached to
  a non-name or an address-less record.
