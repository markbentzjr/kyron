package com.kyronapp.kyron.ui

import android.location.Geocoder
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Place
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import java.util.Locale

class MapFragment : Fragment() {

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var mapView: MapView? = null
    private var statusView: TextView? = null
    private var places: List<Place> = emptyList()
    private var geocodeStarted = false

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val v = inflater.inflate(R.layout.fragment_map, container, false)
        statusView = v.findViewById(R.id.map_status)
        val mv = v.findViewById<MapView>(R.id.map)
        mapView = mv
        mv.setTileSource(TileSourceFactory.MAPNIK)
        mv.setMultiTouchControls(true)
        mv.controller.setZoom(11.0)
        mv.controller.setCenter(GeoPoint(app.prefs.homeLat, app.prefs.homeLng))

        scope.launch {
            app.repository.places.collectLatest { list ->
                places = list
                drawMarkers()
                maybeGeocode()
            }
        }
        return v
    }

    private fun drawMarkers() {
        val mv = mapView ?: return
        val existing = mv.overlays.filterIsInstance<Marker>()
        val withCoords = places.filter { it.lat != null && it.lng != null }
        val existingIds = existing.map { it.id }.toSet()
        val wanted = withCoords.map { it.id }.toSet() + "__home__"
        if (existingIds != wanted) {
            mv.overlays.removeAll(existing)
            for (p in withCoords) {
                val marker = Marker(mv)
                marker.id = p.id
                marker.position = GeoPoint(p.lat!!, p.lng!!)
                marker.title = "${p.name} — ${p.score}"
                marker.snippet = "${p.city} · inspected ${p.date} · tap again to open"
                marker.setOnMarkerClickListener { m, _ ->
                    if (m.isInfoWindowShown) {
                        (activity as? MainActivity)?.openPlace(p.id)
                    } else {
                        m.showInfoWindow()
                    }
                    true
                }
                mv.overlays.add(marker)
            }
            val home = Marker(mv)
            home.id = "__home__"
            home.position = GeoPoint(app.prefs.homeLat, app.prefs.homeLng)
            home.title = "Your area center — ${app.prefs.homeLabel}"
            mv.overlays.add(home)
            mv.invalidate()
        }
        statusView?.text = "${withCoords.size} places on the map · tap a pin twice to open its page. Green home pin = your area center."
    }

    private fun maybeGeocode() {
        if (geocodeStarted) return
        val missing = places.filter { it.lat == null }.take(40)
        if (missing.isEmpty()) return
        geocodeStarted = true
        scope.launch {
            val geocoder = Geocoder(requireContext(), Locale.US)
            var done = 0
            for (p in missing) {
                statusView?.text = "Locating places on the map… $done/${missing.size}"
                val found = withContext(Dispatchers.IO) {
                    runCatching {
                        @Suppress("DEPRECATION")
                        geocoder.getFromLocationName(p.fullAddress(), 1)?.firstOrNull()
                    }.getOrNull()
                }
                if (found != null) app.repository.setCoords(p.id, found.latitude, found.longitude)
                done++
            }
            drawMarkers()
        }
    }

    override fun onResume() {
        super.onResume()
        mapView?.onResume()
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
