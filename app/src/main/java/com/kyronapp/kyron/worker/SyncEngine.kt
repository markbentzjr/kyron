package com.kyronapp.kyron.worker

import android.content.Context
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.PlaceEvent
import com.kyronapp.kyron.data.PlaceRepository
import com.kyronapp.kyron.data.Prefs
import com.kyronapp.kyron.data.AlertItem
import com.kyronapp.kyron.source.SourceRegistry
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

data class SyncReport(
    val updated: Int,
    val newInspections: Int,
    val alertsFired: Int,
    val sourcesOk: List<String>,
    val sourcesFailed: List<String>
)

/**
 * One sync pass:
 *  1. Pull the Jefferson County latest list (fast) and merge.
 *  2. Re-check favorites against ADPH by name (fast, targeted).
 *  3. Refresh monitored counties from ADPH when due (county queries are heavy).
 *  4. Enrich changed/favorite Jefferson places with violation detail.
 *  5. Fire alerts for new inspections per the user's rules.
 * A failing source never blocks the others, and merging never wipes data.
 */
object SyncEngine {

    suspend fun run(
        context: Context,
        repo: PlaceRepository,
        prefs: Prefs,
        includeCounties: Boolean
    ): SyncReport {
        repo.load()
        val ok = mutableListOf<String>()
        val failed = mutableListOf<String>()
        val events = mutableListOf<PlaceEvent>()

        // 1) JCDH latest
        runCatching { SourceRegistry.jcdh.fetchLatest() }
            .onSuccess { fresh ->
                events += repo.mergeFresh(fresh)
                ok += "JCDH"
            }
            .onFailure { failed += "JCDH" }

        // 2) Favorites via ADPH name search (skip ones JCDH already covers well)
        val favPlaces = prefs.favorites.mapNotNull { repo.byId(it) }
        var adphUsed = false
        for (fav in favPlaces) {
            if (fav.source != "ADPH") continue
            adphUsed = true
            runCatching { SourceRegistry.adph.fetchByName(fav.name) }
                .onSuccess { results ->
                    val matches = results.filter {
                        Place.matchKey(it.name, it.zip, it.address) ==
                            Place.matchKey(fav.name, fav.zip, fav.address)
                    }
                    if (matches.isNotEmpty()) events += repo.mergeFresh(matches)
                }
                .onFailure { if (!failed.contains("ADPH")) failed += "ADPH" }
        }
        if (adphUsed && !failed.contains("ADPH")) ok += "ADPH (favorites)"

        // 2b) Favorites in Mobile County — MCHD publishes one full table, so a
        // single fetch covers every Mobile favorite at once.
        if (favPlaces.any { it.source == "MCHD" }) {
            runCatching { SourceRegistry.mchd.fetchAll() }
                .onSuccess { fresh ->
                    val favKeys = favPlaces.filter { it.source == "MCHD" }
                        .map { Place.matchKey(it.name, it.zip, it.address) }.toSet()
                    val matches = fresh.filter {
                        Place.matchKey(it.name, it.zip, it.address) in favKeys
                    }
                    if (matches.isNotEmpty()) events += repo.mergeFresh(matches)
                    ok += "MCHD (favorites)"
                }
                .onFailure { failed += "MCHD" }
        }

        // 3) Monitored counties (heavy; only when due or explicitly requested)
        val now = System.currentTimeMillis()
        val countyDue = now - prefs.lastCountySyncMs > 20 * 60 * 60 * 1000L
        if (includeCounties || countyDue) {
            var anyCountyOk = false
            for (county in prefs.monitoredCounties) {
                // Jefferson is covered by the JCDH feed above (ADPH delegates
                // Jefferson to JCDH and returns nothing for it).
                if (county == "Jefferson") { anyCountyOk = true; continue }
                // Mobile is an independent health department — not in ADPH.
                if (county == "Mobile") {
                    runCatching { SourceRegistry.mchd.fetchAll() }
                        .onSuccess { fresh -> events += repo.mergeFresh(fresh); anyCountyOk = true; if (!ok.contains("MCHD")) ok += "MCHD" }
                        .onFailure { if (!failed.contains("MCHD")) failed += "MCHD" }
                    continue
                }
                runCatching { SourceRegistry.adph.fetchCounty(county) }
                    .onSuccess { fresh -> events += repo.mergeFresh(fresh); anyCountyOk = true }
                    .onFailure { if (!failed.contains("ADPH")) failed += "ADPH" }
            }
            if (anyCountyOk) {
                prefs.lastCountySyncMs = now
                if (!ok.contains("ADPH (counties)")) ok += "ADPH (counties)"
            }
        }

        // 4) Enrich Jefferson places with violation detail where it matters
        val enrichTargets = LinkedHashMap<String, Place>()
        events.forEach { e -> if (e.new.source == "JCDH" || e.new.county == "Jefferson") enrichTargets[e.new.id] = e.new }
        favPlaces.forEach { p -> if (p.detailUrl != null && p.inspections.isEmpty()) enrichTargets[p.id] = p }
        for (target in enrichTargets.values.take(12)) {
            val url = target.detailUrl ?: continue
            runCatching { SourceRegistry.jcdh.fetchDetail(target.copy(detailUrl = url)) }
                .onSuccess { insps ->
                    if (insps.isNotEmpty()) {
                        val cur = repo.byId(target.id) ?: target
                        repo.updatePlace(cur.copy(inspections = insps))
                    }
                }
        }

        // 5) Alerts
        var fired = 0
        val seen = HashSet<String>()
        for (e in events) {
            val p = repo.byId(e.new.id) ?: e.new
            if (!seen.add(p.id)) continue
            val isFav = prefs.favorites.contains(p.id)
            val oldScore = e.old?.score
            if (isFav && prefs.alertsForFavorites) {
                if (p.hasNumericScore) {
                    val title = "New score for ★ ${p.name}: ${p.score}"
                    val body = "${p.name} (${p.city}) was re-inspected on ${p.date} and scored ${p.score}" +
                        (oldScore?.let { " (was $it)" } ?: "") + "."
                    fire(context, prefs, p, title, body, p.score < prefs.threshold)
                } else {
                    // LF-4: disposition jurisdictions (e.g. Florida DBPR)
                    // publish an outcome, not a score. Never render the
                    // NO_SCORE sentinel as a number, and never call the
                    // result "low" — there is no scale to be low on.
                    val result = p.nativeResult.ifBlank { "recorded" }
                    val title = "New inspection for ★ ${p.name}"
                    val body = "${p.name} (${p.city}) was re-inspected on ${p.date} — " +
                        "result: $result" +
                        (e.old?.nativeResult?.takeIf { it.isNotBlank() && it != p.nativeResult }
                            ?.let { " (was: $it)" } ?: "") + "."
                    fire(context, prefs, p, title, body, false)
                }
                fired++
                continue
            }
            if (prefs.alertsForArea && p.hasNumericScore && p.score < prefs.threshold && inMonitoredArea(p, prefs)) {
                val title = "Low score near you: ${p.name} scored ${p.score}"
                val body = "${p.name} (${p.city}) posted a new score of ${p.score} on ${p.date}, " +
                    "below your threshold of ${prefs.threshold}."
                fire(context, prefs, p, title, body, true)
                fired++
            }
        }

        prefs.lastSyncMs = System.currentTimeMillis()
        return SyncReport(
            updated = events.size,
            newInspections = events.size,
            alertsFired = fired,
            sourcesOk = ok,
            sourcesFailed = failed
        )
    }

    private fun fire(context: Context, prefs: Prefs, p: Place, title: String, body: String, low: Boolean) {
        prefs.addAlert(AlertItem(p.id, title, body, System.currentTimeMillis(), low))
        Notifier.notify(context, p.id, title, body)
    }

    fun inMonitoredArea(p: Place, prefs: Prefs): Boolean {
        if (prefs.monitoredCounties.contains(p.county)) return true
        val lat = p.lat ?: return false
        val lng = p.lng ?: return false
        return haversineMiles(prefs.homeLat, prefs.homeLng, lat, lng) <= prefs.radiusMiles
    }

    fun haversineMiles(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val r = 3958.8
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a = sin(dLat / 2) * sin(dLat / 2) +
            cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * r * asin(sqrt(a))
    }
}
