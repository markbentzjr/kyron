package com.kyronapp.kyron

import android.content.Context
import com.kyronapp.kyron.data.AlertItem
import com.kyronapp.kyron.data.Backup
import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.PlaceRepository
import com.kyronapp.kyron.data.Prefs
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

/**
 * LF-2 acceptance tests:
 *  1. v2.0 SharedPreferences user data migrates into the SQLite user store
 *     with zero loss (favorites, counties, profile, threshold, inbox),
 *     every row under the UUID/timestamp/tombstone contract, and the
 *     sync_outbox records the migration.
 *  2. Backup export -> fresh store -> import reproduces the data exactly
 *     (the kyron-backup round trip), and re-importing is a no-op.
 *  3. The catalog repository serves targeted queries from SQLite and a
 *     merge writes only the changed row (no places.json ever reappears).
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class DbTest {

    private fun ctx(): Context = RuntimeEnvironment.getApplication()

    @Test
    fun prefsMigrateIntoUserStoreWithoutLoss() {
        val ctx = ctx()
        val sp = ctx.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE)
        sp.edit().clear()
            .putString("profile_name", "Mark Test")
            .putBoolean("seen_welcome", true)
            .putStringSet("favorites", setOf("place_a", "place_b", "place_c"))
            .putBoolean("alerts_favorites", false)
            .putBoolean("alerts_area", true)
            .putInt("threshold", 90)
            .putStringSet("monitored_counties", setOf("Jefferson", "Mobile"))
            .putFloat("home_lat", 34.7304f).putFloat("home_lng", -86.5861f)
            .putString("home_label", "Huntsville")
            .putFloat("radius_miles", 15f)
            .putLong("last_sync", 123456789L)
            .putString("inbox", "[{\"pid\":\"place_a\",\"t\":\"New score\",\"b\":\"Scored 72 on 10/1/2026\",\"w\":987654321,\"low\":true}]")
            .commit()

        val prefs = Prefs(ctx)
        assertEquals("Mark Test", prefs.profileName)
        assertTrue(prefs.seenWelcome)
        assertEquals(setOf("place_a", "place_b", "place_c"), prefs.favorites)
        assertFalse(prefs.alertsForFavorites)
        assertTrue(prefs.alertsForArea)
        assertEquals(90, prefs.threshold)
        assertEquals(setOf("Jefferson", "Mobile"), prefs.monitoredCounties)
        assertEquals("Huntsville", prefs.homeLabel)
        assertEquals(15.0, prefs.radiusMiles, 0.01)
        assertEquals(123456789L, prefs.lastSyncMs)
        assertEquals(1, prefs.inbox.size)
        assertEquals("place_a", prefs.inbox[0].placeId)
        assertTrue(prefs.inbox[0].lowScore)

        val store = prefs.store
        val favRows = store.allFavorites()
        assertEquals(3, favRows.size)
        assertTrue("favorites carry UUID ids", favRows.all { it.id.length >= 32 })
        assertTrue("favorites are version 1, live", favRows.all { it.version == 1 && it.deletedAt == null })
        val areas = store.allAreas()
        assertEquals(setOf("Jefferson", "Mobile"), areas.filter { it.kind == "COUNTY" }.map { it.countyName }.toSet())
        assertEquals(1, areas.count { it.kind == "RADIUS" })
        assertEquals(2, store.allRules().size)
        assertTrue("outbox recorded the migration", store.outboxCount() >= 3 + 2 + 1 + 2 + 1)
        println("KYRONTEST migration OK outbox=${store.outboxCount()}")

        // Tombstone semantics: unfavorite keeps the row, deleted.
        prefs.toggleFavorite("place_a")
        assertEquals(setOf("place_b", "place_c"), prefs.favorites)
        val all = store.allFavorites(includeDeleted = true)
        assertEquals(3, all.size)
        assertEquals(1, all.count { it.deletedAt != null })
        // Re-favorite revives the same row id.
        val tombId = all.first { it.deletedAt != null }.id
        prefs.toggleFavorite("place_a")
        val revived = store.allFavorites(includeDeleted = true).first { it.placeId == "place_a" }
        assertEquals(tombId, revived.id)
        assertEquals(null, revived.deletedAt)
        println("KYRONTEST tombstone/revive OK")
    }

    @Test
    fun backupRoundTripReproducesUserData() {
        val ctx = ctx()
        val prefs = Prefs(ctx)
        prefs.profileName = "Round Trip"
        prefs.store.setFavorite("place_x", true)
        prefs.store.setFavorite("place_y", true)
        prefs.store.setFavorite("place_y", false) // tombstone travels too
        prefs.monitoredCounties = setOf("Jefferson", "Madison")
        prefs.addAlert(AlertItem("place_x", "New score", "Scored 61", 424242L, true))
        val exported = Backup.export(prefs.store, "2.0", "2026-10-13T00:00:00Z").toString()
        println("KYRONTEST backup bytes=${exported.length}")

        // Simulate a fresh device: wipe the DB, and clear prefs so the
        // migration cannot resurrect the source data.
        ctx.deleteDatabase("kyron_user.db")
        ctx.getSharedPreferences("kyron_prefs", Context.MODE_PRIVATE).edit().clear().commit()
        val fresh = Prefs(ctx)
        assertTrue(fresh.favorites.isEmpty())

        val report = Backup.import(fresh.store, JSONObject(exported)) { true }
        println("KYRONTEST import report=$report")
        assertEquals("Round Trip", fresh.profileName)
        assertEquals(setOf("place_x"), fresh.favorites)
        assertEquals(setOf("Jefferson", "Madison"), fresh.monitoredCounties)
        assertEquals(1, fresh.inbox.size)
        assertEquals("place_x", fresh.inbox[0].placeId)
        assertEquals(1, fresh.store.allFavorites(includeDeleted = true).count { it.deletedAt != null })

        // Idempotent: importing the same file again changes nothing.
        val before = fresh.store.outboxCount()
        val report2 = Backup.import(fresh.store, JSONObject(exported)) { true }
        assertEquals(0, report2.inserted)
        assertEquals(0, report2.updated)
        assertTrue("second import writes no rows", fresh.store.outboxCount() == before)
        println("KYRONTEST round trip OK")
    }

    @Test
    fun catalogQueriesAndRowLevelMerge() {
        val ctx = ctx()
        val assetsDir = File("/home/hatch/kyron-build/test/robo-apk/assets")
        File(ctx.filesDir, "places_seed_geocoded.json")
            .writeBytes(File(assetsDir, "places_seed_geocoded.json").readBytes())
        val repo = PlaceRepository(ctx)
        runBlocking { repo.load() }
        assertEquals(23526, repo.count())

        val below = runBlocking { repo.searchPlaces(PlaceQuery(band = "Below 85", limit = 100)) }
        assertEquals(100, below.size)
        assertTrue(below.all { it.score < 85 })
        val jeff = runBlocking { repo.searchPlaces(PlaceQuery(county = "Jefferson", limit = 5000)) }
        assertTrue(jeff.all { it.county == "Jefferson" })
        println("KYRONTEST jefferson=${jeff.size} below85sample=${below.size}")

        // Merge one changed place: exactly one event, row updated, and the
        // repository never recreates the legacy whole-catalog JSON file.
        val victim = jeff.first()
        val changed = victim.copy(score = 42, date = "10/13/2026")
        val events = runBlocking { repo.mergeFresh(listOf(changed)) }
        assertEquals(1, events.size)
        assertEquals(42, repo.byId(victim.id)?.score)
        assertFalse("no whole-catalog JSON rewrite", File(ctx.filesDir, "places.json").exists())

        // Re-merging identical data produces no event and no write churn.
        val events2 = runBlocking { repo.mergeFresh(listOf(changed)) }
        assertEquals(0, events2.size)
        println("KYRONTEST merge OK")
    }
}
