package com.kyronapp.kyron.data.db

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.kyronapp.kyron.data.Inspection
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.Violation
import org.json.JSONArray
import org.json.JSONObject

/**
 * Catalog store (LF-2, region-scoped in LF-4): the replaceable
 * places/inspections database.
 *
 * Replaces the old design where the whole catalog lived in one 5.3 MB JSON
 * file that was parsed fully at launch and rewritten fully on every merge
 * or single-place update. Here:
 *  - first launch imports the bundled seed (or the legacy on-device
 *    places.json, preserving merged data) into indexed SQLite tables once;
 *  - reads are targeted queries (by id, by county, FTS text search,
 *    lat/lng bounds for the map) — no screen needs the whole state;
 *  - writes touch only the changed rows, in one transaction.
 *
 * Schema v2 (LF-4) adds the region model: every place carries its USPS
 * state, its inspecting jurisdiction, its region_id ("us-al", "us-fl", …)
 * and — for jurisdictions that publish no numeric score — the native
 * result text (place-level latest + per-inspection). v1 data was entirely
 * Alabama, so the v1→v2 migration simply stamps state='AL',
 * region_id='us-al' on every existing row; user data lives in a separate
 * database (UserStore) and is never touched by catalog migrations or by
 * region-pack installs.
 *
 * Implemented over Android's built-in SQLite (SQLiteOpenHelper + FTS4)
 * rather than Room: the manual build pipeline has no kapt/annotation
 * processing, so Room codegen is impractical here. The schema and the
 * repository contract above it are the architecture; the library is an
 * implementation detail (Free/LocalFirst plan section 1.3).
 */
class CatalogDb(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "kyron_catalog.db", null, 2) {

