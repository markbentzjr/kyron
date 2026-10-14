package com.kyronapp.kyron.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * LF-4 region model: what a "region" is, which ones Kyron knows about,
 * and which one is active.
 *
 * A region is one downloadable catalog pack (today: a US state). Alabama
 * is bundled with the app; Florida is the first downloadable pack. Every
 * other state is honestly "not covered yet" until a pack exists — the
 * Coverage screen never presents an uncovered state as an empty region.
 */
data class RegionInfo(
    val regionId: String,
    val state: String,
    val displayName: String,
    /** Regions.MODEL_SCORE (jurisdiction publishes a 0–100-style score) or
     *  Regions.MODEL_DISPOSITION (native outcome text only). */
    val scoreModel: String,
    /** True when the region's data ships inside the APK (no pack). */
    val bundled: Boolean,
    val centerLat: Double,
    val centerLng: Double,
    /** Where the region's pack manifest lives once published (LF-5 ops).
     *  Null = no downloadable pack exists for this region. */
    val manifestUrl: String? = null
)

object Regions {
    const val MODEL_SCORE = "SCORE_100"
    const val MODEL_DISPOSITION = "DISPOSITION"

    val ALABAMA = RegionInfo(
        regionId = "us-al", state = "AL", displayName = "Alabama",
        scoreModel = MODEL_SCORE, bundled = true,
        centerLat = 32.78, centerLng = -86.83
    )

    val FLORIDA = RegionInfo(
        regionId = "us-fl", state = "FL", displayName = "Florida",
        scoreModel = MODEL_DISPOSITION, bundled = false,
        centerLat = 28.63, centerLng = -81.71,
        manifestUrl = "https://markbentzjr.github.io/kyron/data/us-fl.manifest.json"
    )

    /** Regions with a real data source today. Everything else is uncovered. */
    val KNOWN: List<RegionInfo> = listOf(ALABAMA, FLORIDA)

    fun byId(regionId: String): RegionInfo? = KNOWN.firstOrNull { it.regionId == regionId }

    fun byState(state: String): RegionInfo? =
        KNOWN.firstOrNull { it.state.equals(state, ignoreCase = true) }

    fun regionIdForState(state: String): String = "us-" + state.lowercase()

    /** Friendly source label for sources the AL-only SourceRegistry doesn't know. */
    fun sourceDisplayName(source: String): String = when (source) {
        "FL-DBPR" -> "Florida DBPR (Dept. of Business & Professional Regulation)"
        else -> source
    }

    /** All 50 states, for the Coverage screen's truthful status list. */
    val US_STATES: List<Pair<String, String>> = listOf(
        "AL" to "Alabama", "AK" to "Alaska", "AZ" to "Arizona", "AR" to "Arkansas",
        "CA" to "California", "CO" to "Colorado", "CT" to "Connecticut", "DE" to "Delaware",
        "FL" to "Florida", "GA" to "Georgia", "HI" to "Hawaii", "ID" to "Idaho",
        "IL" to "Illinois", "IN" to "Indiana", "IA" to "Iowa", "KS" to "Kansas",
        "KY" to "Kentucky", "LA" to "Louisiana", "ME" to "Maine", "MD" to "Maryland",
        "MA" to "Massachusetts", "MI" to "Michigan", "MN" to "Minnesota", "MS" to "Mississippi",
        "MO" to "Missouri", "MT" to "Montana", "NE" to "Nebraska", "NV" to "Nevada",
        "NH" to "New Hampshire", "NJ" to "New Jersey", "NM" to "New Mexico", "NY" to "New York",
        "NC" to "North Carolina", "ND" to "North Dakota", "OH" to "Ohio", "OK" to "Oklahoma",
        "OR" to "Oregon", "PA" to "Pennsylvania", "RI" to "Rhode Island", "SC" to "South Carolina",
        "SD" to "South Dakota", "TN" to "Tennessee", "TX" to "Texas", "UT" to "Utah",
        "VT" to "Vermont", "VA" to "Virginia", "WA" to "Washington", "WV" to "West Virginia",
        "WI" to "Wisconsin", "WY" to "Wyoming"
    )

