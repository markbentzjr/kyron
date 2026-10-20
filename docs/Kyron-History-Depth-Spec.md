# Kyron — Score-History Depth: Feature Specification (Workstream E)

**Status:** SPEC ONLY — no code in this document's wave. **Build wave: after FIX5**
(GA registration), per `Kyron-Plan-Completeness-History-Expansion.md` Step 3.
**Date:** October 15, 2026 · **Author:** Workstream E (spec agent) · **Owner:** Zyros (CSDM)
**Scope discipline:** FIX-line tree (`~/kyron-build/manual/src`) only. The frozen 2.1
tree is not touched. $0, guest-first, on-device only, no accounts, no invented data.

---

## 1. What Mark asked for (verbatim requirements)

1. **Default view = last 5 scores** per restaurant. A **global setting** chooses
   the default depth: **3 / 5 / 10 / all**.
2. A **per-restaurant "show older scores"** control expands *that place* to the
   deepest history the pack/source holds.
3. **Expanded history is saved locally, with a timestamp.**
4. **Automatic cleanup:** 1 year after a place's expansion, it reverts to the
   default last-5. Cleanup runs **inside the existing background sync**.
   Everything on-device; guest-first; no sign-up.

---

## 2. Data reality — measured, not assumed (Oct 15, 2026)

All figures measured directly from the shipped seed and the built pack DBs.

| Source | Places | Inspections held on device today | Depth per place | Snapshot cost / inspection |
|---|---|---|---|---|
| **ADPH** (AL, bundled) | 18,996 | **0 embedded** — latest score+date live on the place row only | **1 event** (the latest) | — |
| **JCDH** (AL, bundled seed) | 2,295 | **80 embedded total** (35 places ≥1, 29 ≥2, max 5) | seed ≈ 0 for most places; **live detail fetch ≤ 4** with violations | 802 B mean (JSON, w/ violations) |
| **MCHD** (AL, bundled) | 2,233 | 7,139 | mean 3.20, **max 4**, every place ≥1 | 45 B (score+date only) |
| **FL pack** `2026-10-15.1` | 70,033 | 44,660 visits | 34,002 places have **0 visits**; 29,266 ×1; 5,455 ×2; 979 ×3; max **14**; only 49 places >5 | 464 B mean row payload |
| **GA pack** `2026-10-15.1` | 33,514 | 138,922 | **mean 4.145, median 4, max 29**; 8,989 places (26.8%) have >5; 2,620 have ≥7 | 918 B mean row payload (max single inspection 38 KB) |

**Corrections to the briefing assumptions, on the record:**

- **"JCDH: full history" is true of the source, not of the shipped seed.** The
  bundled seed carries almost no JCDH inspections (80 total). JCDH depth on a
  real device today comes from the *live* detail-page fetch
  (`JcdhSource.fetchDetail`, already used by DetailActivity's "Load full
  inspection details" button and SyncEngine step 4), whose parser returns
  **up to 4 inspections with violations** per the detail page. The spec below
  treats JCDH expansion as a *fetch + snapshot* operation, not a local unlock.
- **FL's "history" is a ~3.5-month rolling window** (DBPR extract dates
  2026-07-01 → 2026-10-12). Deep FL history does not exist in the source
  extracts; the pack already holds every published visit.
- **GA/FL/MCHD packs and seed already ship their full published history.**
  Expansion for those sources is a display unlock + a user-store snapshot
  (for survival across pack operations), not a download.
- **Ordering invariant (verified):** inspection lists are **newest-first**
  (index 0 = newest) in the AL seed (1,899 multi-inspection places checked,
  0 violations) and FL data (6,765 checked, 0 violations); GA QA verified
  "latest matches raw" per place. All depth logic below relies on this.
- **"Scores" means inspection events.** FL publishes no scores at all, and GA
  has 8 inspections whose score is the NO_SCORE sentinel (blank source score,
  band in the native result). Depth counts *inspections*, never just scored
  ones. UI wording adapts per region (§6.4).

---

## 3. Concepts

- **Held history** — the inspections the catalog currently has for a place
  (`CatalogDb.inspectionsFor`, from seed/pack/live merge), newest-first.
- **Default depth `D`** — the user's setting: 3, 5, 10, or ALL. Default **5**.
- **Shown set** — the inspections the detail screen renders, computed by one
  funnel function (§5, D2). Everything downstream (chips/timeline, sparkline,
  why-summary selection) consumes the shown set and nothing else.
- **Expansion** — a user-store record stating "the user saved this place's
  older history at `expanded_at`", plus a **snapshot**: the deepest history
  obtainable at expansion time, serialized in the user store.
- **Live expansion** — a record with `deleted_at IS NULL` **and**
  `expires_at > now`. Both conditions are checked at read time (§8.3).

---

## 4. Headline design decisions

- **D1 — Two layers, one-way valve.** The catalog stays replaceable; the
  snapshot lives in the **sacred user store**. Data flows catalog → snapshot
  at expansion time, and snapshot → *display only*. Snapshot data is **never**
  written back into the catalog and **never** feeds merge/alert logic. This
  makes phantom "new inspection" alerts from restored history impossible.
- **D2 — One funnel.** `HistoryDepth.shownInspections(place, expansion, nowMs)`
  is the only place depth policy exists. Today's chip picker consumes it;
  the Presentation Spec's timeline/sparkline (§4.6) will consume the same
  function when that wave lands. No second implementation.
