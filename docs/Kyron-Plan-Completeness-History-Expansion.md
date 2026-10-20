# Kyron Plan — Completeness, History Depth & the 47-State March
Mark's directives, Oct 15, 2026 (evening). Owner: Zyros (CSDM). Standing rules unchanged: test twice (independent pass 2), no invented data, verified address-level pins only, guest-first, no test-account dependencies, builds staged to CSDM — never direct to Mark.

## Mark's directives (verbatim intent)
1. **Completeness is the main thing:** "we capture ALL scores and have them on the app in the right location." A missing restaurant is the worst defect class.
2. **Geocoding:** he dislikes the Geocodio 2,500/day free-tier limit and asked why we can't "use the address for location" — clarification for the record: we DO geocode from the restaurant's own address; coordinates are computed once in the offline pipeline and shipped inside the app/packs, so every user's phone just reads them (no per-user calls, no keys in the app, works offline). The limit binds only the mop-up of addresses Census lacks. Response: add more free sources (Step 4) so Geocodio is an accelerator, not a gate.
3. **Score history as a setting:** default = last 5 scores per restaurant; per-restaurant button to search/load older scores; expanded history saved locally; automatic cleanup: 1 year after the user saved the expanded history, it reverts to the default last-5.
4. **States:** Georgia done — "only 47 more to go." Keep marching (Step 5).

## Step 1 — P0: The Chelsea McDonald's + completeness audit (data wave, starts now)
- Target record: McDonald's, 16758 US-280, Chelsea, AL 35043 (Shelby County; Google Maps link from Mark). Determine: in shipped seed? pinned? which source (ADPH Shelby)? If absent or pinless, root-cause at harvest/parser/dedup/gate level — no anecdote fixes.
- County-by-county reconciliation: seed counts vs source listing counts for all 67 AL counties (and per-source for JCDH/MCHD); every gap explained or fixed.
- Address/name variant sweep: highway formats (US-280 / Hwy 280 / Highway 280), apostrophes, suite numbers, "#xxxx" store numbers — search the app the way a user would.
- **Canary gate (new, permanent):** a curated list of known establishments per county (chains + landmarks) that MUST be present (and pinned or explicitly accounted) or the build fails — same class as the seed-validation and pathData gates.
- Output: report + remediated seed; ships as a data update on the FIX line after independent QA recount.

## Step 2 — FIX5: Georgia registration (already decided)
- One RegionInfo entry for us-ga (+ cosmetic source-name line), rebuild, independent pass 2, Mark's device gate.
- Then publish FL + GA packs in one session (packs first, manifests last).

## Step 3 — Score-history depth feature (wave after FIX5; spec now)
- Data reality first: history depth = what the source publishes. JCDH: full history. MCHD: up to 4 inspections. ADPH: latest score + date only (no published history — show latest, label honestly). FL: inspection visits. GA: ~4.1 inspections/place average (138,922 / 33,514).
- App behavior:
  - Global setting: default history depth = **last 5 scores** (options e.g. 3 / 5 / 10 / all available).
  - Per-restaurant: "Show older scores" button loads the deepest history the pack/source holds for that place; where the source supports live detail (e.g. JCDH), refresh may fetch more.
  - Persistence: expanded history is stored in the user store with `history_expanded_at` timestamp.
  - Cleanup (automatic, default on): when an expansion is 1 year old, drop back to the default last-5 for that place. Cleanup runs inside the existing background sync cycle; no user action.
  - Guest-first: all of this works with no sign-up (on-device), per standing policy.
- Pass 1 build + independent pass 2 (storage/cleanup edge cases: clock changes, depth-setting changes, pack updates replacing catalog while expanded history persists).

## Step 4 — Geocoding residual: more free weapons (parallel, pipeline-only)
Current AL residual: 4,812 places / ~4,103 unique addresses (Census-exhausted).
1. **USDOT National Address Database (NAD)** + state/county E911 address-point layers: exact address-point matches, free, unlimited, storable.
2. **OpenStreetMap/Nominatim** (self-hosted or policy-compliant throttled use): strong on highway/rural addresses.
3. Census alternate strategies/vintages for the remainder.
4. **Geocodio free tier (2,500/day)** once Mark's key lands: mop-up only — report the residual AFTER steps 1–3 so the key ask shrinks or disappears.
- Rules unchanged: verified address-level only, provenance per pin, no centroid/jitter pins.

## Step 5 — The state march (47 to go)
Order (research-ranked): **TN** (prototype in flight) → **SC** → **NC** → Socrata wave (NYC, Chicago, SF, King County) → remaining statewide portals → county-by-county states last.
Per state, the proven conveyor: prototype (source audit, zero invented) → gate (incl. Step 1 canaries + orphan-score gate) → geocode (Step 4 stack) → pack → registration rides the next build → publish with pass 2 + device gate.
Reality note for expectations: states with statewide portals move fast (FL, GA did); states fragmented by county will be slower and batched.

## Sequencing summary
Step 1 (now, P0) ∥ Step 4 (pipeline, parallel) → Step 2 FIX5 → FL+GA publish → Step 3 history wave → Step 5 marching throughout (TN prototype already in flight).
