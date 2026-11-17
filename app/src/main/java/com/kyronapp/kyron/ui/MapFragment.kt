package com.kyronapp.kyron.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.os.Bundle
import android.os.SystemClock
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
import com.kyronapp.kyron.data.NationalCoverage
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
    private var viewportEmpty = false
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
        // Esri World Light Gray Canvas — flat, desaturated basemap that
        // keeps score-colored pills as the visual focus (MAPNIK's dense
        // colors fight the markers). Free, key-free; Esri orders tile
        // URLs z/y/x unlike osmdroid's z/x/y, hence YXTileSource.
        mv.setTileSource(YXTileSource(
            "Esri.LightGrayCanvas", 0, 19, 256, "",
            arrayOf(
                "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/"
            ),
            "Esri, HERE, Garmin, © OpenStreetMap contributors"
        ))
        mv.setMultiTouchControls(true)
        // The dedicated +/− FABs replace osmdroid's transient built-ins.
        mv.zoomController.setVisibility(
            org.osmdroid.views.CustomZoomButtonsController.Visibility.NEVER
        )
        // Initial camera: home point when it sits inside the ACTIVE region;
        // otherwise anchor on the region itself (a region may have switched
        // while this fragment was not alive, e.g. a Coverage download).
        val initInfo = app.regions.activeInfo()
        val homeInInit = app.prefs.homeLat in (initInfo.centerLat - 6)..(initInfo.centerLat + 6) &&
            app.prefs.homeLng in (initInfo.centerLng - 7)..(initInfo.centerLng + 7)
        mv.controller.setZoom(if (homeInInit) 11.0 else 8.0)
        mv.controller.setCenter(
            if (homeInInit) GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
            else GeoPoint(initInfo.centerLat, initInfo.centerLng)
        )
        mv.overlays.add(0, PulseOverlay(mv) {
            GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
        })
        mv.addMapListener(DelayedMapListener(object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean { refreshViewport(); return true }
            override fun onZoom(event: ZoomEvent?): Boolean { refreshViewport(); return true }
        }, 250L))

        // Tap on empty map (not a pin) dismisses the place card.
        mv.overlays.add(0, org.osmdroid.views.overlay.MapEventsOverlay(
            object : org.osmdroid.events.MapEventsReceiver {
                override fun singleTapConfirmedHelper(p: GeoPoint?): Boolean {
                    if (sheet?.visibility == View.VISIBLE) { hideSheet(); return true }
                    return false
                }
                override fun longPressHelper(p: GeoPoint?): Boolean = false
            }
        ))

        v.findViewById<ImageButton>(R.id.sheet_close).setOnClickListener { hideSheet() }
        v.findViewById<View>(R.id.map_locate).setOnClickListener {
            val info = app.regions.activeInfo()
            val homeInRegion = app.prefs.homeLat in (info.centerLat - 6)..(info.centerLat + 6) &&
                app.prefs.homeLng in (info.centerLng - 7)..(info.centerLng + 7)
            mv.controller.animateTo(
                if (homeInRegion) GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
                else GeoPoint(info.centerLat, info.centerLng)
            )
            mv.controller.setZoom(13.0)
        }
        v.findViewById<View>(R.id.map_zoom_in).setOnClickListener {
            mv.controller.zoomIn()
        }
        v.findViewById<View>(R.id.map_zoom_out).setOnClickListener {
            mv.controller.zoomOut()
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

        // FAB column + status pill entrance — staggered rise so the
        // controls feel like they arrive, not pop.
        listOf(R.id.map_zoom_in, R.id.map_zoom_out, R.id.map_locate)
            .forEachIndexed { i, id ->
                v.findViewById<View>(id)?.let { fab ->
                    fab.alpha = 0f
                    fab.translationY = 40f
                    fab.scaleX = 0.6f; fab.scaleY = 0.6f
                    fab.animate().alpha(1f).translationY(0f)
                        .scaleX(1f).scaleY(1f)
                        .setStartDelay(120L + i * 70L)
                        .setDuration(340)
                        .setInterpolator(
                            android.view.animation.OvershootInterpolator(1.8f)
                        ).start()
                }
            }
        statusView?.let { sv ->
            // Empty state → the pill is a door into Browse, where the same
            // places are always listed even without mappable coordinates.
            sv.setOnClickListener {
                if (viewportEmpty) (activity as? MainActivity)?.selectTab(1)
            }
            sv.translationY = -sv.height.toFloat() - 24f
            sv.alpha = 0f
            sv.animate().translationY(0f).alpha(1f)
                .setStartDelay(80).setDuration(300)
                .setInterpolator(android.view.animation.DecelerateInterpolator())
                .start()
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
                    // Recentre unless the camera already sits inside the new
                    // region. The box must be tight — ~1 viewport at zoom 8 —
                    // because neighbouring regions' centres are only ~3° apart;
                    // the old ±6/±7 box let a Mississippi view pass as "in
                    // Alabama", leaving the map on the wrong state entirely.
                    val inRegion = center.latitude in (info.centerLat - 1.5)..(info.centerLat + 1.5) &&
                        center.longitude in (info.centerLng - 1.5)..(info.centerLng + 1.5)
                    if (!inRegion) {
                        val homeInRegion = app.prefs.homeLat in (info.centerLat - 6)..(info.centerLat + 6) &&
                            app.prefs.homeLng in (info.centerLng - 7)..(info.centerLng + 7)
                        val target = if (homeInRegion)
                            GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
                        else
                            GeoPoint(info.centerLat, info.centerLng)
                        c.setZoom(8.0)
                        c.animateTo(target)
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
     *  LF-N: score bands are interpreted in the ACTIVE REGION's own
     *  result model — a penalty-scale region gets demerit ranges, a
     *  disposition region gets no numeric bands at all, and the
     *  NO_SCORE sentinel never falls into a band in any model. */
    private fun applyFilter(places: List<Place>): List<Place> {
        val q = currentFilter
        // LF-N hardening: bands resolve in the region's registry model
        // (per-source semantics live in the registry), never from the
        // legacy two-value mapping alone.
        val states = com.kyronapp.kyron.data.NationalCoverage.cached()
            ?: runCatching {
                com.kyronapp.kyron.data.NationalCoverage.load(requireContext())
            }.getOrDefault(emptyList())
        val model = com.kyronapp.kyron.data.NationalCoverage
            .byRegionId(states, app.regions.activeRegionId())?.resultModel
            ?: Regions.nationalModel(app.regions.activeInfo())
        // Workstream D / FIX5: the map's copy of the shared Explore query
        // must be apostrophe-insensitive like Browse search (CatalogDb) —
        // a "McDonalds" filter used to hide every "McDonald's" pin here
        // even though the pin itself was on the map.
        val text = com.kyronapp.kyron.data.db.CatalogDb.stripApostrophes(q.text.trim())
        fun field(s: String) = com.kyronapp.kyron.data.db.CatalogDb.stripApostrophes(s)
        return places.filter { p ->
            (q.county == null || p.county == q.county) &&
                NationalCoverage.bandMatches(model, q.band, p.score) &&
                (text.isEmpty() || field(p.name).contains(text, true) || field(p.city).contains(text, true) ||
                    field(p.address).contains(text, true) || p.zip.contains(text) || field(p.county).contains(text, true))
        }
    }

    private data class Cluster(val centerLat: Double, val centerLng: Double, val members: List<Place>)

    private fun render(places: List<Place>, zoom: Double) {
        val mv = mapView ?: return
        mv.overlays.removeAll(mv.overlays.filterIsInstance<Marker>())
        selectedMarker = null

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

        // Home marker sits at the BOTTOM of the overlay stack (index 0)
        // so place pins always draw above it; its pulse ring is drawn
        // beneath everything by PulseOverlay (index 0 of the stack).
        val home = Marker(mv)
        home.id = "__home__"
        home.position = GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
        home.title = "Your area center — ${app.prefs.homeLabel}"
        home.icon = homeDotIcon()
        home.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
        mv.overlays.add(0, home)

        // Pop-in: pins/clusters stagger-fade in so fresh renders read
        // as alive rather than appearing all at once.
        animateMarkersIn(mv)

        // Re-highlight the selected place if its pin survived the re-render.
        selected?.let { sel ->
            mv.overlays.filterIsInstance<Marker>()
                .firstOrNull { it.id == sel.id }
                ?.let { m ->
                    m.relatedObject = sel
                    selectedMarker = m
                    m.icon = pillIcon(
                        "pin",
                        if (sel.hasNumericScore) sel.score.toString() else sel.badgeText,
                        pinFill(sel), big = false, selected = true
                    )
                }
        }
        mv.invalidate()

        val filtered = currentFilter.text.isNotBlank() || currentFilter.county != null ||
            currentFilter.band != "All scores"
        val region = app.regions.activeInfo()
        val newStatus = buildString {
            if (places.isEmpty()) {
                append("No verified locations in this view of ${region.displayName}")
                if (region.regionId == "us-fl") {
                    append(" — Florida places are mostly Browse-only for now")
                } else {
                    append(" — places stay listed in Browse")
                }
            } else {
                if (showPins && places.size > MAX_OVERLAYS) {
                    append("First $MAX_OVERLAYS of ${places.size} verified places — zoom in")
                } else {
                    append("${places.size} verified places in view")
                    if (clusterCount > 0) append(" · clustered — zoom in")
                }
            }
            if (filtered) append(" · filtered")
        }
        viewportEmpty = places.isEmpty()
        statusView?.let { sv ->
            if (sv.text.toString() != newStatus) {
                sv.text = newStatus
                sv.animate().cancel()
                sv.translationY = -14f
                sv.alpha = 0.4f
                sv.animate().translationY(0f).alpha(1f)
                    .setDuration(220)
                    .setInterpolator(android.view.animation.DecelerateInterpolator())
                    .start()
            }
        }
    }

    // -------------------------------------------------------------- markers

    // Per-place model cache — pin/cluster/sheet all call modelFor, hitting
    // the bundled national registry once per process at most.
    private var cacheStates: List<com.kyronapp.kyron.data.NationalCoverage.Jurisdiction>? = null
    private fun statesForModels(): List<com.kyronapp.kyron.data.NationalCoverage.Jurisdiction> {
        cacheStates ?: run {
            cacheStates = com.kyronapp.kyron.data.NationalCoverage.cached()
                ?: runCatching {
                    com.kyronapp.kyron.data.NationalCoverage.load(requireContext())
                }.getOrDefault(emptyList())
        }
        return cacheStates ?: emptyList()
    }

    /** The result model THIS place publishes under, resolved at SOURCE
     *  level (a state may contain sources with different scales; an
     *  unresolved place degrades to UNKNOWN, never to Alabama's scale). */
    private fun modelFor(p: Place): String =
        com.kyronapp.kyron.data.NationalCoverage.modelForPlace(statesForModels(), p)

    /**
     * Pin/cluster fill color, score-direction aware: on a 0–100 scale
     * HIGH is good; on a penalty scale HIGH is BAD. Non-numeric or
     * unknown-model scores stay neutral gray.
     */
    private fun bandColor(score: Int, model: String): Int = when {
        score < 0 -> toneColor(0)
        model == com.kyronapp.kyron.data.NationalCoverage.MODEL_PENALTY_LOW -> when {
            score <= 13 -> 0xFF2E9E4F.toInt()
            score <= 27 -> 0xFFE8A13A.toInt()
            else -> 0xFFD9534F.toInt()
        }
        model == com.kyronapp.kyron.data.NationalCoverage.MODEL_SCORE_100_HIGH -> when {
            score >= 95 -> 0xFF2E9E4F.toInt()
            score >= 85 -> 0xFF7AB648.toInt()
            else -> 0xFFE8A13A.toInt()
        }
        else -> toneColor(0)
    }

    /** Tone colors for native (non-numeric) results: good/warn/bad/neutral. */
    private fun toneColor(tone: Int): Int = when (tone) {
        1 -> 0xFF2E9E4F.toInt()
        2 -> 0xFFE8A13A.toInt()
        3 -> 0xFFD9534F.toInt()
        else -> 0xFF8A97A5.toInt()
    }

    /**
     * Modern pill marker: white rounded pill with a band-colored ring and
     * text (Airbnb price-pill style). Selected pins invert to a filled
     * colored pill with white text and render slightly larger.
     */
    private fun pillIcon(
        key: String, text: String, band: Int, big: Boolean, selected: Boolean
    ): BitmapDrawable {
        val cacheKey = "$key|$text|$band|$big|$selected"
        iconCache[cacheKey]?.let { return it }
        val w = if (big) 150 else 128
        val h = if (big) 84 else 72
        val bmp = Bitmap.createBitmap(w, h + 14, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val cx = w / 2f
        // Soft grounding shadow under the pill.
        val shadow = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0x33000000; style = Paint.Style.FILL
        }
        c.drawOval(cx - w * 0.28f, h - 10f, cx + w * 0.28f, h + 10f, shadow)
        val rect = android.graphics.RectF(4f, 2f, w - 4f, h.toFloat())
        val radius = h / 2f - 2f
        val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = if (selected) band else 0xFFFFFFFF.toInt()
            style = Paint.Style.FILL
        }
        c.drawRoundRect(rect, radius, radius, fillPaint)
        val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = band; style = Paint.Style.STROKE
            strokeWidth = if (selected) 0f else 5f
        }
        if (!selected) c.drawRoundRect(
            android.graphics.RectF(6f, 4f, w - 6f, h - 2f), radius - 2f, radius - 2f, ring
        )
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = if (selected) 0xFFFFFFFF.toInt() else band
            textAlign = Paint.Align.CENTER
            typeface = Typeface.DEFAULT_BOLD
        }
        // Shrink-to-fit: numbers stay big, long word badges (native
        // results like "Out of Business") shrink until they fit.
        tp.textSize = if (big) 40f else 34f
        while (tp.textSize > 15f && tp.measureText(text) > w - 30f) {
            tp.textSize -= 2f
        }
        val ty = h / 2f - (tp.descent() + tp.ascent()) / 2f
        c.drawText(text, cx, ty, tp)
        val d = BitmapDrawable(resources, bmp)
        iconCache[cacheKey] = d
        return d
    }

    private fun pinFill(p: Place): Int =
        if (p.hasNumericScore) bandColor(p.score, modelFor(p)) else toneColor(p.resultTone)

    /** Small branded dot for the user's area center — pulsing-halo style,
     *  visually distinct from place pills. */
    private fun homeDotIcon(): BitmapDrawable {
        iconCache["__home_dot__"]?.let { return it }
        val size = 56
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val cx = size / 2f
        c.drawCircle(cx, cx, 22f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0x331E6B38
        })
        c.drawCircle(cx, cx, 13f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFF1E6B38.toInt()
        })
        c.drawCircle(cx, cx, 10f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFFFFFFFF.toInt(); style = Paint.Style.STROKE; strokeWidth = 4f
        })
        val d = BitmapDrawable(resources, bmp)
        iconCache["__home_dot__"] = d
        return d
    }

    private var selectedMarker: Marker? = null

    private fun pinMarker(p: Place): Marker {
        val mv = mapView!!
        val marker = Marker(mv)
        marker.id = p.id
        marker.position = GeoPoint(p.lat!!, p.lng!!)
        marker.icon = pillIcon(
            "pin", if (p.hasNumericScore) p.score.toString() else p.badgeText,
            pinFill(p), big = false, selected = false
        )
        // Anchor the geo-point to the pill's center (the bitmap extends
        // below the pill for its shadow strip).
        marker.setAnchor(Marker.ANCHOR_CENTER, 0.44f)
        marker.title = p.name
        marker.setOnMarkerClickListener { m, _ ->
            selectPin(m, p)
            true
        }
        return marker
    }

    /** Highlight the tapped pin (filled pill, raised above others) and
     *  open the place card. The previous selection reverts. */
    private fun selectPin(m: Marker, p: Place) {
        selectedMarker?.let { old ->
            old.relatedObject?.let { oldPlace ->
                if (oldPlace is Place) old.icon = pillIcon(
                    "pin",
                    if (oldPlace.hasNumericScore) oldPlace.score.toString() else oldPlace.badgeText,
                    pinFill(oldPlace), big = false, selected = false
                )
            }
        }
        m.relatedObject = p
        selectedMarker = m
        m.icon = pillIcon(
            "pin", if (p.hasNumericScore) p.score.toString() else p.badgeText,
            pinFill(p), big = false, selected = true
        )
        mapView?.invalidate()
        showSheet(p)
        // If the pin now sits behind the sheet, nudge the camera so it
        // lands in the middle of the still-visible strip.
        val s = sheet ?: return
        s.post {
            val mv = mapView ?: return@post
            val pinPx = android.graphics.Point()
            mv.projection.toPixels(m.position, pinPx)
            val visibleH = mv.height - s.height
            val targetY = visibleH * 0.45f
            if (pinPx.y > targetY) {
                val newCenter = mv.projection.fromPixels(
                    mv.width / 2, (mv.height / 2f + (pinPx.y - targetY)).toInt()
                ) as GeoPoint
                mv.controller.animateTo(newCenter)
            }
        }
    }

    private fun clusterMarker(cluster: Cluster): Marker {
        val mv = mapView!!
        val scored = cluster.members.filter { it.hasNumericScore }
        // "Worst" is model-relative: on a 0–100 scale the LOWEST score is
        // worst; on a penalty scale the HIGHEST penalty is worst. Members
        // may even mix sources with different scales — each is judged by
        // its own registry model's tone, and the worst tone wins.
        val worstMember = scored.maxByOrNull {
            com.kyronapp.kyron.data.NationalCoverage.numericTone(modelFor(it), it.score)
        }
        val worst = worstMember?.score ?: Place.NO_SCORE
        val worstModel = worstMember?.let { modelFor(it) } ?: ""
        val penaltyScale = worstModel == com.kyronapp.kyron.data.NationalCoverage.MODEL_PENALTY_LOW
        val marker = Marker(mv)
        marker.id = "__cluster__"
        marker.position = GeoPoint(cluster.centerLat, cluster.centerLng)
        marker.icon = if (worst != Place.NO_SCORE) {
            pillIcon(
                "clu", "${cluster.members.size} · $worst",
                bandColor(worst, worstModel), big = true, selected = false
            )
        } else {
            // No numeric scores in this cluster (disposition region):
            // the badge is the count alone, in neutral gray.
            pillIcon(
                "clures", cluster.members.size.toString(),
                toneColor(0), big = true, selected = false
            )
        }
        marker.setAnchor(Marker.ANCHOR_CENTER, 0.44f)
        marker.title = if (worst != Place.NO_SCORE) {
            if (penaltyScale) "${cluster.members.size} places — highest penalty $worst"
            else "${cluster.members.size} places — lowest score $worst"
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
        val wasHidden = sheet?.visibility != View.VISIBLE
        selected = p
        val s = sheet ?: return
        s.visibility = View.VISIBLE
        if (wasHidden) {
            s.translationY = 60f
            s.alpha = 0f
            s.animate().translationY(0f).alpha(1f)
                .setDuration(280).setInterpolator(
                    android.view.animation.DecelerateInterpolator(1.6f)
                ).start()
        }
        val root = view ?: return
        val badge = root.findViewById<TextView>(R.id.sheet_badge)
        badge.text = p.badgeText
        // Word badges (native results) need smaller type than numbers.
        badge.textSize = if (p.hasNumericScore) 20f else 10f
        badge.setBackgroundResource(
            when {
                !p.hasNumericScore -> when (p.resultTone) {
                    1 -> R.drawable.score_green
                    2 -> R.drawable.score_amber
                    3 -> R.drawable.score_red
                    else -> R.drawable.score_gray
                }
                // LF-N hardening: numeric fills are MODEL-aware (the place's
                // own registry source model). On a penalty scale HIGH is
                // bad — the naive >=95/<=85 thresholds would paint the
                // WORST penalty places green.
                else -> when (com.kyronapp.kyron.data.NationalCoverage
                    .numericTone(modelFor(p), p.score)) {
                    1 -> R.drawable.score_green
                    2 -> if (modelFor(p) == com.kyronapp.kyron.data.NationalCoverage.MODEL_SCORE_100_HIGH)
                        R.drawable.score_lime else R.drawable.score_amber
                    3 -> R.drawable.score_red
                    else -> R.drawable.score_gray
                }
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
        )?.mutate()
        icon?.setTint(ContextCompat.getColor(fav.context, R.color.kyron_primary))
        fav.setCompoundDrawablesWithIntrinsicBounds(icon, null, null, null)
    }

    private fun hideSheet() {
        selectedMarker?.let { m ->
            (m.relatedObject as? Place)?.let { p ->
                m.icon = pillIcon(
                    "pin",
                    if (p.hasNumericScore) p.score.toString() else p.badgeText,
                    pinFill(p), big = false, selected = false
                )
            }
        }
        selectedMarker = null
        selected = null
        mapView?.invalidate()
        val s = sheet ?: return
        if (s.visibility == View.VISIBLE) {
            s.animate().translationY(80f).alpha(0f).setDuration(180)
                .setInterpolator(android.view.animation.AccelerateInterpolator())
                .withEndAction {
                    s.visibility = View.GONE
                    s.translationY = 0f
                    s.alpha = 1f
                }.start()
        } else {
            s.visibility = View.GONE
        }
    }

    /** Stagger-fade pin/cluster markers in after a render — the
     *  "alive" entrance the map was missing. Cap at ~40 items so a
     *  dense city re-render doesn't queue hundreds of animators. */
    private fun animateMarkersIn(mv: MapView) {
        val pins = mv.overlays.filterIsInstance<Marker>()
            .filter { it.id != "__home__" }
        if (pins.size > 80) return  // too dense — instant is kinder
        pins.forEachIndexed { i, m ->
            m.alpha = 0f
            m.infoWindow = null
        }
        pins.take(40).forEachIndexed { i, m ->
            m.alpha = 0f
            val startAt = i * 14L
            android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
                startDelay = startAt
                duration = 240
                addUpdateListener {
                    m.alpha = it.animatedValue as Float
                    mv.postInvalidate()
                }
                start()
            }
        }
        pins.drop(40).forEach { it.alpha = 1f }
    }

    /** Esri's tile service orders paths z/y/x; osmdroid's XYTileSource
     *  emits z/x/y. This subclass just reorders the two indices. */
    private class YXTileSource(
        name: String, zoomMin: Int, zoomMax: Int, tileSize: Int,
        ext: String, urls: Array<String>, copyright: String
    ) : org.osmdroid.tileprovider.tilesource.XYTileSource(
        name, zoomMin, zoomMax, tileSize, ext, urls, copyright
    ) {
        override fun getTileURLString(pMapTileIndex: Long): String =
            baseUrl +
                org.osmdroid.util.MapTileIndex.getZoom(pMapTileIndex) + "/" +
                org.osmdroid.util.MapTileIndex.getY(pMapTileIndex) + "/" +
                org.osmdroid.util.MapTileIndex.getX(pMapTileIndex) +
                mImageFilenameEnding
    }

    /** Expanding "radar" ring around the area-center dot — drawn in the
     *  overlay pass and driven by invalidateOnAnimation, so it pulses
     *  continuously without a thread of its own. */
    private inner class PulseOverlay(
        private val mv: MapView,
        private val point: () -> GeoPoint
    ) : org.osmdroid.views.overlay.Overlay() {
        private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFF1E6B38.toInt()
            style = Paint.Style.STROKE
            strokeWidth = 3f
        }
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFF1E6B38.toInt()
            style = Paint.Style.FILL
        }
        private val t0 = SystemClock.uptimeMillis()
        private val px = android.graphics.Point()

        override fun draw(canvas: Canvas, map: MapView, shadow: Boolean) {
            if (shadow) return
            val frac = ((SystemClock.uptimeMillis() - t0) % 2200L) / 2200f
            mv.projection.toPixels(point(), px)
            val r = 14f + frac * 46f
            fill.alpha = ((1f - frac) * 40).toInt()
            ring.alpha = ((1f - frac) * 110).toInt()
            canvas.drawCircle(px.x.toFloat(), px.y.toFloat(), r, fill)
            canvas.drawCircle(px.x.toFloat(), px.y.toFloat(), r, ring)
            mv.postInvalidateOnAnimation()
        }
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