- **D3 — Expansion is a snapshot, not a flag.** Because pack full-swaps
  replace region rows wholesale and regions can be removed, a flag alone
  cannot honor "saved locally." The snapshot guarantees the captured depth
  survives pack swaps, region removal + reinstall, and (via backup export)
  device replacement, for exactly its 1-year life.
- **D4 — Expiry is enforced twice.** Read-time (the detail screen treats an
  expired record as absent, even if the worker hasn't run) and write-time
  (the sync cleanup tombstones the record and drops the payload). Display
  policy never depends on the worker having run.
- **D5 — Expandability is data-driven, never source-hardcoded.** A place is
  expandable iff obtainable depth > shown depth. If ADPH ever publishes
  history, ADPH places become expandable with zero new code (§11, E4).
- **D6 — Phase 1 changes no pack format.** Packs keep shipping full history;
  catalog schema stays v2; `SUPPORTED_PACK_SCHEMA` unchanged; `build_pack.py`
  untouched. The history-supplement design for a possible Phase 2 is
  specified in §10 and explicitly **not** built in this wave.
- **D7 — Outbox deviation, documented.** For every other entity the sync
  outbox payload is the full entity JSON. For `history_expansion` the outbox
  payload is **metadata only** (place_id, timestamps, source_depth,
  payload_bytes, payload_sha256) — the snapshot bytes are a *cache of public
  catalog data*, re-derivable from the source; the sacred user datum is the
  expansion fact. The full payload **is** included in user-initiated backup
  exports (§7.4), where fidelity matters. Rationale and the rejected
  alternative are in §7.3.

---

## 5. Display semantics (the funnel)

```
shownInspections(place, expansion, nowMs):
  held      = place.inspections                      # newest-first, catalog
  if expansion is live at nowMs:
      merged = union(held, expansion.snapshot)       # dedup §5.1
      return merged                                  # ALL of it
  return held.take(D)                                # D = setting; ALL → held
```

- **§5.1 Union rule.** Dedup key = `(date, type)`. On collision the
  **catalog copy wins** (the catalog is the living source; if a source
  corrects an inspection, the pack/merge version is the truth and the
  snapshot fills only dates the catalog lacks). Result sorted newest-first
  by `CatalogDb.dateKey(date)` descending; ties keep catalog-before-snapshot
  order. Snapshot-only entries keep their snapshot relative order.
- **§5.2 Selection state.** `DetailActivity.inspIdx` indexes the **shown
  set** and is clamped into range on every render (a settings change or an
  expiry between renders must never leave a dangling selection).
- **§5.3 Count line.** The history section always states the truth:
  - Trimmed: `Showing the last 5 of 9 inspections`
  - Expanded: `Showing all 9 inspections on file`
  - Single: no count line (section shows the one entry).
- **§5.4 Sparkline/timeline.** Per Presentation Spec §4.6, both draw from
  the shown set. When trimmed, the sparkline's older end terminates in the
  expand affordance (§6.2) — the chart never draws data it isn't showing.
  The §4.6 caption `History as published by <source>` closes the section
  in all states.

---

## 6. Exact UI behavior

### 6.1 Detail screen — history section states

The existing history card (`d_history_card`, chips + text line) is fed the
shown set instead of `place.inspections` wholesale. Section title:
`Score history` in numeric regions, `Inspection history` in disposition
regions (FL). States, in priority order:

| # | Condition | Section renders |
|---|---|---|
| S1 | Held = 0, source publishes latest-only (ADPH) | Single latest entry implied by hero; **no card**; one caption line under the source block (§6.4 copy A). No button. |
| S2 | Held = 0, FL license-only place | No card. Existing `No inspection on file` band behavior unchanged. No button. |
| S3 | Held ≥ 1, not expanded, held ≤ D, no fetcher | Shown = held. Caption B (§6.4). No button — nothing older exists to load. |
| S4 | Held > D, not expanded | Shown = newest D. Count line (§5.3). **Expand button** (§6.2). |
| S5 | Held ≤ D, source has a detail fetcher (JCDH today), not expanded | Shown = held. **Expand button** (the fetcher may hold more than the seed). |
| S6 | Expanded (live record) | Shown = union (§5.1). Saved-until line (§6.3). **Refresh button** (§6.2). |
| S7 | Record exists but expired at render | Identical to S3/S4/S5 as applicable — expired = absent (D4). |

### 6.2 The expand control

One button in the history card footer (new view in `activity_detail.xml`),
label by state:

- S4: `Show older scores (4 more)` — the parenthetical is the exact count
  `held − D`. FL wording: `Show older visits (N more)`.
- S5 (JCDH): `Load full history from Jefferson County` — names the source,
  because this one can use the network.
- S6: `Refresh older scores` (re-capture; restarts the 1-year clock, §7.2).
- During a JCDH fetch: disabled, `Loading inspection details…` (reuses the
  existing load-button strings/pattern in DetailActivity), failure renders
  the existing error copy style into `d_load_msg`:
  `Couldn't load details (<reason>). The county site may be busy.` — and the
  expansion **still succeeds** with the on-device held history, flagged
  partial (§9.2).

Tap behavior (S4/S5): capture snapshot (§9) → write expansion record →
re-render. GA/FL/MCHD captures are local and effectively instant; no
spinner, no network, works in airplane mode.

### 6.3 Saved-until line (S6 only)

Directly under the count line, secondary text:

```
Older scores saved on this device until Mar 2027 — then this place returns to your last-5 view.
```

Month/year is derived from the record's `expires_at` (always truthful,
even if the device clock was wrong — §8.4). If `partial = 1`, append:

