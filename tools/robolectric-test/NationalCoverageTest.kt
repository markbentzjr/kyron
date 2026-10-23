package com.kyronapp.kyron

import android.content.Context
import com.kyronapp.kyron.data.NationalCoverage
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.Regions
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * LF-N nationwide acceptance tests. Synthetic records are used ONLY in
 * this isolated test fixture — never in production datasets.
 *
 * Covers:
 *  1. exactly 50 unique state registrations + D.C. as a separate district
 *  2. per-state result models incl. opposite score directions
 *  3. band math: missing scores excluded from numeric bands, both scales
 *  4. antimeridian-safe map bounds (Alaska west of +180)
 *  5. identity: same-name restaurants in different states never merge
 *  6. legacy Regions API preserved (AL bundled, FL/GA pack-capable)
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml",
    application = android.app.Application::class
)
class NationalCoverageTest {

    private fun ctx(): Context = RuntimeEnvironment.getApplication()

    private fun coverage(): List<NationalCoverage.Jurisdiction> =
        NationalCoverage.load(ctx())

    // 1 ------------------------------------------------------------------

    @Test
    fun exactlyFiftyUniqueStatesRegistered() {
        val all = coverage()
        val states = all.filter { it.type == "state" }
        assertEquals(50, states.size)
        val codes = states.map { it.state }.toSet()
        assertEquals(50, codes.size)
        for ((code, _) in Regions.US_STATES) {
            assertTrue("registry missing state $code", codes.contains(code))
        }
    }

    @Test
    fun dcRepresentedSeparately() {
        val dc = coverage().firstOrNull { it.state == "DC" }
        assertNotNull("District of Columbia must be registered", dc)
        assertEquals("federal-district", dc!!.type)
        assertEquals("us-dc", dc.regionId)
        assertFalse("D.C. must not be counted as a state", dc.type == "state")
    }

    @Test
    fun regionIdsFollowUsXxConvention() {
        for (j in coverage()) {
            val expected = if (j.state == "DC") "us-dc" else "us-" + j.state.lowercase()
            assertEquals(expected, j.regionId)
        }
    }

    @Test
    fun everyStateHasAtLeastOneSource() {
        for (j in coverage()) {
            assertTrue("${j.regionId} has no registered source", j.sources.isNotEmpty())
        }
    }

    @Test
    fun statusesStayDistinctForPackRegions() {
        // Data availability vs pack availability vs host health are separate
        // fields: a built pack with a dead host is NOT "published".
        val fl = coverage().first { it.state == "FL" }
        assertTrue(fl.sources.all { it.status == "pack-built" || it.status == "integrated" })
        assertEquals("published", fl.packStatus)
        assertEquals("unreachable-404", fl.packHostStatus)
        val tn = coverage().first { it.state == "TN" }
        assertEquals("built", tn.packStatus)
        val de = coverage().first { it.state == "DE" }
        // DE slice (2026-10-22): pack BUILT and validated locally, NOT
        // published — so the manifest URL stays null and no download is
        // ever offered (staged-local), even though the artifact verified.
        assertEquals("pack-built", de.sources.first().status)
        assertEquals("built", de.packStatus)
        assertEquals("staged-local", de.packAvailability)
        assertEquals("2026-10-22", de.artifactVerified)
        assertNull(de.packManifestUrl)
    }

    // 2 ------------------------------------------------------------------

    @Test
    fun oppositeScoreDirectionsAreRepresented() {
        val al = coverage().first { it.state == "AL" }
        assertEquals(NationalCoverage.MODEL_SCORE_100_HIGH, al.resultModel)
        val va = coverage().first { it.state == "VA" }
        assertEquals(NationalCoverage.MODEL_VIOLATIONS_ONLY, va.resultModel)
        val ms = coverage().first { it.state == "MS" }
        assertEquals(NationalCoverage.MODEL_LETTER_GRADE, ms.resultModel)
        val or = coverage().first { it.state == "OR" }
        assertEquals(NationalCoverage.MODEL_SCORE_100_HIGH, or.resultModel)
        // Threshold alerts are Alabama-scale only.
        assertTrue(NationalCoverage.supportsThresholdAlerts("SCORE_100_HIGH"))
        assertFalse(NationalCoverage.supportsThresholdAlerts("PENALTY_LOW"))
        assertFalse(NationalCoverage.supportsThresholdAlerts("LETTER_GRADE"))
    }

    // 3 ------------------------------------------------------------------

    @Test
    fun bandsExcludeMissingScoresOnBothScales() {
        // 0–100: NO_SCORE never banded.
        assertFalse(NationalCoverage.bandMatches("SCORE_100_HIGH", "Below 85", Place.NO_SCORE))
        assertTrue(NationalCoverage.bandMatches("SCORE_100_HIGH", "Below 85", 84))
        assertFalse(NationalCoverage.bandMatches("SCORE_100_HIGH", "Below 85", 85))
        assertTrue(NationalCoverage.bandMatches("SCORE_100_HIGH", "95+", 95))
        // Penalty scale: low points = good; NO_SCORE never banded either.
        assertTrue(NationalCoverage.bandMatches("PENALTY_LOW", "0–9", 7))
        assertFalse(NationalCoverage.bandMatches("PENALTY_LOW", "0–9", 12))
        assertTrue(NationalCoverage.bandMatches("PENALTY_LOW", "20+", 25))
        assertFalse(NationalCoverage.bandMatches("PENALTY_LOW", "20+", Place.NO_SCORE))
    }