    // Rough state bounding boxes (minLat, maxLat, minLng, maxLng), used ONLY
    // to *propose* a state from a GPS fix on the Coverage screen — the user
    // always confirms, and a manual choice is never overridden. On overlap,
    // the smallest containing box wins.
    private val STATE_BOUNDS: Map<String, DoubleArray> = mapOf(
        "AL" to doubleArrayOf(30.14, 35.01, -88.47, -84.89),
        "AK" to doubleArrayOf(51.21, 71.35, -179.99, -129.98),
        "AZ" to doubleArrayOf(31.33, 37.00, -114.81, -109.05),
        "AR" to doubleArrayOf(33.00, 36.50, -94.62, -89.64),
        "CA" to doubleArrayOf(32.53, 42.01, -124.41, -114.13),
        "CO" to doubleArrayOf(36.99, 41.00, -109.06, -102.04),
        "CT" to doubleArrayOf(40.99, 42.05, -73.73, -71.79),
        "DE" to doubleArrayOf(38.45, 39.84, -75.79, -75.05),
        "FL" to doubleArrayOf(24.40, 31.00, -87.63, -79.81),
        "GA" to doubleArrayOf(30.36, 35.00, -85.61, -80.84),
        "HI" to doubleArrayOf(18.91, 22.24, -160.25, -154.81),
        "ID" to doubleArrayOf(41.99, 49.00, -117.24, -111.04),
        "IL" to doubleArrayOf(36.97, 42.51, -91.51, -87.53),
        "IN" to doubleArrayOf(37.77, 41.76, -88.10, -84.81),
        "IA" to doubleArrayOf(40.38, 43.50, -96.45, -91.20),
        "KS" to doubleArrayOf(36.99, 40.00, -102.05, -94.59),
        "KY" to doubleArrayOf(36.50, 39.30, -89.57, -81.96),
        "LA" to doubleArrayOf(28.93, 33.02, -94.04, -88.82),
        "ME" to doubleArrayOf(43.06, 47.46, -71.08, -66.95),
        "MD" to doubleArrayOf(37.89, 39.72, -79.49, -75.05),
        "MA" to doubleArrayOf(41.24, 42.73, -73.51, -69.93),
        "MI" to doubleArrayOf(41.70, 48.30, -90.42, -82.12),
        "MN" to doubleArrayOf(43.50, 49.38, -97.24, -89.57),
        "MS" to doubleArrayOf(30.10, 34.66, -91.66, -88.10),
        "MO" to doubleArrayOf(35.99, 40.62, -95.77, -89.38),
        "MT" to doubleArrayOf(44.36, 49.00, -116.05, -104.04),
        "NE" to doubleArrayOf(39.99, 43.00, -104.05, -95.31),
        "NV" to doubleArrayOf(35.00, 42.00, -120.01, -114.04),
        "NH" to doubleArrayOf(42.70, 45.31, -72.56, -70.71),
        "NJ" to doubleArrayOf(38.93, 41.36, -75.56, -73.89),
        "NM" to doubleArrayOf(31.33, 37.00, -109.05, -103.00),
        "NY" to doubleArrayOf(40.50, 45.02, -79.76, -71.86),
        "NC" to doubleArrayOf(33.84, 36.59, -84.32, -75.46),
        "ND" to doubleArrayOf(45.94, 49.00, -104.05, -97.09),
        "OH" to doubleArrayOf(38.40, 41.98, -84.82, -80.52),
        "OK" to doubleArrayOf(33.62, 37.00, -103.00, -94.43),
        "OR" to doubleArrayOf(41.99, 46.29, -124.57, -116.46),
        "PA" to doubleArrayOf(39.72, 42.27, -80.52, -74.69),
        "RI" to doubleArrayOf(41.32, 42.02, -71.86, -71.12),
        "SC" to doubleArrayOf(32.03, 35.22, -83.35, -78.57),
        "SD" to doubleArrayOf(42.48, 45.95, -104.06, -96.45),
        "TN" to doubleArrayOf(34.98, 36.68, -90.31, -81.65),
        "TX" to doubleArrayOf(25.84, 36.50, -106.65, -93.51),
        "UT" to doubleArrayOf(36.99, 42.00, -114.05, -109.04),
        "VT" to doubleArrayOf(42.73, 45.01, -73.44, -71.46),
        "VA" to doubleArrayOf(36.54, 39.47, -83.68, -75.24),
        "WA" to doubleArrayOf(45.54, 49.00, -124.73, -116.92),
        "WV" to doubleArrayOf(37.20, 40.64, -82.64, -77.72),
        "WI" to doubleArrayOf(42.49, 47.08, -92.89, -86.81),
        "WY" to doubleArrayOf(40.99, 45.01, -111.06, -104.05)
    )

    /** Best-guess USPS state for a coordinate, or null when no box contains it. */
    fun stateForPoint(lat: Double, lng: Double): String? {
        var best: String? = null
        var bestArea = Double.MAX_VALUE
        for ((state, b) in STATE_BOUNDS) {
            if (lat in b[0]..b[1] && lng in b[2]..b[3]) {
                val area = (b[1] - b[0]) * (b[3] - b[2])
                if (area < bestArea) { bestArea = area; best = state }
            }
        }
        return best
    }
}

/**
 * Which region is active, persisted as a DEVICE setting (SharedPreferences,
 * deliberately not in the backed-up user store: region choice is about
 * this device's downloads, and a manual choice must never be silently
 * overridden — GPS only ever proposes, see CoverageActivity).
 */
class RegionManager(context: Context) {

    private val sp = context.applicationContext
        .getSharedPreferences("kyron_regions", Context.MODE_PRIVATE)

    private val _activeRegion = MutableStateFlow(
        sp.getString(KEY_ACTIVE, Regions.ALABAMA.regionId) ?: Regions.ALABAMA.regionId
    )
    val activeRegion: StateFlow<String> = _activeRegion

    /** True once the user has picked a region by hand. A GPS proposal must
     *  still ask, and must never apply itself, when this is set. */
    var manualOverride: Boolean
        get() = sp.getBoolean(KEY_MANUAL, false)
        private set(v) = sp.edit().putBoolean(KEY_MANUAL, v).apply()

    fun activeRegionId(): String = _activeRegion.value

    fun activeInfo(): RegionInfo =
        Regions.byId(_activeRegion.value) ?: Regions.ALABAMA

    fun setActive(regionId: String, manual: Boolean) {
        if (Regions.byId(regionId) == null) return
        sp.edit().putString(KEY_ACTIVE, regionId).apply()
        if (manual) manualOverride = true
        _activeRegion.value = regionId
    }

    companion object {
        private const val KEY_ACTIVE = "active_region"
        private const val KEY_MANUAL = "region_manual_override"
    }
}
