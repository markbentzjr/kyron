package com.kyronapp.kyron.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.ExploreState
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.Regions
import com.kyronapp.kyron.source.SourceRegistry
import com.kyronapp.kyron.data.WhySummary
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.osmdroid.events.DelayedMapListener
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

/**
 * Map (LF-3, Presentation Spec section 3): viewport-based loading with
 * grid clustering, replacing the old home-anchored scan-and-truncate-500.
 *
 *  - The catalog is queried by the VISIBLE bounding box (SQLite lat/lng
 *    index), never scanned whole; queries re-run on camera idle only.
 *  - Only places with a real, accepted address-level geocode are pinned
 *    (LF-1). Places without one stay in Browse/detail with address text —
 *    no centroid ever poses as a restaurant again.
 *  - At wide zooms, pins cluster into grid cells; a cluster badge shows
 *    the count and is colored by its WORST member's score band.
 *  - One tap on a pin opens the bottom-sheet place card (Spec 4.1 Peek);
 *    the Browse search (ExploreState) filters the map too — one query
 *    drives both surfaces.
 */
class MapFragment : Fragment() {

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var mapView: MapView? = null
    private var statusView: TextView? = null
    private var sheet: View? = null
    private var selected: Place? = null
    private var viewportJob: Job? = null
    private var currentFilter = ExploreState.current()
    private var filterRegionId: String? = null
    private val iconCache = HashMap<String, BitmapDrawable>()

    companion object {
        /** Street-level zoom at which clusters always split into pins. */
        private const val PIN_ZOOM = 14.5
        /** Hard overlay cap (Spec 3.1); clustering tightens before this bites. */
        private const val MAX_OVERLAYS = 400
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val v = inflater.inflate(R.layout.fragment_map, container, false)
        statusView = v.findViewById(R.id.map_status)
        sheet = v.findViewById(R.id.place_sheet)
        val mv = v.findViewById<MapView>(R.id.map)
        mapView = mv
        mv.setTileSource(TileSourceFactory.MAPNIK)
        mv.setMultiTouchControls(true)
        mv.controller.setZoom(11.0)
        mv.controller.setCenter(GeoPoint(app.prefs.homeLat, app.prefs.homeLng))
        mv.addMapListener(DelayedMapListener(object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean { refreshViewport(); return true }
            override fun onZoom(event: ZoomEvent?): Boolean { refreshViewport(); return true }
        }, 250L))

        v.findViewById<ImageButton>(R.id.sheet_close).setOnClickListener { hideSheet() }
        v.findViewById<View>(R.id.map_locate).setOnClickListener {
            mv.controller.animateTo(GeoPoint(app.prefs.homeLat, app.prefs.homeLng))
            mv.controller.setZoom(13.0)
        }
        v.findViewById<Button>(R.id.sheet_open).setOnClickListener {
            selected?.let { (activity as? MainActivity)?.openPlace(it.id) }
        }
        v.findViewById<Button>(R.id.sheet_fav).setOnClickListener {
            val p = selected ?: return@setOnClickListener
            val now = app.prefs.toggleFavorite(p.id)
            bindSheetFav(p)
            Toast.makeText(
                requireContext(),
                if (now) "Watching ${p.name} — you'll be alerted on new scores" else "Stopped watching ${p.name}",
                Toast.LENGTH_SHORT
            ).show()
        }

