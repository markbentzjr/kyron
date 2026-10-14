package com.kyronapp.kyron.data

import org.json.JSONArray
import org.json.JSONObject

/** One recorded violation from an inspection report. */
data class Violation(
    val points: Int,
    val critical: Boolean,
    val remarks: String
) {
    /** Rule text with the code stripped, e.g. "Maintain TCS food at 41 F or below." */
    val ruleText: String
        get() {
            val head = remarks.substringBefore("//").trim()
            return head.replace(Regex("^\\S+\\s+"), "").trim().ifEmpty { head }
        }

    /** The inspector's own observation (after "//"), if recorded. */
    val inspectorNote: String
        get() = remarks.split("//").drop(1).joinToString(" ").trim()

    fun toJson(): JSONObject = JSONObject()
        .put("p", points)
        .put("c", critical)
        .put("r", remarks)

    companion object {
        fun fromJson(o: JSONObject): Violation = Violation(
            points = o.optInt("p"),
            critical = o.optBoolean("c"),
            remarks = o.optString("r")
        )
    }
}

/** One inspection event for a place. */
data class Inspection(
    val score: Int,
    val date: String,
    val type: String = "",
    val violations: List<Violation> = emptyList(),
    /** The jurisdiction's own result for this inspection, in its own terms
     *  (e.g. a Florida DBPR disposition), for jurisdictions that do not
     *  publish a numeric score. Empty for score-model jurisdictions. */
    val nativeResult: String = ""
) {
    /** True when this inspection carries a real numeric score (score >= 0).
     *  A negative score is the NO_SCORE sentinel — it is never a result. */
    val hasNumericScore: Boolean get() = score >= 0

    /** Short badge label: the number, or a compact form of the native result. */
    val badgeText: String
        get() = if (hasNumericScore) score.toString() else Place.shortResultLabel(nativeResult)

    fun toJson(): JSONObject = JSONObject()
        .put("s", score)
        .put("d", date)
        .put("t", type)
        .put("disp", nativeResult)
        .put("v", JSONArray().apply { violations.forEach { put(it.toJson()) } })

    companion object {
        fun fromJson(o: JSONObject): Inspection {
            val vs = mutableListOf<Violation>()
            val arr = o.optJSONArray("v")
            if (arr != null) for (i in 0 until arr.length()) vs += Violation.fromJson(arr.getJSONObject(i))
            return Inspection(o.optInt("s"), o.optString("d"), o.optString("t"), vs, o.optString("disp"))
        }
    }
}