```
Saved the 2 inspections on this device — connect to the internet and tap Refresh to load the county's full record.
```

### 6.4 Honest source labels (verbatim copy deck)

- **Copy A — ADPH (latest-only source),** under the source block:
  `Alabama Department of Public Health publishes only the latest score for this place — older scores are not published, so there are no older scores to show.`
- **Copy B — held ≤ D, no fetcher:** the Presentation §4.6 single-entry copy
  where depth = 1 (`Only the latest inspection is published by this source`),
  otherwise the closing caption alone suffices.
- **Closing caption (all states):** `History as published by <source display name>.`
  (Source display name from `SourceRegistry` / `Regions.sourceDisplayName`,
  as the detail screen's existing Source line resolves it.)
- **FL section:** title `Inspection history`; button `Show older visits`;
  entries show the native disposition verbatim — never the word "score".

### 6.5 The setting UI

The Alerts tab already hosts the app's settings-style controls (threshold
slider, radius slider, toggles — FIX-line `AlertsFragment`). Add one card:

- Title: `Score history`
- Row label: `Show last N scores per place`
- Control: four-option selector — `3` · `5` · `10` · `All` (segmented
  radio row in classic Views; writes through immediately, no Apply button,
  matching the existing controls' behavior).
- Helper text: `Places where you tap "Show older scores" keep their full
  history for a year, then return to this setting.`
- Status line (live count, from the user store):
  `Older scores are saved for N places.` — omitted when N = 0. This makes
  the invisible cleanup policy visible and auditable by the user.

Changing the setting takes effect on the next detail-screen render,
including for a screen already open (render-on-resume, §11 E1). It never
creates or destroys expansion records.

---

## 7. Data model

### 7.1 The setting

- **Storage:** new column on the user-store `profile` table:
  `history_depth INTEGER NOT NULL DEFAULT 5`.
- **Encoding:** `3`, `5`, `10` literal; **`0` means ALL**. The sentinel is
  named in code as `Prefs.HISTORY_DEPTH_ALL = 0`. No other values are
  valid; reads coerce anything unexpected to 5.
- **API:** `Prefs.historyDepth: Int` facade property over
  `ProfileRow.historyDepth`, via `store.updateProfile { … }` (which bumps
  `profile.updated_at` and writes the profile outbox op, as every profile
  mutation does today). Unlike `threshold`, it has **no alert-rule side
  effects**.

### 7.2 The expansion record — `history_expansions` (user store)

Full §1.2 contract compliance: UUID id, `owner_id = 'local'`, created /
updated timestamps, tombstone deletes, per-row version, outbox op per
mutation in the same transaction.

```sql
CREATE TABLE history_expansions(
    id TEXT PRIMARY KEY,                       -- UUIDv4, on-device
    owner_id TEXT NOT NULL DEFAULT 'local',
    place_id TEXT NOT NULL,                    -- catalog place id (adph_…, jcdh_…, gadph_…, fldbpr_…)
    region_id TEXT NOT NULL DEFAULT '',        -- place.regionId at capture time
    expanded_at INTEGER NOT NULL,              -- epoch ms of latest (re)capture
    expires_at INTEGER NOT NULL,               -- expanded_at + 365 days (§8.2)
    source_depth INTEGER NOT NULL,             -- inspections in the snapshot
    partial INTEGER NOT NULL DEFAULT 0,        -- 1 = capture incomplete; deeper may exist (§9.2)
    payload_json TEXT NOT NULL DEFAULT '[]',   -- Inspection[] JSON (Models.kt shape), newest-first
    payload_bytes INTEGER NOT NULL DEFAULT 0,  -- UTF-8 byte length of payload_json
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted_at INTEGER,                        -- tombstone; NULL while live
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_hist_exp_place ON history_expansions(place_id);
CREATE INDEX idx_hist_exp_expires ON history_expansions(expires_at);
```

- **Payload format** is exactly the seed's `insp` array shape
  (`Inspection.toJson()` / `Inspection.fromJson()`), so no new serializer
  exists and old/new app versions parse each other's payloads (all fields
  are read with `opt*` — additive-tolerant by existing discipline).
- **Re-expansion / refresh** of a place with a live record: replace the
  snapshot with a fresh capture, `expanded_at = now`,
  `expires_at = now + 365d`, `version++`, outbox UPDATE. (Mark's rule keys
  off when the user saved it; a deliberate re-save is a new save — §11 E5.)
- **One live record per place.** Writes follow the favorites discipline
  (the 2026-10-13 QA lesson): operate on *all* rows for the place —
  revive/update the newest, tombstone any extra live duplicates in the
  same transaction.
- **Model class:** `HistoryExpansionRow` beside the other row types in
  `UserStore.kt`, with `historyExpansionJson(row)` following the existing
  `favoriteJson` / `areaJson` pattern (metadata form — §7.3).

### 7.3 Outbox payload (decision D7)

Every mutation appends a `sync_outbox` row, `entity_type =
'history_expansion'`, in the same transaction — the outbox is still
written from day one for this entity. Its `payload_json` is the
**metadata form**: `{id, placeId, regionId, expandedAt, expiresAt,
sourceDepth, partial, payloadBytes, payloadSha256, createdAt, updatedAt,
deletedAt, version}` — **without** `payload_json` itself.

