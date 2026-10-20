# Kyron — Workstream C6 Report: Tennessee Goes Pack-Ready

**Date:** October 15–16, 2026 · **Workstream:** C6 (P1) — mirror of C1 (FL) / C3 (GA)
**Outcome: Tennessee is pack-ready. Gate PASS (no adjudication), 29,183 of 33,262 places pinned (87.74%), pack `us-tn-2026-10-16.1` staged beside FL/GA, independent audit all-pass, live verification green twice — against a scratch build carrying only the one-entry region registration (see Finding 1).**

---

## 1. Gate confirm (Task 1) — PASS, clean

`validate_seed.py` over the C4 prototype's `places_tn.json` (33,262 places): **G1–G6 all 0, GATE PASS** — exactly as the prototype reported. No violation, no adjudication, no stop-and-report trigger. The 3 portal-truncated names and 2 hollow inspections C4 excluded stay excluded (they are in the prototype's `exclusions.json`, never in the dataset).

## 2. Census geocoding (Task 2) — 29,183 / 33,262 pinned (87.74%)

Pipeline: clone of the C3 GA script (`~/kyron-build/harvest/tn/work/geocode_tn.py`), same adjudication discipline — dedupe to unique normalized addresses, ≤10,000 rows per Census batch file, verified address-level matches only, provenance per place, **no centroid/jitter pins anywhere**. Output `OUTPUT/places_tn_geocoded.json`; the prototype file is untouched.

