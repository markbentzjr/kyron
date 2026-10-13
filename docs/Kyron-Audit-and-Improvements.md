# Kyron — Audit & Improvement Report

**Date:** October 13, 2026
**APK audited:** `Kyron_4_0run.apk` — 82 MB, SHA-256 `b2e8d37c0bda96083aa3e8295ef8ccc7d8fc8e02417f579555b957479d4a0bf2`
**Package:** `com.example.kyron` · **Internal version:** versionCode 1 / versionName 1.0 · minSdk 33 (Android 13), targetSdk 37

## What Kyron is (from the APK itself)

An Alabama restaurant health-score app built with Kotlin + Jetpack Compose (Material 3), Hilt, Room, WorkManager and OkHttp/Jsoup:

- **List** of food establishments with search, county filter, minimum-score filter, category exclusions, and distance-from-home filtering (haversine, Earth radius 3,958.8 mi)
- **Map** screen, **restaurant detail** screen with inspection history, **settings** (monitored counties, score threshold, alerts toggle, home location, monitor radius)
- **Data sources (scrapers):** Jefferson County (JCDH), Montgomery County (ArcGIS), ADPH statewide, plus a Mock scraper
- **Background sync** every 12 hours (`SyncDataWork`, requires network) with notifications when a monitored restaurant drops below your score threshold
- **Android App Functions** integration: `findRestaurantScore(name)` so an assistant can answer "what's the health score of X?"
- Score bands in the UI: **95+ Excellent · 85–94 Good/Fair · <85 Needs Improvement**

The architecture is genuinely good — repository pattern, polite scraping (custom user-agent `KyronHealthApp/1.0`, 2 requests/second rate limit, 30s timeouts). The problems below are specific, fixable bugs — not design flaws.

## How this was verified

The APK was unpacked and its own code (267 Kyron classes across 19 dex files) was disassembled and read: manifest, DI modules, repository, DAOs (including the raw SQL), scrapers, sync worker, preferences, and the App Function. All three live data sources were also tested directly on Oct 13, 2026.

**Live source status (checked Oct 13, 2026):**

