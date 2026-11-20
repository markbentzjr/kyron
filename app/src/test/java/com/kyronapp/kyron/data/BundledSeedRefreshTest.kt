package com.kyronapp.kyron.data

import android.app.Application
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.SQLiteMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, manifest = Config.NONE, sdk = [34])
@SQLiteMode(SQLiteMode.Mode.NATIVE)
class BundledSeedRefreshTest {

    private val context get() = RuntimeEnvironment.getApplication()
    private val regionId = Regions.ALABAMA.regionId

    @Test
    fun smallerSeedPreservesCatalogInspectionsAndSearch() = runBlocking {
        writeSeed(place("existing", "Existing Diner", 92), place("watched", "Watched Cafe", 88))
        val original = PlaceRepository(context).also { it.load() }
        val originalSeed = original.metaGet(PlaceRepository.META_BUNDLED_SHA)
        val originalVersion = original.installedRegionVersion(regionId)

        writeSeed(place("existing", "Existing Diner", 67))
        val upgraded = PlaceRepository(context).also { it.load() }

        assertEquals(2, upgraded.regionPlaceCount(regionId))
        assertEquals(92, upgraded.byId("existing")?.score)
        assertEquals(88, upgraded.byId("watched")?.inspections?.single()?.score)
        assertEquals(
            listOf("watched"),
            upgraded.searchPlaces(PlaceQuery(text = "Watched Cafe"), regionId).map { it.id }
        )
        assertEquals(originalSeed, upgraded.metaGet(PlaceRepository.META_BUNDLED_SHA))
        assertEquals(originalVersion, upgraded.installedRegionVersion(regionId))
    }

    @Test
    fun comparesImportedRowsAfterRejectingInvalidRecords() = runBlocking {
        writeSeed(place("existing", "Existing Diner", 92), place("watched", "Watched Cafe", 88))
        PlaceRepository(context).load()

        val invalid = place("invalid", "Pager link", 70).put("d", "3")
        writeSeed(place("existing", "Existing Diner", 67), invalid)
        val upgraded = PlaceRepository(context).also { it.load() }

        assertEquals(2, upgraded.regionPlaceCount(regionId))
        assertNotNull(upgraded.byId("watched"))
    }

    @Test
    fun refreshCanRemoveOneRecordWhilePreservingDeviceCoordinates() = runBlocking {
        writeSeed(
            place("existing", "Existing Diner", 92),
            place("watched", "Watched Cafe", 88),
            place("closed", "Closed Cafe", 90)
        )
        val original = PlaceRepository(context).also { it.load() }
        val originalSeed = original.metaGet(PlaceRepository.META_BUNDLED_SHA)
        original.setCoords("existing", 33.52, -86.8)

        writeSeed(place("existing", "Existing Diner", 95), place("watched", "Watched Cafe", 88))
        val upgraded = PlaceRepository(context).also { it.load() }

        assertEquals(2, upgraded.regionPlaceCount(regionId))
        assertEquals(95, upgraded.byId("existing")?.score)
        assertEquals(33.52, upgraded.byId("existing")?.lat)
        assertEquals("DEVICE", upgraded.byId("existing")?.geoProvider)
        assertNotEquals(originalSeed, upgraded.metaGet(PlaceRepository.META_BUNDLED_SHA))
    }

    private fun writeSeed(vararg places: JSONObject) {
        File(context.filesDir, "places_seed_geocoded.json")
            .writeText(JSONArray(places.toList()).toString())
    }

    private fun place(id: String, name: String, score: Int): JSONObject =
        JSONObject()
            .put("id", id)
            .put("n", name)
            .put("a", "100 Main St")
            .put("c", "Birmingham")
            .put("ct", "Jefferson")
            .put("s", score)
            .put("d", "11/16/2026")
            .put("src", "JCDH")
            .put(
                "insp",
                JSONArray().put(JSONObject().put("s", score).put("d", "11/16/2026"))
            )
}
