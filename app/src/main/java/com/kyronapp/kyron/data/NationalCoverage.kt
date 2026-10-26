package com.kyronapp.kyron.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * LF-N (nationwide expansion): the data-driven national coverage registry.
 *
 * Kyron's Coverage screen used to know only three regions (Regions.KNOWN).
 * This registry instead describes EVERY US state — plus
 * Washington, D.C. as a separate federal-district jurisdiction — from a
 * single JSON document bundled in the APK:
 * `assets/coverage/us_national_registry.json`.
 *
 * The registry is DATA, not scattered state conditionals:
 *  - each jurisdiction carries its own result model (scores where higher
 *    is better, penalty points where lower is better, letter grades,
 *    pass/fail, violations-only, dispositions );
 *  - each jurisdiction lists its official source(s) with access method,
 *    coverage, exclusions, verification date, and an honest IMPLEMENTATION
 *    status (see [Source]);
 *  - pack availability, source health, and official-link-only fallback are
 *    kept as DISTINCT fields — a state with a verified source but no
 *    download and a state that is link-only are never conflated.
 *
 *
 * The registry is bounded and small: parsing it is a one-shot at first
 * use, nothing here loads restaurant data into memory.
 */
object NationalCoverage {

    // ------------------------------------------------ result model model

    /**
     * How a jurisdiction publishes inspection results. One presentation
     * model per jurisdiction; a source may additionally publish a
     * secondary form (noted per source).
     */
    const val MODEL_SCORE_100_HIGH = "SCORE_100_HIGH" // higher is better
    const val MODEL_PENALTY_LOW = "PENALTY_LOW" // demerit points; LOWER is better
    const val MODEL_LETTER_GRADE = "LETTER_GRADE" // A/B/C/…
    const val MODEL_PASS_FAIL = "PASS_FAIL" // pass / pass-with-conditions / fail
    const val MODEL_DISPOSITION = "DISPOSITION" // native outcome text (FL DBPR)
    const val MODEL_VIOLATIONS_ONLY = "VIOLATIONS_ONLY" // no overall result at all
    /**
     * LF-N hardening: an explicitly UNKNOWN model. Used when a place's
     * source cannot be resolved to a registry source/jurisdiction, or the
     * registry itself hasn't been read yet. UNKNOWN silently degrades to
     * NOTHING: no score bands, no score sorts, no threshold alerts, and
     * the UI says so — it must NEVER silently default to Alabama's
     * 0–100 scale.
     */
    const val MODEL_UNKNOWN = "UNKNOWN"

    /** Presentation-active models that publish a numeric value. */
    fun isNumeric(model: String): Boolean =
        model == MODEL_SCORE_100_HIGH || model == MODEL_PENALTY_LOW

    /** True when the active region hides score-band chips and score sorts. */
    fun hidesScoreFilters(model: String): Boolean =
        model != MODEL_SCORE_100_HIGH && model != MODEL_PENALTY_LOW

    /**
     * Numeric band bounds (min to max; null = unbounded) for a band label
     * under [model]. The SQL layer excludes the NO_SCORE sentinel (-1)
     * whenever a band is applied, and any in-memory check must agree.
     */
    fun bandRange(model: String, band: String): Pair<Int?, Int?> = when (model) {
        MODEL_SCORE_100_HIGH -> when (band) {
            "Below 85" -> null to 84
            "85–94" -> 85 to 94
            "95+" -> 95 to null
            else -> null to null
        }
        MODEL_PENALTY_LOW -> when (band) {
            // Penalty points build up: a low count is the GOOD side.
            // Cut-offs follow NYC DOHMH grades: A = 0–13, B = 14–27, C = 28+.
            "0–13" -> 0 to 13
            "14–27" -> 14 to 27
            "28+" -> 28 to null
            else -> null to null
        }
        else -> null to null
    }

