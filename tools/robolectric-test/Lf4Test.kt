package com.kyronapp.kyron

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.kyronapp.kyron.data.Inspection
import com.kyronapp.kyron.data.PackException
import com.kyronapp.kyron.data.PackManager
import com.kyronapp.kyron.data.PackManifest
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.PlaceRepository
import com.kyronapp.kyron.data.Prefs
import com.kyronapp.kyron.data.RegionManager
import com.kyronapp.kyron.data.Violation
import com.kyronapp.kyron.data.db.CatalogDb
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File
import java.io.FileOutputStream
import java.util.zip.GZIPOutputStream

/**
 * LF-4 acceptance tests (pass 1 — adversarial by construction):
 *  1. The catalog v1→v2 migration stamps state/region in place and loses
 *     nothing; the user store (separate DB) is untouched by it.
 *  2. A region pack installs, is region-scoped in search/bounds/counties,
 *     formats addresses with the right state, and preserves native
 *     results — with NO numeric score ever appearing for Florida.
 *  3. A corrupted pack (checksum or size) is rejected and the working
 *     region is byte-for-byte intact afterwards.
 *  4. Deltas apply only on their exact base version, are parsed fully
 *     before any write, and a bad delta changes nothing.
 *  5. Rollback restores the N−1 full pack; removing a region deletes its
 *     rows but never the user's favorites/rules/inbox (proven by
 *     snapshotting the user store across every pack operation).
 *  6. The real Florida DBPR pack (70,051 places) installs end-to-end and
 *     region switching AL↔FL returns each state's own data.
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class Lf4Test {

    private fun ctx(): Context = RuntimeEnvironment.getApplication()

    private fun clean(ctx: Context) {
        ctx.deleteDatabase("kyron_catalog.db")
        ctx.deleteDatabase("kyron_user.db")
        ctx.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE).edit().clear().commit()
        ctx.getSharedPreferences("kyron_regions", Context.MODE_PRIVATE).edit().clear().commit()
        File(ctx.filesDir, "packs").deleteRecursively()
    }

    // ------------------------------------------------------------ fixtures

    private fun flPlace(
        id: String, name: String, county: String = "Alachua",
        disp: String = "", date: String = "",
        lat: Double? = null, lng: Double? = null,
        inspections: List<Inspection> = emptyList()
    ) = Place(
        id = id, name = name, address = "100 Main St", city = "GAINESVILLE",
        zip = "32608", county = county, score = Place.NO_SCORE, date = date,
        source = "FL-DBPR", lat = lat, lng = lng,
        detailUrl = "https://example.test/$id",
        inspections = inspections,
        geoStatus = if (lat != null) Place.STATUS_ACCEPTED else "UNRESOLVED",
        geoAccuracy = if (lat != null) Place.ACC_ADDRESS_RANGE else Place.ACC_NONE,
        geoProvider = if (lat != null) "CENSUS" else "",
        state = "FL", jurisdiction = "FL-DBPR", nativeResult = disp
    )

    private fun fixturePlaces(): List<Place> = listOf(
        flPlace(
            "fl_a", "HILLS BAR B QUE & CATERING", disp = "Warning Issued", date = "9/22/2026",
            inspections = listOf(
                Inspection(
                    Place.NO_SCORE, "9/22/2026", "Routine - Food",
                    listOf(Violation(0, false, "08 Food protection, cross-contamination (2 findings)")),
                    nativeResult = "Warning Issued"
                )
            )
        ),
        flPlace("fl_b", "NO INSPECTION CAFE"),
        flPlace("fl_c", "GEOCODED GATOR DINER", county = "Orange", lat = 28.5383, lng = -81.3792,
            disp = "Inspection Completed - No Further Action", date = "10/1/2026")
    )

    /** Build a pack artifact (gzipped SQLite + manifest) exactly the way
     *  the offline pipeline does, from in-memory places. */
    private fun buildPack(
        dir: File, version: String, places: List<Place>,
        regionId: String = "us-fl", state: String = "FL"
    ): Pair<File, PackManifest> {
        val rawDb = File(dir, "fixture-$regionId-$version.db")
        rawDb.delete()
        val db = SQLiteDatabase.openOrCreateDatabase(rawDb, null)
        db.execSQL("CREATE TABLE pack_meta(k TEXT PRIMARY KEY, v TEXT)")
        db.execSQL(
            """CREATE TABLE places(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_lc TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
                zip TEXT NOT NULL DEFAULT '', county TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
                date_key INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '',
                lat REAL, lng REAL, geo_status TEXT NOT NULL DEFAULT 'LEGACY',
                geo_acc TEXT NOT NULL DEFAULT 'NONE', geo_prov TEXT NOT NULL DEFAULT '',
                geo_match TEXT NOT NULL DEFAULT '', detail_url TEXT,
                state TEXT NOT NULL DEFAULT 'AL', jurisdiction TEXT NOT NULL DEFAULT '',
                region_id TEXT NOT NULL DEFAULT 'us-al', result_text TEXT NOT NULL DEFAULT '')"""
        )
        db.execSQL(
            """CREATE TABLE inspections(
                place_id TEXT NOT NULL, idx INTEGER NOT NULL, score INTEGER NOT NULL DEFAULT 0,
                date TEXT NOT NULL DEFAULT '', type TEXT NOT NULL DEFAULT '',
                violations_json TEXT NOT NULL DEFAULT '[]', result_text TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(place_id, idx))"""
        )
        val meta = mapOf(
            "region_id" to regionId, "state" to state, "dataset_version" to version,
            "generated_at" to "2026-10-13T00:00:00Z", "place_count" to places.size.toString(),
            "schema_version" to "2", "score_model" to "DISPOSITION"
        )
        for ((k, v) in meta) db.execSQL("INSERT INTO pack_meta VALUES (?,?)", arrayOf(k, v))
        for (p in places) {
            val cv = ContentValues().apply {
                put("id", p.id); put("name", p.name); put("name_lc", p.name.lowercase())
                put("address", p.address); put("city", p.city); put("zip", p.zip)
                put("county", p.county); put("score", p.score); put("date", p.date)
                put("date_key", CatalogDb.dateKey(p.date)); put("source", p.source)
                if (p.lat != null) put("lat", p.lat) else putNull("lat")
                if (p.lng != null) put("lng", p.lng) else putNull("lng")
                put("geo_status", p.geoStatus); put("geo_acc", p.geoAccuracy)
                put("geo_prov", p.geoProvider); put("geo_match", p.geoMatch)
                if (p.detailUrl != null) put("detail_url", p.detailUrl) else putNull("detail_url")
                put("state", p.state); put("jurisdiction", p.jurisdiction)
                put("region_id", p.regionId); put("result_text", p.nativeResult)
            }
            db.insert("places", null, cv)
            p.inspections.forEachIndexed { i, insp ->
                val iv = ContentValues().apply {
                    put("place_id", p.id); put("idx", i); put("score", insp.score)
                    put("date", insp.date); put("type", insp.type)
                    put("violations_json", org.json.JSONArray().apply {
                        insp.violations.forEach { v -> put(v.toJson()) }
                    }.toString())
                    put("result_text", insp.nativeResult)
                }
                db.insert("inspections", null, iv)
            }
        }
        db.close()
        val gz = File(dir, "fixture-$regionId-$version.db.gz")
        GZIPOutputStream(FileOutputStream(gz)).use { out -> rawDb.inputStream().use { it.copyTo(out) } }
        rawDb.delete()
        val manifestJson = JSONObject()
            .put("regionId", regionId).put("displayName", "Florida").put("state", state)
            .put("datasetVersion", version).put("generatedAt", "2026-10-13T00:00:00Z")
            .put("placeCount", places.size).put("schemaVersion", 2)
            .put("full", JSONObject().put("file", gz.name).put("bytes", gz.length())
                .put("sha256", PackManager.sha256(gz)))
            .put("delta", JSONObject.NULL)
        return gz to PackManifest.fromJson(manifestJson)
    }

    private data class UserSnapshot(
        val favorites: Set<String>, val counties: Set<String>, val rules: Int,
        val inbox: Int, val profileName: String, val outbox: Int
    )

    private fun snapshot(prefs: Prefs) = UserSnapshot(
        prefs.favorites, prefs.monitoredCounties,
        prefs.store.allRules(includeDeleted = true).size,
        prefs.store.allInbox(includeDeleted = true).size,
        prefs.profileName, prefs.store.outboxCount()
    )

    // ---------------------------------------------------------------- tests

    @Test
    fun catalogMigrationV1toV2PreservesEverything() {
        val ctx = ctx()
        clean(ctx)

        // User data first: the catalog migration must not touch it.
        val prefs = Prefs(ctx)
        prefs.profileName = "Migration Mark"
        prefs.store.setFavorite("al_place_1", true)
        prefs.monitoredCounties = setOf("Jefferson", "Mobile")
        val before = snapshot(prefs)

        // Hand-build a v1 catalog exactly as the pre-LF-4 app wrote it.
        val path = ctx.getDatabasePath("kyron_catalog.db")
        path.parentFile?.mkdirs()
        val raw = SQLiteDatabase.openOrCreateDatabase(path, null)
        raw.execSQL(
            """CREATE TABLE places(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, name_lc TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
                zip TEXT NOT NULL DEFAULT '', county TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
                date_key INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '',
                lat REAL, lng REAL, geo_status TEXT NOT NULL DEFAULT 'LEGACY',
                geo_acc TEXT NOT NULL DEFAULT 'NONE', geo_prov TEXT NOT NULL DEFAULT '',
                geo_match TEXT NOT NULL DEFAULT '', detail_url TEXT)"""
        )
        raw.execSQL(
            """CREATE TABLE inspections(
                place_id TEXT NOT NULL, idx INTEGER NOT NULL, score INTEGER NOT NULL DEFAULT 0,
                date TEXT NOT NULL DEFAULT '', type TEXT NOT NULL DEFAULT '',
                violations_json TEXT NOT NULL DEFAULT '[]', PRIMARY KEY(place_id, idx))"""
        )
        raw.execSQL("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
        raw.execSQL(
            "INSERT INTO places (id,name,name_lc,address,city,zip,county,score,date,date_key,source,lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url)" +
                " VALUES ('al_place_1','Test BBQ','test bbq','1 Main St','Birmingham','35203','Jefferson',88,'9/1/2026',0,'JCDH',33.52,-86.80,'ACCEPTED','ADDRESS_RANGE','CENSUS','Exact',NULL)"
        )
        raw.execSQL(
            "INSERT INTO inspections (place_id,idx,score,date,type,violations_json) VALUES ('al_place_1',0,88,'9/1/2026','Routine','[]')"
        )
        raw.execSQL("INSERT INTO meta VALUES ('imported_at','123')")
        raw.version = 1
        raw.close()

        val catalog = CatalogDb(ctx)
        val db = catalog.writableDatabase
        assertEquals("helper upgraded the file to v2", 2, db.version)
        val p = catalog.placeById(db, "al_place_1")
        assertNotNull(p)
        assertEquals("AL", p!!.state)
        assertEquals("us-al", p.regionId)
        assertEquals("", p.jurisdiction)
        assertEquals("", p.nativeResult)
        assertEquals(88, p.score)
        assertEquals("1 Main St, Birmingham, AL 35203", p.fullAddress())
        assertEquals(1, p.inspections.size)
        assertEquals("123", catalog.metaGet(db, "imported_at"))
        assertEquals(listOf("Jefferson"), catalog.counties(db, "us-al"))
        assertTrue(catalog.counties(db, "us-fl").isEmpty())

        assertEquals("user store untouched by catalog migration", before, snapshot(prefs))
        println("KYRONTEST migration v1->v2 OK")
    }

    @Test
    fun packInstallScopesRegionsAndPreservesNativeResults() {
        val ctx = ctx()
        clean(ctx)
        val repo = PlaceRepository(ctx)
        val (gz, manifest) = buildPack(ctx.cacheDir, "1.0", fixturePlaces())
        val result = runBlocking { repo.installPack(gz, manifest) }
        assertEquals(3, result.placeCount)
        assertEquals("1.0", repo.installedRegionVersion("us-fl"))
        assertEquals(3, repo.regionPlaceCount("us-fl"))
        assertEquals(0, repo.regionPlaceCount("us-al"))

        val a = repo.byId("fl_a")!!
        assertEquals("FL", a.state)
        assertEquals("us-fl", a.regionId)
        assertEquals("100 Main St, GAINESVILLE, FL 32608", a.fullAddress())
        assertEquals("Warning Issued", a.nativeResult)
        assertFalse("Florida has no numeric score", a.hasNumericScore)
        assertEquals("Warning", a.badgeText)
        assertEquals(1, a.inspections.size)
        assertEquals("Warning Issued", a.inspections[0].nativeResult)
        assertEquals(0, a.inspections[0].violations[0].points)

        val b = repo.byId("fl_b")!!
        assertEquals("", b.nativeResult)
        assertEquals("—", b.badgeText)
        assertTrue(b.date.isBlank())

        // Region-scoped search/bounds/counties.
        val fl = runBlocking { repo.searchPlaces(PlaceQuery(text = "GATOR"), "us-fl") }
        assertEquals(listOf("fl_c"), fl.map { it.id })
        val none = runBlocking { repo.searchPlaces(PlaceQuery(text = "GATOR"), "us-al") }
        assertTrue(none.isEmpty())
        assertEquals(setOf("Alachua", "Orange"), repo.counties("us-fl").toSet())
        assertTrue(repo.counties("us-al").isEmpty())
        val inBox = runBlocking { repo.placesInBounds(28.0, 29.0, -82.0, -81.0, regionId = "us-fl") }
        assertEquals(listOf("fl_c"), inBox.map { it.id })
        val wrongRegion = runBlocking { repo.placesInBounds(28.0, 29.0, -82.0, -81.0, regionId = "us-al") }
        assertTrue(wrongRegion.isEmpty())

        // The sentinel guard: NO band may match a scoreless place.
        val below = runBlocking { repo.searchPlaces(PlaceQuery(band = "Below 85", limit = 50), "us-fl") }
        assertTrue("NO_SCORE must not fall into 'Below 85'", below.isEmpty())
        val high = runBlocking { repo.searchPlaces(PlaceQuery(band = "95+", limit = 50), "us-fl") }
        assertTrue(high.isEmpty())

        // Region switching state.
        val regions = RegionManager(ctx)
        assertEquals("us-al", regions.activeRegionId())
        regions.setActive("us-fl", manual = true)
        assertEquals("us-fl", regions.activeRegionId())
        assertEquals("Florida", regions.activeInfo().displayName)
        assertTrue(regions.manualOverride)
        regions.setActive("us-al", manual = true)
        assertEquals("us-al", regions.activeRegionId())
        println("KYRONTEST pack install + region scoping OK")
    }

    @Test
    fun corruptPackIsRejectedAndWorkingRegionIntact() {
        val ctx = ctx()
        clean(ctx)
        val repo = PlaceRepository(ctx)
        val (gz, manifest) = buildPack(ctx.cacheDir, "1.0", fixturePlaces())
        runBlocking { repo.installPack(gz, manifest) }
        assertEquals(3, repo.regionPlaceCount("us-fl"))

        // Bit-flipped pack: checksum must refuse it before any write.
        val tampered = File(ctx.cacheDir, "tampered.db.gz")
        val bytes = gz.readBytes()
        bytes[bytes.size / 2] = (bytes[bytes.size / 2] + 1).toByte()
        tampered.writeBytes(bytes)
        try {
            runBlocking { repo.installPack(tampered, manifest) }
            fail("tampered pack must be rejected")
        } catch (e: PackException) {
            assertTrue(e.message!!.contains("checksum", ignoreCase = true))
        }
        assertEquals(3, repo.regionPlaceCount("us-fl"))
        assertEquals("Warning Issued", repo.byId("fl_a")!!.nativeResult)

        // Truncated pack: size check refuses it too.
        val truncated = File(ctx.cacheDir, "truncated.db.gz")
        truncated.writeBytes(bytes.copyOf(bytes.size - 100))
        try {
            runBlocking { repo.installPack(truncated, manifest) }
            fail("truncated pack must be rejected")
        } catch (e: PackException) {
            // size or checksum refusal — either is a clean rejection
        }
        assertEquals(3, repo.regionPlaceCount("us-fl"))

        // A pack whose own metadata lies (place count) is refused even
        // with a valid checksum of its actual bytes.
        val (gz2, m2) = buildPack(ctx.cacheDir, "2.0", fixturePlaces().take(2))
        val lying = PackManifest.fromJson(JSONObject(m2.raw.toString()).apply {
            put("placeCount", 99)
        })
        try {
            runBlocking { repo.installPack(gz2, lying) }
            fail("count-lying pack must be rejected")
        } catch (e: PackException) {
            assertTrue(e.message!!.contains("count", ignoreCase = true))
        }
        assertEquals(3, repo.regionPlaceCount("us-fl"))
        assertEquals("1.0", repo.installedRegionVersion("us-fl"))
        println("KYRONTEST corrupt pack rejection OK")
    }

    @Test
    fun deltaAppliesOnExactBaseOnlyAndParsesFirst() {
        val ctx = ctx()
        clean(ctx)
        val repo = PlaceRepository(ctx)
        val (gz, m1) = buildPack(ctx.cacheDir, "1.0", fixturePlaces())
        runBlocking { repo.installPack(gz, m1) }

        fun deltaManifest(deltaFile: File, from: String, to: String): PackManifest {
            val raw = JSONObject(m1.raw.toString())
            raw.put("datasetVersion", to)
            raw.put("delta", JSONObject()
                .put("fromVersion", from).put("file", deltaFile.name)
                .put("bytes", deltaFile.length()).put("sha256", PackManager.sha256(deltaFile)))
            return PackManifest.fromJson(raw)
        }
        fun writeDelta(name: String, json: JSONObject): File {
            val f = File(ctx.cacheDir, name)
            f.writeText(json.toString())
            return f
        }

        // Happy path: change fl_a's result, add fl_d, delete fl_b.
        val updatedA = flPlace("fl_a", "HILLS BAR B QUE & CATERING",
            disp = "Call Back - Complied", date = "10/5/2026")
        val newD = flPlace("fl_d", "DELTA DONUTS", county = "Duval")
        val deltaJson = JSONObject()
            .put("regionId", "us-fl").put("fromVersion", "1.0").put("toVersion", "1.1")
            .put("upserts", org.json.JSONArray().put(updatedA.toJson()).put(newD.toJson()))
            .put("deletions", org.json.JSONArray().put("fl_b"))
        val deltaFile = writeDelta("delta-1.1.json", deltaJson)
        val dm = deltaManifest(deltaFile, "1.0", "1.1")
        val res = runBlocking { repo.applyPackDelta(deltaFile, dm) }
        assertEquals("1.1", res.datasetVersion)
        assertEquals(3, repo.regionPlaceCount("us-fl"))
        assertEquals("Call Back - Complied", repo.byId("fl_a")!!.nativeResult)
        assertNull(repo.byId("fl_b"))
        assertNotNull(repo.byId("fl_d"))

        // Same delta again: base is now 1.1, not 1.0 — must refuse.
        try {
            runBlocking { repo.applyPackDelta(deltaFile, dm) }
            fail("stale-base delta must be rejected")
        } catch (e: PackException) {
            assertTrue(e.message!!.contains("full pack required", ignoreCase = true))
        }
        assertEquals(3, repo.regionPlaceCount("us-fl"))

        // Parse-first: a delta mixing a valid upsert with a foreign-region
        // upsert applies NOTHING (the valid row must not slip in).
        val poison = JSONObject()
            .put("regionId", "us-fl").put("fromVersion", "1.1").put("toVersion", "1.2")
            .put("upserts", org.json.JSONArray()
                .put(flPlace("fl_e", "SHOULD NOT APPEAR").toJson())
                .put(flPlace("xx_1", "FOREIGN").copy(state = "GA").toJson()))
            .put("deletions", org.json.JSONArray())
        val poisonFile = writeDelta("delta-1.2.json", poison)
        val pm = deltaManifest(poisonFile, "1.1", "1.2")
        try {
            runBlocking { repo.applyPackDelta(poisonFile, pm) }
            fail("foreign-region delta must be rejected")
        } catch (e: PackException) {
        }
        assertNull("valid-looking upsert in a bad delta must not be applied", repo.byId("fl_e"))
        assertEquals("1.1", repo.installedRegionVersion("us-fl"))
        println("KYRONTEST delta discipline OK")
    }

    @Test
    fun rollbackRestoresPreviousPackAndUserStoreIsUntouched() {
        val ctx = ctx()
        clean(ctx)
        val prefs = Prefs(ctx)
        prefs.profileName = "Pack Tester"
        prefs.store.setFavorite("fl_a", true)
        prefs.store.setFavorite("some_al_place", true)
        prefs.monitoredCounties = setOf("Jefferson")
        val before = snapshot(prefs)

        val repo = PlaceRepository(ctx)
        val (gz1, m1) = buildPack(ctx.cacheDir, "1.0", fixturePlaces())
        runBlocking { repo.installPack(gz1, m1) }
        assertEquals(before, snapshot(prefs))

        val v2Places = fixturePlaces() + flPlace("fl_e", "VERSION TWO TACOS", county = "Duval")
        val changedA = v2Places.map {
            if (it.id == "fl_a") it.copy(nativeResult = "Emergency Order Callback Complied") else it
        }
        val (gz2, m2) = buildPack(ctx.cacheDir, "2.0", changedA)
        runBlocking { repo.installPack(gz2, m2) }
        assertEquals(4, repo.regionPlaceCount("us-fl"))
        assertEquals("Emergency Order Callback Complied", repo.byId("fl_a")!!.nativeResult)
        assertEquals(before, snapshot(prefs))

        assertTrue(repo.packHasRollback("us-fl"))
        assertTrue(runBlocking { repo.rollbackPack("us-fl") })
        assertEquals(3, repo.regionPlaceCount("us-fl"))
        assertEquals("Warning Issued", repo.byId("fl_a")!!.nativeResult)
        assertEquals("1.0", repo.installedRegionVersion("us-fl"))
        assertNull(repo.byId("fl_e"))
        assertEquals(before, snapshot(prefs))

        // Remove: rows go, user data stays — including the favorite that
        // points at a now-uninstalled Florida place.
        runBlocking { repo.removePack("us-fl") }
        assertEquals(0, repo.regionPlaceCount("us-fl"))
        assertNull(repo.byId("fl_a"))
        assertEquals(before, snapshot(prefs))
        assertTrue("favorite survives region removal", prefs.favorites.contains("fl_a"))

        // The bundled region refuses removal.
        try {
            runBlocking { repo.removePack("us-al") }
            fail("bundled region must refuse removal")
        } catch (e: PackException) {
        }
        println("KYRONTEST rollback + removal + user-store isolation OK")
    }

    @Test
    fun ftsAvailableOnReopenedDatabase() {
        // Regression (LF-4 recovery): ftsAvailable used to be set only in
        // onCreate, so a CatalogDb opened on an EXISTING database — every
        // returning user, and any second instance — reported FTS off:
        // search silently degraded to LIKE and pack swaps skipped FTS
        // rows, making installed regions unsearchable by text.
        val ctx = ctx()
        clean(ctx)
        val assetsDir = File("/home/hatch/kyron-build/test/robo-apk/assets")
        File(ctx.filesDir, "places_seed_geocoded.json")
            .writeBytes(File(assetsDir, "places_seed_geocoded.json").readBytes())
        val repo = PlaceRepository(ctx)
        runBlocking { repo.load() }
        assertEquals(23526, repo.regionPlaceCount("us-al"))

        val reopened = CatalogDb(ctx)
        val rdb = reopened.readableDatabase // opening fires onOpen, which probes for the FTS table
        assertTrue("FTS must be available on a reopened database", reopened.ftsAvailable)
        val ids = reopened.ftsIds(rdb, "Walmart", 10)
        assertNotNull(ids)
        assertTrue(ids!!.isNotEmpty())
        println("KYRONTEST fts-on-reopen OK")
    }

    @Test
    fun fullFloridaPackProof() {
        val ctx = ctx()
        clean(ctx)
        val packDir = File("/home/hatch/kyron-build/manual/tools/packs/out/us-fl")
        val manifestFile = File(packDir, "us-fl.manifest.json")
        assertTrue("FL pack must be built by the pipeline first", manifestFile.exists())
        val manifest = PackManifest.fromJson(JSONObject(manifestFile.readText()))
        val packFile = File(packDir, manifest.fullFile)
        assertTrue(packFile.exists())
        assertEquals(70051, manifest.placeCount)

        // Alabama via the app's real first-launch path.
        val assetsDir = File("/home/hatch/kyron-build/test/robo-apk/assets")
        File(ctx.filesDir, "places_seed_geocoded.json")
            .writeBytes(File(assetsDir, "places_seed_geocoded.json").readBytes())
        val repo = PlaceRepository(ctx)
        runBlocking { repo.load() }
        assertEquals(23526, repo.regionPlaceCount("us-al"))

        // Install the FL pack through PackManager directly (the repository
        // wrapper is covered by the synthetic tests; this avoids reloading
        // a 93k-place in-memory snapshot just to prove the pack path).
        val catalog = CatalogDb(ctx)
        val pm = PackManager(ctx, catalog)
        val t0 = System.currentTimeMillis()
        val res = pm.installFullPack(catalog.writableDatabase, packFile, manifest)
        val installMs = System.currentTimeMillis() - t0
        println("KYRONTEST FL pack install ms=$installMs")
        assertEquals(70051, res.placeCount)
        assertEquals(70051, repo.regionPlaceCount("us-fl"))
        assertEquals(23526 + 70051, repo.count())

        // Region switching returns each state's own data.
        val hills = runBlocking { repo.searchPlaces(PlaceQuery(text = "HILLS BAR"), "us-fl") }
        val h = hills.single { it.name == "HILLS BAR B QUE & CATERING" }
        assertEquals("fldbpr_CAT1102926", h.id)
        assertEquals("FL", h.state)
        assertEquals("Inspection Completed - No Further Action", h.nativeResult)
        assertEquals("10/8/2026", h.date)
        assertTrue(h.fullAddress().contains("FL 32608"))
        assertFalse(h.hasNumericScore)
        assertEquals(1, h.inspections.size)
        assertEquals("Inspection Completed - No Further Action", h.inspections[0].nativeResult)

        val alJeff = runBlocking {
            repo.searchPlaces(PlaceQuery(county = "Jefferson", limit = 200), "us-al")
        }
        assertTrue(alJeff.isNotEmpty())
        assertTrue(alJeff.all { it.state == "AL" && it.hasNumericScore })

        val flCounties = repo.counties("us-fl")
        assertTrue(flCounties.contains("Alachua"))
        assertTrue(flCounties.contains("Miami-Dade") || flCounties.contains("Dade"))
        val alCounties = repo.counties("us-al")
        assertTrue(alCounties.contains("Jefferson"))
        assertFalse(alCounties.contains("Alachua"))

        // At scale: no Florida place may surface a numeric score, through
        // any band, ever.
        val banded = runBlocking { repo.searchPlaces(PlaceQuery(band = "Below 85", limit = 100), "us-fl") }
        assertTrue(banded.isEmpty())
        val sample = runBlocking { repo.searchPlaces(PlaceQuery(limit = 1000), "us-fl") }
        assertEquals(1000, sample.size)
        assertTrue(sample.all { !it.hasNumericScore && it.state == "FL" })
        val noInsp = sample.firstOrNull { it.inspections.isEmpty() && it.nativeResult.isBlank() }
        assertNotNull("pack must include license-only places with no inspection", noInsp)
        println("KYRONTEST full FL pack proof OK (install ${installMs} ms)")
    }
}