*Rationale:* the outbox exists so a future backend can replay user
*intent*. An expansion's intent is fully described by its metadata; the
snapshot bytes are a cache of public catalog data that any future sync
can re-derive from the source by place_id. Embedding them would double
the storage cost of every expansion forever (§12) to protect data that is
not user-created. *Rejected alternative:* full-payload outbox (the
favorites/areas pattern) — correct for user-created entities, wasteful
here. The DELETE op written by cleanup carries the same metadata form
(with the final `payloadSha256`/`payloadBytes`), so an auditor can verify
exactly what was dropped.

### 7.4 Backup / export

`kyron-backup` gains a `history_expansions` section: **full rows including
`payload_json`** (user-initiated export is the fidelity path — a restored
phone should not need the region pack re-downloaded before expansions
render). Import merges by **natural key `place_id`** with the established
rules (newest `updated_at` wins; tombstones honored; rival live rows for
the place are tombstoned in the same transaction), implemented as
`UserStore.mergeHistoryExpansion(row)` mirroring `mergeFavorite`. Old
backups without the section import unchanged; backups without
`profile.historyDepth` default it to 5.

---

## 8. Cleanup — the 1-year auto-revert

### 8.1 Where it runs

A new final step in `SyncEngine.run` (after step 5, alerts), so it rides
**both** the periodic worker (WorkManager, 12-hour cadence, existing
`SyncWorker` — unchanged) and manual syncs, exactly as Mark specified:
*inside the existing background sync*. No new WorkManager request, no new
schedule. `SyncReport` gains `historyExpired: Int` (default 0).

### 8.2 Expiry rule

`expires_at = expanded_at + 365 × 86,400,000 ms` (31,536,000,000 ms),
stored on the record at capture time. Fixed-millisecond arithmetic —
timezone-, DST-, and leap-proof by construction (§11 E14). A record is
expired when `nowMs >= expires_at`.

### 8.3 Two enforcement points (D4)

1. **Read-time:** `HistoryDepth` treats a record with `expires_at <= nowMs`
   as absent. The detail screen therefore reverts on schedule even if the
   worker has been starved for months (§11 E10).
2. **Write-time (cleanup proper):** one set-based pass —
   for every live record with `expires_at <= nowMs`, in a single user-store
   transaction: `payload_json := '[]'`, `payload_bytes := 0`,
   `deleted_at := nowMs`, `updated_at := nowMs`, `version++`, and one
   outbox DELETE (metadata form) per record.

### 8.4 Idempotence & failure isolation

- The pass is a pure function of `(store state, nowMs)`: running it twice,
  concurrently with a worker retry, or after a crash mid-transaction
  leaves the same end state. Tombstoned rows are never re-selected
  (`deleted_at IS NULL` is in the predicate) and never resurrected (merge
  rules honor tombstones by `updated_at`).
- Wrapped in `runCatching` like every other sync step. A cleanup failure
  is counted nowhere in `sourcesOk/sourcesFailed` and **never** changes
  the worker's retry decision; it simply retries next sync. Cleanup never
  touches the catalog DB — it cannot corrupt catalog state by
  construction (different database file).
- **Silent:** no notification, no inbox entry. Reverting a view is a
  storage/display policy, not news about a restaurant.
- **Clock rules:** all stamps use `System.currentTimeMillis()` (wall
  clock) — the same clock that stamped `expanded_at`. Elapsed-realtime
  clocks are forbidden here (they reset at reboot). Consequences, accepted
  and documented: clock set backward → expansions live longer (harmless);
  clock corrected forward → earlier expiry, and the saved-until line
  (§6.3) always showed the true `expires_at`-derived date, so the UI never
  promised anything else.
- **Testability:** the cleanup entry point is
  `HistoryCleanup.expire(store, nowMs): Int` — clock injected, never read
  internally. Same for the read-time check. Production passes
  `System.currentTimeMillis()`.

### 8.5 Storage-pressure early expiry (cap)

If live payload sum exceeds **16 MB** *or* live records exceed **1,000**,
cleanup additionally expires the **oldest** live records (by
`expanded_at`) until under the cap — **except** it never expires a record
younger than 30 days; if only young records remain and the cap is still
exceeded, it allows the overflow and reports the count in
`SyncReport.historyExpired` as usual (correctness over cap, §11 E9).
Early-expiry uses the identical tombstone path as age expiry.

---

## 9. Capturing an expansion, per source

Capture = build the deepest obtainable inspection list, newest-first,
write/refresh the record (§7.2), re-render.

### 9.1 Catalog-held sources (GA, FL, MCHD, and JCDH's seed-held part)

Snapshot = the place's full held history from the catalog. No network.
`partial = 0`. `source_depth = held.size`.

### 9.2 JCDH (live fetcher)

Snapshot = union (§5.1 rule) of held history and
`SourceRegistry.jcdh.fetchDetail(place)` — the existing code path used by
today's detail-load button and SyncEngine enrichment. This also *updates
the catalog* via the existing `repository.updatePlace(...)` flow, as
today (that behavior is unchanged and independent of the snapshot).

