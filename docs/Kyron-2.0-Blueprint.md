# Kyron 2.0 — Product Blueprint

*Built from Mark's vision (Oct 13, 2026) and verified against the live data sources the same day.*

## The product in one paragraph

Kyron tells you whether the food at a place is safe — and warns you when that changes. Browse restaurants and other food establishments the way you'd browse Google Maps, tap any place to see its health-inspection score **and a plain-language summary of why it got that score**, favorite the places you care about, and get alerted when a favorite gets a new score or when a place in an area you chose posts a bad score. Free on the Play Store, with your own account and your own alerts.

## Features, mapped to what you asked for

### 1. Alerts that work the way you described
- **Favorites alerts:** star any place → you get a push notification whenever it receives a **new inspection score** (good or bad).
- **Area alerts:** pick an area — a pin + radius ("within 5 miles of home"), a ZIP, or a whole county — and set a threshold (default 85, Alabama's reinspection line). When a **new score below your threshold** posts inside that area, you get an alert.
- Alerts fire on *new inspections*, not on a timer re-checking old scores — no spam, no repeats for the same inspection (each inspection has a unique ID: permit + inspection number + date).
- Every alert opens the place page, with what changed: "New score 84 (was 92) — below your 85 threshold."

### 2. "Why does it have this score?" — the signature feature
Verified Oct 13, 2026: Jefferson County's detail pages publish, for **each inspection**, every violation with the points deducted and the inspector's own notes. That is everything a why-summary needs. Example, from a real inspection harvested during testing (a Graysville gas station, scored 85):

> **Why an 85?** It lost 15 points. The biggest problem was food temperature (5 pts): milk sitting at 50°F in a cooler that must stay at or below 41°F — it was thrown out during the inspection. Next, no paper towels at a handwashing sink (4 pts). The rest was housekeeping: stained ceilings and splattered walls (2), dirty equipment surfaces (1), a leaking faucet (1), dead insects in the back (1), and the previous inspection report not posted (1).

The summary generator works in three layers:
1. **Structured facts** — violations sorted by points, grouped into plain categories: Food temperature · Handwashing · Cleanliness · Food storage/contact surfaces · Plumbing & repairs · Pests · Equipment · Paperwork/posting.
2. **Inspector evidence** — the short observation after "//" in each violation (e.g. "Milk in RI cooler at 50F") quoted or lightly paraphrased.
3. **Verdict line** — score band in plain words: 95+ Excellent · 85–94 Good/Fair (note: below 85 Alabama requires reinspection within 60 days) · <85 Needs improvement.

Version 1 of the generator is rules-based (deterministic, testable, no AI cost). An AI-polish layer can come later for tone, never for facts.

### 3. Browse like Google Maps
- **Map-first home:** OpenStreetMap (your choice — no API key, no billing) with pins colored by score band: green 95+, yellow-green 85–94, orange <85, grey = no recent score.
- Drag the map → "Search this area" refreshes results; a bottom sheet lists the places in view, sorted by distance or worst-score-first.
- **Place pages** modeled on Google Maps listings: name, address, big score badge, score trend (history chart from all inspections), the Why card, full violation list per inspection, inspection history, buttons: Favorite ★, Directions (opens your maps app), Share, "Alert me about this place."
- Search by name, filter by score band/category (restaurant, grocery, school, daycare, gas station — categories Kyron already infers).

### 4. Accounts & personal data
- Each user signs in (Google Sign-In or email) and gets: favorites, saved areas, alert rules, threshold, notification history. Settings sync across devices.
- Guest mode: browse everything without an account; account required only for alerts/favorites sync.
- Play Store rules this triggers: in-app account deletion + a web deletion page, privacy policy, Data Safety section. All planned below.

## What testing proved (Oct 13, 2026)

| Capability | Result |
|---|---|
| JCDH latest-scores list | ✅ Live; 50 most recent inspections with permit, score, name, address, date + a detail link per inspection |
| JCDH detail pages | ✅ **The gold mine:** up to 4 inspections per place, each with score, date, type, and every violation with points deducted, critical flag, rule text, and inspector notes |
| Score math | ✅ Verified: deductions sum exactly to 100 − score (85 = 15 pts of violations) |
| ADPH statewide search | ⚠️ Form confirmed (search by name / city / county — all 67 counties, numeric county codes, ViewState postback, matching Kyron's existing scraper design) **but bulk queries are slow** — a county query didn't finish in 30s. Conclusion: ADPH must be ingested server-side in small chunks (by city), never scraped from phones |
| Montgomery County | ❌ Source retired (404; nothing on the city's new GIS host). Launch coverage = Jefferson County + ADPH-covered counties as ingestion matures; Montgomery returns if an official source reappears |
| Geocoding addresses → map pins | ✅ OpenStreetMap Nominatim works with Kyron's addresses (used for the prototype dataset) |

## Architecture — why v2 needs a small backend

Kyron 1.x scrapes websites on each phone. That cannot support accounts, shared alert rules, or push alerts (a phone that's off can't warn you, and the ADPH query alone can take 30s+). Version 2:

```
County/State sites ──► INGESTION (server, scheduled every few hours)
                          • fetch latest lists + changed detail pages
                          • parse violations, geocode new addresses
                          • diff vs database → emit "new inspection" events
                              │
                              ▼
                       DATABASE (places, inspections, violations)
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
        APP API (read)                  ALERT ENGINE
   search / map / place pages     match events vs users' favorites,
                                  areas + thresholds → FCM push
              │                                │
              └──────────► ANDROID APP ◄───────┘
             accounts (Auth), favorites, areas, alerts inbox
```

**Recommended stack (keeps "free" realistic):**
- **Firebase** — Auth (Google/email), Firestore (places + user data), Cloud Functions (ingestion + alert engine on a schedule), Cloud Messaging/FCM (push), Crashlytics. Spark (free) tier covers development and early launch; Blaze pay-as-you-go at this scale is typically a few dollars/month. One console, made for Android.
- Alternative considered: Supabase (Postgres + Auth + Edge Functions) — also good, and cheaper at some scales; Firebase wins here on push integration and Android tooling.
- App stays Kotlin/Compose with the fix pack applied (osmdroid map, fixed repository, working inspection history), plus new screens from this blueprint.
- **Not** scraped from phones anymore: the app reads the API only. Faster, battery-friendly, and a source-site change breaks one server job (which alerts *us*), not every user's phone.

## Keeping it free — money notes
- Costs at launch scale: Firebase free tier → likely $0 for months; domain for privacy policy/deletion pages ~$12/yr; Play developer account $25 one-time (Google's fee).
- **Advertising (later, Phase 5):** AdMob banner on list screens + a native ad in the results feed; never on alert flows or blocking place pages. Requires Google's consent (UMP) flow and a Play "Contains ads" declaration. Realistic expectation: ads on a local utility app pay little until there's real traffic — treat as Phase 5 pocket money, not the business model. A "Kyron Plus" tier (unlimited favorites/areas, no ads) is the more reliable lever if it grows.

## Play Store launch checklist (baked into the plan)
- [ ] Real package name — `com.example.kyron` cannot be published; pick e.g. `com.kyronapp.kyron` early (it can never change after first publish)
- [ ] Release build, signed with an upload key, Play App Signing on (fix pack)
- [ ] Target the latest **stable** Android SDK Google requires at submission time (v1 was built against a preview SDK)
- [ ] Privacy policy page + Data Safety form (location is optional/approximate; account data; no data sold)
- [ ] In-app account deletion + public web deletion link (Google requirement for account apps)
- [ ] Content rating questionnaire; "scores are public health-department data, shown as-is" disclaimer with source attribution (JCDH / ADPH)
- [ ] Store listing: screenshots from the real app, feature graphic, short/full descriptions (drafted in Phase 4)
- [ ] Closed test track first (Google requires a closed test with ≥12 testers for 14 days for new personal developer accounts before production)

## Phases

- **Phase 0 — Prototype (today).** Clickable Kyron 2.0 running on real harvested Jefferson County data: map browse, place pages with Why summaries and history, favorites, area+threshold alert settings, and a simulated "new inspection" alert so you can feel the whole loop.
- **Phase 1 — Data pipeline.** Server ingestion for the full Jefferson County catalog (JCDH search covers every establishment, not just the latest 50) + ADPH chunked by city; parser test-suite built from saved real pages so site changes get caught in tests, not by users.
- **Phase 2 — Android app v2.** Fix pack + accounts, favorites, areas, Why pages, osmdroid browse. (Needs the original project from you, or we rebuild the app project fresh against this blueprint — a fresh project is honestly viable now that the blueprint + parsers are proven.)
- **Phase 3 — Alerts engine.** Event diffing, rule matching, FCM push, in-app alerts inbox, per-user sync.
- **Phase 4 — Store launch.** Checklist above, closed test, listing, launch Jefferson-first ("Every Jefferson County food score, explained").
- **Phase 5 — Growth.** More counties via ADPH, Montgomery if a source returns, AdMob, possible Plus tier.

## Risks & honest unknowns
- **Source fragility:** county sites can change layout (it happened to Montgomery). Mitigation: server-side parsers + golden-file tests + monitoring; one fix heals all users.
- **Data freshness:** JCDH's public list shows the latest ~50 inspections; full-catalog freshness depends on scheduled search crawls. The app will always show "last updated" honestly.
- **Why-summary accuracy:** rules-based summaries only restate the inspector's recorded deductions — no invented facts. Inspector notes are public records.
- **Accounts add obligations:** privacy policy, deletion, breach basics. Firebase handles the heavy lifting; the checklist above covers the rest.
