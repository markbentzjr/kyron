package com.kyronapp.kyron.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** One row of the sacred user store. Every user-owned entity carries the
 *  Free/LocalFirst plan section 1.2 contract: UUID id, owner_id ('local'
 *  until a future claim), created_at / updated_at, a deleted_at tombstone
 *  instead of hard deletes, and a per-row version. */
data class FavoriteRow(
    val id: String, val placeId: String,
    val createdAt: Long, val updatedAt: Long, val deletedAt: Long?, val version: Int
)

data class AreaRow(
    val id: String, val kind: String, // COUNTY | RADIUS
    val countyName: String, val centerLat: Double, val centerLng: Double,
    val radiusMiles: Double,
    val createdAt: Long, val updatedAt: Long, val deletedAt: Long?, val version: Int
)

data class RuleRow(
    val id: String, val kind: String, // FAVORITES | AREA
    val enabled: Boolean, val threshold: Int,
    val createdAt: Long, val updatedAt: Long, val deletedAt: Long?, val version: Int
)

data class InboxRow(
    val id: String, val placeId: String, val title: String, val body: String,
    val whenMs: Long, val lowScore: Boolean,
    val createdAt: Long, val updatedAt: Long, val deletedAt: Long?, val version: Int
)

data class ProfileRow(
    var name: String = "",
    var homeLat: Double = 33.5207, var homeLng: Double = -86.8025,
    var homeLabel: String = "Downtown Birmingham",
    var radiusMiles: Double = 10.0,
    var alertsFavorites: Boolean = true, var alertsArea: Boolean = true,
    var threshold: Int = 85,
    var seenWelcome: Boolean = false,
    var lastSyncMs: Long = 0L, var lastCountySyncMs: Long = 0L,
    var updatedAt: Long = 0L
)

