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
                importInitial(db)
            }
            _places.value = catalog.allPlaces(db)
            loaded = true
        }
    }

    /** First-import source order: on-device geocoded seed (tests/sideload),
     *  legacy places.json (upgrades — preserves merged data), bundled asset. */
    private fun importInitial(db: android.database.sqlite.SQLiteDatabase) {
        val filesDir = appContext.filesDir
        val stagedSeed = File(filesDir, "places_seed_geocoded.json")
        val legacy = File(filesDir, "places.json")
        val text: String = when {
            stagedSeed.exists() -> stagedSeed.readText()
            legacy.exists() -> legacy.readText()
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

    /** FTS-backed structured search for Browse (LF-2/LF-3).
     *  [regionId] scopes to the active region (LF-4); null = all regions. */
    suspend fun searchPlaces(query: PlaceQuery, regionId: String? = null): List<Place> = withContext(Dispatchers.IO) {
        val db = catalog.readableDatabase
        val (minScore, maxScore) = when (query.band) {
            "Below 85" -> null to 84
            "85–94" -> 85 to 94
            "95+" -> 95 to null
            else -> null to null
        }
        val orderBy = when (query.sort) {
            "Best first" -> "score DESC, name_lc ASC"
            "Most recent" -> "date_key DESC, name_lc ASC"
            "Name A–Z" -> "name_lc ASC"
            else -> "score ASC, name_lc ASC"
        }
        val text = query.text.trim()
        val ftsIds = if (text.isNotEmpty()) catalog.ftsIds(db, text, 2000) else null
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
