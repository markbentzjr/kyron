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
 * Coverage & states (LF-4, Presentation Spec §9.8; LF-N nationwide): the
 * state picker.
 *
 * LF-N: ALL 50 states — plus Washington, D.C. as a separate federal-district
 * jurisdiction — come from the bundled national coverage registry
 * (NationalCoverage, assets/coverage/us_national_registry.json). Statuses
 * stay truthful and DISTINCT:
 *  - "Included"/"Downloaded"/"Active now" describe what is ON the device.
 *  - "Available" describes a published pack; the pack HOST health is
 *    checked separately — a 404 host is shown as unreachable, never as the
 *    user's fault.
 *  - "Pack built — publication pending" describes TN/SC-class states.
 *  - "Verified official sources — not integrated" describes states whose
 *    portal was verified but no ingestion exists; the source list dialog
 *    links the OFFICIAL sites (never presented as restaurant data).
 *  - "Registered — official sources listed" is the official-link-only
 *    fallback, explicitly labeled as such.
 * GPS *proposes* a state — the user always confirms, and a state Kyron
 * doesn't cover is named as such, never shown as an empty region.
 */
class CoverageActivity : AppCompatActivity() {

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var filter: String = ""
    private var busy: Boolean = false
    private var jurisdictions: List<com.kyronapp.kyron.data.NationalCoverage.Jurisdiction> =
        emptyList()
    // LF-N: per-region LIVE pack-host probe results (key = regionId, value =
    // the manifest fetch returned HTTP 200). Absent = not probed yet in this
    // session. Filled by probePackHosts() / probeOne(); consulted by
    // render() — a "declared-only" publication only becomes a real
    // Download button after its host answered a live probe.
    private val liveProbe = HashMap<String, Boolean>()

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
            jurisdictions = com.kyronapp.kyron.data.NationalCoverage.load(this@CoverageActivity)
            render()
            probePackHosts()
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
        val coverage = if (jurisdictions.isEmpty())
            com.kyronapp.kyron.data.NationalCoverage.load(this) else jurisdictions
        for (jur in coverage) {
            val code = jur.state
            val name = jur.name
            if (filter.isNotBlank() && !name.contains(filter, ignoreCase = true) &&
                !code.contains(filter, ignoreCase = true)
            ) continue
            // Pack-capable regions (installed/bundled/downloadable) stay
            // governed by Regions; everything else is registry-driven. A
            // registry-vouched pack-capable region outside KNOWN gets a
            // registry-derived descriptor (model/manifest/eligibility).
            val info = Regions.byId(jur.regionId)
                ?: Regions.fromRegistry(applicationContext, jur.regionId)
            val regionId = jur.regionId
            val installedCount = if (info != null) app.repository.regionPlaceCount(regionId) else 0
            val installed = info != null && (info.bundled || installedCount > 0)
            val isActive = regionId == activeId && info != null

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
            val title = TextView(this).apply {
                text = name
                textSize = 16f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
            }
            titleRow.addView(title)
            if (jur.type == "federal-district") {
                titleRow.addView(TextView(this).apply {
                    text = "DISTRICT (not a state)"
                    textSize = 10f
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setTextColor(0xFF5A6B7A.toInt())
                    setPadding(dp(8), 0, 0, 0)
                })
            }
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

            val hostNote = when (jur.packHostStatus) {
                "unreachable-404" ->
                    " — pack host unreachable (HTTP 404, checked ${jur.packHostChecked})"
                "unreachable" ->
                    " — pack host unreachable (checked ${jur.packHostChecked})"
                "reachable" -> ""
                else -> ""
            }
            // LF-N hardening: an explicit THREE-WAY download state. A
            // publication declared in the registry alone ("published") is
            // NEVER sufficient to show a usable download button — the pack
            // must be verified downloadable (registry field, or probed
            // reachable live in this session, since a fresh 200 + hash
            // check at install time is a verification).
            val probed = liveProbe[regionId]
            val downloadable = jur.packAvailability == "downloadable-verified" ||
                (jur.packAvailability == "declared-only" && probed == true)
            val statusText = when {
                isActive && installed -> "Active now · ${"%,d".format(installedCount)} places"
                info?.bundled == true -> "Included with the app · ${"%,d".format(installedCount)} places"
                installed -> {
                    val v = app.repository.installedRegionVersion(regionId) ?: "?"
                    "Downloaded · data v$v · ${"%,d".format(installedCount)} places"
                }
                downloadable ->
                    "Available — free region-pack download${hostNote}" +
                        (if (jur.artifactVerified.isNotBlank())
                            " · artifact verified ${jur.artifactVerified}" else "")
                jur.packAvailability == "declared-only" && probed == false ->
                    "Publication declared — but the pack host returned an error" +
                        "$hostNote. NOT downloadable right now."
                jur.packAvailability == "declared-only" ->
                    "Publication declared — download availability not yet verified."
                jur.packStatus == "built" ->
                    "Data harvested & pack built — publication pending (no download yet)"
                else -> "Not integrated yet — registered official source(s) listed below"
            }
            row.addView(TextView(this).apply {
                text = statusText
                textSize = 13f
                setTextColor(0xFF5A6B7A.toInt())
            })
            row.addView(TextView(this).apply {
                text = com.kyronapp.kyron.data.NationalCoverage.legend(jur.resultModel)
                textSize = 12f
                setTextColor(0xFF7A8A97.toInt())
                setPadding(0, dp(2), 0, 0)
            })

            val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            if (installed && info != null && !isActive) {
                actions.addView(actionButton("Use $name") {
                    app.regions.setActive(regionId, manual = true)
                    Toast.makeText(this, "Kyron is now showing $name", Toast.LENGTH_SHORT).show()
                    finish()
                })
            }
            // LF-N hardening: publication declared ("published") in the
            // registry is NOT the same as verified downloadable — only
            // "downloadable-verified" rows, or "declared-only" rows whose
            // host answered a LIVE probe in this session, get a real
            // Download button.
            if (info != null && !info.bundled && !installed && info.manifestUrl != null &&
                downloadable
            ) {
                // Pack host unreachable note ONLY when the latest live probe
                // FAILED but the registry already vouched this pack as
                // downloadable-verified — still downloadable, honestly
                // flagged as re-checking.
                actions.addView(actionButton(
                    if (probed == false) "Download\n(re-checking host)" else "Download"
                ) { downloadRegion(info.regionId) })
            } else if (info != null && !info.bundled && !installed &&
                info.manifestUrl != null && jur.packAvailability == "declared-only"
            ) {
                if (probed == false) {
                    // Probed and failed this session: this state can't be
                    // downloaded right now, and the button says so instead
                    // of pretending otherwise.
                    val btn = actionButton("Unavailable\n(host error — checked)") { }
                    btn.isEnabled = false
                    actions.addView(btn)
                } else {
                    // Declared but not yet probed: offer a one-shot live
                    // check; a success flips this card to a Download button
                    // on the immediate re-render.
                    actions.addView(actionButton("Check availability") {
                        scope.launch {
                            status("Probing ${name}'s pack host…")
                            val ok = probeOne(jur)
                            liveProbe[regionId] = ok
                            if (ok) {
                                status("${name}'s pack host responded OK — download enabled.")
                            } else {
                                status("${name}'s region-pack host responded with an error — " +
                                    "its download cannot complete right now. Data on this device is unaffected.")
                            }
                            render()
                        }
                    })
                }
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
            // LF-N: every state stays explorable — a registry row always
            // lists its official sources (tapping opens the OFFICIAL site;
            // this is explicitly NOT restaurant data).
            actions.addView(actionButton("Official sources") {
                showSources(jur)
            })
            if (actions.childCount > 0) row.addView(actions)
            // LF-N UX hardening (Kyron-2.0 field report): the card itself is
            // tappable — a tap on the name/status area opens the same honest
            // info dialog ("official sources") as the card's action button,
            // so a state never answers with dead silence. Child buttons keep
            // their own clicks; this is the fallback affordance only.
            card.isClickable = true
            card.setOnClickListener { showSources(jur) }
            list.addView(card)
        }
    }