    /**
     * In-memory mirror of bandRange, used by the map's shared query
     * filter. A place with no numeric score (NO_SCORE) never matches a
     * specific band in ANY model — missing data is not a result.
     *
     * LF-N hardening: UNKNOWN is NOT "match anything". A model-specific
     * band label ("85–94", "28+") carries scale semantics the unknown
     * model cannot interpret, so under UNKNOWN it must admit NOTHING —
     * otherwise a 0–100 band silently swallows penalty points the way
     * the old hard-coded defaults did. Only the scale-free "All scores"
     * label (and empty band strings) passes through.
     */
    fun bandMatches(model: String, band: String, score: Int): Boolean {
        if (model == MODEL_UNKNOWN) return band == "All scores" || band.isBlank()
        val (min, max) = bandRange(model, band)
        if (min == null && max == null) return true
        if (score < 0) return false
        return (min == null || score >= min) && (max == null || score <= max)
    }

    /**
     * True when numeric THRESHOLD alerts make sense in this model
     * ("score < threshold"). Only a higher-is-better 0–100 scale
     * (Alabama and its peers) carries Kyron's threshold semantics;
     * a penalty scale or letter grade must never be compared against
     * an Alabama threshold.
     */
    fun supportsThresholdAlerts(model: String): Boolean = model == MODEL_SCORE_100_HIGH

    /** Band set for a model, in the FIXED label vocabulary shared by
     *  Browse and Map. Returns an empty list when the model has no
     *  numeric bands (chips hidden). */
    fun bands(model: String): List<String> = when (model) {
        MODEL_SCORE_100_HIGH -> listOf("All scores", "Below 85", "85–94", "95+")
        MODEL_PENALTY_LOW -> listOf("All scores", "0–13", "14–27", "28+")
        else -> emptyList()
    }

    /**
     * Screen-order sort choices. Score sorts only exist for numeric
     * models; for a PENALTY model "Worst first" means HIGHEST penalty.
     */
    fun scoreSortLabel(model: String): String =
        if (model == MODEL_PENALTY_LOW) "Most penalty points first" else "Worst first"

    /**
     * Pin/badge tone (map + sheet): 1 = good, 2 = warn, 3 = bad, 0/other =
     * neutral. Score-direction aware: on a 0–100 scale HIGH is good; on a
     * penalty scale HIGH is BAD. Non-numeric models have no numeric tone.
     */
    fun numericTone(model: String, score: Int): Int = when {
        score < 0 -> 0
        model == MODEL_SCORE_100_HIGH -> when {
            score >= 95 -> 1
            score >= 85 -> 2
            else -> 3
        }
        model == MODEL_PENALTY_LOW -> when {
            score <= 13 -> 1
            score <= 27 -> 2
            else -> 3
        }
        else -> 0
    }

    /**
     * SQL ORDER BY for a sort label under [model]. Extracted so tests can
     * verify the direction mapping directly; keep in lockstep with
     * PlaceRepository.searchPlaces.
     */
    fun orderByFor(model: String, sort: String?): String = when {
        sort == "Worst first" || sort == "Most penalty points first" ->
            if (model == MODEL_PENALTY_LOW) "score DESC, name_lc ASC" else "score ASC, name_lc ASC"
        sort == "Best first" || sort == "Fewest penalty points first" ->
            if (model == MODEL_PENALTY_LOW) "score ASC, name_lc ASC" else "score DESC, name_lc ASC"
        sort == "Most recent" -> "date_key DESC, name_lc ASC"
        sort == "Name A–Z" -> "name_lc ASC"
        else -> "score ASC, name_lc ASC"
    }

    /** A human explanation of what results in this model mean. */
    fun legend(model: String): String = when (model) {
        MODEL_SCORE_100_HIGH ->
            "Scores are the jurisdiction's own 0–100 inspection scores; higher is better."
        MODEL_PENALTY_LOW ->
            "Numbers are demerit/penalty points from the jurisdiction's own reports; LOWER is better."
        MODEL_LETTER_GRADE ->
            "This jurisdiction publishes letter grades, not numeric scores."
        MODEL_PASS_FAIL ->
            "This jurisdiction publishes pass / pass-with-conditions / fail outcomes, not numeric scores."
        MODEL_DISPOSITION ->
            "This jurisdiction publishes inspection outcomes (e.g. met standards, warning, closure), not scores."
        MODEL_VIOLATIONS_ONLY ->
            "This jurisdiction publishes individual violations without an overall result."
        MODEL_UNKNOWN ->
            "This jurisdiction's result scale is not yet resolved — scores shown are the raw source record; no bands, sorts, or threshold alerts apply."
        else -> "This jurisdiction publishes its own native inspection results."
    }