    /** True when the FTS4 module accepted the virtual table at create time. */
    @Volatile var ftsAvailable: Boolean = false
        private set

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE places(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_lc TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
                zip TEXT NOT NULL DEFAULT '', county TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
                date_key INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                lat REAL, lng REAL,
                geo_status TEXT NOT NULL DEFAULT 'LEGACY',
                geo_acc TEXT NOT NULL DEFAULT 'NONE',
                geo_prov TEXT NOT NULL DEFAULT '',
                geo_match TEXT NOT NULL DEFAULT '',
                detail_url TEXT,
                state TEXT NOT NULL DEFAULT 'AL',
                jurisdiction TEXT NOT NULL DEFAULT '',
                region_id TEXT NOT NULL DEFAULT 'us-al',
                result_text TEXT NOT NULL DEFAULT '')"""
        )
        db.execSQL("CREATE INDEX idx_places_county ON places(county)")
        db.execSQL("CREATE INDEX idx_places_zip ON places(zip)")
        db.execSQL("CREATE INDEX idx_places_score ON places(score)")
        db.execSQL("CREATE INDEX idx_places_latlng ON places(lat, lng)")
        db.execSQL("CREATE INDEX idx_places_region ON places(region_id)")
        db.execSQL(
            """CREATE TABLE inspections(
                place_id TEXT NOT NULL, idx INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '', violations_json TEXT NOT NULL DEFAULT '[]',
                result_text TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(place_id, idx))"""
        )
        db.execSQL("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
        createFts(db)
    }

    private fun createFts(db: SQLiteDatabase) {
        ftsAvailable = runCatching {
            db.execSQL(
                "CREATE VIRTUAL TABLE places_fts USING fts4(place_id UNINDEXED, name, city, address, zip, county)"
            )
            true
        }.getOrDefault(false)
    }

    override fun onOpen(db: SQLiteDatabase) {
        super.onOpen(db)
        // LF-4 recovery fix: ftsAvailable was only ever set in onCreate,
        // so on every launch against an EXISTING database (i.e. every
        // returning user) it stayed false — FTS search silently fell back
        // to LIKE and pack installs skipped FTS rows entirely. Probe for
        // the table instead; create it if a legacy DB somehow lacks it.
        if (!ftsAvailable) {
            val exists = db.rawQuery(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='places_fts'", null
            ).use { it.moveToFirst() }
            if (exists) ftsAvailable = true else createFts(db)
        }
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            // LF-4 region model. Every v1 row is Alabama data (the catalog
            // was single-state), so the defaults ARE the migration: stamp
            // state/region in place; no row is moved, rewritten in content,
            // or deleted. The FTS table and indexes are untouched.
            db.execSQL("ALTER TABLE places ADD COLUMN state TEXT NOT NULL DEFAULT 'AL'")
            db.execSQL("ALTER TABLE places ADD COLUMN jurisdiction TEXT NOT NULL DEFAULT ''")
            db.execSQL("ALTER TABLE places ADD COLUMN region_id TEXT NOT NULL DEFAULT 'us-al'")
            db.execSQL("ALTER TABLE places ADD COLUMN result_text TEXT NOT NULL DEFAULT ''")
            db.execSQL("ALTER TABLE inspections ADD COLUMN result_text TEXT NOT NULL DEFAULT ''")
            db.execSQL("CREATE INDEX idx_places_region ON places(region_id)")
        }
    }

    companion object {
        /** Highest pack schema this build can install (pack_meta.schema_version). */
        const val SUPPORTED_PACK_SCHEMA = 2

        // ---------------------------------------------------- search text
        // Workstream D / FIX5: the FTS tokenizer splits "McDonald's" into
        // the tokens (mcdonald, s), so a user typing "McDonalds" (or with
        // a curly apostrophe from Android autocorrect, which tokenizes
        // differently again) could NEVER match. Fix: the FTS name column
        // stores the verbatim name PLUS an apostrophe-stripped alias
        // ("McDonald's Chelsea McDonalds Chelsea"), and queries strip
        // apostrophes the same way before MATCH is built. The places
        // table always keeps the verbatim source name — only the search
        // index carries the alias. Both apostrophes (ASCII ' and the
        // U+2019 autocorrect form) are stripped on both sides.
        fun stripApostrophes(s: String): String =
            s.replace("'", "").replace("\u2019", "")

        /** Value stored in places_fts.name for [name] (verbatim + alias). */
        fun ftsName(name: String): String {
            val alias = stripApostrophes(name)
            return if (alias == name) name else "$name $alias"
        }

        /** SQL expression producing the same value as [ftsName] for the
         *  places.name column (used by SQL-side FTS rebuilds). */
        const val FTS_NAME_SQL: String =
            "name || ' ' || REPLACE(REPLACE(name, '''', ''), '\u2019', '')"

        private val dateFmt = java.text.SimpleDateFormat("M/d/yyyy", java.util.Locale.US)

        /** Epoch-day sort key for an "M/d/yyyy" inspection date (0 when unparseable).
         *  QA fix (2026-10-13): SimpleDateFormat is NOT thread-safe, and this
         *  is called from parallel Dispatchers.IO coroutines (seed import,
         *  merges, detail updates) — an unsynchronized shared formatter can
         *  corrupt parses or throw. Parse under the formatter's monitor. */
        fun dateKey(date: String): Long = runCatching {
            val ms = synchronized(dateFmt) { dateFmt.parse(date.trim())?.time } ?: 0L
            ms / 86_400_000L
        }.getOrDefault(0L)
    }

    // ------------------------------------------------------------------ meta

    fun metaGet(db: SQLiteDatabase, key: String): String? =
        db.rawQuery("SELECT v FROM meta WHERE k=?", arrayOf(key)).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }

    fun metaPut(db: SQLiteDatabase, key: String, value: String) {
        val cv = ContentValues().apply { put("k", key); put("v", value) }
        db.insertWithOnConflict("meta", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun metaDelete(db: SQLiteDatabase, key: String) {
        db.delete("meta", "k=?", arrayOf(key))
    }

    fun placeCount(db: SQLiteDatabase): Int =
        db.rawQuery("SELECT COUNT(*) FROM places", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    fun regionPlaceCount(db: SQLiteDatabase, regionId: String): Int =
        db.rawQuery("SELECT COUNT(*) FROM places WHERE region_id=?", arrayOf(regionId)).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    fun regionIds(db: SQLiteDatabase): List<String> =
        db.rawQuery("SELECT DISTINCT region_id FROM places ORDER BY region_id", null).use { c ->
            val out = mutableListOf<String>()
            while (c.moveToNext()) out += c.getString(0)
            out
        }

    /**
     * Delete every catalog row of one region (places + their inspections +
     * FTS rows). Caller owns the transaction. The user store is a different
     * database file and is never touched by region operations.
     */
    fun deleteRegionRows(db: SQLiteDatabase, regionId: String) {
        db.execSQL(
            "DELETE FROM inspections WHERE place_id IN (SELECT id FROM places WHERE region_id=?)",
            arrayOf(regionId)
        )
        if (ftsAvailable) {
            db.execSQL(
                "DELETE FROM places_fts WHERE place_id IN (SELECT id FROM places WHERE region_id=?)",
                arrayOf(regionId)
            )
        }
        db.execSQL("DELETE FROM places WHERE region_id=?", arrayOf(regionId))
    }

    /** Rows in the FTS index (0 when FTS is unavailable). */
    fun ftsRowCount(db: SQLiteDatabase): Int {
        if (!ftsAvailable) return 0
        return db.rawQuery("SELECT COUNT(*) FROM places_fts", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }
    }

    /**
     * Workstream D / FIX5 self-heal: the FTS index must mirror the places
     * table exactly. A lost FTS row (the LF-4 desync class) makes a place
     * invisible to text search while Browse and the map still find it, and
     * before this check NOTHING ever reconciled the two tables — the
     * desync was permanent. Count mismatch ⇒ rebuild the whole index from
     * the places table (with the search alias, see [ftsName]). Returns
     * true when a rebuild happened.
     */
    fun reconcileFts(db: SQLiteDatabase): Boolean {
        if (!ftsAvailable) return false
        if (ftsRowCount(db) == placeCount(db)) return false
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM places_fts")
            db.execSQL(
                "INSERT INTO places_fts(place_id,name,city,address,zip,county) " +
                    "SELECT id, $FTS_NAME_SQL, city, address, zip, county FROM places"
            )
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return true
    }

    /** Coordinates a device itself produced (geo_prov='DEVICE' — the old
     *  on-device geocoder cache, drive-by fixes) for one region. The
     *  bundled-region refresh preserves these across the swap: they are
     *  device data, not seed data. */
    fun deviceCoords(db: SQLiteDatabase, regionId: String): Map<String, Pair<Double, Double>> =
        db.rawQuery(
            "SELECT id, lat, lng FROM places WHERE region_id=? AND geo_prov='DEVICE' AND lat IS NOT NULL AND lng IS NOT NULL",
            arrayOf(regionId)
        ).use { c ->
            val out = HashMap<String, Pair<Double, Double>>()
            while (c.moveToNext()) out[c.getString(0)] = c.getDouble(1) to c.getDouble(2)
            out
        }

    // ---------------------------------------------------------------- writes

    /** Insert or replace one place and its inspections + FTS row. */
    fun upsertPlace(db: SQLiteDatabase, p: Place) {
        val cv = ContentValues().apply {
            put("id", p.id); put("name", p.name); put("name_lc", p.name.lowercase())
            put("address", p.address); put("city", p.city); put("zip", p.zip)
            put("county", p.county); put("score", p.score); put("date", p.date)
            put("date_key", dateKey(p.date))
            put("source", p.source)
            if (p.lat != null) put("lat", p.lat) else putNull("lat")
            if (p.lng != null) put("lng", p.lng) else putNull("lng")
            put("geo_status", p.geoStatus); put("geo_acc", p.geoAccuracy)
            put("geo_prov", p.geoProvider); put("geo_match", p.geoMatch)
            if (p.detailUrl != null) put("detail_url", p.detailUrl) else putNull("detail_url")
            put("state", p.state); put("jurisdiction", p.jurisdiction)
            put("region_id", p.regionId); put("result_text", p.nativeResult)
        }
        db.insertWithOnConflict("places", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        db.delete("inspections", "place_id=?", arrayOf(p.id))
        p.inspections.forEachIndexed { i, insp ->
            val iv = ContentValues().apply {
                put("place_id", p.id); put("idx", i)
                put("score", insp.score); put("date", insp.date); put("type", insp.type)
                put("violations_json", JSONArray().apply {
                    insp.violations.forEach { v -> put(v.toJson()) }
                }.toString())
                put("result_text", insp.nativeResult)
            }
            db.insert("inspections", null, iv)
        }
        if (ftsAvailable) {
            db.delete("places_fts", "place_id=?", arrayOf(p.id))
            val fv = ContentValues().apply {
                put("place_id", p.id); put("name", ftsName(p.name)); put("city", p.city)
                put("address", p.address); put("zip", p.zip); put("county", p.county)
            }
            db.insert("places_fts", null, fv)
        }
    }

    /** Delete one place and its inspections + FTS row (pack delta deletions). */
    fun deletePlace(db: SQLiteDatabase, placeId: String) {
        db.delete("inspections", "place_id=?", arrayOf(placeId))
        if (ftsAvailable) db.delete("places_fts", "place_id=?", arrayOf(placeId))
        db.delete("places", "id=?", arrayOf(placeId))
    }

    fun setCoords(db: SQLiteDatabase, placeId: String, lat: Double, lng: Double, provider: String) {
        val cv = ContentValues().apply {
            put("lat", lat); put("lng", lng)
            put("geo_status", Place.STATUS_ACCEPTED)
            put("geo_acc", Place.ACC_ADDRESS_RANGE)
            put("geo_prov", provider)
        }
        db.update("places", cv, "id=?", arrayOf(placeId))
    }

    /**
     * Bulk-import a seed/pack JSON array. One transaction, prepared statements.
     * Legacy places carrying coordinates but no provenance are marked
     * ACCEPTED/HARVEST (they came from the earlier harvest pipeline).
     */
    fun importSeed(db: SQLiteDatabase, arr: JSONArray) {
        val ps = db.compileStatement(
            """INSERT OR REPLACE INTO places
               (id,name,name_lc,address,city,zip,county,score,date,source,lat,lng,
                geo_status,geo_acc,geo_prov,geo_match,detail_url,date_key,
                state,jurisdiction,region_id,result_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        )
        val isStmt = db.compileStatement(
            "INSERT OR REPLACE INTO inspections(place_id,idx,score,date,type,violations_json,result_text) VALUES (?,?,?,?,?,?,?)"
        )
        val fs = if (ftsAvailable) db.compileStatement(
            "INSERT INTO places_fts(place_id,name,city,address,zip,county) VALUES (?,?,?,?,?,?)"
        ) else null
        db.beginTransaction()
        try {
            for (i in 0 until arr.length()) {
                val p = Place.fromJson(arr.getJSONObject(i))
                val hasCoords = p.lat != null && p.lng != null
                val status = when {
                    p.geoStatus != Place.STATUS_LEGACY -> p.geoStatus
                    hasCoords -> Place.STATUS_ACCEPTED
                    else -> p.geoStatus
                }
                val acc = when {
                    p.geoAccuracy != Place.ACC_NONE -> p.geoAccuracy
                    hasCoords -> Place.ACC_ADDRESS_RANGE
                    else -> p.geoAccuracy
                }
                val prov = if (p.geoProvider.isEmpty() && hasCoords) "HARVEST" else p.geoProvider
                ps.clearBindings()
                ps.bindString(1, p.id); ps.bindString(2, p.name); ps.bindString(3, p.name.lowercase())
                ps.bindString(4, p.address); ps.bindString(5, p.city); ps.bindString(6, p.zip)
                ps.bindString(7, p.county); ps.bindLong(8, p.score.toLong()); ps.bindString(9, p.date)
                ps.bindString(10, p.source)
                if (p.lat != null) ps.bindDouble(11, p.lat) else ps.bindNull(11)
                if (p.lng != null) ps.bindDouble(12, p.lng) else ps.bindNull(12)
                ps.bindString(13, status); ps.bindString(14, acc); ps.bindString(15, prov)
                ps.bindString(16, p.geoMatch)
                if (p.detailUrl != null) ps.bindString(17, p.detailUrl) else ps.bindNull(17)
                ps.bindLong(18, dateKey(p.date))
                ps.bindString(19, p.state); ps.bindString(20, p.jurisdiction)
                ps.bindString(21, p.regionId); ps.bindString(22, p.nativeResult)
                ps.executeInsert()
                p.inspections.forEachIndexed { idx, insp ->
                    isStmt.clearBindings()
                    isStmt.bindString(1, p.id); isStmt.bindLong(2, idx.toLong())
                    isStmt.bindLong(3, insp.score.toLong()); isStmt.bindString(4, insp.date)
                    isStmt.bindString(5, insp.type)
                    isStmt.bindString(6, JSONArray().apply {
                        insp.violations.forEach { v -> put(v.toJson()) }
                    }.toString())
                    isStmt.bindString(7, insp.nativeResult)
                    isStmt.executeInsert()
                }
                if (fs != null) {
                    fs.clearBindings()
                    fs.bindString(1, p.id); fs.bindString(2, ftsName(p.name)); fs.bindString(3, p.city)
                    fs.bindString(4, p.address); fs.bindString(5, p.zip); fs.bindString(6, p.county)
                    fs.executeInsert()
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ----------------------------------------------------------------- reads

    private fun placeFromCursor(c: Cursor, inspections: List<Inspection>): Place = Place(
        id = c.getString(0),
        name = c.getString(1),
        address = c.getString(2),
        city = c.getString(3),
        zip = c.getString(4),
        county = c.getString(5),
        score = c.getInt(6),
        date = c.getString(7),
        source = c.getString(8),
        lat = if (c.isNull(9)) null else c.getDouble(9),
        lng = if (c.isNull(10)) null else c.getDouble(10),
        detailUrl = if (c.isNull(11)) null else c.getString(11),
        inspections = inspections,
        geoStatus = c.getString(12),
        geoAccuracy = c.getString(13),
        geoProvider = c.getString(14),
        geoMatch = c.getString(15),
        state = c.getString(16) ?: "AL",
        jurisdiction = c.getString(17) ?: "",
        nativeResult = c.getString(18) ?: ""
    )

    private val placeCols =
        "id,name,address,city,zip,county,score,date,source,lat,lng,detail_url,geo_status,geo_acc,geo_prov,geo_match,state,jurisdiction,result_text"

    fun inspectionsFor(db: SQLiteDatabase, placeId: String): List<Inspection> =
        db.rawQuery(
            "SELECT score,date,type,violations_json,result_text FROM inspections WHERE place_id=? ORDER BY idx",
            arrayOf(placeId)
        ).use { c ->
            val out = mutableListOf<Inspection>()
            while (c.moveToNext()) {
                val vs = mutableListOf<Violation>()
                val arr = runCatching { JSONArray(c.getString(3)) }.getOrNull()
                if (arr != null) for (i in 0 until arr.length()) {
                    vs += Violation.fromJson(arr.getJSONObject(i))
                }
                out += Inspection(c.getInt(0), c.getString(1) ?: "", c.getString(2) ?: "", vs, c.getString(4) ?: "")
            }
            out
        }

    fun placeById(db: SQLiteDatabase, id: String): Place? =
        db.rawQuery("SELECT $placeCols FROM places WHERE id=?", arrayOf(id)).use { c ->
            if (c.moveToFirst()) placeFromCursor(c, inspectionsFor(db, id)) else null
        }

    fun allPlaces(db: SQLiteDatabase): List<Place> {
        val insps = HashMap<String, MutableList<Inspection>>()
        db.rawQuery("SELECT place_id,score,date,type,violations_json,result_text FROM inspections ORDER BY place_id, idx", null)
            .use { c ->
                while (c.moveToNext()) {
                    val vs = mutableListOf<Violation>()
                    val arr = runCatching { JSONArray(c.getString(4)) }.getOrNull()
                    if (arr != null) for (i in 0 until arr.length()) {
                        vs += Violation.fromJson(arr.getJSONObject(i))
                    }
                    insps.getOrPut(c.getString(0)) { mutableListOf() } +=
                        Inspection(c.getInt(1), c.getString(2) ?: "", c.getString(3) ?: "", vs, c.getString(5) ?: "")
                }
            }
        return db.rawQuery("SELECT $placeCols FROM places ORDER BY name_lc", null).use { c ->
            val out = ArrayList<Place>(c.count)
            while (c.moveToNext()) {
                val id = c.getString(0)
                out += placeFromCursor(c, insps[id] ?: emptyList())
            }
            out
        }
    }

    /** Attach inspections to a page of places with one batched query. */
    fun attachInspections(db: SQLiteDatabase, places: List<Place>): List<Place> {
        if (places.isEmpty()) return places
        val byId = HashMap<String, MutableList<Inspection>>()
        val ids = places.map { it.id }
        for (chunk in ids.chunked(400)) {
            val ph = chunk.joinToString(",") { "?" }
            db.rawQuery(
                "SELECT place_id,score,date,type,violations_json,result_text FROM inspections WHERE place_id IN ($ph) ORDER BY place_id, idx",
                chunk.toTypedArray()
            ).use { c ->
                while (c.moveToNext()) {
                    val vs = mutableListOf<Violation>()
                    val arr = runCatching { JSONArray(c.getString(4)) }.getOrNull()
                    if (arr != null) for (i in 0 until arr.length()) {
                        vs += Violation.fromJson(arr.getJSONObject(i))
                    }
                    byId.getOrPut(c.getString(0)) { mutableListOf() } +=
                        Inspection(c.getInt(1), c.getString(2) ?: "", c.getString(3) ?: "", vs, c.getString(5) ?: "")
                }
            }
        }
        return places.map { p -> if (byId.containsKey(p.id)) p.copy(inspections = byId[p.id]!!) else p }
    }

    fun counties(db: SQLiteDatabase, regionId: String? = null): List<String> {
        val sql = if (regionId != null)
            "SELECT DISTINCT county FROM places WHERE county<>'' AND region_id=? ORDER BY county"
        else
            "SELECT DISTINCT county FROM places WHERE county<>'' ORDER BY county"
        val args = if (regionId != null) arrayOf(regionId) else null
        return db.rawQuery(sql, args).use { c ->
            val out = mutableListOf<String>()
            while (c.moveToNext()) out += c.getString(0)
            out
        }
    }

    /**
     * Text search: FTS4 MATCH when available (prefix matching per token),
     * LIKE fallback otherwise. Returns place ids in relevance/insert order;
     * the caller applies structured filters + sort in SQL via [search].
     */
    fun ftsIds(db: SQLiteDatabase, text: String, limit: Int): List<String>? {
        if (!ftsAvailable || text.isBlank()) return null
        // Workstream D / FIX5: strip apostrophes from the query exactly as
        // the index alias does (see ftsName) — "McDonald's", "McDonalds"
        // and the autocorrect form "McDonald’s" all become the token
        // "mcdonalds", which the alias in the index carries.
        val cleaned = stripApostrophes(text)
        if (cleaned.isBlank()) return null
        val query = cleaned.trim().split(Regex("\\s+"))
            .filter { it.isNotEmpty() }
            .joinToString(" ") { "\"" + it.replace("\"", "\"\"") + "\"*" }
        if (query.isEmpty()) return null
        return runCatching {
            db.rawQuery(
                "SELECT place_id FROM places_fts WHERE places_fts MATCH ? LIMIT ?",
                arrayOf(query, limit.toString())
            ).use { c ->
                val out = mutableListOf<String>()
                while (c.moveToNext()) out += c.getString(0)
                out
            }
        }.getOrNull()
    }

    /** Structured search over the catalog. [orderBy] is a fixed internal string, never user input.
     *  [regionId] (LF-4) scopes results to one region pack; null = all regions. */
    fun search(
        db: SQLiteDatabase,
        ids: List<String>?,
        county: String?,
        minScore: Int?,
        maxScore: Int?,
        textLike: String?,
        orderBy: String,
        limit: Int,
        regionId: String? = null
    ): List<Place> {
        val where = StringBuilder("1=1")
        val args = mutableListOf<String>()
        if (regionId != null) { where.append(" AND region_id=?"); args.add(regionId) }
        if (ids != null) {
            if (ids.isEmpty()) return emptyList()
            where.append(" AND id IN (${ids.joinToString(",") { "?" }})")
            args.addAll(ids)
        }
        if (county != null) { where.append(" AND county=?"); args.add(county) }
        // Score-band filters apply only to places that HAVE a numeric score:
        // the NO_SCORE sentinel (-1) must never fall into a band like
        // "Below 85" just because -1 <= 84.
        if (minScore != null || maxScore != null) { where.append(" AND score>=0") }
        if (minScore != null) { where.append(" AND score>=?"); args.add(minScore.toString()) }
        if (maxScore != null) { where.append(" AND score<=?"); args.add(maxScore.toString()) }
        if (textLike != null) {
            // QA fix (2026-10-13): escape LIKE wildcards so user text is
            // matched literally — searching "%" or "_" used to return the
            // whole catalog through this fallback path.
            // Workstream D / FIX5: the comparison is apostrophe-insensitive
            // on BOTH sides (columns via REPLACE, pattern pre-stripped), so
            // this fallback — now also used when FTS returns zero hits —
            // finds "McDonald's" from a "McDonalds" query too.
            fun col(c: String) = "REPLACE(REPLACE($c,'''',''),'\u2019','')"
            where.append(
                " AND (${col("name")} LIKE ? ESCAPE '\\' OR ${col("city")} LIKE ? ESCAPE '\\'" +
                    " OR ${col("address")} LIKE ? ESCAPE '\\' OR ${col("zip")} LIKE ? ESCAPE '\\'" +
                    " OR ${col("county")} LIKE ? ESCAPE '\\')"
            )
            val esc = stripApostrophes(textLike)
                .replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            val pat = "%$esc%"
            repeat(5) { args.add(pat) }
        }
        val sql = "SELECT $placeCols FROM places WHERE $where ORDER BY $orderBy LIMIT ?"
        args.add(limit.toString())
        return db.rawQuery(sql, args.toTypedArray()).use { c ->
            val out = mutableListOf<Place>()
            while (c.moveToNext()) out += placeFromCursor(c, emptyList())
            out
        }
    }

    /** Pre-LF-4 signature kept as a delegate: compiled consumers of the
     *  old 8-arg search (e.g. the QA harness classes) link against it. */
    fun search(
        db: SQLiteDatabase,
        ids: List<String>?,
        county: String?,
        minScore: Int?,
        maxScore: Int?,
        textLike: String?,
        orderBy: String,
        limit: Int
    ): List<Place> = search(db, ids, county, minScore, maxScore, textLike, orderBy, limit, null)

    /** Places with real coordinates inside a lat/lng box (map viewport).
     *  [regionId] (LF-4) scopes to one region; null = all regions. */
    fun inBounds(
        db: SQLiteDatabase, minLat: Double, maxLat: Double,
        minLng: Double, maxLng: Double, limit: Int,
        regionId: String? = null
    ): List<Place> {
        val regionClause = if (regionId != null) " AND region_id=?" else ""
        val args = mutableListOf(
            minLat.toString(), maxLat.toString(), minLng.toString(), maxLng.toString()
        )
        if (regionId != null) args.add(regionId)
        args.add(limit.toString())
        return db.rawQuery(
            """SELECT $placeCols FROM places
               WHERE lat IS NOT NULL AND lng IS NOT NULL AND geo_status='ACCEPTED'
                 AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?$regionClause
               LIMIT ?""",
            args.toTypedArray()
        ).use { c ->
            val out = mutableListOf<Place>()
            while (c.moveToNext()) out += placeFromCursor(c, emptyList())
            out
        }
    }

    fun exists(db: SQLiteDatabase, id: String): Boolean =
        db.rawQuery("SELECT 1 FROM places WHERE id=?", arrayOf(id)).use { it.moveToFirst() }

    /** eventKey lookup used by merge: id -> "date|score" for a set of ids / zips. */
    fun eventKeysByZip(db: SQLiteDatabase, zip: String): Map<String, String> =
        db.rawQuery("SELECT id,date,score FROM places WHERE zip=?", arrayOf(zip)).use { c ->
            val out = HashMap<String, String>()
            while (c.moveToNext()) out[c.getString(0)] = "${c.getString(1)}|${c.getInt(2)}"
            out
        }
}
