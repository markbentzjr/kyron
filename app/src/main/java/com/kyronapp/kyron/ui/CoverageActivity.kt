package com.kyronapp.kyron.ui

import android.Manifest
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.PackManifest
import com.kyronapp.kyron.data.Regions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Coverage & states (LF-4, Presentation Spec §9.8): the state picker.
 *
 * Truthful statuses only: a state is "Included" (bundled), "Downloaded"
 * (a verified pack is installed), "Available to download" (a pack is
 * published), or "Not covered yet". GPS *proposes* a state — the user
 * always confirms, and a state Kyron doesn't cover is named as such,
 * never shown as an empty region. Picking by hand marks the choice as
 * manual, and nothing automatic ever overrides it.
 *
 * LF4FIX2: view construction uses the classic widget set (header bar,
 * card-background containers, plain buttons) instead of Material
 * components. Behavior, copy, statuses, dialogs, and entry points are
 * byte-for-byte the LF-4 contract.
 */
class CoverageActivity : AppCompatActivity() {

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var filter: String = ""
    private var busy: Boolean = false

    private val locationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) proposeFromLocation() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        app = application as KyronApplication
        setContentView(R.layout.activity_coverage)
        findViewById<View>(R.id.cov_back).setOnClickListener { finish() }
        findViewById<Button>(R.id.cov_location_btn).setOnClickListener { onUseLocation() }
        findViewById<EditText>(R.id.cov_search).addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) { filter = s?.toString() ?: ""; render() }
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
        })
        scope.launch {
            app.repository.load()
            render()
        }
    }

    // ------------------------------------------------------------ rendering

    private fun status(text: String?) {
        val v = findViewById<TextView>(R.id.cov_status)
        if (text == null) {
            v.visibility = View.GONE
        } else {
            v.visibility = View.VISIBLE
            v.text = text
        }
    }

    private fun render() {
        val list = findViewById<LinearLayout>(R.id.cov_list)
        list.removeAllViews()
        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()
        val activeId = app.regions.activeRegionId()
        for ((code, name) in Regions.US_STATES) {
            if (filter.isNotBlank() && !name.contains(filter, ignoreCase = true) &&
                !code.contains(filter, ignoreCase = true)
            ) continue
            val info = Regions.byState(code)
            val regionId = Regions.regionIdForState(code)
            val installedCount = if (info != null) app.repository.regionPlaceCount(regionId) else 0
            val installed = info != null && (info.bundled || installedCount > 0)
            val isActive = regionId == activeId

            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundResource(R.drawable.card_bg)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(dp(4), dp(4), dp(4), dp(4)) }
            }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(14), dp(12), dp(14), dp(12))
            }
            card.addView(row)
            val titleRow = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
            }
            titleRow.addView(TextView(this).apply {
                text = name
                textSize = 16f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
            })
            if (isActive) {
                titleRow.addView(TextView(this).apply {
                    text = "ACTIVE NOW"
                    textSize = 11f
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setTextColor(0xFF1E6B38.toInt())
                    setPadding(dp(8), 0, 0, 0)
                })
            }
            row.addView(titleRow)
            val statusText = when {
                isActive && installed -> "Active now · ${"%,d".format(installedCount)} places"
                info?.bundled == true -> "Included with the app · ${"%,d".format(installedCount)} places"
                installed -> {
                    val v = app.repository.installedRegionVersion(regionId) ?: "?"
                    "Downloaded · data v$v · ${"%,d".format(installedCount)} places"
                }
                info?.manifestUrl != null -> "Available — free region-pack download"
                else -> "Not covered yet — no region pack exists for this state"
            }
            row.addView(TextView(this).apply {
                text = statusText
                textSize = 13f
                setTextColor(0xFF5A6B7A.toInt())
            })

            val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            if (installed && !isActive) {
                actions.addView(actionButton("Use $name") {
                    app.regions.setActive(regionId, manual = true)
                    Toast.makeText(this, "Kyron is now showing $name", Toast.LENGTH_SHORT).show()
                    finish()
                })
            }
            if (info != null && !info.bundled && !installed && info.manifestUrl != null) {
                actions.addView(actionButton("Download") { downloadRegion(info.regionId) })
            }
            if (info != null && !info.bundled && installed) {
                if (app.repository.packHasRollback(regionId)) {
                    actions.addView(actionButton("Roll back") {
                        confirm("Roll back $name?", "Restore the previous ${name} data pack? Your favorites and alerts are not affected.") {
                            scope.launch {
                                runCatching { app.repository.rollbackPack(regionId) }
                                    .onSuccess {
                                        status("$name rolled back to the previous data pack.")
                                        render()
                                    }
                                    .onFailure { status("Rollback failed: ${it.message}") }
                            }
                        }
                    })
                }
                actions.addView(actionButton("Remove") {
                    confirm("Remove $name?", "The downloaded ${name} data will be deleted from this device. Your favorites and alert settings stay — places from $name will show again if you re-download the pack.") {
                        scope.launch {
                            if (app.regions.activeRegionId() == regionId) {
                                app.regions.setActive(Regions.ALABAMA.regionId, manual = true)
                            }
                            runCatching { app.repository.removePack(regionId) }
                                .onSuccess { status("$name removed."); render() }
                                .onFailure { status("Remove failed: ${it.message}") }
                        }
                    }
                })
            }
            if (actions.childCount > 0) row.addView(actions)
            list.addView(card)
        }
    }

    private fun actionButton(label: String, onClick: () -> Unit): Button =
        Button(this).apply {
            text = label
            isAllCaps = false
            textSize = 13f
            backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFDAE7DB.toInt())
            setTextColor(0xFF16281B.toInt())
            setOnClickListener { onClick() }
        }

    private fun confirm(title: String, message: String, onYes: () -> Unit) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("Yes") { d, _ -> d.dismiss(); onYes() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ------------------------------------------------------------ download

    /** Fetch the region's manifest, then its pack, verify + install.
     *  PackManager refuses anything whose checksum, region, schema, or
     *  place count disagrees with the manifest — a bad download changes
     *  nothing on the device. */
    private fun downloadRegion(regionId: String) {
        val info = Regions.byId(regionId) ?: return
        val manifestUrl = info.manifestUrl ?: return
        if (busy) return
        busy = true
        status("Downloading the ${info.displayName} region pack…")
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    val manifestText = fetchText(manifestUrl)
                    val manifest = PackManifest.fromJson(JSONObject(manifestText))
                    if (manifest.regionId != regionId) {
                        throw IllegalStateException("Manifest is for ${manifest.regionId}, not $regionId")
                    }
                    val packUrl = manifestUrl.substringBeforeLast('/') + "/" + manifest.fullFile
                    val packFile = File(cacheDir, manifest.fullFile)
                    fetchToFile(packUrl, packFile)
                    app.repository.installPack(packFile, manifest)
                }
                status("${info.displayName} downloaded: ${"%,d".format(result.placeCount)} places (data v${result.datasetVersion}).")
                app.regions.setActive(regionId, manual = true)
                render()
                Toast.makeText(this@CoverageActivity, "Kyron is now showing ${info.displayName}", Toast.LENGTH_SHORT).show()
                finish()
            } catch (e: Exception) {
                status("Download failed: ${e.message ?: "network error"}. Your current data is unchanged — the pack is only installed after it verifies.")
            } finally {
                busy = false
            }
        }
    }

    private fun fetchText(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 30_000
        return conn.inputStream.bufferedReader().use { it.readText() }
    }

    private fun fetchToFile(url: String, out: File) {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 120_000
        conn.inputStream.use { input -> out.outputStream().use { input.copyTo(it) } }
    }

    // -------------------------------------------------------------- GPS

    private fun onUseLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            proposeFromLocation()
        } else {
            locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    /** GPS proposes; the user disposes. Nothing here ever switches the
     *  region without an explicit tap on a confirmation. */
    private fun proposeFromLocation() {
        val loc = try {
            val lm = getSystemService(LOCATION_SERVICE) as LocationManager
            listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
                .firstNotNullOfOrNull { p -> runCatching { lm.getLastKnownLocation(p) }.getOrNull() }
        } catch (e: SecurityException) {
            null
        }
        if (loc == null) {
            Toast.makeText(this, "No location fix available yet — pick a state from the list instead", Toast.LENGTH_LONG).show()
            return
        }
        val state = Regions.stateForPoint(loc.latitude, loc.longitude)
        if (state == null) {
            Toast.makeText(this, "That location isn't in a US state Kyron can identify — pick from the list", Toast.LENGTH_LONG).show()
            return
        }
        val stateName = Regions.US_STATES.firstOrNull { it.first == state }?.second ?: state
        val info = Regions.byState(state)
        when {
            info != null && info.regionId == app.regions.activeRegionId() ->
                Toast.makeText(this, "You're in $stateName — already your active region", Toast.LENGTH_SHORT).show()
            info == null ->
                AlertDialog.Builder(this)
                    .setTitle("You're in $stateName")
                    .setMessage("Kyron doesn't cover $stateName yet. Coverage today: Alabama (included with the app) and Florida (free download). Nothing was changed.")
                    .setPositiveButton("OK", null)
                    .show()
            info.bundled || app.repository.regionPlaceCount(info.regionId) > 0 ->
                AlertDialog.Builder(this)
                    .setTitle("Switch to $stateName?")
                    .setMessage("Your location appears to be in $stateName. Switch Kyron's region to $stateName?")
                    .setPositiveButton("Switch") { d, _ ->
                        app.regions.setActive(info.regionId, manual = false)
                        d.dismiss()
                        finish()
                    }
                    .setNegativeButton("Not now", null)
                    .show()
            else ->
                AlertDialog.Builder(this)
                    .setTitle("Download $stateName?")
                    .setMessage("Your location appears to be in $stateName. Its region pack is a free download — download it and switch?")
                    .setPositiveButton("Download & switch") { d, _ ->
                        d.dismiss()
                        downloadRegion(info.regionId)
                    }
                    .setNegativeButton("Not now", null)
                    .show()
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
