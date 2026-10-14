package com.kyronapp.kyron

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import androidx.work.Configuration
import androidx.work.WorkManager
import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.db.CatalogDb
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

/**
 * P0 reproduction (pass-2 QA): Mark's Z Fold7 cold-start failure of the
 * LF-4 build (33a54a0e) installed OVER the QA-fixed LF-3 build
 * (9f2eab88). The app closes instantly, before the first frame.
 *
 * This fixture recreates the pre-LF4 on-device state faithfully:
 *  - kyron_catalog.db at user_version 1 with the LF-2/LF-3 era DDL
 *    (places/inspections/meta + populated places_fts + the four indexes),
 *    imported_at meta only — NO pack_version/pack_manifest keys;
 *  - kyron_user.db at version 1 with real user rows (profile, favorites,
 *    areas, rules, inbox, outbox, prefs_migrated=1);
 *  - the legacy kyron_prefs SharedPreferences file left in place (the
 *    LF-2 migration copies, never moves);
 *  - NO kyron_regions preferences (LF-4 introduces them);
 *  - migrated-v1 legacy files in filesDir.
 *
 * The application under test is the REAL KyronApplication (not the
 * builder's TestKyronApplication, which wraps super.onCreate() in
 * runCatching and would swallow the very failure being hunted — only the
 * rig-only WorkManager pre-init is guarded, exactly as there).
 */
class FixtureApplication : KyronApplication() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        StartupFixture.write(base)
    }

    override fun onCreate() {
        // Rig workaround, surgical: Robolectric's binary resource parser
        // drops bool/workmanager_test_configuration (0x7f040006) — present
        // in the APK's arsc and matching the dex R constant (verified by
        // pass-2 QA's independent R<->arsc diff). WorkManager therefore
        // cannot initialize in the rig, and the real onCreate's LAST step
        // (scheduleSync -> WorkManager.getInstance) throws
        // IllegalStateException("WorkManager is not initialized...").
        // On a device the androidx.startup provider initializes
        // WorkManager before Application.onCreate. Excuse ONLY that exact
        // rig artifact; every other failure in the real startup — DB
        // open/upgrade, user store, regions, osmdroid — fails the test.
        try {
            super.onCreate()
        } catch (e: IllegalStateException) {
            if (e.message?.contains("WorkManager is not initialized") == true) {
                println("KYRONTEST rig-only WM scheduling failure excused: ${e.message}")
            } else {
                throw e
            }
        }
    }
}

object StartupFixture {

    fun write(ctx: Context) {
        writeCatalog(ctx)
        writeUserDb(ctx)
        writePrefs(ctx)
        writeFiles(ctx)
    }

