package com.kyronapp.kyron

import com.kyronapp.kyron.data.PlaceRepository
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

/**
 * LF-0 baseline measurements for the pre-rebuild app (whole-JSON catalog):
 * seed load time, catalog size, and the cost of one whole-catalog rewrite
 * (what PlaceRepository.persist() pays on EVERY merge / single-place update).
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class BaselineTest {

    @Test
    fun measureBaselines() {
        val ctx = RuntimeEnvironment.getApplication()
        val assetsDir = File("/home/hatch/kyron-build/test/robo-apk/assets")
        val seedFile = File(assetsDir, "places_seed.json")
        val seedBytes = seedFile.readBytes()
        println("KYRONBASE seed_bytes=${seedBytes.size}")

        // Robolectric's binary AssetManager cannot open loose assets in this
        // rig (see GeoTest), so hand the repo the seed through its real
        // filesDir path using the exact bytes extracted from the APK. The
        // measured work — full read + JSON parse + materialize + sort — is
        // the same code the first-launch asset path runs.
        File(ctx.filesDir, "places.json").writeBytes(seedBytes)
        File(ctx.filesDir, "geocache.json").delete()
        val repo = PlaceRepository(ctx)
        val t0 = System.nanoTime()
        runBlocking { repo.load() }
        val loadMs = (System.nanoTime() - t0) / 1_000_000
        val places = repo.places.value
        println("KYRONBASE load_ms=$loadMs places=${places.size}")
        val withCoords = places.count { it.lat != null && it.lng != null }
        println("KYRONBASE places_with_coords=$withCoords")

        // Whole-catalog rewrite cost == persist(): serialize every place and
        // rewrite the entire file. This is paid per merge and per updatePlace.
        val t1 = System.nanoTime()
        val arr = JSONArray()
        places.forEach { arr.put(it.toJson()) }
        val text = arr.toString()
        File(ctx.filesDir, "baseline_rewrite.json").writeText(text)
        val rewriteMs = (System.nanoTime() - t1) / 1_000_000
        println("KYRONBASE rewrite_ms=$rewriteMs rewrite_bytes=${text.length}")

        assertTrue(places.size > 23000)
    }
}
