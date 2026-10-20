# Kyron — Build Orchestration

Created Oct 13, 2026 at Mark's request ("add tasks to orchestrate better app building").
This is the standing task structure every Kyron build wave runs through. It encodes Mark's build rules from Oct 13, 2026: set up needed accounts under the Kyron identity, don't stop coding, **test at least twice (nothing ships on a first pass — pass 2 is an independent bug-hunt)**, and outsource to other AI agents — work extremely smart, not hard.

## Ownership — Chief Software Development Manager

On Oct 13, 2026 Mark appointed Zyros **Chief Software Development Manager for Kyron**, accountable for making the app successful. That means Zyros owns: the roadmap and wave sequencing, task assignment to builder/data/research/QA agents, the quality gates below, release decisions (ship / don't ship), and honest status reporting to Mark. Mark remains product owner: he sets direction, makes account/money/stack decisions, and runs the device gate.

**What "successful" means (the scoreboard):**
1. It opens and works — every release passes the device gate on Mark's Z Fold7, zero launch crashes.
2. The data is real — address-level coordinates keep climbing toward full coverage (74.9% after Census; Geocodio residual is the closer); no fake or centroid pins, provenance on every coordinate.
3. It grows — Alabama complete → Florida + Socrata metros via region packs → nationwide adapter coverage.
4. It's fast and usable — presentation-spec performance budgets (B1–B12) met; Google-Maps-style Explore experience.
5. It launches — Play Store: targetSdk 36, closed test passed, public free release, accounts persistent via the migration-ready local store (cloud backend only when a written LF-7 trigger fires).
6. People use it — TikTok @kyronfoodsafety drives installs; audience feedback visibly shapes the backlog.

## The pipeline (every wave)

- **Stage 0 — Chief Software Development Manager (Zyros):** pick the wave's scope from the gameplan + improvement backlog, write each task brief with explicit acceptance gates, assign agents, track the board below, and make the ship / don't-ship call at Stage 4.
- **Stage 1 — Parallel builders, isolated work areas:** one writer per area at a time.
  - App builder → `~/kyron-build/manual/` only
  - Data agent → `~/kyron-build/harvest/<source>/` only (one source per agent)
  - Research agent → read-only, writes only its report
- **Stage 2 — Pass 1 tests (the builder's own):** unit/parser tests against live or fixture data, full build, dex audit (zero NEW missing classes), data validation (counts, provenance, no centroid pins).
- **Stage 3 — Pass 2 QA bug-hunt (independent agent, never the builder):** adversarial pass — tries to break the wave's changes, re-runs the test suite, audits the APK. Defects go back to the builder; QA re-verifies fixes. **A wave does not ship until pass 2 is clean.**
- **Stage 4 — Release gate:** delivered APK md5 must match the verified build output; version/badging checked; META-INF/services merge confirmed; changelog written to the goal files; GitHub export synced.
- **Stage 5 — Device gate (Mark):** Mark installs on his Z Fold7 and confirms it opens + core flows work. Until then a build is "shipped for testing," never "ready."
- **Stage 6 — Feedback loop:** once TikTok clips are live, harvest @kyronfoodsafety comments into the improvement backlog and feed recurring themes into Stage 0 of the next wave.

## Binding product policies (Mark, Oct 13, 2026, 5:43 PM CDT)

1. **No test-account dependencies in production.** The shipped app must not use, embed, or rely on any API key or credential tied to Mark's test/Kyron email account (kyronfoodsafety@gmail.com) or any personal account. Pipeline keys (e.g. Geocodio) are offline-only: they build region packs on our side and are never embedded in the APK or called at runtime. Any future production backend runs under a proper production-owned account.
2. **Guest-first, always.** The app works fully out of the box with no sign-up — browse, map, scores, favorites, alerts all functional in the default local mode. Sign-up, when it exists, is reserved for enhancements only (cross-device sync, instant push), is per-user, and is never a gate for core features or a first-run wall.

Every wave's pass-1 checklist includes an audit for embedded keys/tokens/test-account references; QA pass 2 re-checks it.

## Working rules

- Agents report evidence — test names, counts, checksums — not vibes.
- A failed gate stops the wave at that stage; no skipping ahead.
- Escalate to Mark only for his accounts, his decisions, his money, or the device gate. Everything else, Zyros handles.
- Passwords for Kyron accounts are only ever entered by Mark via Secure Vault cards.

## Task board

### In flight (Oct 13, 2026, ~5:06 PM CDT)
- **K-01** Independent QA bug-hunt (pass 2) on the LF-0→LF-3 build — running
- **K-02** Florida DBPR ingestion prototype (`~/kyron-build/harvest/fl_dbpr/`) — ✅ DONE Oct 13: 70,051 establishments + 44,664 inspection visits normalized, native dispositions preserved, zero invented scores (report: Kyron-FL-DBPR-Prototype-Report.md)
- **K-03** Geocodio free-account signup (Kyron identity) — account CREATED Oct 13 under kyronfoodsafety@gmail.com; email verification still pending Mark entering the Kyron Google password via the secure capture link (browser Google session was signed out). Blocks K-04 only, not LF-4.
- **K-05 / LF-4** — ARMED Oct 13, 5:11 PM CDT: Mark approved "Start LF-4 as soon as QA clears." Trigger instruction sent to the coordinating chat that owns the QA agent: on a clean QA verdict (or defects fixed + re-verified), LF-4 starts immediately with no further check-in, followed by its own independent pass-2 bug-hunt.

### Queued
- **K-04** Geocodio residual geocoding pass — 5,058 addresses / 5,916 places at 2,500/day free; merge with full provenance (status/accuracy/provider), re-run GeoTest. *Depends on K-03.*
- **K-05** LF-4: region packs + state selection — add state/jurisdiction to the data model, remove the hard-coded "AL" in addresses, state picker in the UI, region-pack download/update format (static packs, SHA-256 manifest, N−1 rollback per the free/local-first gameplan).
- **K-06** Integrate Florida DBPR as the first region pack. *Depends on K-02 + K-05.*
- **K-07** LF-5 Socrata wave 1 adapters: NYC, Chicago, San Francisco, King County — reusing the K-02 prototype pattern; native result always shown, never an invented score.
- **K-08** Device gate: Mark confirms the current APK opens and core flows work on his Z Fold7. *Mark's step — gates every "ready" claim.*
- **K-09** Backend decision for persistent accounts: Supabase vs Firebase (see Kyron-Backend-Decision-Brief.md). *Mark's decision — blocks the accounts phase, nothing else.*
- **K-10** LF-6 Play hardening: targetSdk 36, AAB + release signing key, in-app + web account deletion, privacy policy + Data Safety, closed test (12 testers × 14 days).
- **K-11** TikTok feedback harvest → backlog. *Starts when Clip 1 posts; gated on Mark's verdict on Clip 1 v2's warm voice.*
- **K-12 / Wave UX-1 (P0, Kyron 2.1)** — Material 3 UI overhaul, ordered by Mark's verdicts (Oct 13: "UI needs a ton of work… barely usable"; 5:39 PM CDT: "the icons and alerts selection is terrible; app navigation and user friendliness sucks — fix it"). Acceptance gates: (1) real Material icons everywhere, no emoji-as-icons, labels/content descriptions; (2) alerts selection rebuilt — searchable county picker, favorites one-tap path, plain-language threshold control, readable alert-rule cards (the 67-checkbox wall never returns); (3) labeled bottom navigation, predictable back behavior with state/scroll preserved; (4) ≥48dp touch targets, plain-language labels, helpful empty states. Ships only after pass-2 bug-hunt + Mark's device gate. Version bump to versionCode 3 / "2.1".

## How a wave gets reported to Mark
One message per wave: what changed, pass 1 results, pass 2 (bug-hunt) results, the APK checksum, and what the device gate needs from him. No wave is described as "ready" before Stage 5.
