package com.kyronapp.kyron

import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.PlaceRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * LF-1 geocoding acceptance test, run against the exact seed bytes shipped
 * in the APK (extracted into robo-apk/assets by the runner):
 *  - every place carries a geocode status;
 *  - the large majority have REAL coordinates from the Census batch pass;
 *  - ZERO stored coordinates are centroid-sourced — a place either has an
 *    accepted address-level result or no coordinates at all;
 *  - ZERO coordinates fall outside Alabama's envelope;
 *  - places without coordinates are still fully listed/searchable;
 *  - the map bounds query returns only real-location places.
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class GeoTest {

    @Test
    fun geocodedSeedHasOnlyRealCoordinates() {
        val ctx = RuntimeEnvironment.getApplication()
        val assetsDir = java.io.File("/home/hatch/kyron-build/test/robo-apk/assets")
        val seedBytes = java.io.File(assetsDir, "places_seed_geocoded.json").readBytes()
        // Stage through the repository's real filesDir import path.
        java.io.File(ctx.filesDir, "places_seed_geocoded.json").writeBytes(seedBytes)
        val repo = PlaceRepository(ctx)
        runBlocking { repo.load() }
        val places = repo.places.value
        println("KYRONTEST places loaded = ${places.size}")
        assertEquals(23526, places.size)

        var real = 0
        var addressRange = 0
        var noCoords = 0
        var centroidSourced = 0
        var outOfState = 0
        var statusMissing = 0
        for (p in places) {
            if (p.geoStatus.isBlank()) statusMissing++
            val lat = p.lat
            val lng = p.lng
            when {
                lat != null && lng != null -> {
                    real++
                    if (p.geoAccuracy == Place.ACC_ADDRESS_RANGE) addressRange++
                    if (!p.hasRealLocation) centroidSourced++
                    if (lat !in 30.1..35.05 || lng !in -88.5..-84.85) outOfState++
                }
                else -> noCoords++
            }
        }
        val pct = real * 100.0 / places.size
        println("KYRONTEST real=$real (${"%.1f".format(pct)}%) addressRange=$addressRange noCoords=$noCoords centroidSourced=$centroidSourced outOfState=$outOfState statusMissing=$statusMissing")
        assertEquals("every place must carry a geocode status", 0, statusMissing)
        assertEquals("no stored coordinate may be centroid-sourced", 0, centroidSourced)
        assertEquals("no coordinate may fall outside Alabama", 0, outOfState)
        assertEquals("every real coordinate is address-range class or better", real, addressRange)
        assertTrue("Census pass should locate at least 70% of places (was 0.17%)", pct >= 70.0)

        // Places without coordinates remain listed with their address text.
        val unlocated = places.filter { it.lat == null }
        assertEquals(noCoords, unlocated.size)
        assertTrue("unlocated places keep address text", unlocated.count { it.address.isNotBlank() } > 5000)

        // Bounds query (Birmingham) returns only real-location places.
        val inBham = runBlocking { repo.placesInBounds(33.35, 33.70, -87.00, -86.60) }
        println("KYRONTEST birmingham bounds places=${inBham.size}")
        assertTrue(inBham.size > 500)
        assertTrue("bounds results are all real locations", inBham.all { it.hasRealLocation })

        // Search still finds unlocated places by name.
        val search = runBlocking { repo.searchPlaces(PlaceQuery(text = "Piggly", limit = 50)) }
        println("KYRONTEST search 'Piggly' = ${search.size}")
        assertTrue(search.isNotEmpty())
    }
}
