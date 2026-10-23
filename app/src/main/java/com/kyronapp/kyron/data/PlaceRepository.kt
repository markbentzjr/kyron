package com.kyronapp.kyron.data

import android.content.Context
import com.kyronapp.kyron.data.db.CatalogDb
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A detected change: a place received a new inspection (date/score changed). */
data class PlaceEvent(val old: Place?, val new: Place)

/** Structured catalog query shared by Browse and Map (Stage D unified query). */
data class PlaceQuery(
    val text: String = "",
    val county: String? = null,
    val band: String = "All scores",
    val sort: String = "Worst first",
    val limit: Int = 500
)

/**
 * Owns the place catalog (LF-2): a SQLite catalog store behind this
 * repository interface, replacing the whole-JSON-file design.
 *
 *  - First launch imports the bundled geocoded seed — or, on an upgraded
 *    device, the legacy places.json (+ geocache) so no merged data or
 *    device-geocoded coordinates are lost — into indexed tables once.
 *  - Merges write only changed rows in one transaction (never a
 *    whole-catalog rewrite); reads are targeted SQL queries.
 *  - [places] remains as a loaded snapshot flow for the screens that
 *    still consume it, refreshed from the DB after writes.
 */
class PlaceRepository(private val context: Context) {

    companion object {
        /** Meta key holding the SHA-256 of the bundled seed this catalog
         *  was last refreshed from (Workstream D / FIX5). Absent on every
         *  catalog created before the fix — which is exactly the aged-DB
         *  population the refresh exists to heal. */
        const val META_BUNDLED_SHA = "bundled_seed_sha:us-al"
    }

    private val catalog = CatalogDb(context)
    val packs: PackManager = PackManager(context, catalog)
    private val appContext = context.applicationContext

    private val _places = MutableStateFlow<List<Place>>(emptyList())
    val places: StateFlow<List<Place>> = _places

    @Volatile private var loaded = false

    suspend fun load() {
        if (loaded) return
        withContext(Dispatchers.IO) {
            val db = catalog.writableDatabase
            if (catalog.placeCount(db) == 0) {
                val importedBundled = importInitial(db)
                if (importedBundled) {
                    // Fresh install from the bundled seed: record its
                    // fingerprint so a later seed change is detectable.
                    bundledSeed()?.let { (_, sha) ->
                        catalog.metaPut(db, META_BUNDLED_SHA, sha)
                    }
                } else {
                    // The catalog was seeded from a LEGACY places.json
                    // (pre-SQLite app): its rows predate the bundled
                    // seed's geocoding. Refresh the bundled region from
                    // the current seed right away — this is the exact
                    // state that left upgraded phones serving a pre-
                    // geocode catalog (and a pin-less map) forever.
                    refreshBundledRegion(db)
                }
            } else {
                refreshBundledRegionIfSeedChanged(db)
            }
            // Self-heal: the FTS index must mirror the places table.
            catalog.reconcileFts(db)
            _places.value = catalog.allPlaces(db)
            loaded = true
        }
    }

    /** The bundled region's seed (staged sideload file wins over the APK
     *  asset — same precedence as the first import, minus the legacy file,
     *  which is a one-time migration source, never a refresh source) plus
     *  its SHA-256 fingerprint. Null when unreadable. */
    private fun bundledSeed(): Pair<String, String>? = runCatching {
        val stagedSeed = File(appContext.filesDir, "places_seed_geocoded.json")
        val text = if (stagedSeed.exists()) stagedSeed.readText() else readAssetSeed()
        val sha = java.security.MessageDigest.getInstance("SHA-256")
            .digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        text to sha
    }.getOrNull()

    /**
     * Workstream D / FIX5 — the catalog-refresh trigger that did not exist:
     * before this, load() imported the bundled seed ONLY into an empty
     * catalog, so no bundled-seed improvement (the LF-1 Census pins, the
     * FIX4 name restorations and orphan drops, Workstream A's +1,099 pins)
     * EVER reached a device that had installed an earlier build — its
     * catalog stayed at whatever its first install imported. When the
     * bundled seed's fingerprint differs from the one recorded on device,
     * replace the bundled region's rows from the current seed (the same
     * wholesale-swap semantics PackManager applies to downloaded packs),
     * in one transaction. Device-produced coordinates (geo_prov='DEVICE')
     * are preserved across the swap; downloaded regions and the user
     * store are untouched. Sync-merged freshness for Alabama places is
     * re-merged by the next scheduled sync, exactly as after a pack
     * full-install.
     */
    private fun refreshBundledRegionIfSeedChanged(db: android.database.sqlite.SQLiteDatabase) {
        val (text, sha) = bundledSeed() ?: return
        if (catalog.metaGet(db, META_BUNDLED_SHA) == sha) return
        swapBundledRegion(db, text, sha)
    }