    /** LF-N: the official-source list for a jurisdiction. Tapping a source
     *  opens the AGENCY's site in the browser; nothing here pretends to be
     *  crawlable restaurant data. */
    private fun showSources(jur: com.kyronapp.kyron.data.NationalCoverage.Jurisdiction) {
        val lines = StringBuilder()
        lines.append(com.kyronapp.kyron.data.NationalCoverage.legend(jur.resultModel))
        lines.append("\n\n")
        jur.sources.forEachIndexed { i, s ->
            lines.append("${i + 1}. ${s.agency}\n")
            lines.append("   Coverage: ${s.coverage} · Access: ${s.access} · Status: ${s.status}\n")
            if (s.verified.isNotBlank()) lines.append("   Last verified: ${s.verified}\n")
            if (s.blocker.isNotBlank()) lines.append("   Blocker: ${s.blocker}\n")
            if (s.notes.isNotBlank()) lines.append("   ${s.notes}\n")
        }
        AlertDialog.Builder(this)
            .setTitle("${jur.name} — official sources")
            .setMessage(lines.toString())
            .setPositiveButton("OK", null)
            .setNeutralButton("Open first source") { _, _ ->
                runCatching {
                    startActivity(
                        android.content.Intent(
                            android.content.Intent.ACTION_VIEW,
                            android.net.Uri.parse(jur.sources.first().website)
                        )
                    )
                }.onFailure {
                    Toast.makeText(this, "No browser available", Toast.LENGTH_SHORT).show()
                }
            }
            .show()
    }