- Fetch succeeds → `partial = 0`, `source_depth = snapshot.size`.
- Fetch fails / offline → snapshot = held only, `partial = 1`, expansion
  **still succeeds**, UI shows the partial note (§6.3). If held is empty
  *and* the fetch fails, no record is written and the existing error copy
  shows — saving nothing would be a lie.
- Eligibility: `place.detailUrl != null` and the place's source exposes a
  detail fetcher (today: JCDH only — gate on the capability, not the
  literal source id, so a future fetcher slots in).

### 9.3 ADPH (nothing to expand)

Held depth = the latest event only; no fetcher exists. The place is never
expandable; the UI shows Copy A (§6.4). This is a *data* outcome, not a
special case in code: `expandable(place) = obtainableDepth(place) >
shownDepth(place)` evaluates false (§11 E4).

### 9.4 FL places with zero visits

Not expandable (nothing held, nothing fetchable). No history section
(state S2). If a future FL pack ships more visits for such a place, it
becomes expandable by the same data-driven rule.

---

## 10. Pack-format implications

### 10.1 Phase 1 (this wave): none

Packs and the seed already ship full published history for GA/FL/MCHD;
the catalog schema stays **v2**; `PackManager` and `datasetVersion`
semantics are unchanged; `build_pack.py` is untouched. Pack full-swaps,
deltas, and rollbacks interact with expansions *only* through §11 E2/E7 —
the user store is a different file and PackManager cannot touch it
(existing architectural guarantee, restated as an acceptance test AT-14).

### 10.2 Phase 2 (specified, NOT built): optional history supplement

*Trigger:* only if a future pack's size forces history trimming (GA's pack
is already 33.7 MB gz / 173 MB raw). Design, for when it's needed:

- The full pack ships the newest **5** per place. A separate optional
  artifact per region ships the rest:
  `us-ga.history-2026-10-15.1.db.gz` — a standalone SQLite file with
  `supplement_meta(k,v)` and one table
  `deep_history(place_id TEXT PRIMARY KEY, inspections_json TEXT)`.
- The region manifest gains an optional block:
  `history: {file, bytes, sha256, forDatasetVersion, depthFrom: 6}`.
  `datasetVersion` remains the **catalog** version, unchanged in meaning;
  the supplement is bound to exactly one catalog version.
- Install discipline mirrors full packs: SHA-256 + size verified before
  open; `forDatasetVersion` must equal the installed catalog version or
  the supplement is refused (fail-closed, catalog untouched). A catalog
  full-swap, delta, or rollback to any other version **deletes the
  supplement file** and its meta keys
  (`history_supp_version:<regionId>`) in the same operation.
- Expansions read through the supplement when present (it's just another
  contributor to "held"); snapshots in the user store are unaffected by
  supplement lifecycle — that independence is their purpose.
- **Delta vs full for history payloads: full, always.** Inspection events
  are immutable once published; history changes only by accretion and by
  dataset re-export. A delta chain would impose exact-base-version
  bookkeeping to save bytes that don't need saving at these sizes:

  | GA trim point | Inspections moved to supplement | Raw size | Est. gz |
  |---|---|---|---|
  | beyond 10 | 42 | ~0.04 MB | negligible |
  | beyond 5 | 12,795 | ~11.7 MB | ~2–4 MB |
  | beyond 3 | 48,508 | ~44.5 MB | ~9 MB |

  (FL beyond-5 is 117 inspections — noise.) A versioned full supplement
  at ≤ ~9 MB gz worst case is simpler and safer than a second delta
  mechanism. **No history deltas.**
- The supplement does **not** bump the catalog's
  `SUPPORTED_PACK_SCHEMA` (it is never copied into the catalog schema);
  it carries its own meta version. App builds without supplement support
  ignore the manifest block (`optJSONObject`, the existing tolerant
  parsing pattern).

---

## 11. Interactions with existing features

- **Why-summary (`WhySummary`): unchanged code.** It summarizes the
  *selected* inspection; expansion enlarges the selectable set to older
  inspections, whose violations then render/summarize exactly as the
  latest one's do today. FL older visits flow through
  `dispositionExplainer` unchanged. ADPH places keep the band explainer +
  "publishes scores and dates only" copy — unaffected by this feature.
- **Alerts (`SyncEngine` steps 1–5): untouched.** Alerting keys off
  `Place.eventKey` (latest event) from *catalog merges only*. Snapshots
  never enter `mergeFresh`, never produce `PlaceEvent`s, and cleanup
  never fires alerts. Expansion or expiry of a favorite changes nothing
  about its alerts.
- **Favorites: orthogonal.** Favoriting doesn't expand; expanding doesn't
  favorite; un-favoriting keeps the expansion until its own expiry.
- **Favorites score delta (Presentation §4.3, backlog P1-10, not yet
  built):** when implemented, the delta should be computed against the
  previous entry of the *shown set* — so an expanded favorite can show a
  delta even where the catalog holds a single inspection. Noted here as a
  decision for that wave; nothing to build now.
- **Region removal / reinstall:** see E2. **Region switching:** expansion
  state is per place_id; switching regions neither shows nor hides records.
- **Search / map / browse:** untouched. Depth policy exists only on the
  detail screen.

---

## 12. Storage budget — the math

Measured payload costs (§2): GA ≈ **918 B**/inspection, JCDH ≈ **802 B**,
FL ≈ **464–667 B**, MCHD ≈ **45 B**. A stored expansion ≈ payload +
~250 B of record columns; outbox ops are metadata-only (~300 B each, D7).
SQLite page overhead adds ~5–10%. Scenarios (payload only):

