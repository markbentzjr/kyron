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

        // 5) Alerts — AlertEvaluator (context-free) decides; this loop only
        //    reads/writes the persisted metadata and delivers.
        //
        // Persisted metadata (catalog meta table, survives restarts +
        // pack updates + process rollback; removed WITH the region):
        //  - `alerts_baseline:<regionId>`  stamped by PackManager at first
        //    full install, or here at the end of a first successful sync
        //    for a bundled region (Alabama ships with no install step).
        //  - `alerts_evt:<placeId>`        the last event key seen for that
        //    place — repeat deliveries/retries/corrections are judged
        //    against it.
        //
        // Result-model semantics resolve at SOURCE level per place
        // (modelForPlace): unresolved → UNKNOWN, and UNKNOWN never earns
        // an Alabama threshold comparison (or any numeric framing).
        val natcov = com.kyronapp.kyron.data.NationalCoverage
        val coverage = natcov.load(context)
        val baselineSeenBefore = HashMap<String, Boolean>() // regionId -> was baselined BEFORE this cycle
        val baselineStampedThisCycle = LinkedHashSet<String>()
        val regionsTouched = LinkedHashSet<String>()
        var fired = 0
        val seen = HashSet<String>()
        for (e in events) {
            val p = repo.byId(e.new.id) ?: e.new
            if (!seen.add(p.id)) continue
            val regionId = p.regionId
            regionsTouched += regionId
            val isFav = prefs.favorites.contains(p.id)
            val baselineDone = baselineSeenBefore.getOrPut(regionId) {
                repo.metaGet("alerts_baseline:$regionId") != null
            }
            val lastKey = repo.metaGet("alerts_evt:${p.id}")
            val model = natcov.modelForPlace(coverage, p)
            val thresholdApplies = natcov.supportsThresholdAlerts(model)
            val oldScore = e.old?.score
            val inArea = inMonitoredArea(p, prefs)
            val d = AlertEvaluator.evaluate(
                AlertEvaluator.Input(
                    hasPrior = e.old != null,
                    baselineDone = baselineDone,
                    lastEventKey = lastKey,
                    eventKey = p.eventKey,
                    oldDate = e.old?.date,
                    newDate = p.date,
                    isFavorite = isFav,
                    alertsForFavorites = prefs.alertsForFavorites,
                    alertsForArea = prefs.alertsForArea,
                    inMonitoredArea = inArea,
                    thresholdApplies = thresholdApplies,
                    numeric = p.hasNumericScore,
                    belowThreshold = p.hasNumericScore && thresholdApplies && p.score < prefs.threshold,
                    areaEligible = prefs.alertsForArea && thresholdApplies &&
                        p.hasNumericScore && p.score < prefs.threshold && inArea
                )
            )
            // Record the event key for every OBSERVED place (baseline rows
            // too) so later deliveries dedupe and corrections are detected
            // against the real history — never against a date cutoff.
            if (d.kind != AlertEvaluator.Kind.IGNORE) {
                repo.metaPut("alerts_evt:${p.id}", p.eventKey)
            }
            when (d.kind) {
                AlertEvaluator.Kind.SUPPRESS_BASELINE,
                AlertEvaluator.Kind.SUPPRESS_DUPLICATE,
                AlertEvaluator.Kind.IGNORE -> Unit
                AlertEvaluator.Kind.NEW_ESTABLISHMENT -> {
                    if (d.inbox) {
                        prefs.addAlert(
                            AlertItem(
                                p.id,
                                "Newly listed: ${p.name}",
                                "First result on file for ${p.name} (${p.city}) — " +
                                    p.date.ifBlank { "no date on file" } + ". " +
                                    "This is an initial record, not a new inspection result.",
                                System.currentTimeMillis(), false
                            )
                        )
                        fired++
                    }
                }
                AlertEvaluator.Kind.CORRECTED_RECORD,
                AlertEvaluator.Kind.NEW_INSPECTION_LOW,
                AlertEvaluator.Kind.NEW_INSPECTION_NUM,
                AlertEvaluator.Kind.NEW_INSPECTION_TEXT -> {
                    val corrected = d.kind == AlertEvaluator.Kind.CORRECTED_RECORD
                    val nameStar = if (isFav) "★ ${p.name}" else p.name
                    val title: String
                    val body: String
                    if (p.hasNumericScore) {
                        title = if (corrected) "Corrected result for $nameStar: ${p.score}"
                        else "New result for $nameStar: ${p.score}"
                        body = buildString {
                            append("$nameStar (${p.city}) ")
                            append(
                                if (corrected)
                                    "published a corrected result for the ${p.date} inspection"
                                else
                                    "was re-inspected on ${p.date}"
                            )
                            append(" — ${p.score}")
                            oldScore?.takeIf { it != p.score }?.let { append(" (was $it)") }
                            append(". ${natcov.legend(model)}")
                        }
                    } else {
                        val result = p.nativeResult.ifBlank { "recorded" }
                        title = if (corrected) "Corrected result for $nameStar"
                        else "New inspection for $nameStar"
                        body = buildString {
                            append("$nameStar (${p.city}) ")
                            append(
                                if (corrected)
                                    "published a corrected result for the ${p.date} inspection"
                                else
                                    "was re-inspected on ${p.date}"
                            )
                            append(" — result: $result")
                            e.old?.nativeResult
                                ?.takeIf { it.isNotBlank() && it != p.nativeResult }
                                ?.let { append(" (was: $it)") }
                            append(".")
                        }
                    }
                    fire(context, prefs, p, title, body, d.low, d.sysNotify)
                    fired++
                }
            }
        }
        // End-of-cycle baseline stamping, AFTER the loop: this cycle's
        // events were already treated as baseline (suppressed); painting
        // the marker here makes the NEXT cycle the first monitored one.
        // Bundled regions (Alabama) get their baseline here — they never
        // go through a pack install.
        for (regionId in regionsTouched) {
            if (baselineSeenBefore[regionId] != true &&
                baselineStampedThisCycle.add(regionId) &&
                repo.metaGet("alerts_baseline:$regionId") == null
            ) {
                repo.metaPut(
                    "alerts_baseline:$regionId",
                    java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
                        .format(java.util.Date())
                )
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

    /** LF-N: [sysNotify] gates the system notification (the in-app inbox
     *  row is always written by [fire]'s addAlert). Newly listed places use
     *  inbox-only delivery — an informational listing, not an incident. */
    private fun fire(
        context: Context, prefs: Prefs, p: Place,
        title: String, body: String, low: Boolean, sysNotify: Boolean = true
    ) {
        prefs.addAlert(AlertItem(p.id, title, body, System.currentTimeMillis(), low))
        if (sysNotify) Notifier.notify(context, p.id, title, body)
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