    // -------------------------------------------------- pack availability

    /**
     * Pack DOWNLOAD state — deliberately distinct from [Jurisdiction.packStatus]
     * ("publication declared") and packHostStatus ("host health"):
     *  DOWNLOADABLE_VERIFIED: the expedited manifest/artifact was fetched and
     *      its bytes verified against the pack metadata — shown as installable.
     *  DECLARED_ONLY: the registry records a publication claim, but the
     *      artifact could NOT be verified downloadable (e.g. host 404). The
     *      Coverage screen must NOT offer a working download.
     *  STAGED_LOCAL: pack built and validated locally, not published — never
     *      user-downloadable.
     *  NONE: no pack at all.
     */
    const val AVAIL_DOWNLOADABLE = "downloadable-verified"
    const val AVAIL_DECLARED_ONLY = "declared-only"
    const val AVAIL_STAGED_LOCAL = "staged-local"
    const val AVAIL_NONE = "none"

    fun downloadStateOf(jur: Jurisdiction?): String = jur?.packAvailability ?: AVAIL_NONE

    /** Statuses whose packs PackManager may install (registry-derived).
     *  A source-verified state (pack_status "none") is NEVER pack-installable. */
    fun packInstallable(jur: Jurisdiction?): Boolean = jur != null &&
        jur.packStatus in setOf("bundled", "published", "built")

    // -------------------------------------------------------- data types

    /** One official publication the registry knows about. */
    data class Source(
        /** Stable source id, parent-state namespaced ("al-jcdh"). */
        val id: String,
        /** The inspecting agency in its own words. */
        val agency: String,
        /** Exact geographic scope: "Statewide", "Jefferson County", "King County", …. */
        val coverage: String,
        /** Access method: "live-sync", "html", "bulk-csv", "api", "pdf", "official-link-only". */
        val access: String,
        /** Official website / portal (verbatim from the agency). */
        val website: String,
        /** Violation detail: "full", "partial", or "none". */
        val violations: String,
        /** History depth: "latest-only", "some-history", or "full-history". */
        val history: String,
        /** Native result this source publishes (may differ from the region model). */
        val resultModel: String,
        /** Implementation status — see the constants below. */
        val status: String,
        /** Last source verification date (ISO), or "" when unverified. */
        val verified: String,
        /** Human-readable known blocker, or "". */
        val blocker: String,
        /** Access restrictions / attribution / redistribution notes, or "". */
        val restrictions: String,
        /** Refresh method and cadence, or "". */
        val refresh: String,
        /** Where refreshed data last succeeded, or "". NOT a health claim. */
        val lastRefresh: String,
        /** Free-text notes. */
        val notes: String
    )

    // Honest, mutually distinct implementation statuses.
    //  INTEGRATED: data ships today (bundled seed and/or live sync).
    //  PACK_BUILT: verified ingestion -> validated pack artifact built;
    //              publication state carried separately in [Region.packHostStatus].
    //  SOURCE_VERIFIED: official endpoint verified reachable with public
    //              data; no ingestion pipeline yet.
    //  OFFICIAL_LINK_ONLY: official portal known; no integration and
    //              (yet) no verified reproducible access. NEVER counts as
    //              restaurant data.
    //  BLOCKED:    integration attempted or considered; a named blocker
    //              (access restriction, upstream errors) prevents it.
    const val STATUS_INTEGRATED = "integrated"
    const val STATUS_PACK_BUILT = "pack-built"
    const val STATUS_SOURCE_VERIFIED = "source-verified"
    const val STATUS_OFFICIAL_LINK_ONLY = "official-link-only"
    const val STATUS_BLOCKED = "blocked"

