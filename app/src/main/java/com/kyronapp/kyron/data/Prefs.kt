package com.kyronapp.kyron.data

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray

/** User profile, favorites, alert rules and inbox — the per-user account data (stored on device in v2.0). */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE)

    var profileName: String
        get() = sp.getString("profile_name", "") ?: ""
        set(v) = sp.edit().putString("profile_name", v).apply()

    var favorites: Set<String>
        get() = sp.getStringSet("favorites", emptySet()) ?: emptySet()
        set(v) = sp.edit().putStringSet("favorites", v).apply()

    fun toggleFavorite(id: String): Boolean {
        val cur = favorites.toMutableSet()
        val now = if (cur.contains(id)) { cur.remove(id); false } else { cur.add(id); true }
        favorites = cur
        return now
    }

    var alertsForFavorites: Boolean
        get() = sp.getBoolean("alerts_favorites", true)
        set(v) = sp.edit().putBoolean("alerts_favorites", v).apply()

    var alertsForArea: Boolean
        get() = sp.getBoolean("alerts_area", true)
        set(v) = sp.edit().putBoolean("alerts_area", v).apply()

    var threshold: Int
        get() = sp.getInt("threshold", 85)
        set(v) = sp.edit().putInt("threshold", v).apply()

    var monitoredCounties: Set<String>
        get() = sp.getStringSet("monitored_counties", setOf("Jefferson")) ?: setOf("Jefferson")
        set(v) = sp.edit().putStringSet("monitored_counties", v).apply()

    var homeLat: Double
        get() = sp.getFloat("home_lat", 33.5207f).toDouble()
        set(v) = sp.edit().putFloat("home_lat", v.toFloat()).apply()

    var homeLng: Double
        get() = sp.getFloat("home_lng", (-86.8025f)).toDouble()
        set(v) = sp.edit().putFloat("home_lng", v.toFloat()).apply()

    var homeLabel: String
        get() = sp.getString("home_label", "Downtown Birmingham") ?: "Downtown Birmingham"
        set(v) = sp.edit().putString("home_label", v).apply()

    var radiusMiles: Double
        get() = sp.getFloat("radius_miles", 10f).toDouble()
        set(v) = sp.edit().putFloat("radius_miles", v.toFloat()).apply()

    var lastSyncMs: Long
        get() = sp.getLong("last_sync", 0L)
        set(v) = sp.edit().putLong("last_sync", v).apply()

    var lastCountySyncMs: Long
        get() = sp.getLong("last_county_sync", 0L)
        set(v) = sp.edit().putLong("last_county_sync", v).apply()

    var inbox: List<AlertItem>
        get() {
            val raw = sp.getString("inbox", "[]") ?: "[]"
            val arr = JSONArray(raw)
            return (0 until arr.length()).map { AlertItem.fromJson(arr.getJSONObject(it)) }
        }
        set(v) {
            val arr = JSONArray()
            v.take(50).forEach { arr.put(it.toJson()) }
            sp.edit().putString("inbox", arr.toString()).apply()
        }

    fun addAlert(item: AlertItem) {
        inbox = listOf(item) + inbox
    }
}