- 33,262 places → **26,046 unique addresses** (764 collapsed by the corrected canonicalizer — the LF-1 suffix-doubling lesson applies to TN too) → **25,996 submitted** (48 PO boxes + 2 intersections held back, never submitted). Border permits publish out-of-state tails, so submissions carried per-address states: TN 25,935 · MS 28 · GA 26 · VA 21 · KY 18 · NC 8 · AL 7 · AR/TX/WV 3 — each adjudicated against its own state's envelope (Regions.kt bounds, widened a hair, C1/C3 treatment).
- Production rounds accepted 22,422 addresses. Repair ladder: R1 full-word suffixes **+0**, R2 suffix-dropped **+0** (for TN, Census's own canonicalization already absorbs those variants — the failures were evidentiary, not orthographic), R3 zip_drop **+428**, R4 recanon **+4**. Final: **22,854 / 26,046 addresses accepted (87.7%)**.
- **Places pinned: 29,183 (87.74%)** — EXACT 24,210 / NON_EXACT 4,973, every one `ACCEPTED / CENSUS / ADDRESS_RANGE`.
- **Residual, 4,079 places (12.26%), by reason:** NO_MATCH 2,880 · NEEDS_REVIEW 633 · TIE 489 · PO_BOX 51 · INTERSECTION 2 · REJECTED 24. (Address level: NO_MATCH 2,154 · NEEDS_REVIEW 566 · TIE 400 · REJECTED 22 · not submittable 50.) These stay unpinned by design — the map shows verified pins only; every residual place remains fully list/search-visible. The residual is a future free-source/Geocodio mop-up candidate, not a blocker.
- **Coverage vs. the brief's trigger:** TN lands **above** GA (83.86%) and FL (84.66%), consistent with C4's 99.41% geocode-readiness — nothing anomalous to investigate.

## 3. The pack (Task 3)

| | |
|---|---|
| Region | `us-tn` — Tennessee, `SCORE_100` |
| File | `us-tn-2026-10-16.1.db.gz` |
| Bytes | **18,424,434** |
| SHA-256 | `40ef34ce088a38f65069a45b9b9d8c457c60d0784ae7beadd1485c460e14ca38` |
| datasetVersion | **2026-10-16.1** — derived from the source manifest's `generated_at` (2026-10-16T02:49:59Z) by the builder's standing method, same as FL/GA's 2026-10-15.1; the version follows the data (the C4 harvest completed after midnight UTC), not the wave date |
| Contents | 33,262 places · 122,079 inspections · 343,776 violations · 29,183 verified pins |
| Staged | `~/kyron-build/fl-publish/us-tn.manifest.json` + the pack, beside the FL/GA pairs. **Not published** (Task 4) — same infrastructure blocker as C1/C3. Note: at 18.4 MB the TN pack is **under GitHub's 25 MB web-upload cap**, so unlike GA it can ride the FL browser-upload route once the CSDM unblocks publishing. |

**Converter decisions** (`convert_tn_place` in `build_pack.py`, the only production file this wave edited):

- **Scores verbatim.** Native 0–100 copied; nothing converted, estimated, or averaged. The source's 155 scoreless inspections — and the 24 places whose newest visit is scoreless — ship as the app's NO_SCORE sentinel (−1) for that record only (the C3/GA treatment of its 3 scoreless places), never backfilled from an older scored visit.
- **No grade, ever.** Tennessee publishes no letter grade, so `result_text` is **empty at place and inspection level** — the deliberate divergence from GA, where the state itself publishes the band. Builder asserts now fail the build if any TN record carries a `result_text`.
- **Violations in the app's `{p, c, r}` shape, all 343,776 carried.** `r` = `"<item> <title> — <rule citation>"` plus `" // "` + the inspector's narrative verbatim where the portal prints one (235,929 narrative-bearing rows). **`p = 0` and `c = false` for every row:** TN publishes no per-violation points and marks no critical/priority flag in its data — unlike GA (whose own (p) citation suffix set GA's flag) there is nothing source-marked to carry, and criticality is never inferred from the item number. The checklist `status` is the outcome that selected a row into the source's violation list; per the GA precedent it is selection metadata and is not duplicated into `r`. Per-inspection portal comments are not carried (no app field; FL/GA precedent).

**FL/GA non-regression proof (required by the brief):** with the edited builder, rebuilding the FL pack reproduces the staged artifact **byte-for-byte** (sha256 `2c47c3d5…` ✓) and the GA pack likewise (`47810503…` ✓). The TN additions are pure registry/converter additions; the FL/GA paths are behavior-identical. (Both were also reproduced pre-edit, so the baseline itself is sound.)

## 4. Independent pack audit — ALL CHECKS PASS

`~/kyron-build/harvest/tn/work/audit_tn_pack.py` queries the pack DB directly and compares against the geocoded source without reusing builder code (the `{p,c,r}` expectation is an independent re-implementation):

- pack_meta ↔ manifest ↔ source manifest agree (region, version, count 33,262, schema 2, SCORE_100);
- rows: 33,262 places / 122,079 inspections / **0 orphans**;
- **full-table** place comparison (name, street, city, ZIP, county, score, date, detail URL, state/region/jurisdiction/source tags, lat/lng): **zero mismatches**; place id sets identical;
- NO_SCORE sentinels exact: **24 places / 155 inspections**; 0 out-of-model scores anywhere;
- `result_text` **empty everywhere** (places + inspections) — no invented grade;
- 29,183 pinned; **0 coordinates without complete provenance**; 0 half-null coordinates;
- per-place inspection counts and per-place violation counts equal the source **everywhere**; total violations **343,776**; narrative-bearing rows **235,929 = source exactly**;
- deterministic 20-place stride sample with **full `violations_json` equality** — all OK.

## 5. Finding 1 — Tennessee registration (replicates C3's Georgia finding)

**The shipped app does not know Tennessee exists.** The FIX5 production tree's `Regions.KNOWN` registers `us-al`, `us-fl`, `us-ga` only, so `PackManager` rejects a `us-tn` pack exactly as it rejected Georgia in C3. **The pack itself needs no other app change** — Tennessee is `SCORE_100` like Alabama/Georgia, and the live test below proves the empty-`result_text` (no-band) shape is safe in browse, filters, and the why-summary.

Registration snippet for the CSDM to approve (identical shape to Georgia's; verified working in §6):

```kotlin
val TENNESSEE = RegionInfo(
    regionId = "us-tn", state = "TN", displayName = "Tennessee",
    scoreModel = MODEL_SCORE, bundled = false,
    centerLat = 35.86, centerLng = -86.35,
    manifestUrl = "https://markbentzjr.github.io/kyron/data/us-tn.manifest.json"
)
// KNOWN = listOf(ALABAMA, FLORIDA, GEORGIA, TENNESSEE)
// + cosmetic: sourceDisplayName "TN-DOH" -> "Tennessee Dept. of Health"
```

As with Georgia, the CSDM batches registrations per build — TN's rides the next one.

## 6. Live verification (Task 5) — TnLiveTest green, twice

`~/kyron-build/test/src/TnLiveTest.kt` (+ `run_one_tn.sh`) against a scratch tree (`~/kyron-build/scratch-tn/`) that is a byte copy of the production tree plus **only** the §5 registration (build-script diff: two path lines; source diff: the registration block only). Scratch build **BUILD OK** with all gates green (pathData, seed, canary); scratch APK md5 `4c54f0674c4af5891af968857a6aceb6`. **Production tree untouched: `Regions.kt` md5 `943f704da72124018bd14a0786cbb4fe` before and after this wave**; the only existing file edited anywhere is `build_pack.py` (permitted), and the only test file added is `TnLiveTest.kt`.

Both runs drive the production code path (PackManager with SHA-256 + pack_meta verification, CatalogDb, PlaceRepository, WhySummary) against the **staged publish bytes**:

- **Install:** TN pack installs through PackManager — 33,262 places, `installedRegionVersion = 2026-10-16.1`.
- **Co-residence:** AL 23,527 + TN 33,262 + GA 33,514 + FL 70,033 = **160,336** places in one catalog; region switching to `us-tn` works.
- **Browse:** Brugada Bar & Restaurant (Nashville, Davidson Co.) — score **76**, numeric, `nativeResult == ""`, source `TN-DOH`; "Below 85" includes it, "95+" excludes it; a 1,000-place TN sample is uniformly state TN with empty native results.
- **Why-summary:** newest inspection's violations render with the TN narrative verbatim — *"Scored 76 — … Observed raw fish stored above ready to eat sauce in prep cooler 1. Also, observed par-cooked raw bone marrow stored above ready to eat pasta in prep cooler 3…"*
- **Map:** Nashville viewport (36.05–36.25, −86.95…−86.65) returns **3,618 pinned places** — exactly the source-data count — all verified-coordinate TN; catalog coord count equals the pack's own count (**29,183**); 0 coordinates without ACCEPTED/CENSUS provenance.
- **Isolation & removal:** no TN bleed into GA browse; `Davidson` exists only under `us-tn`; removing TN leaves AL/FL/GA counts exact, removing GA then leaves AL+FL exact.
- **Run results: run 1 OK (1 test), run 2 OK (1 test)** — identical evidence lines. (TN install took 32.6 s in run 1 under concurrent-agent CPU contention, 5.3 s in run 2; TN is the heaviest pack to date at 343,776 violation rows — a one-time install cost, noted for the publish decision.)

## 7. What the CSDM gets from C6

1. **A staged, audited Tennessee pack** (`us-tn-2026-10-16.1`, 18.4 MB, sha256 above) in `~/kyron-build/fl-publish/`, ready to publish with FL/GA; at 18.4 MB it fits the browser-upload route GA can't use.
2. **One registration snippet** (§5) to batch into the next build — no other app change.
3. Coverage **87.74%** pinned at launch quality, with the 4,079-place residual enumerated by reason for a later mop-up wave.

*Artifacts: geocode pipeline + checkpoints `~/kyron-build/harvest/tn/work/` (`geocode_tn.py`, `geo/`), geocoded dataset `~/kyron-build/harvest/tn/OUTPUT/places_tn_geocoded.json`, audit `~/kyron-build/harvest/tn/work/audit_tn_pack.py`, test `~/kyron-build/test/src/TnLiveTest.kt` + `run_one_tn.sh`, scratch tree `~/kyron-build/scratch-tn/`, run logs `~/kyron-build/harvest/tn/work/tnlive_run{1,2}.log`. $0 spent; nothing pushed; nothing published.*
