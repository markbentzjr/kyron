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
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.Lifecycle
import com.kyronapp.kyron.ui.AlertsFragment
import com.kyronapp.kyron.ui.BrowseFragment
import com.kyronapp.kyron.ui.CoverageActivity
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

    /** Classic tab bar (LF4FIX2): four labeled tabs, the pre-2.1
     *  navigation. Selection is rendered directly by [selectTab]. */
    private val tabIds = intArrayOf(R.id.tab_browse, R.id.tab_map, R.id.tab_favorites, R.id.tab_alerts)

    /** Tab fragments are created once and kept alive, so switching tabs never
     *  loses Browse's search/scroll or other in-progress state. */
    private val frags = arrayOfNulls<Fragment>(4)

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

        tabIds.forEachIndexed { idx, id ->
            findViewById<TextView>(id).setOnClickListener { selectTab(idx) }
        }
        // Region chip (LF-4): shows the active region everywhere; tapping
        // it opens Coverage, where states are picked/downloaded. The chip
        // follows RegionManager, so a switch made in Coverage lands here.
        val chip = findViewById<android.widget.Button>(R.id.region_chip)
        chip.setOnClickListener {
            startActivity(Intent(this, CoverageActivity::class.java))
        }
        scope.launch {
            app.regions.activeRegion.collect {
                chip.text = app.regions.activeInfo().displayName
            }
        }
        selectTab(0)
        maybeShowWelcome()

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

    /** Switch tabs, keeping every tab's fragment (and its scroll/search
     *  state) alive. Also used by other screens (e.g. the Favorites empty
     *  state's "Browse restaurants" button). */
    fun selectTab(i: Int) {
        tab = i
        // Render the selection on the classic tab bar (bold + brand
        // color on the active tab). Setting visuals directly cannot
        // re-enter this method, so no syncingNav-style guard is needed.
        tabIds.forEachIndexed { idx, id ->
            findViewById<TextView>(id)?.let { tv ->
                val active = idx == i
                tv.setTextColor(
                    ContextCompat.getColor(
                        this, if (active) R.color.kyron_primary else R.color.muted
                    )
                )
                tv.setTypeface(
                    tv.typeface,
                    if (active) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL
                )
            }
        }
        val target = frags[i]
            ?: supportFragmentManager.findFragmentByTag("tab$i")
            ?: when (i) {
                0 -> BrowseFragment()
                1 -> MapFragment()
                2 -> FavoritesFragment()
                else -> AlertsFragment()
            }
        frags[i] = target
        val tx = supportFragmentManager.beginTransaction()
        // Hide every other added fragment — including ones FragmentManager
        // restored after a process recreation that we haven't tracked yet.
        (supportFragmentManager.fragments + frags.filterNotNull()).distinct().forEach { f ->
            if (f !== target && f.isAdded) {
                tx.hide(f).setMaxLifecycle(f, Lifecycle.State.STARTED)
            }
        }
        if (target.isAdded) {
            tx.show(target)
        } else {
            tx.add(R.id.container, target, "tab$i")
        }
        tx.setMaxLifecycle(target, Lifecycle.State.RESUMED)
        tx.commit()
    }

    private fun maybeShowWelcome() {
        if (app.prefs.seenWelcome) return
        AlertDialog.Builder(this)
            .setTitle("Welcome to Kyron")
            .setMessage(
                "Kyron shows official health-inspection results for " +
                    "restaurants and food stores. Every result is shown with its " +
                    "inspection date and the health department it came from. " +
                    "Alabama is included with the app; more states can be added " +
                    "from Coverage (tap the state name at the top).\n\n" +
                    "• Browse or search below, then tap a place to see why it " +
                    "got its score (where the county publishes the details).\n" +
                    "• Tap the star on a place to watch it — you'll get an " +
                    "alert when it receives a new score.\n" +
                    "• The Map pins every place at its real street address, " +
                    "verified against the US Census Bureau's address data. " +
                    "Places whose address couldn't be verified aren't pinned — " +
                    "they're still in Browse with their address.\n" +
                    "• Set up alerts any time in the Alerts tab. Data refreshes " +
                    "automatically about every 12 hours.\n\n" +
                    "No sign-up needed — everything works right away. " +
                    "The app ships with an October 2026 snapshot and updates " +
                    "from there."
            )
            .setPositiveButton("Start exploring") { d, _ ->
                app.prefs.seenWelcome = true
                d.dismiss()
            }
            .setOnDismissListener { app.prefs.seenWelcome = true }
            .show()
    }

    fun openPlace(placeId: String) {
        val intent = Intent(this, DetailActivity::class.java)
            .putExtra(DetailActivity.EXTRA_PLACE_ID, placeId)
        startActivity(intent)
    }

    fun startSync(includeCounties: Boolean, onDone: (() -> Unit)? = null) {
        if (syncing) { onDone?.invoke(); return }
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
                (frags.getOrNull(3) as? AlertsFragment)?.refresh()
                onDone?.invoke()
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
                (frags.getOrNull(3) as? AlertsFragment)?.refresh()
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