| Scenario | Math | Payload |
|---|---|---|
| Typical heavy user: 500 GA places at mean depth | 500 × 4.145 × 918 B | **≈ 1.9 MB** |
| Mark's worst case: 500 *deepest* GA places | depths 29,13,12,11,10,9×217,8×231 → 4,363 inspections × 918 B | **≈ 4.0 MB** |
| Hard bound at today's data: 500 × max depth 29 | 14,500 × 918 B (impossible in practice — one 29-deep place exists) | **≈ 13.3 MB** |
| 500 JCDH places via live fetch | 500 × 4 × 802 B | ≈ 1.6 MB |
| 500 deepest FL places | ≈ 2,054 visits × ~550 B | ≈ 1.1 MB |
| 500 MCHD places | 500 × 4 × 45 B | ≈ 0.09 MB |

With record overhead and the §8.5 caps (**16 MB live payload / 1,000 live
records**), the user store's history feature is bounded at ≈ **17 MB**
worst case and ≈ **2 MB** for a realistic power user — against a GA
catalog that is itself 173 MB on device, and inside Android Auto Backup's
25 MB/app quota alongside the (small) rest of the user store. The
pathological bound (13.3 MB) fits under the cap without early expiry; the
cap exists for future deeper sources (e.g. a 10-year-history state), not
for today's data.

---

## 13. Acceptance tests (implementer + independent QA pass)

Rig: the existing Robolectric harness (`~/kyron-build/test`), Lf4Test /
GaLiveTest style. All time-dependent tests inject `nowMs`.

**Setting & migration**
- AT-01 Fresh install: `historyDepth == 5`; detail screen trims a 9-deep
  GA place to 5 with count line `Showing the last 5 of 9 inspections`.
- AT-02 Upgrade: user DB at v1 → v2 migration creates `history_expansions`
  and `profile.history_depth = 5`; all pre-existing favorites/areas/
  rules/inbox rows byte-identical after migration; `profile.updated_at`
  not bumped by the migration itself.
- AT-03 Setting 3 / 10 / ALL re-trims the same place to 3 / 10 / 9 with no
  restart and no expansion record created. Invalid stored value coerces
  to 5.
- AT-04 Backup round-trip: export → wipe → import preserves
  `historyDepth` and all live expansion records (payload included);
  a pre-feature backup (no key/section) imports with depth 5, no
  expansions, no errors.

**Expansion capture**
- AT-05 GA place, depth 9, offline (airplane mode): expand → record
  written, `source_depth = 9`, `partial = 0`, shown set = 9, saved-until
  line shows `expanded_at + 365d` month/year.
- AT-06 JCDH place with detailUrl, online: expand → snapshot =
  union(held, fetchDetail), deduped by (date, type) with catalog winning
  collisions; catalog also updated via the existing updatePlace path.
- AT-07 JCDH place, offline: expand → record written from held only,
  `partial = 1`, partial note rendered; if held empty and fetch fails,
  no record and the error copy shows.
- AT-08 ADPH place: no expand button in any state; Copy A verbatim.
  MCHD place with 4 inspections at D=3: button reads `Show older scores
  (1 more)`; at D=5: no button. FL place with 0 visits: no history
  section; FL place with 8 visits at D=5: button reads `Show older
  visits (3 more)`.
- AT-09 Re-expansion (Refresh) at T+200d: snapshot refreshed,
  `expanded_at`/`expires_at` restarted, `version` incremented, exactly
  one live record for the place, one outbox UPDATE appended.

**Expiry & cleanup**
- AT-10 Boundary: record with `expires_at = T` is live at T−1 ms and
  expired at T — at read time (no cleanup run) and after
  `HistoryCleanup.expire(store, T)`.
- AT-11 Cleanup: expired record → payload dropped (`payload_json = '[]'`),
  tombstone set, outbox DELETE (metadata form, correct sha of the dropped
  payload); live records untouched; second run is a no-op (idempotent);
  run inside a full `SyncEngine.run` reports `historyExpired = 1` and
  leaves `sourcesOk/sourcesFailed` semantics unchanged.
- AT-12 Cleanup failure injection (store throws): sync completes, alerts
  still fire, worker retry decision unchanged.
- AT-13 Cap: seed live payload > 16 MB → oldest-first early expiry to
  under cap; a 10-day-old record is never early-expired; overflow with
  only young records is allowed and counted.

**Survival & isolation**
- AT-14 Pack full-swap (new datasetVersion) and rollback: live expansion
  records and snapshots byte-identical before/after; shown set after swap
  = snapshot ∪ new catalog per §5.1.
- AT-15 Region remove → reinstall (same dataset): expansion reattaches
  automatically (place ids stable); while removed, the record is inert
  and cleanup still expires it on schedule. Region remove provably does
  not delete user-store rows (row count before/after).
- AT-16 One-way valve: after expansion + expiry cycles, catalog
  `inspections` content equals what packs/merges alone would produce;
  no `PlaceEvent` is ever generated from snapshot data (alert inbox
  unchanged across a cleanup run over a favorited, expanded place).
- AT-17 Why-summary: select the oldest inspection of an expanded GA
  place → summary + violations render from that inspection; select an
  FL visit → disposition explainer renders its native result verbatim.

