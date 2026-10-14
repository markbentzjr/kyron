package com.kyronapp.kyron

import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.PlaceRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

/**
 * LF-2 performance measurements on the new SQLite-backed repository,
 * comparable to the LF-0 baselines (BaselineTest, old whole-JSON design:
 * load 765 ms; every merge/single update paid a 505 ms / 5.41 MB rewrite):
 *  - first-launch import of the bundled seed into SQLite (one-time);
 *  - steady-state load (pure DB read);
 *  - one single-place update (was: full-catalog rewrite);
 *  - targeted search + bounds query latency.
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class PerfTest {

    @Test
    fun measureNewArchitecture() {
        val ctx = RuntimeEnvironment.getApplication()
        val assetsDir = File("/home/hatch/kyron-build/test/robo-apk/assets")
        val seedBytes = File(assetsDir, "places_seed_geocoded.json").readBytes()
        println("KYRONPERF seed_bytes=${seedBytes.size}")
        File(ctx.filesDir, "places_seed_geocoded.json").writeBytes(seedBytes)

        val repo = PlaceRepository(ctx)
        val t0 = System.nanoTime()
        runBlocking { repo.load() }
        val importMs = (System.nanoTime() - t0) / 1_000_000
        println("KYRONPERF first_load_import_ms=$importMs places=${repo.count()}")

        val repo2 = PlaceRepository(ctx)
        val t1 = System.nanoTime()
        runBlocking { repo2.load() }
        val loadMs = (System.nanoTime() - t1) / 1_000_000
        println("KYRONPERF steady_load_ms=$loadMs")

        val victim = repo2.places.value.first()
        val t2 = System.nanoTime()
        runBlocking { repo2.updatePlace(victim.copy(score = victim.score)) }
        val updateMs = (System.nanoTime() - t2) / 1_000_000
        println("KYRONPERF single_update_ms=$updateMs")

        val t3 = System.nanoTime()
        val search = runBlocking { repo2.searchPlaces(PlaceQuery(text = "Walmart", limit = 100)) }
        val searchMs = (System.nanoTime() - t3) / 1_000_000
        println("KYRONPERF search_walmart_ms=$searchMs results=${search.size}")

        val t4 = System.nanoTime()
        val bounds = runBlocking { repo2.placesInBounds(33.35, 33.70, -87.00, -86.60) }
        val boundsMs = (System.nanoTime() - t4) / 1_000_000
        println("KYRONPERF bounds_birmingham_ms=$boundsMs results=${bounds.size}")

        assertTrue(repo.count() == 23526)
    }
}