    /** One US state (or D.C.) — the coverage unit shown on the Coverage screen. */
    data class Jurisdiction(
        /** Kyron region id ("us-al") or "us-dc" for the District. */
        val regionId: String,
        /** USPS code, or "DC". */
        val state: String,
        /** Display name. */
        val name: String,
        /** "state" or "federal-district". */
        val type: String,
        /** The jurisdiction's PRIMARY result model. */
        val resultModel: String,
        /** Every known official publication the registry tracks. */
        val sources: List<Source>,
        /** Pack status: "bundled", "published", "built", or "none". */
        val packStatus: String,
        /** Pack manifest URL when a published pack exists (FL/GA today). */
        val packManifestUrl: String?,
        /** Pack download state — see the AVAIL_* constants. "declared-only"
         *  must never earn a working download button. */
        val packAvailability: String,
        /** Somewhat the artifact was last VERIFIED (download fetched and
         *  hash-checked, or the local pack validated at build time), "" = never. */
        val artifactVerified: String,
        /** Last check of the pack host: "reachable", "unreachable-404", "unreachable", "not-published", or "" (never checked). */
        val packHostStatus: String,
        /** When the pack host was last checked (ISO), or "". */
        val packHostChecked: String,
        /** Coarse centroid (registry data, used only for anchor-level map
         *  defaults when synthesizing a RegionInfo). */
        val centerLat: Double?,
        val centerLng: Double?
    )

    // ------------------------------------------------------------ loading

    @Volatile private var cache: List<Jurisdiction>? = null

    /**
     * Parse the bundled registry. Results are cached; the registry is a
     * tiny bounded document, and every screen reads the parsed list.
     * Throws nothing: a damaged asset degrades to an empty registry and
     * the Coverage screen falls back to Regions.KNOWN rendering.
     */
    fun load(context: Context): List<Jurisdiction> {
        cache?.let { return it }
        val parsed = runCatching {
            val text = try {
                context.assets.open("coverage/us_national_registry.json")
                    .bufferedReader().use { it.readText() }
            } catch (missing: java.io.FileNotFoundException) {
                // Assets first. Test rigs (Robolectric) don't always mount the
                // staged assets directory on the real AssetManager, and the
                // sandbox classloader can't see rig classpath entries either —
                // so rigs hand the registry's absolute file path via
                // -Dkyron.registry.file=... A release build always succeeds on
                // the assets branch, so this fallback cannot mask a packaging
                // bug in production.
                val path = System.getProperty("kyron.registry.file")
                if (path == null) throw missing
                java.io.File(path).readText()
            }
            parse(JSONObject(text))
        }.getOrDefault(emptyList())
        cache = parsed
        return parsed
    }

    /** Reset the cache (tests). */
    fun resetForTests() { cache = null }

    /**
     * The registry WITHOUT needing a Context (PackManager / RegionManager
     * call sites). Returns null if the loader never ran in this process;
     * those call sites fall back to Regions.KNOWN behavior.
     */
    fun cached(): List<Jurisdiction>? = cache

