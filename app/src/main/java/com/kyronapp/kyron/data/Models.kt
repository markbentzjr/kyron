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
    val violations: List<Violation> = emptyList()
) {
    fun toJson(): JSONObject = JSONObject()
        .put("s", score)
        .put("d", date)
        .put("t", type)
        .put("v", JSONArray().apply { violations.forEach { put(it.toJson()) } })

    companion object {
        fun fromJson(o: JSONObject): Inspection {
            val vs = mutableListOf<Violation>()
            val arr = o.optJSONArray("v")
            if (arr != null) for (i in 0 until arr.length()) vs += Violation.fromJson(arr.getJSONObject(i))
            return Inspection(o.optInt("s"), o.optString("d"), o.optString("t"), vs)
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
    val inspections: List<Inspection> = emptyList()
) {
    val bandLabel: String
        get() = when {
            score >= 95 -> "Excellent"
            score >= 85 -> "Good / Fair"
            else -> "Needs improvement"
        }

    /** Stable event key for "is this a new inspection?" checks. */
    val eventKey: String get() = "$date|$score"

    fun fullAddress(): String =
        listOf(address, city, "AL $zip").filter { it.isNotBlank() }.joinToString(", ")

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
        .put("insp", JSONArray().apply { inspections.forEach { put(it.toJson()) } })

    companion object {
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
                inspections = insps
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
