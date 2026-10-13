package com.kyronapp.kyron.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.io.File

/** A detected change: a place received a new inspection (date/score changed). */
data class PlaceEvent(val old: Place?, val new: Place)

/**
 * Owns the place catalog: bundled seed (statewide snapshot) merged with
 * live refreshes. Merging is failure-safe — fresh data updates matching
 * places but never wipes places a source didn't return.
 */
class PlaceRepository(private val context: Context) {

    private val file: File get() = File(context.filesDir, "places.json")
    private val geoFile: File get() = File(context.filesDir, "geocache.json")

    private val _places = MutableStateFlow<List<Place>>(emptyList())
    val places: StateFlow<List<Place>> = _places

    @Volatile private var loaded = false

    suspend fun load() {
        if (loaded) return
        withContext(Dispatchers.IO) {
            val text: String = if (file.exists()) {
                file.readText()
            } else {
                val seed = context.assets.open("places_seed.json").bufferedReader().readText()
                file.writeText(seed)
                seed
            }
            val arr = JSONArray(text)
            val list = (0 until arr.length()).map { Place.fromJson(arr.getJSONObject(it)) }
            _places.value = list.sortedWith(compareBy({ it.name.lowercase() }))
            applyGeoCache()
            loaded = true
        }
    }

    fun byId(id: String): Place? = _places.value.firstOrNull { it.id == id }

    fun counties(): List<String> = _places.value.map { it.county }.distinct().sorted()

    /** Merge fresh places; returns events for places whose inspection changed. */
    suspend fun mergeFresh(fresh: List<Place>): List<PlaceEvent> = withContext(Dispatchers.IO) {
        if (fresh.isEmpty()) return@withContext emptyList()
        val current = _places.value.toMutableList()
        val byId = current.associateBy { it.id }.toMutableMap()
        val byKey = current.associateBy { Place.matchKey(it.name, it.zip, it.address) }.toMutableMap()
        val events = mutableListOf<PlaceEvent>()

        for (f in fresh) {
            val key = Place.matchKey(f.name, f.zip, f.address)
            val existing = byId[f.id] ?: byKey[key]
            if (existing == null) {
                current += f
                byId[f.id] = f
                byKey[key] = f
            } else {
                val merged = f.copy(
                    id = existing.id,
                    county = f.county.ifBlank { existing.county },
                    city = f.city.ifBlank { existing.city },
                    lat = f.lat ?: existing.lat,
                    lng = f.lng ?: existing.lng,
                    detailUrl = f.detailUrl ?: existing.detailUrl,
                    inspections = if (f.inspections.isNotEmpty()) f.inspections else existing.inspections
                )
                if (existing.eventKey != merged.eventKey) {
                    events += PlaceEvent(existing, merged)
                }
                val idx = current.indexOfFirst { it.id == existing.id }
                if (idx >= 0) current[idx] = merged
                byId[existing.id] = merged
                byKey[key] = merged
            }
        }
        _places.value = current.sortedWith(compareBy({ it.name.lowercase() }))
        persist()
        events
    }

    /** Update one place in place (e.g. after fetching its detail page). */
    suspend fun updatePlace(updated: Place) = withContext(Dispatchers.IO) {
        val current = _places.value.toMutableList()
        val idx = current.indexOfFirst { it.id == updated.id }
        if (idx >= 0) {
            current[idx] = updated
            _places.value = current
            persist()
        }
    }

    suspend fun setCoords(placeId: String, lat: Double, lng: Double) = withContext(Dispatchers.IO) {
        val p = byId(placeId) ?: return@withContext
        updatePlace(p.copy(lat = lat, lng = lng))
        val cache = readGeoCache()
        cache.put(placeId, JSONArray().put(lat).put(lng))
        geoFile.writeText(cache.toString())
    }

    private fun readGeoCache(): org.json.JSONObject =
        if (geoFile.exists()) runCatching { org.json.JSONObject(geoFile.readText()) }.getOrElse { org.json.JSONObject() }
        else org.json.JSONObject()

    private fun applyGeoCache() {
        val cache = readGeoCache()
        if (cache.length() == 0) return
        _places.value = _places.value.map { p ->
            if (p.lat != null) p else {
                val a = cache.optJSONArray(p.id)
                if (a != null && a.length() == 2) p.copy(lat = a.getDouble(0), lng = a.getDouble(1)) else p
            }
        }
    }

    private fun persist() {
        val arr = JSONArray()
        _places.value.forEach { arr.put(it.toJson()) }
        file.writeText(arr.toString())
    }
}