    internal fun parse(root: JSONObject): List<Jurisdiction> {
        val arr = root.optJSONArray("jurisdictions") ?: JSONArray()
        val out = mutableListOf<Jurisdiction>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val sources = mutableListOf<Source>()
            val srcArr = o.optJSONArray("sources") ?: JSONArray()
            for (s in 0 until srcArr.length()) {
                val so = srcArr.getJSONObject(s)
                sources += Source(
                    id = so.optString("id"),
                    agency = so.optString("agency"),
                    coverage = so.optString("coverage", "Statewide"),
                    access = so.optString("access", "official-link-only"),
                    website = so.optString("website"),
                    violations = so.optString("violations", "none"),
                    history = so.optString("history", "latest-only"),
                    resultModel = so.optString("result_model", ""),
                    status = so.optString("status", STATUS_OFFICIAL_LINK_ONLY),
                    verified = so.optString("verified", ""),
                    blocker = so.optString("blocker", ""),
                    restrictions = so.optString("restrictions", ""),
                    refresh = so.optString("refresh", ""),
                    lastRefresh = so.optString("last_refresh", ""),
                    notes = so.optString("notes", "")
                )
            }
            out += Jurisdiction(
                regionId = o.optString("regionId"),
                state = o.optString("state"),
                name = o.optString("name"),
                type = o.optString("type", "state"),
                resultModel = o.optString("result_model", MODEL_DISPOSITION),
                sources = sources,
                packStatus = o.optString("pack_status", "none"),
                // NB: explicit JSON null ("pack_manifest_url": null) makes
                // optString return the STRING "null" — strip it too, so a
                // not-published region really yields a null manifest URL.
                packManifestUrl = o.optString("pack_manifest_url", "")
                    .takeUnless { it.isBlank() || it == "null" },
                packAvailability = o.optString("pack_availability", AVAIL_NONE),
                artifactVerified = o.optString("artifact_verified", ""),
                packHostStatus = o.optString("pack_host_status", ""),
                packHostChecked = o.optString("pack_host_checked", ""),
                centerLat = if (o.has("center")) o.optJSONObject("center")?.optDouble("lat") else null,
                centerLng = if (o.has("center")) o.optJSONObject("center")?.optDouble("lng") else null
            )
        }
        return out
    }

    // ------------------------------------------------------------ lookup

    fun byState(states: List<Jurisdiction>, stateCode: String): Jurisdiction? =
        states.firstOrNull { it.state.equals(stateCode, ignoreCase = true) }

    fun byRegionId(states: List<Jurisdiction>, regionId: String): Jurisdiction? =
        states.firstOrNull { it.regionId == regionId }

    // ------------------------------------------- source-level model lookup

    /** Normalized ("alphanumenic") key: uppercase, strip non-A-Z0-9. */
    private fun normKey(v: String): String =
        v.uppercase().filter { it in 'A'..'Z' || it in '0'..'9' }

    /**
     * Resolve the result model a PLACE must be read under at SOURCE level:
     *  1. a registry source whose normalized id matches this place's source
     *     (registry "al-jcdh" ↔ stored source "JCDH"), under that source's
     *     own result model;
     *  2. else the state/jurisdiction's primary model — an intra-state
     *     model may differ per source (NYC scores 0–100; Boston passes/
     *     fails; a state can mix);
     *  3. else MODEL_UNKNOWN — NEVER silently Alabama's 0–100 scale.
     */
    fun modelForPlace(states: List<Jurisdiction>, place: Place?): String {
        if (place == null) return MODEL_UNKNOWN
        val jur = byState(states, place.state) ?: return MODEL_UNKNOWN
        val pKey = normKey(place.source)
        jur.sources.firstOrNull { normKey(it.id.removePrefix("${jur.state.lowercase()}-")) == pKey
            || normKey(it.id) == pKey }?.let { return it.resultModel.ifBlank { jur.resultModel } }
        return jur.resultModel
    }

    /** Per-source resolution used by search/alert paths: the model under
     *  which a given region+source id publishes results (fallback:
     *  jurisdiction model; missing jurisdiction: UNKNOWN). */
    fun modelForSource(states: List<Jurisdiction>, regionId: String, sourceId: String?): String {
        val jur = byRegionId(states, regionId) ?: return MODEL_UNKNOWN
        if (!sourceId.isNullOrBlank()) {
            val sKey = normKey(sourceId)
            jur.sources.firstOrNull { normKey(it.id) == sKey
                || normKey(it.id.removePrefix("${jur.state.lowercase()}-")) == sKey }
                ?.let { return it.resultModel.ifBlank { jur.resultModel } }
        }
        return jur.resultModel
    }

    /** The 50 states, registry order, D.C. excluded (it is a separate row). */
    fun statesOnly(all: List<Jurisdiction>): List<Jurisdiction> =
        all.filter { it.type == "state" }
}