private class UserDbHelper(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "kyron_user.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE profile(
                id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL DEFAULT '',
                home_lat REAL NOT NULL DEFAULT 33.5207, home_lng REAL NOT NULL DEFAULT -86.8025,
                home_label TEXT NOT NULL DEFAULT 'Downtown Birmingham',
                radius_miles REAL NOT NULL DEFAULT 10,
                alerts_favorites INTEGER NOT NULL DEFAULT 1, alerts_area INTEGER NOT NULL DEFAULT 1,
                threshold INTEGER NOT NULL DEFAULT 85, seen_welcome INTEGER NOT NULL DEFAULT 0,
                last_sync_ms INTEGER NOT NULL DEFAULT 0, last_county_sync_ms INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0)"""
        )
        db.execSQL(
            """CREATE TABLE favorites(
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
                place_id TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                deleted_at INTEGER, version INTEGER NOT NULL DEFAULT 1)"""
        )
        db.execSQL("CREATE INDEX idx_favorites_place ON favorites(place_id)")
        db.execSQL(
            """CREATE TABLE areas(
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
                kind TEXT NOT NULL, county_name TEXT NOT NULL DEFAULT '',
                center_lat REAL NOT NULL DEFAULT 0, center_lng REAL NOT NULL DEFAULT 0,
                radius_miles REAL NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                deleted_at INTEGER, version INTEGER NOT NULL DEFAULT 1)"""
        )
        db.execSQL(
            """CREATE TABLE alert_rules(
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
                kind TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                threshold INTEGER NOT NULL DEFAULT 85,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                deleted_at INTEGER, version INTEGER NOT NULL DEFAULT 1)"""
        )
        db.execSQL(
            """CREATE TABLE alert_inbox(
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
                place_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '', when_ms INTEGER NOT NULL DEFAULT 0,
                low_score INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                deleted_at INTEGER, version INTEGER NOT NULL DEFAULT 1)"""
        )
        db.execSQL(
            """CREATE TABLE sync_outbox(
                id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                operation TEXT NOT NULL, payload_json TEXT NOT NULL,
                base_version INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)"""
        )
        db.execSQL("CREATE TABLE user_meta(k TEXT PRIMARY KEY, v TEXT)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}
}

/**
 * The user store (LF-2): profile, favorites, areas, alert rules and inbox
 * in SQLite, behind the plan's data contract. Every mutation also appends
 * a sync_outbox row in the same transaction — the outbox is written from
 * day one and drained by nobody until a backend upgrade trigger fires
 * (plan section 1.2). An in-memory cache serves the synchronous reads the
 * UI expects; the DB is the source of truth.
 */
class UserStore(context: Context) {

    private val helper = UserDbHelper(context)
    private val appContext = context.applicationContext

    @Volatile private var profileCache: ProfileRow = ProfileRow()
    @Volatile private var favoritesCache: Set<String> = emptySet()
    @Volatile private var countiesCache: Set<String> = setOf("Jefferson")
    @Volatile private var inboxCache: List<AlertItem> = emptyList()

    init {
        synchronized(this) {
            val db = helper.writableDatabase
            migrateFromPrefsIfNeeded(db)
            ensureDefaults(db)
            reloadCaches(db)
        }
    }

    // ------------------------------------------------------------ migration

    private fun metaGet(db: SQLiteDatabase, key: String): String? =
        db.rawQuery("SELECT v FROM user_meta WHERE k=?", arrayOf(key)).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }

    private fun metaPut(db: SQLiteDatabase, key: String, value: String) {
        val cv = ContentValues().apply { put("k", key); put("v", value) }
        db.insertWithOnConflict("user_meta", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    /**
     * One-time migration of the v2.0 SharedPreferences user data
     * (kyron_prefs) into the user store. Values are copied, never moved:
     * the legacy prefs file stays in place (and in Auto Backup) as a
     * recovery path for one release cycle, per plan section 1.4 step 5's
     * spirit. Runs inside one transaction; every created row also writes
     * its outbox operation, so the migrated state is fully replayable.
     */
    private fun migrateFromPrefsIfNeeded(db: SQLiteDatabase) {
        if (metaGet(db, "prefs_migrated") == "1") return
        val sp = appContext.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            val prof = ProfileRow(
                name = sp.getString("profile_name", "") ?: "",
                homeLat = sp.getFloat("home_lat", 33.5207f).toDouble(),
                homeLng = sp.getFloat("home_lng", -86.8025f).toDouble(),
                homeLabel = sp.getString("home_label", "Downtown Birmingham") ?: "Downtown Birmingham",
                radiusMiles = sp.getFloat("radius_miles", 10f).toDouble(),
                alertsFavorites = sp.getBoolean("alerts_favorites", true),
                alertsArea = sp.getBoolean("alerts_area", true),
                threshold = sp.getInt("threshold", 85),
                seenWelcome = sp.getBoolean("seen_welcome", false),
                lastSyncMs = sp.getLong("last_sync", 0L),
                lastCountySyncMs = sp.getLong("last_county_sync", 0L),
                // A profile migrated from an EMPTY prefs file was never
                // actually modified by anyone: stamp 0 ("never modified")
                // so a backup import on a fresh install can still win.
                updatedAt = if (sp.all.isEmpty()) 0L else now
            )
            writeProfile(db, prof)
            outbox(db, "profile", "profile", "CREATE", profileJson(prof), 0, now)

            val favs = sp.getStringSet("favorites", emptySet()) ?: emptySet()
            for (pid in favs.sorted()) {
                val row = FavoriteRow(UUID.randomUUID().toString(), pid, now, now, null, 1)
                insertFavorite(db, row)
                outbox(db, "favorite", row.id, "CREATE", favoriteJson(row), 0, now)
            }
            val counties = sp.getStringSet("monitored_counties", setOf("Jefferson")) ?: setOf("Jefferson")
            for (county in counties.sorted()) {
                val row = AreaRow(UUID.randomUUID().toString(), "COUNTY", county, 0.0, 0.0, 0.0, now, now, null, 1)
                insertArea(db, row)
                outbox(db, "area", row.id, "CREATE", areaJson(row), 0, now)
            }
            // Home radius as a RADIUS area (the claim flow converts exactly this).
            val home = AreaRow(
                UUID.randomUUID().toString(), "RADIUS", "",
                prof.homeLat, prof.homeLng, prof.radiusMiles, now, now, null, 1
            )
            insertArea(db, home)
            outbox(db, "area", home.id, "CREATE", areaJson(home), 0, now)

            val favRule = RuleRow(UUID.randomUUID().toString(), "FAVORITES", prof.alertsFavorites, prof.threshold, now, now, null, 1)
            insertRule(db, favRule)
            outbox(db, "alert_rule", favRule.id, "CREATE", ruleJson(favRule), 0, now)
            val areaRule = RuleRow(UUID.randomUUID().toString(), "AREA", prof.alertsArea, prof.threshold, now, now, null, 1)
            insertRule(db, areaRule)
            outbox(db, "alert_rule", areaRule.id, "CREATE", ruleJson(areaRule), 0, now)

            val rawInbox = sp.getString("inbox", "[]") ?: "[]"
            val arr = runCatching { JSONArray(rawInbox) }.getOrNull()
            if (arr != null) {
                for (i in 0 until arr.length()) {
                    val item = AlertItem.fromJson(arr.getJSONObject(i))
                    val row = InboxRow(
                        UUID.randomUUID().toString(), item.placeId, item.title, item.body,
                        item.whenMs, item.lowScore, now, now, null, 1
                    )
                    insertInbox(db, row)
                    outbox(db, "alert_inbox", row.id, "CREATE", inboxJson(row), 0, now)
                }
            }
            metaPut(db, "prefs_migrated", "1")
            metaPut(db, "prefs_migrated_at", now.toString())
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun ensureDefaults(db: SQLiteDatabase) {
        val hasProfile = db.rawQuery("SELECT 1 FROM profile WHERE id=1", null).use { it.moveToFirst() }
        if (hasProfile) return
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            // updatedAt = 0: the default profile has never been modified,
            // so any real backup import must be able to replace it.
            writeProfile(db, ProfileRow(updatedAt = 0L))
            val county = AreaRow(UUID.randomUUID().toString(), "COUNTY", "Jefferson", 0.0, 0.0, 0.0, now, now, null, 1)
            insertArea(db, county)
            outbox(db, "area", county.id, "CREATE", areaJson(county), 0, now)
            val home = AreaRow(UUID.randomUUID().toString(), "RADIUS", "", 33.5207, -86.8025, 10.0, now, now, null, 1)
            insertArea(db, home)
            outbox(db, "area", home.id, "CREATE", areaJson(home), 0, now)
            val r1 = RuleRow(UUID.randomUUID().toString(), "FAVORITES", true, 85, now, now, null, 1)
            insertRule(db, r1); outbox(db, "alert_rule", r1.id, "CREATE", ruleJson(r1), 0, now)
            val r2 = RuleRow(UUID.randomUUID().toString(), "AREA", true, 85, now, now, null, 1)
            insertRule(db, r2); outbox(db, "alert_rule", r2.id, "CREATE", ruleJson(r2), 0, now)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ------------------------------------------------------------- row I/O

    private fun writeProfile(db: SQLiteDatabase, p: ProfileRow) {
        val cv = ContentValues().apply {
            put("id", 1); put("name", p.name)
            put("home_lat", p.homeLat); put("home_lng", p.homeLng); put("home_label", p.homeLabel)
            put("radius_miles", p.radiusMiles)
            put("alerts_favorites", if (p.alertsFavorites) 1 else 0)
            put("alerts_area", if (p.alertsArea) 1 else 0)
            put("threshold", p.threshold)
            put("seen_welcome", if (p.seenWelcome) 1 else 0)
            put("last_sync_ms", p.lastSyncMs); put("last_county_sync_ms", p.lastCountySyncMs)
            put("updated_at", p.updatedAt)
        }
        db.insertWithOnConflict("profile", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    private fun readProfile(db: SQLiteDatabase): ProfileRow =
        db.rawQuery("SELECT name,home_lat,home_lng,home_label,radius_miles,alerts_favorites,alerts_area,threshold,seen_welcome,last_sync_ms,last_county_sync_ms,updated_at FROM profile WHERE id=1", null)
            .use { c ->
                if (!c.moveToFirst()) return@use ProfileRow()
                ProfileRow(
                    name = c.getString(0) ?: "",
                    homeLat = c.getDouble(1), homeLng = c.getDouble(2),
                    homeLabel = c.getString(3) ?: "",
                    radiusMiles = c.getDouble(4),
                    alertsFavorites = c.getInt(5) == 1, alertsArea = c.getInt(6) == 1,
                    threshold = c.getInt(7), seenWelcome = c.getInt(8) == 1,
                    lastSyncMs = c.getLong(9), lastCountySyncMs = c.getLong(10),
                    updatedAt = c.getLong(11)
                )
            }

    private fun insertFavorite(db: SQLiteDatabase, r: FavoriteRow) {
        db.insert("favorites", null, ContentValues().apply {
            put("id", r.id); put("place_id", r.placeId)
            put("created_at", r.createdAt); put("updated_at", r.updatedAt)
            if (r.deletedAt != null) put("deleted_at", r.deletedAt) else putNull("deleted_at")
            put("version", r.version)
        })
    }

    private fun insertArea(db: SQLiteDatabase, r: AreaRow) {
        db.insert("areas", null, ContentValues().apply {
            put("id", r.id); put("kind", r.kind); put("county_name", r.countyName)
            put("center_lat", r.centerLat); put("center_lng", r.centerLng)
            put("radius_miles", r.radiusMiles)
            put("created_at", r.createdAt); put("updated_at", r.updatedAt)
            if (r.deletedAt != null) put("deleted_at", r.deletedAt) else putNull("deleted_at")
            put("version", r.version)
        })
    }

    private fun insertRule(db: SQLiteDatabase, r: RuleRow) {
        db.insert("alert_rules", null, ContentValues().apply {
            put("id", r.id); put("kind", r.kind)
            put("enabled", if (r.enabled) 1 else 0); put("threshold", r.threshold)
            put("created_at", r.createdAt); put("updated_at", r.updatedAt)
            if (r.deletedAt != null) put("deleted_at", r.deletedAt) else putNull("deleted_at")
            put("version", r.version)
        })
    }

    private fun insertInbox(db: SQLiteDatabase, r: InboxRow) {
        db.insert("alert_inbox", null, ContentValues().apply {
            put("id", r.id); put("place_id", r.placeId); put("title", r.title); put("body", r.body)
            put("when_ms", r.whenMs); put("low_score", if (r.lowScore) 1 else 0)
            put("created_at", r.createdAt); put("updated_at", r.updatedAt)
            if (r.deletedAt != null) put("deleted_at", r.deletedAt) else putNull("deleted_at")
            put("version", r.version)
        })
    }

    private fun outbox(db: SQLiteDatabase, entityType: String, entityId: String,
                       op: String, payload: JSONObject, baseVersion: Int, now: Long) {
        db.insert("sync_outbox", null, ContentValues().apply {
            put("id", UUID.randomUUID().toString())
            put("entity_type", entityType); put("entity_id", entityId)
            put("operation", op); put("payload_json", payload.toString())
            put("base_version", baseVersion); put("created_at", now)
        })
    }

    // ------------------------------------------------------- JSON payloads

    fun favoriteJson(r: FavoriteRow): JSONObject = JSONObject()
        .put("id", r.id).put("placeId", r.placeId)
        .put("createdAt", r.createdAt).put("updatedAt", r.updatedAt)
        .put("deletedAt", r.deletedAt ?: JSONObject.NULL).put("version", r.version)

    fun areaJson(r: AreaRow): JSONObject = JSONObject()
        .put("id", r.id).put("kind", r.kind).put("countyName", r.countyName)
        .put("centerLat", r.centerLat).put("centerLng", r.centerLng)
        .put("radiusMiles", r.radiusMiles)
        .put("createdAt", r.createdAt).put("updatedAt", r.updatedAt)
        .put("deletedAt", r.deletedAt ?: JSONObject.NULL).put("version", r.version)

    fun ruleJson(r: RuleRow): JSONObject = JSONObject()
        .put("id", r.id).put("kind", r.kind).put("enabled", r.enabled)
        .put("threshold", r.threshold)
        .put("createdAt", r.createdAt).put("updatedAt", r.updatedAt)
        .put("deletedAt", r.deletedAt ?: JSONObject.NULL).put("version", r.version)

    fun inboxJson(r: InboxRow): JSONObject = JSONObject()
        .put("id", r.id).put("placeId", r.placeId).put("title", r.title).put("body", r.body)
        .put("whenMs", r.whenMs).put("lowScore", r.lowScore)
        .put("createdAt", r.createdAt).put("updatedAt", r.updatedAt)
        .put("deletedAt", r.deletedAt ?: JSONObject.NULL).put("version", r.version)

    fun profileJson(p: ProfileRow): JSONObject = JSONObject()
        .put("name", p.name).put("homeLat", p.homeLat).put("homeLng", p.homeLng)
        .put("homeLabel", p.homeLabel).put("radiusMiles", p.radiusMiles)
        .put("alertsFavorites", p.alertsFavorites).put("alertsArea", p.alertsArea)
        .put("threshold", p.threshold).put("seenWelcome", p.seenWelcome)
        .put("lastSyncMs", p.lastSyncMs).put("lastCountySyncMs", p.lastCountySyncMs)
        .put("updatedAt", p.updatedAt)

    // ------------------------------------------------------------ raw reads

    @Synchronized fun allFavorites(includeDeleted: Boolean = false): List<FavoriteRow> {
        val db = helper.readableDatabase
        val where = if (includeDeleted) "" else "WHERE deleted_at IS NULL"
        return db.rawQuery("SELECT id,place_id,created_at,updated_at,deleted_at,version FROM favorites $where", null).use { c ->
            val out = mutableListOf<FavoriteRow>()
            while (c.moveToNext()) out += FavoriteRow(
                c.getString(0), c.getString(1), c.getLong(2), c.getLong(3),
                if (c.isNull(4)) null else c.getLong(4), c.getInt(5)
            )
            out
        }
    }

    @Synchronized fun allAreas(includeDeleted: Boolean = false): List<AreaRow> {
        val db = helper.readableDatabase
        val where = if (includeDeleted) "" else "WHERE deleted_at IS NULL"
        return db.rawQuery("SELECT id,kind,county_name,center_lat,center_lng,radius_miles,created_at,updated_at,deleted_at,version FROM areas $where", null).use { c ->
            val out = mutableListOf<AreaRow>()
            while (c.moveToNext()) out += AreaRow(
                c.getString(0), c.getString(1), c.getString(2) ?: "",
                c.getDouble(3), c.getDouble(4), c.getDouble(5),
                c.getLong(6), c.getLong(7), if (c.isNull(8)) null else c.getLong(8), c.getInt(9)
            )
            out
        }
    }

    @Synchronized fun allRules(includeDeleted: Boolean = false): List<RuleRow> {
        val db = helper.readableDatabase
        val where = if (includeDeleted) "" else "WHERE deleted_at IS NULL"
        return db.rawQuery("SELECT id,kind,enabled,threshold,created_at,updated_at,deleted_at,version FROM alert_rules $where", null).use { c ->
            val out = mutableListOf<RuleRow>()
            while (c.moveToNext()) out += RuleRow(
                c.getString(0), c.getString(1), c.getInt(2) == 1, c.getInt(3),
                c.getLong(4), c.getLong(5), if (c.isNull(6)) null else c.getLong(6), c.getInt(7)
            )
            out
        }
    }

    @Synchronized fun allInbox(includeDeleted: Boolean = false): List<InboxRow> {
        val db = helper.readableDatabase
        val where = if (includeDeleted) "" else "WHERE deleted_at IS NULL"
        return db.rawQuery("SELECT id,place_id,title,body,when_ms,low_score,created_at,updated_at,deleted_at,version FROM alert_inbox $where ORDER BY when_ms DESC", null).use { c ->
            val out = mutableListOf<InboxRow>()
            while (c.moveToNext()) out += InboxRow(
                c.getString(0), c.getString(1), c.getString(2) ?: "", c.getString(3) ?: "",
                c.getLong(4), c.getInt(5) == 1, c.getLong(6), c.getLong(7),
                if (c.isNull(8)) null else c.getLong(8), c.getInt(9)
            )
            out
        }
    }

    @Synchronized fun outboxCount(): Int =
        helper.readableDatabase.rawQuery("SELECT COUNT(*) FROM sync_outbox", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    // --------------------------------------------------------- cached state

    private fun reloadCaches(db: SQLiteDatabase) {
        profileCache = readProfile(db)
        favoritesCache = allFavorites().map { it.placeId }.toSet()
        countiesCache = allAreas().filter { it.kind == "COUNTY" }.map { it.countyName }.toSet()
        inboxCache = allInbox().map { AlertItem(it.placeId, it.title, it.body, it.whenMs, it.lowScore) }
    }

    @Synchronized fun refreshCaches() {
        reloadCaches(helper.readableDatabase)
    }

    val profile: ProfileRow get() = profileCache
    fun favorites(): Set<String> = favoritesCache
    fun monitoredCounties(): Set<String> = countiesCache
    fun inbox(): List<AlertItem> = inboxCache

    // ------------------------------------------------------------ mutations

    @Synchronized
    fun updateProfile(mut: (ProfileRow) -> Unit) {
        val db = helper.writableDatabase
        val p = readProfile(db)
        mut(p)
        p.updatedAt = System.currentTimeMillis()
        db.beginTransaction()
        try {
            writeProfile(db, p)
            outbox(db, "profile", "profile", "UPDATE", profileJson(p), 0, p.updatedAt)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        profileCache = p
    }

    /** Set favorite on/off; returns the new state. Tombstones, never deletes.
     *  QA fix (2026-10-13, second round): operate on the place's LIVE row —
     *  and on ALL of them. A place can legitimately have several rows
     *  (one live + tombstones from merges); the old code took whichever
     *  row SQLite returned first, so un-favoriting could tombstone an
     *  already-dead row and leave the live twin untouched — the place
     *  stayed favorited forever. Turning off now tombstones every live
     *  row for the place; turning on revives the newest row and retires
     *  any extra live duplicates the same way. */
    @Synchronized
    fun setFavorite(placeId: String, on: Boolean): Boolean {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        val rows = db.rawQuery(
            "SELECT id,created_at,updated_at,deleted_at,version FROM favorites WHERE place_id=? ORDER BY updated_at DESC",
            arrayOf(placeId)
        ).use { c ->
            val out = mutableListOf<FavoriteRow>()
            while (c.moveToNext()) out += FavoriteRow(
                c.getString(0), placeId, c.getLong(1), c.getLong(2),
                if (c.isNull(3)) null else c.getLong(3), c.getInt(4)
            )
            out
        }
        db.beginTransaction()
        try {
            if (rows.isEmpty()) {
                if (on) {
                    val row = FavoriteRow(UUID.randomUUID().toString(), placeId, now, now, null, 1)
                    insertFavorite(db, row)
                    outbox(db, "favorite", row.id, "CREATE", favoriteJson(row), 0, now)
                }
            } else {
                val live = rows.filter { it.deletedAt == null }
                if (on) {
                    val primary = live.firstOrNull() ?: rows.first()
                    val row = FavoriteRow(primary.id, placeId, primary.createdAt, now, null, primary.version + 1)
                    db.delete("favorites", "id=?", arrayOf(primary.id))
                    insertFavorite(db, row)
                    outbox(db, "favorite", primary.id, "UPDATE", favoriteJson(row), primary.version, now)
                    // Retire any additional live duplicates for this place.
                    for (extra in live.drop(1)) {
                        val tomb = FavoriteRow(extra.id, placeId, extra.createdAt, now, now, extra.version + 1)
                        db.delete("favorites", "id=?", arrayOf(extra.id))
                        insertFavorite(db, tomb)
                        outbox(db, "favorite", extra.id, "DELETE", favoriteJson(tomb), extra.version, now)
                    }
                } else {
                    for (row in live) {
                        val tomb = FavoriteRow(row.id, placeId, row.createdAt, now, now, row.version + 1)
                        db.delete("favorites", "id=?", arrayOf(row.id))
                        insertFavorite(db, tomb)
                        outbox(db, "favorite", row.id, "DELETE", favoriteJson(tomb), row.version, now)
                    }
                }
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        favoritesCache = allFavorites().map { it.placeId }.toSet()
        return on
    }

    @Synchronized
    fun toggleFavorite(placeId: String): Boolean = setFavorite(placeId, placeId !in favoritesCache)

    @Synchronized
    fun setMonitoredCounties(counties: Set<String>) {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        val current = allAreas().filter { it.kind == "COUNTY" }
        db.beginTransaction()
        try {
            for (row in current) {
                if (row.countyName !in counties) {
                    val tomb = row.copy(updatedAt = now, deletedAt = now, version = row.version + 1)
                    db.delete("areas", "id=?", arrayOf(row.id)); insertArea(db, tomb)
                    outbox(db, "area", row.id, "DELETE", areaJson(tomb), row.version, now)
                }
            }
            val live = current.filter { it.deletedAt == null }.map { it.countyName }.toSet()
            val tombstoned = allAreas(includeDeleted = true)
                .filter { it.kind == "COUNTY" && it.deletedAt != null }
                .associateBy { it.countyName }
            for (county in counties) {
                if (county in live) continue
                val revive = tombstoned[county]
                if (revive != null) {
                    val row = revive.copy(updatedAt = now, deletedAt = null, version = revive.version + 1)
                    db.delete("areas", "id=?", arrayOf(row.id)); insertArea(db, row)
                    outbox(db, "area", row.id, "UPDATE", areaJson(row), revive.version, now)
                } else {
                    val row = AreaRow(UUID.randomUUID().toString(), "COUNTY", county, 0.0, 0.0, 0.0, now, now, null, 1)
                    insertArea(db, row)
                    outbox(db, "area", row.id, "CREATE", areaJson(row), 0, now)
                }
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        countiesCache = allAreas().filter { it.kind == "COUNTY" }.map { it.countyName }.toSet()
    }

    /** Keep the single live RADIUS area in step with the profile home. */
    @Synchronized
    fun syncHomeArea() {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        val p = profileCache
        val existing = allAreas().firstOrNull { it.kind == "RADIUS" }
        db.beginTransaction()
        try {
            if (existing == null) {
                val row = AreaRow(UUID.randomUUID().toString(), "RADIUS", "", p.homeLat, p.homeLng, p.radiusMiles, now, now, null, 1)
                insertArea(db, row)
                outbox(db, "area", row.id, "CREATE", areaJson(row), 0, now)
            } else if (existing.centerLat != p.homeLat || existing.centerLng != p.homeLng || existing.radiusMiles != p.radiusMiles) {
                val row = existing.copy(centerLat = p.homeLat, centerLng = p.homeLng, radiusMiles = p.radiusMiles, updatedAt = now, version = existing.version + 1)
                db.delete("areas", "id=?", arrayOf(row.id)); insertArea(db, row)
                outbox(db, "area", row.id, "UPDATE", areaJson(row), existing.version, now)
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    @Synchronized
    fun setRule(kind: String, enabled: Boolean, threshold: Int) {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        val existing = allRules().firstOrNull { it.kind == kind }
        db.beginTransaction()
        try {
            if (existing == null) {
                val row = RuleRow(UUID.randomUUID().toString(), kind, enabled, threshold, now, now, null, 1)
                insertRule(db, row)
                outbox(db, "alert_rule", row.id, "CREATE", ruleJson(row), 0, now)
            } else if (existing.enabled != enabled || existing.threshold != threshold) {
                val row = existing.copy(enabled = enabled, threshold = threshold, updatedAt = now, version = existing.version + 1)
                db.delete("alert_rules", "id=?", arrayOf(row.id)); insertRule(db, row)
                outbox(db, "alert_rule", row.id, "UPDATE", ruleJson(row), existing.version, now)
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }

    @Synchronized
    fun addInboxItem(item: AlertItem) {
        val db = helper.writableDatabase
        val dupe = db.rawQuery(
            "SELECT 1 FROM alert_inbox WHERE place_id=? AND when_ms=? AND deleted_at IS NULL",
            arrayOf(item.placeId, item.whenMs.toString())
        ).use { it.moveToFirst() }
        if (dupe) return
        val now = System.currentTimeMillis()
        val row = InboxRow(UUID.randomUUID().toString(), item.placeId, item.title, item.body, item.whenMs, item.lowScore, now, now, null, 1)
        db.beginTransaction()
        try {
            insertInbox(db, row)
            outbox(db, "alert_inbox", row.id, "CREATE", inboxJson(row), 0, now)
            // Cap at 50 live rows like v2.0: tombstone the overflow.
            val live = allInbox()
            if (live.size > 50) {
                for (old in live.drop(50)) {
                    val tomb = old.copy(updatedAt = now, deletedAt = now, version = old.version + 1)
                    db.delete("alert_inbox", "id=?", arrayOf(old.id)); insertInbox(db, tomb)
                    outbox(db, "alert_inbox", old.id, "DELETE", inboxJson(tomb), old.version, now)
                }
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        inboxCache = allInbox().map { AlertItem(it.placeId, it.title, it.body, it.whenMs, it.lowScore) }
    }

    @Synchronized
    fun replaceInbox(items: List<AlertItem>) {
        val db = helper.writableDatabase
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            for (row in allInbox()) {
                val tomb = row.copy(updatedAt = now, deletedAt = now, version = row.version + 1)
                db.delete("alert_inbox", "id=?", arrayOf(row.id)); insertInbox(db, tomb)
                outbox(db, "alert_inbox", row.id, "DELETE", inboxJson(tomb), row.version, now)
            }
            for (item in items.take(50)) {
                val row = InboxRow(UUID.randomUUID().toString(), item.placeId, item.title, item.body, item.whenMs, item.lowScore, now, now, null, 1)
                insertInbox(db, row)
                outbox(db, "alert_inbox", row.id, "CREATE", inboxJson(row), 0, now)
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        inboxCache = allInbox().map { AlertItem(it.placeId, it.title, it.body, it.whenMs, it.lowScore) }
    }

    // ------------------------------------------- import merge (Backup use)

    /** Merge one imported row: insert if unknown id; replace if the
     *  incoming updatedAt is newer (tombstones honored). Returns:
     *  1 = inserted, 2 = updated, 0 = skipped (local is newer/equal). */
    /**
     * QA fix (2026-10-13): merges reconcile by NATURAL key, not UUID alone.
     * The same favorite/county/rule can exist locally under a different
     * UUID (e.g. a backup made before an app reset, or the seeded defaults
     * on a fresh install). UUID-only merging created duplicate live rows —
     * worst case, a place the user could never un-favorite, because
     * setFavorite() tombstones one row while its twin kept it alive.
     * Rule: the newest updatedAt for the natural entity wins; any rival
     * row it supersedes is tombstoned (never hard-deleted), with an
     * outbox DELETE so a future sync sees the resolution.
     */
    @Synchronized
    fun mergeFavorite(r: FavoriteRow): Int {
        val db = helper.writableDatabase
        val all = allFavorites(includeDeleted = true)
        val sameId = all.firstOrNull { it.id == r.id }
        val rivals = all.filter { it.id != r.id && it.placeId == r.placeId }
        val effective = maxOf(sameId?.updatedAt ?: Long.MIN_VALUE,
            rivals.maxOfOrNull { it.updatedAt } ?: Long.MIN_VALUE)
        if (effective != Long.MIN_VALUE && r.updatedAt <= effective) return 0
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            for (rival in rivals) {
                val tomb = rival.copy(updatedAt = r.updatedAt, deletedAt = r.updatedAt, version = rival.version + 1)
                db.delete("favorites", "id=?", arrayOf(rival.id)); insertFavorite(db, tomb)
                outbox(db, "favorite", rival.id, "DELETE", favoriteJson(tomb), rival.version, now)
            }
            db.delete("favorites", "id=?", arrayOf(r.id))
            insertFavorite(db, r)
            outbox(db, "favorite", r.id, "UPDATE", favoriteJson(r), 0, now)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return if (sameId == null && rivals.isEmpty()) 1 else 2
    }

    @Synchronized
    fun mergeArea(r: AreaRow): Int {
        val db = helper.writableDatabase
        val all = allAreas(includeDeleted = true)
        val sameId = all.firstOrNull { it.id == r.id }
        // Natural key: a COUNTY area is its county name; the RADIUS area
        // is a singleton (the profile home), so every other RADIUS row
        // is a rival.
        val rivals = all.filter {
            it.id != r.id && it.kind == r.kind &&
                (r.kind == "RADIUS" || it.countyName == r.countyName)
        }
        val effective = maxOf(sameId?.updatedAt ?: Long.MIN_VALUE,
            rivals.maxOfOrNull { it.updatedAt } ?: Long.MIN_VALUE)
        if (effective != Long.MIN_VALUE && r.updatedAt <= effective) return 0
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            for (rival in rivals) {
                val tomb = rival.copy(updatedAt = r.updatedAt, deletedAt = r.updatedAt, version = rival.version + 1)
                db.delete("areas", "id=?", arrayOf(rival.id)); insertArea(db, tomb)
                outbox(db, "area", rival.id, "DELETE", areaJson(tomb), rival.version, now)
            }
            db.delete("areas", "id=?", arrayOf(r.id))
            insertArea(db, r)
            outbox(db, "area", r.id, "UPDATE", areaJson(r), 0, now)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return if (sameId == null && rivals.isEmpty()) 1 else 2
    }

    @Synchronized
    fun mergeRule(r: RuleRow): Int {
        val db = helper.writableDatabase
        val all = allRules(includeDeleted = true)
        val sameId = all.firstOrNull { it.id == r.id }
        // Natural key: one rule per kind (FAVORITES | AREA).
        val rivals = all.filter { it.id != r.id && it.kind == r.kind }
        val effective = maxOf(sameId?.updatedAt ?: Long.MIN_VALUE,
            rivals.maxOfOrNull { it.updatedAt } ?: Long.MIN_VALUE)
        if (effective != Long.MIN_VALUE && r.updatedAt <= effective) return 0
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            for (rival in rivals) {
                val tomb = rival.copy(updatedAt = r.updatedAt, deletedAt = r.updatedAt, version = rival.version + 1)
                db.delete("alert_rules", "id=?", arrayOf(rival.id)); insertRule(db, tomb)
                outbox(db, "alert_rule", rival.id, "DELETE", ruleJson(tomb), rival.version, now)
            }
            db.delete("alert_rules", "id=?", arrayOf(r.id))
            insertRule(db, r)
            outbox(db, "alert_rule", r.id, "UPDATE", ruleJson(r), 0, now)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return if (sameId == null && rivals.isEmpty()) 1 else 2
    }

    @Synchronized
    fun mergeInbox(r: InboxRow): Int = mergeRow("alert_inbox", r.id, r.updatedAt) { db ->
        db.delete("alert_inbox", "id=?", arrayOf(r.id)); insertInbox(db, r)
        outbox(db, "alert_inbox", r.id, "UPDATE", inboxJson(r), 0, System.currentTimeMillis())
    }

    private fun mergeRow(table: String, id: String, incomingUpdatedAt: Long, write: (SQLiteDatabase) -> Unit): Int {
        val db = helper.writableDatabase
        val localUpdated = db.rawQuery("SELECT updated_at FROM $table WHERE id=?", arrayOf(id)).use { c ->
            if (c.moveToFirst()) c.getLong(0) else null
        }
        if (localUpdated != null && incomingUpdatedAt <= localUpdated) return 0
        db.beginTransaction()
        try {
            write(db)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        return if (localUpdated == null) 1 else 2
    }

    @Synchronized
    fun mergeProfile(p: ProfileRow): Boolean {
        val db = helper.writableDatabase
        val local = readProfile(db)
        if (p.updatedAt <= local.updatedAt) return false
        db.beginTransaction()
        try {
            writeProfile(db, p)
            outbox(db, "profile", "profile", "UPDATE", profileJson(p), 0, System.currentTimeMillis())
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        profileCache = p
        return true
    }
}