| Source | Status |
|---|---|
| JCDH — jcdh.org FoodServScores.aspx | ✅ Live (HTTP 200), same page structure and detail links the scraper expects |
| ADPH — foodscores.state.al.us | ✅ Live (HTTP 200 after its normal session redirect — the scraper's ViewState postback flow still applies) |
| Montgomery — gis.montgomeryal.gov ArcGIS FoodScores | ❌ **Dead — HTTP 404.** The whole `/arcgis` path is gone on that host, and no FoodScores service exists on the city's new GIS host (mgmgis.montgomeryal.gov). The city relaunched its open-data portal in March 2025; the service appears to have been retired in that move. |

---

## Findings, in priority order

### P0 — Fake restaurants are in your real database
`RepositoryModule` wires **four** scrapers into the production repository — JCDH, Montgomery, ADPH **and `MockScraper`**. The mock injects three invented Birmingham restaurants into the real database on every sync:

- *Southern Comfort BBQ* — 1200 6th Ave S, Birmingham — score 98
- *Iron City Pizza Co* — score 94
- *Bama Burger Express* — 2101 Highland Ave, Birmingham — score **82**

They show up in your list and map, the 82 can trigger a "below threshold" health alert, and `findRestaurantScore` can return a fake score to an assistant query. **Fix included in the pack** (MockScraper removed from production wiring).

### P0 — The map's Google API key is a placeholder
The manifest contains:

```
com.google.android.geo.API_KEY = "YOUR_API_KEY_HERE"
```

So the Google Maps screen can never load tiles as shipped. Kyron also bundles **osmdroid** (OpenStreetMap) — a second, complete map stack that needs no key and is already configured in `KyronApplication`. Carrying two map stacks is also a big part of why the APK is 82 MB. **Recommendation (in BUILD_FIXES.md):** drop Google Maps, switch the map screen to osmdroid. No key, no billing account, offline tile caching possible — and a much smaller APK. If you'd rather keep Google Maps, the alternative (real, restricted API key) is also documented there.

### P0 — One dead source can erase other restaurants, silently
`HealthScoreRepository.refreshData()` aggregates whatever the scrapers return, then `RestaurantDao.refresh()` runs **`DELETE FROM restaurants`** followed by insert — a global wipe-and-replace. Combined with per-scraper errors being swallowed (`printStackTrace()` and continue):

- Montgomery now returns nothing (404) on every sync, so any Montgomery rows are wiped on the next refresh and never come back — with no error shown anywhere.
- The same would happen to *any* county whose source has a bad day.
- `SyncWorker` reports success even when every source fails, so WorkManager never retries and you never learn your data is stale.

**Fix included in the pack:** the new repository keeps existing rows for counties a failed/empty source covers, returns a per-source `RefreshReport`, and the new `SyncWorker` retries when (and only when) all sources fail.

### P1 — Inspection history is a dead feature
The detail screen has an "Inspection History" section, `InspectionDao` has `insertAll()`, and the DB has an `inspections` table — **but nothing in the app ever inserts an inspection.** The section can only ever say "No inspections recorded." **Fix included in the pack:** every refresh now writes an inspection row (deterministic ID `restaurantId_date`, insert-or-replace) for each restaurant that has a score and date, so history starts accumulating from the next sync and repeat syncs don't duplicate rows.

### P1 — You're running a debug build
The manifest has `android:debuggable="true"` and `android:testOnly="true"` — this is an IDE "Run" build, not a release build. That means no code shrinking/obfuscation (part of the 82 MB), slower Compose performance, an exported Compose `PreviewActivity` shipped to production, and a build that can't be distributed properly. Internal version is still 1.0/1 no matter how many "4.0" runs you've made. **Fix documented in BUILD_FIXES.md** (release build type with minify + shrinkResources, version bump, remove testOnly).

### P1 — Montgomery scraper has no pagination (for when a source returns)
The ArcGIS query is a single `where=1=1` request. ArcGIS caps responses (typically 1,000–2,000 records) and flags truncation with `exceededTransferLimit` — which the scraper ignores, so a restored Montgomery source would silently lose every record past the cap. **Fix included in the pack:** the rewritten `MontgomeryScraper` pages with `resultOffset`/`resultRecordCount` until the flag clears, throws on HTTP errors (so the repository can preserve old data), and keeps the endpoint in one clearly-marked constant at the top of the file.

### P2 — Background sync can never be updated
`scheduleSync()` enqueues the 12-hour periodic work with `ExistingPeriodicWorkPolicy.KEEP`. Any future change to interval or constraints in an update will be silently ignored on phones that already ran the old version. No backoff criteria are set either. **Fix documented in BUILD_FIXES.md** (switch to `UPDATE`, add exponential backoff) — a two-line change in `KyronApplication.scheduleSync()`.

### P2 — App Function returns the *first* name match, not the best
`findRestaurantScore` loads all restaurants and returns the first whose name *contains* the query (case-insensitive). Asking about "Burger" can return the wrong place — including, today, the fake Bama Burger Express (see P0). **Fix described in BUILD_FIXES.md:** rank exact match > starts-with > contains, prefer a real (non-null) score, then the newest inspection date.

### P2 — Dead weight in the APK
Bundled but unused by Kyron's own code (no references in any Kyron class): **CameraX** (including its native libraries and a disabled camera service in the manifest), **AppSearch**, **Retrofit** (Kyron uses raw OkHttp), and the **Google Maps + osmdroid** duplication from P0. Removing these plus building a release build should take the APK from 82 MB down dramatically. Checklist in BUILD_FIXES.md.

### P3 — Smaller items
- **Compiled against a preview SDK** (compileSdk/targetSdk 37, "17"). Pin production builds to the latest *stable* SDK.
- `fallbackToDestructiveMigration()` on the Room DB — acceptable for a cache, but it means any future schema change wipes saved data without warning. Fine today; know it's there.
- `allowBackup="true"` — the local DB (your home location + preferences) is included in cloud backups. Consider excluding the database via data-extraction rules if that matters to you.
- Alerts only re-notify when a score *changes* — which is correct behavior, kept as-is in the pack's SyncWorker.
- ADPH note: the statewide scraper and the county scrapers overlap (Jefferson restaurants exist in both). IDs are source-prefixed (`jcdh_`, `adph_`, `montgomery_`), so duplicates can appear as separate rows if ADPH rows carry real counties later — worth a dedupe pass (name+address) in a future version.

## What's in the Fix Pack (`Kyron-Fix-Pack.zip`)

Drop-in files, written against your actual code (same package names, class names, constructor signatures and DAO methods as in the APK):

1. `di/RepositoryModule.kt` — production scraper list: JCDH + ADPH only. Mock removed, Montgomery parked with the reason documented in-line.
2. `data/repository/HealthScoreRepository.kt` — failure-safe refresh (preserves data from failed sources), writes inspection history, returns a per-source `RefreshReport`.
3. `worker/SyncWorker.kt` — uses the report: retries only on total failure, keeps your alert logic (monitored counties + threshold + notify on change/new).
4. `data/remote/scraper/MontgomeryScraper.kt` — paginated, error-throwing rewrite, ready to re-enable the moment a working Montgomery endpoint exists (endpoint is a single constant at the top). Note: in your project all scrapers live in one `Scrapers.kt` file (verified from the APK), so this class is pasted into that file in place of the old MontgomeryScraper class — the pack's README spells this out.
5. `BUILD_FIXES.md` — release-build configuration, the maps decision (osmdroid vs. real API key), sync-policy patch, App Function ranking snippet, unused-dependency removal checklist, SDK pinning.

Each file's header comment lists exactly what changed and why.

## What I could not do from the APK alone

An APK is compiled output — I could audit it completely, but I can't rebuild an installable improved APK from it (no signing key, and decompiled code isn't a buildable project). To take the last step I need **the original project** — the source folder/zip from whatever tool built Kyron. Upload that and I'll apply this pack to it directly, make the build fixes, and hand you back a ready-to-build improved project (and, if the project includes its keystore, a built APK).

Two decisions are also yours, and they're one-tap answers in chat:
1. **Map:** switch to osmdroid (recommended) or keep Google Maps with a real API key?
2. **Montgomery:** park it until a new official source appears (recommended), or should I dig deeper for an alternative Montgomery County data source?
