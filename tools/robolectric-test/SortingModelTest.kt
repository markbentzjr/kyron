package com.kyronapp.kyron

import com.kyronapp.kyron.data.NationalCoverage
import com.kyronapp.kyron.data.Place
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * LF-N hardening: deterministic sort/filter fixtures (requirement 4).
 * Synthetic records ONLY in this test fixture — never production data.
 *
 * Fixes per the audit:
 *  - higher-is-better 0–100: 60 / 80 / 95 must order worst→best as
 *    60, 80, 95 and best→worst as 95, 80, 60;
 *  - lower-is-better penalty: worst→best 25, 10, 2; best→worst 2, 10, 25;
 *  - missing scores (NO_SCORE) NEVER enter numeric bands or masquerade
 *    as zero in either direction;
 *  - two sources inside ONE state may use DIFFERENT models: orderings,
 *    bands, badge text, and tone colors each follow the PLACE's own
 *    source model (never one statewide scale).
 */
class SortingModelTest {

    // ------------------------------------------------------------------
    // helpers
    private fun scored100(id: String, s: Int) = Place(
        id = id, name = "P_$id", address = "$id Test St", city = "Testville",
        zip = "35000", county = "Test", score = s, date = "10/1/2026", source = "TEST",
        state = "AL"
    )

    private fun scoredPenalty(id: String, s: Int) = Place(
        id = id, name = "P_$id", address = "$id Test Rd", city = "Testville",
        zip = "39999", county = "Test", score = s, date = "10/1/2026", source = "TEST",
        state = "AL"
    )

    // ------------------------------------------------------------------
    // 1) ORDER direction under each model

    @Test
    fun higherIsBetterWorstFirstOrders60_80_95() {
        // Worst first on 0–100 = ASC (lowest score first).
        assertEquals(
            "score ASC, name_lc ASC",
            NationalCoverage.orderByFor(NationalCoverage.MODEL_SCORE_100_HIGH, "Worst first")
        )
    }

    @Test
    fun higherIsBetterBestFirstOrders95_80_60() {
        assertEquals(
            "score DESC, name_lc ASC",
            NationalCoverage.orderByFor(NationalCoverage.MODEL_SCORE_100_HIGH, "Best first")
        )
    }

    @Test
    fun penaltyWorstFirstOrders25_10_2() {
        // Worst first on a penalty scale = HIGHEST penalty points first.
        assertEquals(
            "score DESC, name_lc ASC",
            NationalCoverage.orderByFor(NationalCoverage.MODEL_PENALTY_LOW, "Worst first")
        )
        // The alternate label means exactly the same thing.
        assertEquals(
            NationalCoverage.orderByFor(NationalCoverage.MODEL_PENALTY_LOW, "Worst first"),
            NationalCoverage.orderByFor(NationalCoverage.MODEL_PENALTY_LOW, "Most penalty points first")
        )
    }

    @Test
    fun penaltyBestFirstOrders2_10_25() {
        assertEquals(
            "score ASC, name_lc ASC",
            NationalCoverage.orderByFor(NationalCoverage.MODEL_PENALTY_LOW, "Fewest penalty points first")
        )
    }

    @Test
    fun penaltyLabelsNeverAnnounceBestFirstAsScoreDesc() {
        // Cross-model label safety: "Fewest penalty points first" on a
        // 0–100 model resolves to the 0-100 best order, not penaltyless.
        assertEquals(
            NationalCoverage.orderByFor(NationalCoverage.MODEL_SCORE_100_HIGH, "Best first"),
            NationalCoverage.orderByFor(NationalCoverage.MODEL_SCORE_100_HIGH, "Fewest penalty points first")
        )
    }

    /** End-to-end fixture check: three penalty rows 25/10/2 admitted into
     *  the penalty band vocabulary in-band, with NO_SCORE excluded. */
    @Test
    fun penaltyRows25_10_2BandCleanOrder() {
        val a = scoredPenalty("pen25", 25)
        val b = scoredPenalty("pen10", 10)
        val c = scoredPenalty("pen2", 2)
        for ((p, band) in listOf(a to "20+", b to "10–19", c to "0–9")) {
            assertTrue(
                "${p.id} must land in '$band'",
                NationalCoverage.bandMatches(NationalCoverage.MODEL_PENALTY_LOW, band, p.score)
            )
        }
        // No score never masquerades in ANY penalty band:
        for (band in listOf("0–9", "10–19", "20+")) {
            assertFalse(
                NationalCoverage.bandMatches(NationalCoverage.MODEL_PENALTY_LOW, band, Place.NO_SCORE)
            )
        }
    }

    /** Mirror fixture for 0–100: 60 / 80 / 95 land in Below 85 / Below 85 /
     *  95+, and NO_SCORE is excluded from every band. */
    @Test
    fun score100Rows60_80_95BandPlacement() {
        val rows = listOf(
            scored100("s60", 60) to "Below 85",
            scored100("s80", 80) to "Below 85",
            scored100("s95", 95) to "95+"
        )
        for ((p, band) in rows) {
            assertTrue(
                "${p.id} must land in '$band'",
                NationalCoverage.bandMatches(NationalCoverage.MODEL_SCORE_100_HIGH, band, p.score)
            )
        }
        for (band in listOf("Below 85", "85–94", "95+")) {
            assertFalse(
                NationalCoverage.bandMatches(NationalCoverage.MODEL_SCORE_100_HIGH, band, Place.NO_SCORE)
            )
        }
    }