/** A food establishment with its latest score and (where the source publishes them) inspections. */
data class Place(
    val id: String,
    val name: String,
    val address: String,
    val city: String,
    val zip: String,
    val county: String,
    val score: Int,
    val date: String,
    val source: String,
    val lat: Double? = null,
    val lng: Double? = null,
    val detailUrl: String? = null,
    val inspections: List<Inspection> = emptyList(),
    /** Geocode provenance (Gameplan draft section 3.6). Coordinates are only
     *  ever present when [geoStatus] is ACCEPTED with an address-level class;
     *  centroid approximations are never stored as a place location. */
    val geoStatus: String = STATUS_LEGACY,
    val geoAccuracy: String = ACC_NONE,
    val geoProvider: String = "",
    val geoMatch: String = "",
    /** USPS state code of the place ("AL", "FL", …). LF-4: the catalog is
     *  multi-state; nothing may assume Alabama anymore. */
    val state: String = "AL",
    /** The inspecting jurisdiction in the source's own terms
     *  (e.g. "FL-DBPR"). Empty when the source does not name one. */
    val jurisdiction: String = "",
    /** The jurisdiction's own latest result in its own terms (e.g. a
     *  Florida DBPR disposition) for non-score jurisdictions. Empty when
     *  the jurisdiction publishes a numeric score — or when no inspection
     *  is on file at all. Never a converted or invented score. */
    val nativeResult: String = ""
) {
    /** True when this place has a real, address-level location for the map. */
    val hasRealLocation: Boolean
        get() = lat != null && lng != null && geoStatus == STATUS_ACCEPTED

    /** Region pack this place belongs to ("us-al", "us-fl", …). */
    val regionId: String get() = "us-" + state.lowercase()

    /** True when the jurisdiction publishes a numeric score for this place.
     *  score == NO_SCORE (-1) means "no numeric score exists" — it must
     *  never be rendered, banded, or averaged as if it were a result. */
    val hasNumericScore: Boolean get() = score >= 0

    /** Short badge label: the score number, or a compact native result. */
    val badgeText: String
        get() = if (hasNumericScore) score.toString() else shortResultLabel(nativeResult)

    /** Presentation tone for a native result: 0 neutral, 1 good, 2 warn, 3 bad. */
    val resultTone: Int get() = resultToneOf(nativeResult)

    val bandLabel: String
        get() = when {
            !hasNumericScore -> nativeResult.ifBlank { "No inspection on file" }
            score >= 95 -> "Excellent"
            score >= 85 -> "Good / Fair"
            else -> "Needs improvement"
        }

    /** Stable event key for "is this a new inspection?" checks. */
    val eventKey: String get() = "$date|$score|$nativeResult"

    fun fullAddress(): String =
        listOf(address, city, "$state $zip".trim()).filter { it.isNotBlank() }.joinToString(", ")

    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("n", name)
        .put("a", address)
        .put("c", city)
        .put("z", zip)
        .put("ct", county)
        .put("s", score)
        .put("d", date)
        .put("src", source)
        .put("lat", lat ?: JSONObject.NULL)
        .put("lng", lng ?: JSONObject.NULL)
        .put("du", detailUrl ?: JSONObject.NULL)
        .put("gs", geoStatus)
        .put("ga", geoAccuracy)
        .put("gp", geoProvider)
        .put("gm", geoMatch)
        .put("st", state)
        .put("jur", jurisdiction)
        .put("disp", nativeResult)
        .put("insp", JSONArray().apply { inspections.forEach { put(it.toJson()) } })

    companion object {
        const val STATUS_ACCEPTED = "ACCEPTED"
        const val STATUS_LEGACY = "LEGACY"
        const val ACC_ADDRESS_RANGE = "ADDRESS_RANGE"
        const val ACC_NONE = "NONE"

        /** Sentinel score for jurisdictions that publish no numeric score. */
        const val NO_SCORE = -1

        /**
         * Compact badge form of a native (non-numeric) result. This is a
         * presentation shortening of the jurisdiction's own words — the
         * full verbatim result is always shown alongside it. Order of the
         * checks matters ("…Callback Complied" is a complied outcome, not
         * an emergency; "Not Complied" is the opposite of "Complied").
         */
        fun shortResultLabel(nativeResult: String): String {
            val r = nativeResult.trim()
            return when {
                r.isEmpty() -> "—"
                r.contains("No Further Action", true) -> "Passed"
                r.contains("Not Complied", true) -> "Not complied"
                r.contains("Complied", true) -> "Complied"
                r.contains("Emergency", true) -> "Emergency"
                r.contains("complaint recommended", true) -> "Complaint"
                r.contains("Warning", true) -> "Warning"
                r.contains("Extension", true) -> "Extension"
                r.contains("Call Back", true) -> "Follow-up"
                r.contains("Assigned", true) -> "Pending"
                else -> r
            }
        }

        /** Tone bucket for a native result: 0 neutral, 1 good, 2 warn, 3 bad. */
        fun resultToneOf(nativeResult: String): Int {
            val r = nativeResult.trim()
            return when {
                r.isEmpty() -> 0
                r.contains("No Further Action", true) -> 1
                r.contains("Not Complied", true) -> 3
                r.contains("Complied", true) -> 1
                r.contains("Emergency", true) -> 3
                r.contains("complaint recommended", true) -> 3
                r.contains("Warning", true) -> 2
                else -> 2
            }
        }

        fun fromJson(o: JSONObject): Place {
            val insps = mutableListOf<Inspection>()
            val arr = o.optJSONArray("insp")
            if (arr != null) for (i in 0 until arr.length()) insps += Inspection.fromJson(arr.getJSONObject(i))
            return Place(
                id = o.getString("id"),
                name = o.optString("n"),
                address = o.optString("a"),
                city = o.optString("c"),
                zip = o.optString("z"),
                county = o.optString("ct"),
                score = o.optInt("s"),
                date = o.optString("d"),
                source = o.optString("src"),
                lat = if (o.isNull("lat")) null else o.optDouble("lat"),
                lng = if (o.isNull("lng")) null else o.optDouble("lng"),
                detailUrl = if (o.isNull("du")) null else o.optString("du"),
                inspections = insps,
                geoStatus = o.optString("gs", STATUS_LEGACY),
                geoAccuracy = o.optString("ga", ACC_NONE),
                geoProvider = o.optString("gp", ""),
                geoMatch = o.optString("gm", ""),
                state = o.optString("st", "AL").ifBlank { "AL" },
                jurisdiction = o.optString("jur", ""),
                nativeResult = o.optString("disp", "")
            )
        }

        /** Normalized key used to match the same establishment across sources. */
        fun matchKey(name: String, zip: String, address: String): String {
            val n = name.uppercase().replace(Regex("[^A-Z0-9 ]"), "").replace(Regex("\\s+"), " ").trim()
            val num = address.trim().split(" ").firstOrNull() ?: ""
            return "$n|$zip|$num"
        }
    }
}

/** A fired alert, kept in the in-app inbox. */
data class AlertItem(
    val placeId: String,
    val title: String,
    val body: String,
    val whenMs: Long,
    val lowScore: Boolean
) {
    fun toJson(): JSONObject = JSONObject()
        .put("pid", placeId).put("t", title).put("b", body).put("w", whenMs).put("low", lowScore)

    companion object {
        fun fromJson(o: JSONObject): AlertItem = AlertItem(
            o.optString("pid"), o.optString("t"), o.optString("b"), o.optLong("w"), o.optBoolean("low")
        )
    }
}