    /** LF-N pack-host health probe: EVERY jurisdiction with a published
     *  manifest gets a live reachability check (cached per process), and
     *  the result is recorded for BOTH outcomes — a success unlocks the
     *  Download button on "declared-only" rows, a failure is REPORTED so
     *  a broken host is never silently masked. "available" must never
     *  silently fail on tap. */
    private fun probePackHosts() {
        scope.launch {
            for (jur in jurisdictions) {
                if (jur.packStatus != "published") continue
                if (jur.packManifestUrl == null) continue
                val reachable = probeOne(jur)
                // Publication declared != verified downloadable: store the
                // live verdict either way, then re-render immediately so
                // the button ladder reflects the fresh result.
                liveProbe[jur.regionId] = reachable
                if (reachable) {
                    status("${jur.name}'s pack host responded OK — download enabled.")
                } else {
                    status("${jur.name}'s region-pack host responded with an error — " +
                        "its download cannot complete right now. Data on this device is unaffected.")
                }
                render()
            }
        }
    }

    /** Live reachability check for ONE jurisdiction's pack manifest
     *  (8s timeouts, plain GET, connection torn down, every exception
     *  swallowed to `false`). Used by the bulk pre-probe above and by the
     *  per-card "Check availability" button. */
    private suspend fun probeOne(
        jur: com.kyronapp.kyron.data.NationalCoverage.Jurisdiction
    ): Boolean {
        val url = jur.packManifestUrl ?: return false
        return withContext(Dispatchers.IO) {
            runCatching {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.connectTimeout = 8000
                conn.readTimeout = 8000
                conn.requestMethod = "GET"
                val code = conn.responseCode
                conn.disconnect()
                code == 200
            }.getOrDefault(false)
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
        val stateName = com.kyronapp.kyron.data.NationalCoverage.load(this)
            .firstOrNull { it.state == state }?.name ?: state
        val info = Regions.byState(state)
        when {
            info != null && info.regionId == app.regions.activeRegionId() ->
                Toast.makeText(this, "You're in $stateName — already your active region", Toast.LENGTH_SHORT).show()
            info == null ->
                AlertDialog.Builder(this)
                    .setTitle("You're in $stateName")
                    .setMessage(
                        "Kyron's downloadable region packs are published state by state. " +
                            "$stateName is registered in the coverage registry — open its official sources from the list, or wait for its pack. " +
                            "Nothing was changed."
                    )
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