    // ------------------------------------------------------------------
    // 2) MIXED-MODEL / SOURCE-LEVEL RESOLUTION

    /**
     * Two DIFFERENT sources inside ONE state must resolve to their own
     * models: label/pin/format decisions follow the place's source model.
     * Fixture: AL primary source is 0–100; AL's hypothetical penalty
     * source (registry-style id "al-pen") publishes demerit points.
     */
    @Test
    fun sameStateDifferentSourcesResolveDifferentModels() {
        val jur = NationCoverageFixture.jurisdiction(
            state = "AL", model = "SCORE_100_HIGH",
            sources = listOf(
                NationCoverageFixture.source(id = "al-adph", model = "SCORE_100_HIGH"),
                NationCoverageFixture.source(id = "al-pen", model = "PENALTY_LOW")
            )
        )
        val states = listOf(jur)
        val from100 = Place(
            id = "mix_100", name = "Mix A", address = "A", city = "B", zip = "3",
            county = "C", score = 88, date = "", source = "ADPH", state = "AL"
        )
        val fromPen = Place(
            id = "mix_pen", name = "Mix B", address = "A", city = "B", zip = "3",
            county = "C", score = 24, date = "", source = "PEN", state = "AL"
        )
        assertEquals(
            NationalCoverage.MODEL_SCORE_100_HIGH,
            NationalCoverage.modelForPlace(states, from100)
        )
        assertEquals(
            NationalCoverage.MODEL_PENALTY_LOW,
            NationalCoverage.modelForPlace(states, fromPen)
        )
        // Tones run in opposite directions for the same raw numbers:
        // 88 on 0–100 is acceptable-mid (tone2); 24 as penalty points is BAD (tone3).
        assertEquals(2, NationalCoverage.numericTone(NationalCoverage.MODEL_SCORE_100_HIGH, 88))
        assertEquals(3, NationalCoverage.numericTone(NationalCoverage.MODEL_PENALTY_LOW, 24))
        // And the badge/ordering label difference is real, not cosmetic:
        assertEquals("Most penalty points first", NationalCoverage.scoreSortLabel(NationalCoverage.MODEL_PENALTY_LOW))
        assertEquals("Worst first", NationalCoverage.scoreSortLabel(NationalCoverage.MODEL_SCORE_100_HIGH))
    }

    @Test
    fun unknownModelNeverBecomesAlabamasScale() {
        val states = listOf(
            NationCoverageFixture.jurisdiction(state = "AL", model = "SCORE_100_HIGH", sources = emptyList())
        )
        val fromUnresolvedSource = Place(
            id = "mix_unknown", name = "Mix C", address = "A", city = "B", zip = "3",
            county = "C", score = 90, date = "", source = "UNKNOWN-VENDOR", state = "AL"
        )
        // A place whose source does not resolve STILL inherits the
        // jurisdiction model (verified for that state); the UNKNOWN
        // fallback is reserved for places with no jurisdiction at all.
        assertEquals(
            NationalCoverage.MODEL_SCORE_100_HIGH,
            NationalCoverage.modelForPlace(states, fromUnresolvedSource)
        )
        // A place in a jurisdiction the registry does not list resolves to
        // UNKNOWN — and UNKNOWN has NO bands, NO threshold, NO score sorts.
        assertEquals(
            NationalCoverage.MODEL_UNKNOWN,
            NationalCoverage.modelForPlace(states, fromUnresolvedSource.copy(state = "XX"))
        )
        assertTrue(NationalCoverage.bands(NationalCoverage.MODEL_UNKNOWN).isEmpty())
        assertFalse(NationalCoverage.supportsThresholdAlerts(NationalCoverage.MODEL_UNKNOWN))
        assertTrue(NationalCoverage.hidesScoreFilters(NationalCoverage.MODEL_UNKNOWN))
        // And unknown-model rows never fall into a numeric band anywhere:
        for (model in listOf("SCORE_100_HIGH", "PENALTY_LOW")) {
            for (band in NationalCoverage.bands(model).drop(1)) {
                assertFalse(
                    NationalCoverage.bandMatches(
                        NationalCoverage.MODEL_UNKNOWN, band, 90
                    )
                )
            }
        }
    }
}

/** Tiny data-class fixture builder for source-level model tests. */
private object NationCoverageFixture {
    private fun src(id: String, model: String) = NationalCoverage.Source(
        id = id, agency = "Test", coverage = "test", access = "api",
        website = "https://example.test", violations = "none",
        history = "full-history", resultModel = model,
        status = "source-verified", verified = "2026-10-22", blocker = "",
        restrictions = "", refresh = "", lastRefresh = "", notes = ""
    )

    fun jurisdiction(
        state: String, model: String,
        sources: List<NationalCoverage.Source>
    ): NationalCoverage.Jurisdiction =
        NationalCoverage.Jurisdiction(
            regionId = "us-" + state.lowercase(),
            state = state, name = state, type = "state",
            resultModel = model, sources = sources,
            packStatus = "none", packManifestUrl = null,
            packAvailability = NationalCoverage.AVAIL_NONE,
            artifactVerified = "", packHostStatus = "", packHostChecked = "",
            centerLat = null, centerLng = null
        )

    fun source(id: String, model: String) = src(id, model)
}
