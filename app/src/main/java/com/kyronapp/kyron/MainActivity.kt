package com.kyronapp.kyron

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.kyronapp.kyron.ui.AlertsFragment
import com.kyronapp.kyron.ui.BrowseFragment
import com.kyronapp.kyron.ui.DetailActivity
import com.kyronapp.kyron.ui.FavoritesFragment
import com.kyronapp.kyron.ui.MapFragment
import com.kyronapp.kyron.worker.SyncEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_PLACE_ID = "place_id"
    }

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var tab: Int = 0

    var syncing: Boolean = false
        private set
    var lastReport: String? = null
        private set

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    private val locationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) useMyLocation() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        app = application as KyronApplication
        setContentView(R.layout.activity_main)

        val tabs = listOf(
            findViewById<TextView>(R.id.tab_browse),
            findViewById<TextView>(R.id.tab_map),
            findViewById<TextView>(R.id.tab_favs),
            findViewById<TextView>(R.id.tab_alerts)
        )
        tabs.forEachIndexed { i, tv ->
            tv.setOnClickListener { selectTab(i) }
        }
        selectTab(0)

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        intent?.getStringExtra(EXTRA_PLACE_ID)?.let { openPlace(it) }

        scope.launch {
            app.repository.load()
            if (System.currentTimeMillis() - app.prefs.lastSyncMs > 6 * 60 * 60 * 1000L) {
                startSync(includeCounties = false)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_PLACE_ID)?.let { openPlace(it) }
    }

    private fun selectTab(i: Int) {
        tab = i
        val tabs = listOf(
            findViewById<TextView>(R.id.tab_browse),
            findViewById<TextView>(R.id.tab_map),
            findViewById<TextView>(R.id.tab_favs),
            findViewById<TextView>(R.id.tab_alerts)
        )
        tabs.forEachIndexed { idx, tv ->
            tv.setBackgroundResource(if (idx == i) R.drawable.tab_selected else android.R.color.transparent)
        }
        val fragment: Fragment = when (i) {
            0 -> BrowseFragment()
            1 -> MapFragment()
            2 -> FavoritesFragment()
            else -> AlertsFragment()
        }
        supportFragmentManager.beginTransaction()
            .replace(R.id.container, fragment)
            .commit()
    }

    fun openPlace(placeId: String) {
        val intent = Intent(this, DetailActivity::class.java)
            .putExtra(DetailActivity.EXTRA_PLACE_ID, placeId)
        startActivity(intent)
    }

    fun startSync(includeCounties: Boolean) {
        if (syncing) return
        syncing = true
        scope.launch {
            try {
                val report = SyncEngine.run(this@MainActivity, app.repository, app.prefs, includeCounties)
                lastReport = buildString {
                    append("Sync complete. ")
                    if (report.newInspections > 0) append("${report.newInspections} new inspection(s) found. ")
                    if (report.alertsFired > 0) append("${report.alertsFired} alert(s) fired. ")
                    append("Sources OK: ${report.sourcesOk.joinToString(", ").ifBlank { "none" }}")
                    if (report.sourcesFailed.isNotEmpty()) {
                        append(" · Failed: ${report.sourcesFailed.joinToString(", ")} (will retry)")
                    }
                }
            } catch (e: Exception) {
                lastReport = "Sync hit a problem (${e.message ?: "unknown"}). Your saved data is unchanged."
            } finally {
                syncing = false
                if (tab == 3) selectTab(3) // refresh Alerts screen state
            }
        }
    }

    fun requestLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            useMyLocation()
        } else {
            locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    private fun useMyLocation() {
        try {
            val lm = getSystemService(LOCATION_SERVICE) as LocationManager
            val providers = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            val loc = providers.firstNotNullOfOrNull { p ->
                runCatching { lm.getLastKnownLocation(p) }.getOrNull()
            }
            if (loc != null) {
                app.prefs.homeLat = loc.latitude
                app.prefs.homeLng = loc.longitude
                app.prefs.homeLabel = "My location"
                Toast.makeText(this, "Area center set to your location", Toast.LENGTH_SHORT).show()
                if (tab == 3) selectTab(3)
            } else {
                Toast.makeText(this, "No location fix yet — try again outdoors or pick a preset", Toast.LENGTH_LONG).show()
            }
        } catch (e: SecurityException) {
            Toast.makeText(this, "Location permission not granted", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
