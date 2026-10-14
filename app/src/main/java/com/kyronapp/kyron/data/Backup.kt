package com.kyronapp.kyron.data

import org.json.JSONArray
import org.json.JSONObject

data class ImportReport(
    val inserted: Int, val updated: Int, val skipped: Int,
    val unresolvablePlaceIds: List<String>
)

/**
 * Versioned user-data backup — format "kyron-backup" v1 (Free/LocalFirst
 * plan section 1.5). The exporter writes exactly the user-store tables,
 * tombstones included; the importer merges by UUID with newer-updated_at
 * wins and tombstones honored. This same JSON shape is the payload the
 * future claim-on-first-login flow uploads, so it is tested from launch.
 */
object Backup {

    const val FORMAT = "kyron-backup"
    const val FORMAT_VERSION = 1

    fun export(store: UserStore, appVersion: String, exportedAtIso: String): JSONObject {
        val root = JSONObject()
        root.put("format", FORMAT)
        root.put("formatVersion", FORMAT_VERSION)
        root.put("exportedAt", exportedAtIso)
        root.put("appVersion", appVersion)
        root.put("profile", store.profileJson(store.profile))
        root.put("favorites", JSONArray().apply {
            store.allFavorites(includeDeleted = true).forEach { put(store.favoriteJson(it)) }
        })
        root.put("areas", JSONArray().apply {
            store.allAreas(includeDeleted = true).forEach { put(store.areaJson(it)) }
        })
        root.put("alertRules", JSONArray().apply {
            store.allRules(includeDeleted = true).forEach { put(store.ruleJson(it)) }
        })
        root.put("inbox", JSONArray().apply {
            store.allInbox(includeDeleted = true).forEach { put(store.inboxJson(it)) }
        })
        return root
    }

    private fun optDeletedAt(o: JSONObject): Long? =
        if (o.isNull("deletedAt")) null else o.optLong("deletedAt")

    fun import(store: UserStore, root: JSONObject, placeExists: (String) -> Boolean): ImportReport {
        require(root.optString("format") == FORMAT) { "not a kyron-backup file" }
        val version = root.optInt("formatVersion", -1)
        require(version in 1..FORMAT_VERSION) { "unsupported backup formatVersion $version" }

        var inserted = 0
        var updated = 0
        var skipped = 0
        val unresolvable = mutableListOf<String>()
        fun tally(code: Int) {
            when (code) { 1 -> inserted++; 2 -> updated++; else -> skipped++ }
        }

        // QA fix (2026-10-13): PARSE EVERYTHING FIRST. The old code merged
        // rows as it parsed them, so a malformed row halfway through the
        // file threw AFTER earlier sections (profile, first favorites)
        // had already committed — the UI said "import failed" while the
        // store was left half-imported and the caches stale. Parsing the
        // whole file into typed rows up front means a bad file applies
        // NOTHING; the apply phase below cannot fail on file content.
        val profileIn: ProfileRow? = root.optJSONObject("profile")?.let { o ->
            ProfileRow(
                name = o.optString("name", ""),
                homeLat = o.optDouble("homeLat", 33.5207),
                homeLng = o.optDouble("homeLng", -86.8025),
                homeLabel = o.optString("homeLabel", "Downtown Birmingham"),
                radiusMiles = o.optDouble("radiusMiles", 10.0),
                alertsFavorites = o.optBoolean("alertsFavorites", true),
                alertsArea = o.optBoolean("alertsArea", true),
                threshold = o.optInt("threshold", 85),
                seenWelcome = o.optBoolean("seenWelcome", false),
                lastSyncMs = o.optLong("lastSyncMs", 0),
                lastCountySyncMs = o.optLong("lastCountySyncMs", 0),
                updatedAt = o.optLong("updatedAt", 0)
            )
        }

        val favsIn = mutableListOf<FavoriteRow>()
        root.optJSONArray("favorites")?.let { favs ->
            for (i in 0 until favs.length()) {
                val o = favs.getJSONObject(i)
                favsIn += FavoriteRow(
                    o.getString("id"), o.optString("placeId", ""),
                    o.optLong("createdAt"), o.optLong("updatedAt"),
                    optDeletedAt(o), o.optInt("version", 1)
                )
            }
        }

        val areasIn = mutableListOf<AreaRow>()
        root.optJSONArray("areas")?.let { areas ->
            for (i in 0 until areas.length()) {
                val o = areas.getJSONObject(i)
                areasIn += AreaRow(
                    o.getString("id"), o.optString("kind", "COUNTY"), o.optString("countyName", ""),
                    o.optDouble("centerLat", 0.0), o.optDouble("centerLng", 0.0),
                    o.optDouble("radiusMiles", 0.0),
                    o.optLong("createdAt"), o.optLong("updatedAt"),
                    optDeletedAt(o), o.optInt("version", 1)
                )
            }
        }

        val rulesIn = mutableListOf<RuleRow>()
        root.optJSONArray("alertRules")?.let { rules ->
            for (i in 0 until rules.length()) {
                val o = rules.getJSONObject(i)
                rulesIn += RuleRow(
                    o.getString("id"), o.optString("kind", "FAVORITES"),
                    o.optBoolean("enabled", true), o.optInt("threshold", 85),
                    o.optLong("createdAt"), o.optLong("updatedAt"),
                    optDeletedAt(o), o.optInt("version", 1)
                )
            }
        }

        val inboxIn = mutableListOf<InboxRow>()
        root.optJSONArray("inbox")?.let { inbox ->
            for (i in 0 until inbox.length()) {
                val o = inbox.getJSONObject(i)
                inboxIn += InboxRow(
                    o.getString("id"), o.optString("placeId", ""),
                    o.optString("title", ""), o.optString("body", ""),
                    o.optLong("whenMs", 0), o.optBoolean("lowScore", false),
                    o.optLong("createdAt"), o.optLong("updatedAt"),
                    optDeletedAt(o), o.optInt("version", 1)
                )
            }
        }

        // ---- apply phase (file content can no longer throw here) ----
        profileIn?.let { p ->
            if (store.mergeProfile(p)) updated++ else skipped++
        }
        for (row in favsIn) {
            if (row.deletedAt == null && row.placeId.isNotEmpty() && !placeExists(row.placeId)) {
                unresolvable += row.placeId
            }
            tally(store.mergeFavorite(row))
        }
        for (row in areasIn) tally(store.mergeArea(row))
        for (row in rulesIn) tally(store.mergeRule(row))
        for (row in inboxIn) tally(store.mergeInbox(row))

        store.refreshCaches()
        store.syncHomeArea()
        return ImportReport(inserted, updated, skipped, unresolvable.distinct())
    }
}