    @Test
    fun sqlSearchExcludesNoScoreFromNumericBands() {
        val catalog = com.kyronapp.kyron.data.db.CatalogDb(ctx())
        val db = catalog.writableDatabase
        try {
            val scored = Place(
                id = "test_sc_ok", name = "Band A Place", address = "1 Test St",
                city = "Tuscaloosa", zip = "35401", county = "Tuscaloosa",
                score = 88, date = "10/1/2026", source = "TEST"
            )
            val noScore = Place(
                id = "test_sc_ns", name = "Band B Place", address = "2 Test St",
                city = "Tuscaloosa", zip = "35401", county = "Tuscaloosa",
                score = Place.NO_SCORE, date = "", source = "TEST",
                nativeResult = "No Further Action Required"
            )
            catalog.upsertPlace(db, scored)
            catalog.upsertPlace(db, noScore)
            val (min, max) = NationalCoverage.bandRange("SCORE_100_HIGH", "85–94")!!
            val inBand = catalog.search(
                db, ids = null, county = null, minScore = min, maxScore = max,
                textLike = null, orderBy = "name_lc", limit = 10
            )
            assertEquals(listOf("test_sc_ok"), inBand.map { it.id })
        } finally {
            db.close()
        }
    }

    // 4 ------------------------------------------------------------------

    @Test
    fun antimeridianViewportStillFindsWestAlaskaPlaces() {
        val catalog = com.kyronapp.kyron.data.db.CatalogDb(ctx())
        val db = catalog.writableDatabase
        try {
            // Synthetic isolated fixtures near the western Aleutians; real
            // address coordinates only in production datasets.
            fun at(attu: Boolean): Place = Place(
                id = if (attu) "test_ak_attu" else "test_ak_shemya",
                name = if (attu) "Attu Test Place" else "Shemya Test Place",
                address = "N Test Rd", city = if (attu) "Attu" else "Shemya",
                zip = "99599", county = "Aleutians West", score = 90,
                date = "10/1/2026", source = "TEST",
                lat = 52.85, lng = if (attu) 173.2 else -174.1,
                geoStatus = Place.STATUS_ACCEPTED,
                geoAccuracy = Place.ACC_ADDRESS_RANGE, geoProvider = "TEST",
                state = "AK"
            )
            catalog.upsertPlace(db, at(attu = true))   // east of +180
            catalog.upsertPlace(db, at(attu = false))  // west of -180
            // A viewport centered on the dateline: minLng > maxLng.
            val hits = catalog.inBounds(db, 51.0, 54.0, 170.0, -170.0, 100)
            val ids = hits.map { it.id }.toSet()
            assertTrue("east-of-dateline place missing", ids.contains("test_ak_attu"))
            assertTrue("west-of-dateline place missing", ids.contains("test_ak_shemya"))
        } finally {
            db.close()
        }
    }

    @Test
    fun nonCrossingViewportBehaviorUnchanged() {
        val catalog = com.kyronapp.kyron.data.db.CatalogDb(ctx())
        val db = catalog.writableDatabase
        try {
            catalog.upsertPlace(
                db, Place(
                    id = "test_al_huntsville", name = "Huntsville Test Place",
                    address = "3 Test St", city = "Huntsville", zip = "35801",
                    county = "Madison", score = 91, date = "10/1/2026", source = "TEST",
                    lat = 34.7304, lng = -86.5861, geoStatus = Place.STATUS_ACCEPTED,
                    geoAccuracy = Place.ACC_ADDRESS_RANGE, geoProvider = "TEST",
                    state = "AL"
                )
            )
            val hits = catalog.inBounds(db, 34.0, 35.5, -87.0, -86.0, 100)
            assertTrue(hits.any { it.id == "test_al_huntsville" })
        } finally {
            db.close()
        }
    }

    // 5 ------------------------------------------------------------------

    @Test
    fun sameNamedCountiesInDifferentStatesAreQualifiedByState() {
        // Identity is namespace-qualified by state: "Jefferson" county with
        // the same name/zip-ish fields in AL and CO must never resolve to
        // the same row or the same region.
        val alP = Place(
            id = "test_jef_al", name = "Jefferson Test Cafe", address = "4 Test St",
            city = "Birmingham", zip = "35203", county = "Jefferson",
            score = 90, date = "10/1/2026", source = "TEST", state = "AL"
        )
        val coP = Place(
            id = "test_jef_co", name = "Jefferson Test Cafe", address = "4 Test St",
            city = "Golden", zip = "80401", county = "Jefferson",
            score = 90, date = "10/1/2026", source = "TEST", state = "CO"
        )
        assertEquals("us-al", alP.regionId)
        assertEquals("us-co", coP.regionId)
        // matchKeys differ because the zip differs; even identical names
        // stay distinct rows keyed by source-qualified ids.
        assertTrue(alP.id != coP.id)
    }

    @Test
    fun regionMigrationsKeepLegacyAlabamaBehavior() {
        assertEquals("us-al", Regions.ALABAMA.regionId)
        assertTrue(Regions.ALABAMA.bundled)
        assertEquals("us-fl", Regions.FLORIDA.regionId)
        assertEquals("us-ga", Regions.GEORGIA.regionId)
        // Regions still reachable by state code, case-insensitive.
        assertEquals("us-al", Regions.byState("al")!!.regionId)
        assertEquals(NationalCoverage.MODEL_SCORE_100_HIGH, Regions.nationalModel(Regions.ALABAMA))
        assertEquals(NationalCoverage.MODEL_DISPOSITION, Regions.nationalModel(Regions.FLORIDA))
    }
}
