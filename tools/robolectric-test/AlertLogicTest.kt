package com.kyronapp.kyron

import com.kyronapp.kyron.worker.AlertEvaluator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * LF-N hardening: deterministic alert-decision fixtures (requirement 5).
 * Pure JVM — no Robolectric needed; AlertEvaluator is context-free.
 *
 * Fixed semantics under test (the auditor's explicit contract):
 *  1. initial install / first full import / unknown baseline -> SUPPRESS_BASELINE
 *  2. historical backfill == same event key re-delivered       -> SUPPRESS_DUPLICATE
 *  3. newly discovered establishment post-baseline             -> NEW_ESTABLISHMENT
 *     (informational: inbox only, never a system incident)
 *  4. genuinely new inspection on existing place (date moved)  -> NEW_INSPECTION_*
 *  5. corrected record (same date, different result)           -> CORRECTED_RECORD
 *  6. dedupe survives pack updates, restarts, retries, rollbacks (key-based)
 *  7. unknown model NEVER earns an Alabama threshold comparison
 *  8. no date cutoff anywhere in the newness decision
 */
class AlertLogicTest {

    // Fixture shorthand: favorite listener, 0–100 model.
    private fun favInput(
        baselineDone: Boolean = true,
        lastKey: String? = null,
        hasPrior: Boolean = true,
        oldDate: String? = "10/1/2026",
        newDate: String = "10/20/2026",
        eventKey: String = "$newDate|90|",
        numeric: Boolean = true,
        thresholdApplies: Boolean = true,
        belowThreshold: Boolean = false,
        eventK: String? = null
    ) = AlertEvaluator.Input(
        hasPrior = hasPrior, baselineDone = baselineDone,
        lastEventKey = lastKey, eventKey = eventK ?: eventKey,
        oldDate = oldDate, newDate = newDate,
        isFavorite = true, alertsForFavorites = true,
        alertsForArea = false, inMonitoredArea = false,
        thresholdApplies = thresholdApplies, numeric = numeric,
        belowThreshold = belowThreshold, areaEligible = false
    )

    // 1 -----------------------------------------------------------------
    @Test
    fun initialImportSuppressesWhileBaselineNotStamped() {
        val d = AlertEvaluator.evaluate(favInput(baselineDone = false, hasPrior = false))
        assertEquals(AlertEvaluator.Kind.SUPPRESS_BASELINE, d.kind)
        assertFalse(d.inbox); assertFalse(d.sysNotify)
        // Even a real-looking change on an existing row is suppressed
        // before the baseline exists — the sync cannot PROVE it is not a
        // historical backfill.
        val d2 = AlertEvaluator.evaluate(favInput(baselineDone = false, hasPrior = true))
        assertEquals(AlertEvaluator.Kind.SUPPRESS_BASELINE, d2.kind)
    }

    // 2 -----------------------------------------------------------------
    @Test
    fun repeatedImportOrRetryIsDuplicateSuppressed() {
        val key = "10/20/2026|90|"
        val d = AlertEvaluator.evaluate(favInput(lastKey = key, eventK = key))
        assertEquals(AlertEvaluator.Kind.SUPPRESS_DUPLICATE, d.kind)
        assertFalse(d.inbox)
        // Correction vs dedupe: same key = dedupe even with dates equal.
        val same = AlertEvaluator.evaluate(favInput(lastKey = key, eventK = key, oldDate = newDateKeyDate(key)))
        assertEquals(AlertEvaluator.Kind.SUPPRESS_DUPLICATE, same.kind)
    }

    private fun newDateKeyDate(key: String) = key.substringBefore('|')

    // 3 -----------------------------------------------------------------
    @Test
    fun newlyEstablishedPlacePostBaselineIsInformationalOnly() {
        val d = AlertEvaluator.evaluate(favInput(hasPrior = false, lastKey = null))
        assertEquals(AlertEvaluator.Kind.NEW_ESTABLISHMENT, d.kind)
        // Never a system incident, never phrased low:
        assertFalse(d.sysNotify)
        assertFalse(d.low)
        // Inbox only for an area-watching user:
        val notWatching = AlertEvaluator.evaluate(
            favInput(hasPrior = false).copy(alertsForArea = false)
        )
        assertFalse(notWatching.inbox)
        val watching = AlertEvaluator.evaluate(
            favInput(hasPrior = false).copy(alertsForArea = true, inMonitoredArea = true)
        )
        assertTrue(watching.inbox)
    }

    // 4 -----------------------------------------------------------------
    @Test
    fun newInspectionOnExistingPlaceFiresPerModel() {
        // Date moved + result changed, favorite listening, 0–100 model:
        val d = AlertEvaluator.evaluate(
            favInput(lastKey = "10/1/2026|95|", eventK = "10/20/2026|90|")
        )
        assertEquals(AlertEvaluator.Kind.NEW_INSPECTION_NUM, d.kind)
        assertTrue(d.inbox); assertTrue(d.sysNotify)
        // Threshold breach marks LOW only in a threshold model:
        val low = AlertEvaluator.evaluate(
            favInput(lastKey = "10/1/2026|95|", eventK = "10/20/2026|60|", belowThreshold = true)
        )
        assertTrue(low.low)
    }

    @Test
    fun newInspectionOnPenaltyModelNeverMarksLow() {
        // Same numbers but a PENALTY model: 12 points is not "below an
        // Alabama threshold" — no LOW framing ever.
        val d = AlertEvaluator.evaluate(
            favInput(
                lastKey = "10/1/2026|2|", eventK = "10/20/2026|12|",
                thresholdApplies = false, belowThreshold = false
            )
        )
        assertEquals(AlertEvaluator.Kind.NEW_INSPECTION_NUM, d.kind)
        assertTrue(d.inbox); assertTrue(d.sysNotify)
        assertFalse(d.low)
    }

    // 5 -----------------------------------------------------------------
    @Test
    fun correctedRecordSameDateDifferentResult() {
        // Same date, different result than the stored key: a correction.
        val d = AlertEvaluator.evaluate(
            favInput(oldDate = "10/20/2026", newDate = "10/20/2026",
                     lastKey = "10/20/2026|90|", eventK = "10/20/2026|72|")
        )
        assertEquals(AlertEvaluator.Kind.CORRECTED_RECORD, d.kind)
        assertTrue(d.inbox); assertTrue(d.sysNotify)
        // Corrections work in a text (disposition) model too:
        val text = AlertEvaluator.evaluate(
            favInput(numeric = false, oldDate = "10/20/2026", newDate = "10/20/2026",
                     lastKey = "10/20/2026|-1|Pass", eventK = "10/20/2026|-1|Closed")
        )
        assertEquals(AlertEvaluator.Kind.CORRECTED_RECORD, text.kind)
    }

    // 6 -----------------------------------------------------------------
    @Test
    fun dedupeSurvivesPackUpdatesAndRestartsViaStoreKey() {
        // Simulates: pack v1 delivers event K (recorded), pack v2 re-delivers
        // the SAME event rows (old==null because install repopulated, but the
        // persisted key already matches), then a genuinely new event arrives.
        val k1 = "10/1/2026|88|"
        val delivered = AlertEvaluator.evaluate(
            favInput(lastKey = k1, eventK = k1, hasPrior = false)
        )
        // NOTE: an old==null row whose key matches the persisted one is
        // STILL a dedupe, not a "new establishment" — the persisted key is
        // the ground truth for "already seen", checked BEFORE the prior-row
        // check. Order inside evaluate(): baseline → duplicate → new place.
        assertEquals(AlertEvaluator.Kind.SUPPRESS_DUPLICATE, delivered.kind)
    }

    // 7 -----------------------------------------------------------------
    @Test
    fun unknownModelNeverUsesThresholdFramingAtAll() {
        // An unresolved jurisdiction (registry missing) on a changed result:
        val d = AlertEvaluator.evaluate(
            favInput(lastKey = "10/1/2026|95|", eventK = "10/20/2026|55|",
                     thresholdApplies = false, belowThreshold = false)
        )
        // Numeric but UNKNOWN → information notice, never "low score":
        assertEquals(AlertEvaluator.Kind.NEW_INSPECTION_NUM, d.kind)
        assertFalse(d.low)
    }

    // 8 -----------------------------------------------------------------
    @Test
    fun newnessNeverDependsOnADateCutoff() {
        // A HIDORICALLY-dated event that is genuinely NEWLY DELIVERED
        // (changed result, key differs) still counts as new — a date-based
        // cutoff would have swallowed it. The decision only compares keys
        // and dates against each other, never against wall-clock.
        val d = AlertEvaluator.evaluate(
            favInput(oldDate = "3/4/2024", newDate = "3/4/2024",
                     lastKey = "3/4/2024|80|", eventK = "3/4/2024|70|")
        )
        assertEquals(AlertEvaluator.Kind.CORRECTED_RECORD, d.kind)
        val d2 = AlertEvaluator.evaluate(
            favInput(oldDate = "3/4/2024", newDate = "5/9/2024",
                     lastKey = "3/4/2024|80|", eventK = "5/9/2024|70|")
        )
        assertEquals(AlertEvaluator.Kind.NEW_INSPECTION_NUM, d2.kind)
    }

    @Test
    fun eventKeyCanonicalizationIsStable() {
        assertEquals("10/1/2026|88|", AlertEvaluator.eventKeyOf("10/1/2026", 88, ""))
        assertEquals("10/1/2026|-1|Pass", AlertEvaluator.eventKeyOf("10/1/2026", -1, "Pass"))
    }
}