        scope.launch {
            ExploreState.query.collect { q ->
                currentFilter = q
                refreshViewport()
            }
        }
        // LF-4: the map is scoped to the active region. On a region
        // switch, recenter when the old center is outside the new region
        // (home presets stay valid data — they're just a point).
        scope.launch {
            var lastRegion: String? = null
            app.regions.activeRegion.collect { regionId ->
                if (lastRegion != null && lastRegion != regionId) {
                    val info = app.regions.activeInfo()
                    val c = mv.controller
                    val center = mv.mapCenter
                    val inRegion = center.latitude in (info.centerLat - 6)..(info.centerLat + 6) &&
                        center.longitude in (info.centerLng - 7)..(info.centerLng + 7)
                    if (!inRegion) {
                        val homeInRegion = app.prefs.homeLat in (info.centerLat - 6)..(info.centerLat + 6) &&
                            app.prefs.homeLng in (info.centerLng - 7)..(info.centerLng + 7)
                        if (homeInRegion) {
                            c.setCenter(GeoPoint(app.prefs.homeLat, app.prefs.homeLng))
                        } else {
                            c.setCenter(GeoPoint(info.centerLat, info.centerLng))
                        }
                        c.setZoom(8.0)
                    }
                    hideSheet()
                }
                lastRegion = regionId
                refreshViewport()
            }
        }
        scope.launch {
            app.repository.load()
            refreshViewport()
        }
        return v
    }

    // ------------------------------------------------------------- viewport

    private fun refreshViewport() {
        val mv = mapView ?: return
        val box = mv.boundingBox ?: return
        val zoom = mv.zoomLevelDouble
        viewportJob?.cancel()
        viewportJob = scope.launch {
            val places = app.repository.placesInBounds(
                box.latSouth, box.latNorth, box.lonWest, box.lonEast, limit = 6000,
                regionId = app.regions.activeRegionId()
            )
            // ExploreState is shared and region-blind: a county/band
            // chosen under another region must not filter this region's
            // map (it would read as an empty state). Browse republishes a
            // reset query when it binds the new region.
            val rid = app.regions.activeRegionId()
            if (rid != filterRegionId) {
                filterRegionId = rid
                currentFilter = currentFilter.copy(county = null, band = "All scores")
            }
            val filtered = applyFilter(places)
            render(filtered, zoom)
        }
    }

    /** The unified Explore query (Spec priority 1) filters the map too.
     *  Score bands only ever match places that HAVE a numeric score — a
     *  disposition region's NO_SCORE sentinel is not "below 85". */
    private fun applyFilter(places: List<Place>): List<Place> {
        val q = currentFilter
        // Workstream D / FIX5: the map's copy of the shared Explore query
        // must be apostrophe-insensitive like Browse search (CatalogDb) —
        // a "McDonalds" filter used to hide every "McDonald's" pin here
        // even though the pin itself was on the map.
        val text = com.kyronapp.kyron.data.db.CatalogDb.stripApostrophes(q.text.trim())
        fun field(s: String) = com.kyronapp.kyron.data.db.CatalogDb.stripApostrophes(s)
        return places.filter { p ->
            (q.county == null || p.county == q.county) &&
                (when (q.band) {
                    "Below 85" -> p.hasNumericScore && p.score < 85
                    "85–94" -> p.hasNumericScore && p.score in 85..94
                    "95+" -> p.hasNumericScore && p.score >= 95
                    else -> true
                }) &&
                (text.isEmpty() || field(p.name).contains(text, true) || field(p.city).contains(text, true) ||
                    field(p.address).contains(text, true) || p.zip.contains(text) || field(p.county).contains(text, true))
        }
    }

    private data class Cluster(val centerLat: Double, val centerLng: Double, val members: List<Place>)

    private fun render(places: List<Place>, zoom: Double) {
        val mv = mapView ?: return
        mv.overlays.removeAll(mv.overlays.filterIsInstance<Marker>())

        val showPins = zoom >= PIN_ZOOM || places.size <= 60
        var clusterCount = 0
        if (showPins) {
            for (p in places.take(MAX_OVERLAYS)) {
                mv.overlays.add(pinMarker(p))
            }
        } else {
            // Grid clustering over the visible bounds: 5 x 5 cells.
            val box = mv.boundingBox
            val latStep = (box.latNorth - box.latSouth) / 5.0
            val lngStep = (box.lonEast - box.lonWest) / 5.0
            val cells = HashMap<Pair<Int, Int>, MutableList<Place>>()
            for (p in places) {
                val lat = p.lat ?: continue
                val lng = p.lng ?: continue
                val key = (((lat - box.latSouth) / latStep).toInt().coerceIn(0, 4)) to
                    (((lng - box.lonWest) / lngStep).toInt().coerceIn(0, 4))
                cells.getOrPut(key) { mutableListOf() } += p
            }
            val clusters = cells.values.map { members ->
                Cluster(
                    members.mapNotNull { it.lat }.average(),
                    members.mapNotNull { it.lng }.average(),
                    members
                )
            }
            for (cluster in clusters.take(MAX_OVERLAYS)) {
                if (cluster.members.size == 1) {
                    mv.overlays.add(pinMarker(cluster.members[0]))
                } else {
                    clusterCount++
                    mv.overlays.add(clusterMarker(cluster))
                }
            }
        }

        val home = Marker(mv)
        home.id = "__home__"
        home.position = GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
        home.title = "Your area center — ${app.prefs.homeLabel}"
        mv.overlays.add(home)
        mv.invalidate()

        val filtered = currentFilter.text.isNotBlank() || currentFilter.county != null ||
            currentFilter.band != "All scores"
        val region = app.regions.activeInfo()
        statusView?.text = buildString {
            if (places.isEmpty()) {
                append("No places with verified locations in this view of ${region.displayName}. ")
                append("Places without a verified address aren't pinned — they're still in Browse with their address. ")
                if (region.regionId == "us-fl") {
                    append("Florida's addresses haven't been through the verification pass yet, so most Florida places are Browse-only for now.")
                }
            } else {
                if (showPins && places.size > MAX_OVERLAYS) {
                    append("Showing the first $MAX_OVERLAYS of ${places.size} places with verified locations in this view — zoom in to see the rest")
                } else {
                    append("${places.size} places with verified locations in this view")
                    if (clusterCount > 0) append(" (grouped into clusters — zoom in for individual places)")
                }
                append(". Every pin is the place's real, verified address; ")
                append("places without a verified location aren't pinned, but they're still in Browse with their address.")
            }
            if (filtered) append(" Your Browse search filter is applied here too.")
        }
    }

    // -------------------------------------------------------------- markers

    private fun bandColor(score: Int): Int = when {
        score >= 95 -> 0xFF2E9E4F.toInt()
        score >= 85 -> 0xFF7AB648.toInt()
        else -> 0xFFE8A13A.toInt()
    }

    /** Tone colors for native (non-numeric) results: good/warn/bad/neutral. */
    private fun toneColor(tone: Int): Int = when (tone) {
        1 -> 0xFF2E9E4F.toInt()
        2 -> 0xFFE8A13A.toInt()
        3 -> 0xFFD9534F.toInt()
        else -> 0xFF8A97A5.toInt()
    }

    private fun badgeIcon(key: String, lines: List<String>, colorScore: Int, big: Boolean): BitmapDrawable =
        badgeIconColored(
            key, lines, bandColor(colorScore),
            if (colorScore >= 85) 0xFFFFFFFF.toInt() else 0xFF1D2733.toInt(), big
        )

    private fun badgeIconColored(
        key: String, lines: List<String>, fillColor: Int, textColor: Int, big: Boolean
    ): BitmapDrawable {
        // Canonical key: the caller's key plus every input that determines
        // the rendering, so a key can never return a badge drawn for
        // different text, colors, or size (pass-2 hardening).
        val cacheKey = "$key|${lines.joinToString("/")}|$fillColor|$textColor|$big"
        iconCache[cacheKey]?.let { return it }
        val size = if (big) 120 else 96
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fillColor }
        canvas.drawCircle(size / 2f, size / 2f, size / 2f - 4f, fill)
        val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFFFFFFFF.toInt(); style = Paint.Style.STROKE; strokeWidth = 5f
        }
        canvas.drawCircle(size / 2f, size / 2f, size / 2f - 7f, ring)
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = textColor
            textAlign = Paint.Align.CENTER
            typeface = Typeface.DEFAULT_BOLD
        }
        if (lines.size == 1) {
            // Numbers are 1–3 chars at full size; word badges (native
            // results like "Warning") shrink to fit the circle.
            tp.textSize = when {
                lines[0].length <= 3 -> if (big) 40f else 42f
                lines[0].length <= 7 -> 26f
                else -> 20f
            }
            val y = size / 2f - (tp.descent() + tp.ascent()) / 2f
            canvas.drawText(lines[0], size / 2f, y, tp)
        } else {
            tp.textSize = 38f
            var y = size / 2f - (tp.descent() + tp.ascent()) / 2f - 18f
            canvas.drawText(lines[0], size / 2f, y, tp)
            tp.textSize = 26f
            y += 32f
            canvas.drawText(lines[1], size / 2f, y, tp)
        }
        val drawable = BitmapDrawable(resources, bmp)
        iconCache[cacheKey] = drawable
        return drawable
    }

    private fun pinMarker(p: Place): Marker {
        val mv = mapView!!
        val marker = Marker(mv)
        marker.id = p.id
        marker.position = GeoPoint(p.lat!!, p.lng!!)
        marker.icon = if (p.hasNumericScore) {
            badgeIcon("pin${p.score}", listOf(p.score.toString()), p.score, big = false)
        } else {
            // Disposition regions pin the native result's short label,
            // colored by its tone — never an invented number.
            badgeIconColored(
                "pinres${p.badgeText}_${p.resultTone}", listOf(p.badgeText),
                toneColor(p.resultTone), 0xFFFFFFFF.toInt(), big = false
            )
        }
        marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        marker.title = p.name
        marker.setOnMarkerClickListener { _, _ ->
            showSheet(p)
            true
        }
        return marker
    }

    private fun clusterMarker(cluster: Cluster): Marker {
        val mv = mapView!!
        val scored = cluster.members.filter { it.hasNumericScore }
        val worst = if (scored.isNotEmpty()) scored.minOf { it.score } else Place.NO_SCORE
        val marker = Marker(mv)
        marker.id = "__cluster__"
        marker.position = GeoPoint(cluster.centerLat, cluster.centerLng)
        marker.icon = if (worst != Place.NO_SCORE) {
            badgeIcon(
                "clu${cluster.members.size}_$worst",
                listOf(cluster.members.size.toString(), "low $worst"),
                worst, big = true
            )
        } else {
            // No numeric scores in this cluster (disposition region):
            // the badge is the count alone, in neutral gray.
            badgeIconColored(
                "clu${cluster.members.size}_res", listOf(cluster.members.size.toString()),
                toneColor(0), 0xFFFFFFFF.toInt(), big = true
            )
        }
        marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        marker.title = if (worst != Place.NO_SCORE) {
            "${cluster.members.size} places — lowest score $worst"
        } else {
            "${cluster.members.size} places"
        }
        marker.setOnMarkerClickListener { _, _ ->
            // Zoom is the drill-down (Spec 3.2): animate into the cluster.
            mv.controller.animateTo(GeoPoint(cluster.centerLat, cluster.centerLng))
            mv.controller.setZoom(mv.zoomLevelDouble + 2.0)
            true
        }
        return marker
    }

    // ---------------------------------------------------------------- sheet

    private fun showSheet(p: Place) {
        selected = p
        val s = sheet ?: return
        s.visibility = View.VISIBLE
        val root = view ?: return
        val badge = root.findViewById<TextView>(R.id.sheet_badge)
        badge.text = p.badgeText
        // Word badges (native results) need smaller type than numbers.
        badge.textSize = if (p.hasNumericScore) 20f else 10f
        badge.setBackgroundResource(
            when {
                p.hasNumericScore && p.score >= 95 -> R.drawable.score_green
                p.hasNumericScore && p.score >= 85 -> R.drawable.score_lime
                p.hasNumericScore -> R.drawable.score_amber
                p.resultTone == 1 -> R.drawable.score_green
                p.resultTone == 2 -> R.drawable.score_amber
                p.resultTone == 3 -> R.drawable.score_red
                else -> R.drawable.score_gray
            }
        )
        val sourceName = SourceRegistry.byId(p.source)?.displayName
            ?: Regions.sourceDisplayName(p.source)
        root.findViewById<TextView>(R.id.sheet_name).text = p.name
        root.findViewById<TextView>(R.id.sheet_meta).text = buildString {
            append(p.bandLabel)
            if (p.date.isNotBlank()) append(" · inspected ${p.date}")
            append(" · ${sourceName}")
        }
        root.findViewById<TextView>(R.id.sheet_address).text = p.fullAddress()
        val why = p.inspections.firstOrNull()
            ?.takeIf { it.violations.isNotEmpty() && p.hasNumericScore }
            ?.let { WhySummary.summarize(it) }
        root.findViewById<TextView>(R.id.sheet_why).text = when {
            why != null -> "Why this score: $why"
            !p.hasNumericScore && p.nativeResult.isNotBlank() ->
                "Latest result: ${p.nativeResult}${if (p.date.isNotBlank()) " (${p.date})" else ""} — this jurisdiction publishes outcomes, not scores."
            !p.hasNumericScore -> "No inspection on file yet for this place."
            p.source == "JCDH" -> "Tap Full details to load the inspection findings for this place."
            else -> "Score and date only — $sourceName publishes scores without violation detail."
        }
        bindSheetFav(p)
    }

    private fun bindSheetFav(p: Place) {
        val fav = view?.findViewById<Button>(R.id.sheet_fav) ?: return
        val watching = app.prefs.favorites.contains(p.id)
        fav.text = if (watching) "Watching" else "Watch"
        // Classic compound-drawable star (the MaterialButton icon slot's
        // replacement): filled star while watching, outline otherwise.
        val icon = ContextCompat.getDrawable(
            fav.context, if (watching) R.drawable.ic_star else R.drawable.ic_star_border
        )
        fav.setCompoundDrawablesWithIntrinsicBounds(icon, null, null, null)
    }

    private fun hideSheet() {
        sheet?.visibility = View.GONE
        selected = null
    }

    override fun onResume() {
        super.onResume()
        mapView?.onResume()
        refreshViewport() // area center / filters may have changed while hidden
    }

    override fun onPause() {
        mapView?.onPause()
        super.onPause()
    }

    override fun onDestroyView() {
        scope.cancel()
        mapView?.onDetach()
        mapView = null
        super.onDestroyView()
    }
}