    private fun refreshBundledRegion(db: android.database.sqlite.SQLiteDatabase) {
        val (text, sha) = bundledSeed() ?: return
        swapBundledRegion(db, text, sha)
    }

    private fun swapBundledRegion(
        db: android.database.sqlite.SQLiteDatabase, seedText: String, seedSha: String
    ) {
        val regionId = Regions.ALABAMA.regionId
        val deviceCoords = catalog.deviceCoords(db, regionId)
        db.beginTransaction()
        try {
            catalog.deleteRegionRows(db, regionId)
            catalog.importSeed(db, JSONArray(seedText))
            for ((id, ll) in deviceCoords) {
                if (catalog.exists(db, id)) {
                    catalog.setCoords(db, id, ll.first, ll.second, "DEVICE")
                }
            }
            catalog.metaPut(db, META_BUNDLED_SHA, seedSha)
            catalog.metaPut(db, "pack_version:$regionId", "bundled-" + seedSha.take(12))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    /** First-import source order: on-device geocoded seed (tests/sideload),
     *  legacy places.json (upgrades — preserves merged data), bundled asset.
     *  Returns true when the BUNDLED seed (staged or asset) was imported,
     *  false when the legacy file was (the refresh must then run). */
    private fun importInitial(db: android.database.sqlite.SQLiteDatabase): Boolean {
        val filesDir = appContext.filesDir
        val stagedSeed = File(filesDir, "places_seed_geocoded.json")
        val legacy = File(filesDir, "places.json")
        var usedBundled = true
        val text: String = when {
            stagedSeed.exists() -> stagedSeed.readText()
            legacy.exists() -> { usedBundled = false; legacy.readText() }
            else -> readAssetSeed()
        }
        catalog.importSeed(db, JSONArray(text))

        // Legacy device-geocoder cache: coordinates the old app collected
        // on-device are real locations — keep them, labeled as such.
        val geoCache = File(filesDir, "geocache.json")
        if (geoCache.exists()) {
            runCatching {
                val cache = JSONObject(geoCache.readText())
                val keys = cache.keys()
                db.beginTransaction()
                try {
                    while (keys.hasNext()) {
                        val id = keys.next()
                        val a = cache.optJSONArray(id)
                        if (a != null && a.length() == 2) {
                            catalog.setCoords(db, id, a.getDouble(0), a.getDouble(1), "DEVICE")
                        }
                    }
                    db.setTransactionSuccessful()
                } finally { db.endTransaction() }
            }
            geoCache.renameTo(File(filesDir, "geocache.json.migrated-v1"))
        }
        if (legacy.exists()) legacy.renameTo(File(filesDir, "places.json.migrated-v1"))
        catalog.metaPut(db, "imported_at", System.currentTimeMillis().toString())
        // The bundled seed IS the Alabama region (LF-4): record it under
        // the same bookkeeping keys region packs use.
        if (catalog.metaGet(db, "pack_version:us-al") == null) {
            catalog.metaPut(db, "pack_version:us-al", "bundled-2026-10")
        }
        return usedBundled
    }

    private fun readAssetSeed(): String {
        val assets = appContext.assets
        val names = runCatching { assets.list("")?.toList() }.getOrNull() ?: emptyList()
        val asset = if ("places_seed_geocoded.json" in names) "places_seed_geocoded.json" else "places_seed.json"
        return assets.open(asset).bufferedReader().readText()
    }

    fun byId(id: String): Place? = catalog.placeById(catalog.readableDatabase, id)

    /** Counties of one region (LF-4); null = every installed region.
     *  Alert county-sync passes "us-al" explicitly: county sync is
     *  Alabama's ADPH until a region grows its own sync (K-06). */
    fun counties(regionId: String? = null): List<String> =
        catalog.counties(catalog.readableDatabase, regionId)

    fun placeExists(id: String): Boolean = catalog.exists(catalog.readableDatabase, id)

    fun count(): Int = catalog.placeCount(catalog.readableDatabase)

    fun regionPlaceCount(regionId: String): Int =
        catalog.regionPlaceCount(catalog.readableDatabase, regionId)

    fun installedRegionVersion(regionId: String): String? =
        packs.installedVersion(catalog.readableDatabase, regionId)

    // ------------------------------------------------- catalog meta passthrough
    // LF-N alerts: baseline + per-place last-event keys live in the catalog
    // meta table (same store the pack keys use), so dedupe state survives
    // restarts, pack updates, and process rollbacks — but NOT region removal
    // (a re-baselined region legitimately re-baselines its alert state).

    fun metaGet(key: String): String? = catalog.metaGet(catalog.readableDatabase, key)

    fun metaPut(key: String, value: String) =
        catalog.metaPut(catalog.writableDatabase, key, value)

    /** FTS-backed structured search for Browse (LF-2/LF-3).
     *  [regionId] scopes to the active region (LF-4); null = all regions.
     *  [resultModel] (LF-N) interprets [PlaceQuery.band] in the active
     *  region's own result model — a "band" on a penalty scale is a
     *  demerit range, and band bounds never touch the NO_SCORE sentinel.
     *
     *  LF-N hardening: a cross-region search (regionId == null) spans
     *  jurisdictions with DIFFERENT result scales, so it MUST NOT pretend
     *  there is one meaningful nationwide "best/worst" ranking: the band
     *  filter is dropped (a 0–100 range would silently admit penalty
     *  points) and the sort degrades to the neutral "most recent" order.
     *  Sort/band logic lives in NationalCoverage.orderByFor for tests. */
    suspend fun searchPlaces(
        query: PlaceQuery,
        regionId: String? = null,
        resultModel: String = NationalCoverage.MODEL_SCORE_100_HIGH
    ): List<Place> = withContext(Dispatchers.IO) {
        // Mixed-scope search: neutral, model-agnostic semantics (the
        // band range resolves to unconstrained under UNKNOWN, dropping
        // the numeric filter without pretending every row shares a scale).
        val model = if (regionId == null) NationalCoverage.MODEL_UNKNOWN else resultModel
        val (minScore, maxScore) = NationalCoverage.bandRange(model, query.band)
        val orderBy = NationalCoverage.orderByFor(model, query.sort)
        val db = catalog.readableDatabase
        val text = query.text.trim()
        var ftsIds = if (text.isNotEmpty()) catalog.ftsIds(db, text, 2000) else null
        // Workstream D / FIX5 (search defect a): the LIKE fallback used to
        // fire ONLY when FTS was unavailable (ftsIds == null). An FTS
        // query that matched ZERO rows was a dead end — no second chance.
        // Zero hits now falls back to the (apostrophe-insensitive) LIKE
        // scan like any other FTS miss.
        if (ftsIds != null && ftsIds.isEmpty()) ftsIds = null
        val like = if (text.isNotEmpty() && ftsIds == null) text else null
        val found = catalog.search(
            db, ids = ftsIds, county = query.county,
            minScore = minScore, maxScore = maxScore,
            textLike = like, orderBy = orderBy, limit = query.limit,
            regionId = regionId
        )
        catalog.attachInspections(db, found)
    }

    /** Map viewport query: only places with real, accepted coordinates. */
    suspend fun placesInBounds(
        minLat: Double, maxLat: Double, minLng: Double, maxLng: Double, limit: Int = 5000,
        regionId: String? = null
    ): List<Place> = withContext(Dispatchers.IO) {
        catalog.inBounds(catalog.readableDatabase, minLat, maxLat, minLng, maxLng, limit, regionId)
    }

    // ------------------------------------------------------- region packs

    /** Install a full region pack (verified + atomic inside PackManager). */
    suspend fun installPack(packFile: java.io.File, manifest: PackManifest): PackInstallResult =
        withContext(Dispatchers.IO) {
            val r = packs.installFullPack(catalog.writableDatabase, packFile, manifest)
            refreshSnapshotIfLoaded()
            r
        }

    /** Apply a delta change set on top of its exact base version. */
    suspend fun applyPackDelta(deltaFile: java.io.File, manifest: PackManifest): PackInstallResult =
        withContext(Dispatchers.IO) {
            val r = packs.applyDelta(catalog.writableDatabase, deltaFile, manifest)
            refreshSnapshotIfLoaded()
            r
        }

    /** Restore the N−1 pack kept by the last full install. */
    suspend fun rollbackPack(regionId: String): Boolean = withContext(Dispatchers.IO) {
        val ok = packs.rollback(catalog.writableDatabase, regionId)
        if (ok) refreshSnapshotIfLoaded()
        ok
    }

    /** Remove a downloaded region. Favorites/areas/rules in the user store
     *  are never touched — they live in a different database. */
    suspend fun removePack(regionId: String) = withContext(Dispatchers.IO) {
        packs.removeRegion(catalog.writableDatabase, regionId)
        refreshSnapshotIfLoaded()
    }

    fun packHasRollback(regionId: String): Boolean = packs.hasRollback(regionId)

    private fun refreshSnapshotIfLoaded() {
        if (loaded) _places.value = catalog.allPlaces(catalog.readableDatabase)
    }

    /** Merge fresh places; returns events for places whose inspection changed.
     *  Only rows that actually changed are written, in one transaction. */
    suspend fun mergeFresh(fresh: List<Place>): List<PlaceEvent> = withContext(Dispatchers.IO) {
        if (fresh.isEmpty()) return@withContext emptyList()
        val db = catalog.writableDatabase
        val events = mutableListOf<PlaceEvent>()
        var changed = false
        db.beginTransaction()
        try {
            for (f in fresh) {
                val existing = catalog.placeById(db, f.id)
                    ?: findByMatchKey(db, f)
                if (existing == null) {
                    catalog.upsertPlace(db, f)
                    changed = true
                } else {
                    val merged = f.copy(
                        id = existing.id,
                        county = f.county.ifBlank { existing.county },
                        city = f.city.ifBlank { existing.city },
                        lat = f.lat ?: existing.lat,
                        lng = f.lng ?: existing.lng,
                        detailUrl = f.detailUrl ?: existing.detailUrl,
                        inspections = if (f.inspections.isNotEmpty()) f.inspections else existing.inspections,
                        geoStatus = if (f.lat != null) f.geoStatus else existing.geoStatus,
                        geoAccuracy = if (f.lat != null) f.geoAccuracy else existing.geoAccuracy,
                        geoProvider = if (f.lat != null) f.geoProvider else existing.geoProvider,
                        geoMatch = if (f.lat != null) f.geoMatch else existing.geoMatch
                    )
                    if (merged != existing) {
                        if (existing.eventKey != merged.eventKey) {
                            events += PlaceEvent(existing, merged)
                        }
                        catalog.upsertPlace(db, merged)
                        changed = true
                    }
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        if (changed) _places.value = catalog.allPlaces(db)
        events
    }

    private fun findByMatchKey(db: android.database.sqlite.SQLiteDatabase, f: Place): Place? {
        if (f.zip.isBlank()) return null
        val key = Place.matchKey(f.name, f.zip, f.address)
        val matchId = db.rawQuery(
            "SELECT id,name,address,zip FROM places WHERE zip=?", arrayOf(f.zip)
        ).use { c ->
            var found: String? = null
            while (c.moveToNext()) {
                if (Place.matchKey(c.getString(1), c.getString(3), c.getString(2)) == key) {
                    found = c.getString(0); break
                }
            }
            found
        }
        return matchId?.let { catalog.placeById(db, it) }
    }

    /** Update one place in place (e.g. after fetching its detail page). */
    suspend fun updatePlace(updated: Place) = withContext(Dispatchers.IO) {
        val db = catalog.writableDatabase
        db.beginTransaction()
        try {
            catalog.upsertPlace(db, updated)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        val idx = _places.value.indexOfFirst { it.id == updated.id }
        if (idx >= 0) {
            _places.value = _places.value.toMutableList().also { it[idx] = updated }
        }
    }

    suspend fun setCoords(placeId: String, lat: Double, lng: Double) = withContext(Dispatchers.IO) {
        val db = catalog.writableDatabase
        catalog.setCoords(db, placeId, lat, lng, "DEVICE")
        val idx = _places.value.indexOfFirst { it.id == placeId }
        if (idx >= 0) {
            val p = _places.value[idx]
            _places.value = _places.value.toMutableList().also {
                it[idx] = p.copy(
                    lat = lat, lng = lng,
                    geoStatus = Place.STATUS_ACCEPTED,
                    geoAccuracy = Place.ACC_ADDRESS_RANGE,
                    geoProvider = "DEVICE"
                )
            }
        }
    }
}
