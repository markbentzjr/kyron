package com.kyronapp.kyron.worker

/**
 * LF-N hardening: the explicit FIRST-SEEN / NEW-INSPECTION / RETRY /
 * CORRECTION alert decision, extracted from [SyncEngine] so it can be
 * tested with deterministic fixtures (AlertLogicTest) without touching
 * the network.
 *
 * ## Intended behavior (the contract this object implements)
 *
 * | Situation | Persisted marker consumed | Outcome |
 * |---|---|---|
 * | Initial install / first full import of a region | `alerts_baseline:<region>` NOT yet stamped | **SUPPRESS_BASELINE** — the sync cannot yet distinguish initial population from a backfilled historical record, so nothing fires |
 * | Historical backfill (same data re-delivered) | per-place `alerts_evt:<placeId>` == incoming event key | **SUPPRESS_DUPLICATE** — repeated import, retry after a partial sync, or a pack update re-delivering the same event |
 * | Newly discovered establishment during routine monitoring | baseline stamped, prior row absent | **NEW_ESTABLISHMENT** — informational ONLY (inbox, never a system incident, never phrased as a score event; there is no "was" value) |
 * | Genuinely new inspection on an existing establishment | prior row exists, event key differs, DATE moved forward | **NEW_INSPECTION_*** (threshold-num / info-num / text per model) |
 * | Corrected record | prior row exists, event key differs, same DATE | **CORRECTED_RECORD** — the agency published a corrected result for a date we already have; never framed as a new inspection |
 * | Any event under an unresolved region baseline | baseline not stamped | suppressed (see row 1) |
 *
 * Deliberately NOT a newness criterion: date cutoffs. "New" means the
 * event key CHANGED against the persisted per-place key, cross-checked
 * with the prior row — never "the date is within N days".
 *
 * Model guards (requirement: unknown must not silently become Alabama's
 * 0–100 scale): [Input.thresholdApplies] is
 * [com.kyronapp.kyron.data.NationalCoverage.supportsThresholdAlerts]
 * evaluated on the SOURCE-level model, which resolves to UNKNOWN when the
 * source/jurisdiction cannot be named — and then no threshold comparison
 * ever happens.
 */
object AlertEvaluator {

    enum class Kind {
        SUPPRESS_BASELINE,
        SUPPRESS_DUPLICATE,
        NEW_ESTABLISHMENT,
        CORRECTED_RECORD,
        NEW_INSPECTION_LOW,
        NEW_INSPECTION_NUM,
        NEW_INSPECTION_TEXT,
        IGNORE // eligible to observe, but no listening user prefers it
    }

    /** What to do: [inbox] writes the in-app alerts list; [sysNotify] posts
     *  the system notification; [low] marks the inbox row as low-score. */
    data class Decision(
        val kind: Kind,
        val inbox: Boolean,
        val sysNotify: Boolean,
        val low: Boolean
    )

    data class Input(
        /** True when a row for this place existed before this cycle
         *  (SyncEngine's `old != null`). */
        val hasPrior: Boolean,
        /** True when `alerts_baseline:<region>` was stamped BEFORE this
         *  cycle (PackManager.installFullPack, or the end of a previous
         *  successful sync that covered the region). */
        val baselineDone: Boolean,
        /** Persisted per-place event key (`alerts_evt:<placeId>`); null =
         *  never recorded (the place predates the persisted-key scheme). */
        val lastEventKey: String?,
        /** The incoming event's key (date|score|nativeResult). */
        val eventKey: String,
        /** Inspection date on the prior row, when one existed. */
        val oldDate: String?,
        /** Inspection date on the incoming row. */
        val newDate: String?,
        val isFavorite: Boolean,
        val alertsForFavorites: Boolean,
        val alertsForArea: Boolean,
        val inMonitoredArea: Boolean,
        /** NationalCoverage.supportsThresholdAlerts(model) — false for every
         *  model except the 0–100 higher-is-better scale. */
        val thresholdApplies: Boolean,
        /** Place.hasNumericScore. */
        val numeric: Boolean,
        /** True only in a threshold model when score < threshold. */
        val belowThreshold: Boolean,
        /** Numeric + thresholdApplies + belowThreshold + monitored area. */
        val areaEligible: Boolean
    )

    fun evaluate(i: Input): Decision {
        // 1) Baseline / first full import / unknown state: suppressed. The
        //    first cycle after a baseline stamp treats nothing as an
        //    incident, because we cannot PROVE an old==null row is not a
        //    historical record arriving late.
        if (!i.baselineDone) return Decision(Kind.SUPPRESS_BASELINE, false, false, false)

        // 2) Retry / re-import / pack re-delivery: identical key already
        //    persisted per place → it already happened once.
        if (i.lastEventKey != null && i.lastEventKey == i.eventKey) {
            return Decision(Kind.SUPPRESS_DUPLICATE, false, false, false)
        }

        // 3) Newly discovered establishment, post-baseline: INFORMATIONAL.
        //    It is a listing event, not an inspection incident — never a
        //    system notification, never a "score" phrasing. Goes to the
        //    inbox only when the user is actually watching this area.
        if (!i.hasPrior) {
            val inbox = i.alertsForArea && i.inMonitoredArea
            return Decision(Kind.NEW_ESTABLISHMENT, inbox, false, false)
        }

        // 4) Corrected record: the date did not move but the result did.
        if (i.oldDate != null && i.oldDate == i.newDate) {
            return deliver(i, Kind.CORRECTED_RECORD)
        }

        // 5) Genuinely new inspection — branch by model semantics.
        return deliver(i, if (i.numeric) Kind.NEW_INSPECTION_NUM else Kind.NEW_INSPECTION_TEXT)
    }

    /** Delivery rules shared by correction/new-inspection kinds:
     *  favorites listen to every result; area listeners only to threshold
     *  breaches (and only where threshold semantics exist at all). */
    private fun deliver(i: Input, kind: Kind): Decision {
        if (i.isFavorite && i.alertsForFavorites) {
            val low = i.numeric && i.thresholdApplies && i.belowThreshold
            return Decision(kind, inbox = true, sysNotify = true, low = low)
        }
        if (i.alertsForArea && i.areaEligible) {
            return Decision(kind, inbox = true, sysNotify = true, low = true)
        }
        return Decision(Kind.IGNORE, false, false, false)
    }

    /** Canonical recorded key for the pending dedupe check. */
    fun eventKeyOf(date: String, score: Int, nativeResult: String): String =
        "$date|$score|$nativeResult"
}