**Adversarial (from Annex A)**
- AT-18 E1: detail screen open on an expanded place; cleanup expires it
  (via injected clock) → no crash; on next render/resume the place shows
  default depth; `inspIdx` clamped if it pointed past the trimmed set.
- AT-19 E3: setting = ALL with a live expansion → shown = all held;
  cleanup still tombstones the record at expiry; setting later changed
  ALL → 5 → place shows last 5 (record already gone).
- AT-20 E7: snapshot contains (date, type) X with score 80; a later pack
  carries X with score 82 → shown set contains X once, with **82**.
- AT-21 E8: backup import where the same place has a live local record
  and a tombstoned imported record with newer `updated_at` → imported
  tombstone wins; no live record remains; no duplicate live rows.
- AT-22 E13: GA place whose history includes a NO_SCORE inspection
  (band-only) → it counts toward depth, renders its band badge in the
  chip/timeline, and is included in snapshots and unions.
- AT-23 Storage: fabricate the §12 worst case (500 records × top-depth
  GA payloads) → user-store file growth ≤ 4.5 MB payload + overhead;
  live-payload sum query used by the cap returns the fabricated total.
- AT-24 Guest-first: every test above runs with no account, no network
  (except AT-06), and no sign-in surface anywhere in the flow.

---

## 14. Files touched (for CSDM scheduling)

**Modified**
- `data/UserStore.kt` — `UserDbHelper` v1 → **v2** (`onUpgrade`: create
  `history_expansions` + indexes; `ALTER TABLE profile ADD COLUMN
  history_depth`); `ProfileRow.historyDepth`; `readProfile` /
  `writeProfile` / `profileJson` (note: `readProfile` reads cursor
  columns positionally — the SELECT list and indices change together);
  `HistoryExpansionRow`; capture/refresh/expire/merge functions + JSON
  payload fns, all following the existing entity patterns.
- `data/Prefs.kt` — `historyDepth` facade property (0 = ALL sentinel
  constant lives here).
- `data/Backup.kt` — export/import of the `history_expansions` section;
  `profile.historyDepth` in profile JSON (absent → 5).
- `ui/DetailActivity.kt` — shown-set funnel at render; history-section
  states S1–S7; expand/refresh button + saved-until + partial lines;
  honest labels (copy deck §6.4); `onResume` re-render; `inspIdx` clamp.
- `res/layout/activity_detail.xml` — expand button, saved-until line,
  count line, ADPH caption line (new view ids; pathData gate unaffected —
  no new vector drawables required; reuse existing icons).
- `ui/AlertsFragment.kt` + its layout — `Score history` settings card
  (§6.5): selector + helper + live-count line.
- `worker/SyncEngine.kt` — cleanup as final step (runCatching-isolated);
  `SyncReport.historyExpired`.

**New**
- `data/HistoryDepth.kt` — pure policy: shown-set computation, union/
  dedup, liveness check, expandability rule. Clock injected everywhere.
