package com.kyronapp.kyron.data

import android.content.Context

/**
 * User profile, favorites, alert rules and inbox — the per-user data.
 *
 * LF-2: this class is now a thin facade over [UserStore] (SQLite, the
 * plan's migration-ready user-data contract: UUIDs, timestamps,
 * tombstones, sync outbox). The v2.0 SharedPreferences file it used to
 * wrap is migrated into the store on first run and left in place as a
 * recovery copy. The property API is unchanged so callers don't move.
 */
class Prefs(context: Context) {

    val store: UserStore = UserStore(context)

    var profileName: String
        get() = store.profile.name
        set(v) = store.updateProfile { it.name = v }

    var seenWelcome: Boolean
        get() = store.profile.seenWelcome
        set(v) = store.updateProfile { it.seenWelcome = v }

    var favorites: Set<String>
        get() = store.favorites()
        set(v) {
            val current = store.favorites()
            for (id in current - v) store.setFavorite(id, false)
            for (id in v - current) store.setFavorite(id, true)
        }

    fun toggleFavorite(id: String): Boolean = store.toggleFavorite(id)

    var alertsForFavorites: Boolean
        get() = store.profile.alertsFavorites
        set(v) {
            store.updateProfile { it.alertsFavorites = v }
            store.setRule("FAVORITES", v, store.profile.threshold)
        }

    var alertsForArea: Boolean
        get() = store.profile.alertsArea
        set(v) {
            store.updateProfile { it.alertsArea = v }
            store.setRule("AREA", v, store.profile.threshold)
        }

    var threshold: Int
        get() = store.profile.threshold
        set(v) {
            val p = store.profile
            store.updateProfile { it.threshold = v }
            store.setRule("FAVORITES", p.alertsFavorites, v)
            store.setRule("AREA", p.alertsArea, v)
        }

    var monitoredCounties: Set<String>
        get() = store.monitoredCounties()
        set(v) = store.setMonitoredCounties(v)

    var homeLat: Double
        get() = store.profile.homeLat
        set(v) { store.updateProfile { it.homeLat = v }; store.syncHomeArea() }

    var homeLng: Double
        get() = store.profile.homeLng
        set(v) { store.updateProfile { it.homeLng = v }; store.syncHomeArea() }

    var homeLabel: String
        get() = store.profile.homeLabel
        set(v) = store.updateProfile { it.homeLabel = v }

    var radiusMiles: Double
        get() = store.profile.radiusMiles
        set(v) { store.updateProfile { it.radiusMiles = v }; store.syncHomeArea() }

    var lastSyncMs: Long
        get() = store.profile.lastSyncMs
        set(v) = store.updateProfile { it.lastSyncMs = v }

    var lastCountySyncMs: Long
        get() = store.profile.lastCountySyncMs
        set(v) = store.updateProfile { it.lastCountySyncMs = v }

    var inbox: List<AlertItem>
        get() = store.inbox()
        set(v) = store.replaceInbox(v)

    fun addAlert(item: AlertItem) = store.addInboxItem(item)
}