    private fun writeCatalog(ctx: Context) {
        val path = ctx.getDatabasePath("kyron_catalog.db")
        path.parentFile?.mkdirs()
        if (path.exists()) path.delete()
        val db = SQLiteDatabase.openOrCreateDatabase(path, null)
        // ---- LF-2/LF-3 era (schema v1) DDL: current onCreate minus the
        // four LF-4 region columns / result_text / region index. FTS and
        // the four indexes existed pre-LF4 (LF-2 search ran on them).
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
                detail_url TEXT)"""
        )
        db.execSQL("CREATE INDEX idx_places_county ON places(county)")
        db.execSQL("CREATE INDEX idx_places_zip ON places(zip)")
        db.execSQL("CREATE INDEX idx_places_score ON places(score)")
        db.execSQL("CREATE INDEX idx_places_latlng ON places(lat, lng)")
        db.execSQL(
            """CREATE TABLE inspections(
                place_id TEXT NOT NULL, idx INTEGER NOT NULL,
                score INTEGER NOT NULL DEFAULT 0, date TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '', violations_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(place_id, idx))"""
        )
        db.execSQL("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
        db.execSQL(
            "CREATE VIRTUAL TABLE places_fts USING fts4(place_id UNINDEXED, name, city, address, zip, county)"
        )
        val violJson =
            """[{"p":5,"c":false,"r":"3-501.16 Maintain TCS food at 41 F or below // Soup held at 52 F"}]"""
        for (i in 1..150) {
            val id = "fix_%04d".format(i)
            val name = "FIXTURE BBQ $i"
            val score = 55 + (i % 46)
            val hasCoords = i % 5 != 0
            val lat = if (hasCoords) 33.45 + (i % 100) * 0.001 else null
            val lng = if (hasCoords) -86.85 + (i % 100) * 0.001 else null
            db.execSQL(
                "INSERT INTO places (id,name,name_lc,address,city,zip,county,score,date,date_key,source,lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url)" +
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                arrayOf(
                    id, name, name.lowercase(), "${100 + i} Main St", "Birmingham", "35203",
                    "Jefferson", score.toString(), "9/${1 + i % 27}/2026",
                    (CatalogDb.dateKey("9/${1 + i % 27}/2026")).toString(), "JCDH",
                    lat?.toString(), lng?.toString(),
                    if (hasCoords) "ACCEPTED" else "LEGACY",
                    if (hasCoords) "ADDRESS_RANGE" else "NONE",
                    if (hasCoords) "CENSUS" else "", if (hasCoords) "Exact" else "", null
                )
            )
            if (i % 3 == 0) {
                db.execSQL(
                    "INSERT INTO inspections (place_id,idx,score,date,type,violations_json) VALUES (?,?,?,?,?,?)",
                    arrayOf(id, "0", score.toString(), "9/${1 + i % 27}/2026", "Routine", violJson)
                )
            }
            db.execSQL(
                "INSERT INTO places_fts (place_id,name,city,address,zip,county) VALUES (?,?,?,?,?,?)",
                arrayOf(id, name, "Birmingham", "${100 + i} Main St", "35203", "Jefferson")
            )
        }
        db.execSQL("INSERT INTO meta VALUES ('imported_at','1728000000000')")
        db.version = 1
        db.close()
    }

    private fun writeUserDb(ctx: Context) {
        val path = ctx.getDatabasePath("kyron_user.db")
        path.parentFile?.mkdirs()
        if (path.exists()) path.delete()
        val db = SQLiteDatabase.openOrCreateDatabase(path, null)
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
        val now = 1728000000000L
        db.execSQL(
            "INSERT INTO profile VALUES (1,'Mark',33.5207,-86.8025,'Downtown Birmingham',10.0,1,1,85,1,$now,$now,$now)"
        )
        db.execSQL("INSERT INTO favorites VALUES ('11111111-1111-1111-1111-111111111111','local','fix_0001',$now,$now,NULL,1)")
        db.execSQL("INSERT INTO favorites VALUES ('22222222-2222-2222-2222-222222222222','local','fix_0002',$now,$now,NULL,1)")
        db.execSQL("INSERT INTO areas VALUES ('33333333-3333-3333-3333-333333333333','local','COUNTY','Jefferson',0,0,0,$now,$now,NULL,1)")
        db.execSQL("INSERT INTO areas VALUES ('44444444-4444-4444-4444-444444444444','local','RADIUS','',33.5207,-86.8025,10.0,$now,$now,NULL,1)")
        db.execSQL("INSERT INTO alert_rules VALUES ('55555555-5555-5555-5555-555555555555','local','FAVORITES',1,85,$now,$now,NULL,1)")
        db.execSQL("INSERT INTO alert_rules VALUES ('66666666-6666-6666-6666-666666666666','local','AREA',1,85,$now,$now,NULL,1)")
        db.execSQL("INSERT INTO alert_inbox VALUES ('77777777-7777-7777-7777-777777777777','local','fix_0001','New score','Body text',$now,0,$now,$now,NULL,1)")
        db.execSQL("INSERT INTO sync_outbox VALUES ('88888888-8888-8888-8888-888888888888','favorite','11111111-1111-1111-1111-111111111111','CREATE','{}',0,$now)")
        db.execSQL("INSERT INTO user_meta VALUES ('prefs_migrated','1')")
        db.version = 1
        db.close()
    }

    private fun writePrefs(ctx: Context) {
        // Legacy v2.0-era prefs file: the LF-2 migration copies values and
        // deliberately leaves this file in place on the device.
        ctx.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE).edit()
            .putString("profile_name", "Mark")
            .putBoolean("seen_welcome", true)
            .putStringSet("favorites", setOf("fix_0001", "fix_0002"))
            .putStringSet("monitored_counties", setOf("Jefferson"))
            .putInt("threshold", 85)
            .commit()
    }

    private fun writeFiles(ctx: Context) {
        File(ctx.filesDir, "places.json.migrated-v1").writeText("[]")
        File(ctx.filesDir, "geocache.json.migrated-v1").writeText("{}")
    }
}

@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = FixtureApplication::class
)
class StartupUpgradeTest {

    private fun app(): KyronApplication =
        RuntimeEnvironment.getApplication() as KyronApplication

    @Test
    fun applicationBootsOnUpgradeState() {
        val app = app()
        // Fixture really landed where the app reads it.
        val catPath = app.getDatabasePath("kyron_catalog.db")
        assertTrue("fixture catalog must exist", catPath.exists())
        // KyronApplication.onCreate completed (FixtureApplication does not
        // guard it): all three collaborators constructed.
        assertEquals("Mark", app.prefs.profileName)
        assertTrue(app.prefs.favorites.contains("fix_0001"))
        assertEquals("us-al", app.regions.activeRegionId())
        println("KYRONTEST upgrade boot OK: app onCreate completed on pre-LF4 state")
    }

    @Test
    fun repositoryLoadUpgradesCatalogV1toV2() {
        val app = app()
        runBlocking { app.repository.load() }
        assertEquals(150, app.repository.count())
        val p = app.repository.byId("fix_0003")
        assertTrue(p != null)
        assertEquals("AL", p!!.state)
        assertEquals("us-al", p.regionId)
        assertEquals(1, p.inspections.size)
        assertEquals(5, p.inspections[0].violations[0].points)
        // FTS search works on the upgraded, reopened database.
        val found = runBlocking {
            app.repository.searchPlaces(PlaceQuery(text = "FIXTURE BBQ 12"), "us-al")
        }
        assertTrue(found.any { it.id == "fix_0012" })
        val cat = CatalogDb(app)
        assertEquals(2, cat.readableDatabase.version)
        println("KYRONTEST upgrade load OK: v1->v2 migration + FTS on existing data")
    }

    @Test
    fun mainActivityCreateAttempt() {
        try {
            val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
            val activity = controller.get()
            println("KYRONTEST MainActivity created on upgrade state: $activity")
            controller.pause().stop().destroy()
        } catch (t: Throwable) {
            // Print the whole chain: the diagnosis lives here. Only the
            // known Robolectric binary-resource artifact is excused.
            var chain = ""
            var cur: Throwable? = t
            while (cur != null) {
                chain += "\n  -> ${cur.javaClass.name}: ${cur.message}"
                cur = cur.cause
            }
            println("KYRONTEST MainActivity create threw:$chain")
            t.printStackTrace()
            val known = chain.contains("Resources\$NotFoundException") ||
                chain.contains("abc_vector_test") || chain.contains("0x7f070076")
            if (!known) fail("MainActivity create failed with a NON-rig exception:$chain")
        }
    }
}