- `data/HistoryCleanup.kt` — the §8 expiry pass incl. cap logic (or a
  section of `HistoryDepth.kt` — implementer's call, one file preferred).
- Tests under `~/kyron-build/test/src/` — `HistoryDepthTest.kt`
  implementing §13.

**Explicitly NOT touched in Phase 1**
- `data/db/CatalogDb.kt` (schema stays v2), `data/PackManager.kt`,
  `data/Regions.kt`, `data/WhySummary.kt`, `source/Sources.kt`
  (`fetchDetail` reused as-is), `worker/SyncWorker.kt`,
  `KyronApplication.kt` (12 h cadence unchanged),
  `tools/packs/build_pack.py` and all pack artifacts.

**Sequencing:** build after **FIX5** ships. No dependency on WS-D/WS-F
outputs. TN (prototype in flight) needs nothing here: its pack will slot
into the same data-driven rules by held depth when it lands — **TBD input:
TN held-depth distribution**, to be appended to §2 when the TN prototype
report lands; no TN-specific code is anticipated.

---

## Annex A — Pass-2 adversarial review (self-administered)

Each case was generated by attacking this spec; resolutions are normative.

- **E1 — Cleanup fires while the detail screen is open.**
  The screen holds plain `Inspection` objects from its last render, not
  cursors — nothing can crash. Contract: no live invalidation; the open
  screen keeps its rendered list until the next render, and
  `DetailActivity` re-renders on `onResume` and on every interaction
  (existing pattern). The next render applies expiry (read-time rule,
  §8.3). `inspIdx` is clamped into the new shown set (§5.2). → AT-18.
- **E2 — Expansion vs region-pack removal + reinstall.**
  The snapshot lives in `kyron_user.db`; `PackManager.removeRegion`
  deletes catalog rows + pack artifacts only (different file — it
  *cannot* reach the record). While the region is gone the record is
  inert (no place → no detail screen). Place ids are source-derived and
  stable (`gadph_…`, `fldbpr_…`), so reinstalling the region reattaches
  the still-live expansion automatically. If a later dataset *drops* the
  place (gate exclusions happen — FL dropped 18), the record dangles
  until its expiry reaps it; it can never render against a different
  place because ids are never reused across sources. → AT-15.
- **E3 — Setting = ALL vs cleanup conflict. RESOLVED EXPLICITLY:**
  ALL makes the *default* depth infinite, so expansions become
  unnecessary — the button hides whenever `D ≥ obtainable depth`. But
  cleanup is **not** suspended: records created earlier still expire on
  schedule, because expiry governs *saved snapshots*, and ALL governs
  *display*. With ALL set, expiry has no visible effect (the catalog
  still shows everything it holds). If the user later returns to 5, a
  place whose record expired shows last 5 — correct, and the settings
  helper text (§6.5) says exactly this. No conflict remains: the two
  mechanisms govern different layers (D1).
- **E4 — ADPH favorite later gains history.** Expandability is computed
  from data (`obtainable > shown`), never from a hardcoded source list,
  and the honest label is rendered from current data at render time —
  never cached. If a future ADPH dataset carries history, the label
  disappears and the button appears with no code change. The reverse
  (a source *loses* history in a new pack) degrades identically: the
  snapshot still honors already-saved expansions until expiry.
- **E5 — The yearly-refresh treadmill.** A user who taps Refresh every
  year keeps a place's history forever. **Accepted as designed:** Mark's
  rule is "1 year after the user saved it"; a deliberate re-save is a new
  save. Recorded here so QA does not file it as a bug.
- **E6 — Clock manipulation / bad clocks.** Covered in §8.4. Worst case
  of a wrong clock is early/late expiry of a *view preference*; no data
  of value is at risk (snapshots are re-derivable), and the saved-until
  line always reflects the stored `expires_at`.
- **E7 — Source corrects an inspection after it was snapshotted.**
  Union dedups on `(date, type)` with **catalog winning** (§5.1), so the
  corrected version is what renders; the snapshot contributes only
  inspections the catalog no longer carries. Residual risk: a correction
  that changes the *date or type* itself would duplicate — accepted
  (rare, visible, and the catalog copy is present and correct; the
  stale twin ages out with the snapshot). → AT-20.
- **E8 — Backup-restore rival records.** Natural-key (`place_id`) merge,
  newest `updated_at` wins, rivals tombstoned in-transaction — the exact
  discipline the favorites merge learned in QA (2026-10-13). → AT-21.
- **E9 — Cap pressure vs young records.** Early expiry never touches a
  record < 30 days old; overflow is tolerated and reported rather than
  violating the 1-year promise to a recent saver. The 1-year promise
  outranks the storage cap. → AT-13.
- **E10 — Sync never runs** (force-stopped app, background restrictions).
  Read-time expiry (§8.3) still enforces the display policy the moment
  the user opens the place; only storage reclamation waits. Acceptable:
  the user's *view* is always correct; bytes are reclaimed at the next
  sync whenever it comes.
- **E11 — Cross-region id collision.** Ids embed their source prefix by
  construction (`adph_`, `jcdh_`, `gadph_`, `fldbpr_`, `mchd` flows via
  AL ids); `region_id` is also stored on the record. The shown-set union
  only ever runs for the place whose detail screen is open. No
  cross-place application is possible.
- **E12 — Selection past the trim boundary.** Settings change or expiry
  shrinks the shown set under an open screen: clamp on render (§5.2);
  the why card falls back to the newest shown inspection. → AT-18.
- **E13 — Sentinel-score inspections (GA's 8, FL's everything).**
  Depth counts inspections, not scores (§2). Band-only GA inspections
  render via `badgeText`/`nativeResult` exactly as the catalog renders
  them today, are snapshotted verbatim, and participate in union/dedup.
  → AT-22.
- **E14 — "1 year" across leap years.** Defined as 365 × 86,400,000 ms
  (§8.2), not calendar arithmetic: a Feb 29 expansion expires Mar 1 the
  following year. Intentional, documented, testable (AT-10 uses ms
  boundaries, not calendar dates).
- **E15 — App downgrade with v2 user DB.** A pre-feature build opening a
  v2 `kyron_user.db` hits the existing `UserDbHelper.onUpgrade` no-op
  pattern in reverse (SQLiteOpenHelper refuses downgrades by default).
  Out of scope for this wave (sideload FIX-line builds only move
  forward), flagged for the CSDM: if a downgrade path is ever needed,
  the payload format itself is forward/backward tolerant (§7.2) — only
  the DB version gate is not.

---

## Annex B — Numbers provenance

- AL seed: `~/kyron-build/manual/src/main/assets/places_seed_geocoded.json`
  (23,524 places) — per-source inspection counts and JSON byte sizes
  measured directly.
- FL: `~/kyron-build/harvest/fl_dbpr/OUTPUT/places_fl.json` +
  pack DB `tools/packs/out/us-fl/us-fl-2026-10-15.1.db.gz` (row-payload
  measure: `SUM(LENGTH(violations_json)+…)` over 44,660 inspections).
- GA: `~/kyron-build/harvest/ga/OUTPUT/qa_crosscheck.json`
  (`inspections_per_place` histogram, ALL_PASS) + pack DB
  `tools/packs/out/us-ga/us-ga-2026-10-15.1.db.gz` (138,922 inspections;
  violations_json 121.8 MB total, mean 877 B, max 38,343 B; full row
  payload mean 918 B).
- App behavior citations: `DetailActivity.kt` (history chips render all
  held inspections today; JCDH load button), `SyncEngine.kt` (steps 1–5;
  step 4 enrichment), `CatalogDb.kt` (schema v2, `inspectionsFor`),
  `UserStore.kt` (contract, merge discipline, outbox),
  `KyronApplication.kt` (12 h periodic sync), `PackManager.kt`
  (full-swap/delta/rollback semantics), Presentation Spec §4.6.
