package com.kyronapp.kyron.ui

import android.Manifest
import android.app.Dialog
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import android.widget.ToggleButton
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.R
import kotlin.math.roundToInt
import java.text.DateFormat
import java.util.Date

/**
 * Notifications — the alerts surface that used to live as the fourth
 * bottom tab. Rules stay readable cards, not a settings form: favorites
 * are a one-tap switch and the area rule summarizes itself in plain
 * language with Edit/Remove. The DELIVERY card up top states plainly
 * whether notifications can reach this device — background alerts ride
 * the WorkManager 12-hour sync (KyronApplication.scheduleSync), which
 * keeps running while the app is closed, but Android 13+ still gates
 * the visible notification behind POST_NOTIFICATIONS.
 */
class AlertsActivity : AppCompatActivity() {

    private lateinit var app: KyronApplication
    private var editorOpen: Boolean = false

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { bind() }

    private val locationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) useMyLocation() }

    companion object {
        val HOME_PRESETS = listOf(
            Triple("Downtown Birmingham", 33.5207, -86.8025),
            Triple("Hoover", 33.4054, -86.8114),
            Triple("Homewood / UAB", 33.4823, -86.8008),
            Triple("Mountain Brook", 33.4486, -86.7877),
            Triple("Gardendale", 33.6192, -86.8025),
            Triple("Bessemer", 33.3949, -87.0076),
            Triple("Huntsville", 34.7304, -86.5861),
            Triple("Montgomery", 32.3792, -86.3077),
            Triple("Mobile", 30.6944, -88.0431),
            Triple("Auburn", 32.6099, -85.4808),
            Triple("Tuscaloosa", 33.2098, -87.5692)
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        app = application as KyronApplication
        setContentView(R.layout.activity_alerts)
        findViewById<View>(R.id.alerts_back).setOnClickListener { finish() }
        overridePendingTransition(R.anim.frag_in, R.anim.frag_out)
        bind()
    }

    override fun onResume() {
        super.onResume()
        bind()
    }

    private fun bind() {
        val prefs = app.prefs
        // Normalize legacy/imported values into the controls' ranges —
        // same protection the fragment carried for backup-restored values.
        if (prefs.threshold !in 60..99) prefs.threshold = prefs.threshold.coerceIn(60, 99)
        val r0 = prefs.radiusMiles
        if (r0 !in 1.0..50.0 || r0 % 1.0 != 0.0) {
            prefs.radiusMiles = r0.coerceIn(1.0, 50.0).roundToInt().toDouble()
        }

        bindDelivery()

        // Rule card 1: favorites (one-tap quick-pick)
        val swFav = findViewById<SwitchCompat>(R.id.sw_fav_alerts)
        swFav.setOnCheckedChangeListener(null)
        swFav.isChecked = prefs.alertsForFavorites
        swFav.setOnCheckedChangeListener { _, checked ->
            prefs.alertsForFavorites = checked
            bind()
        }

        // Rule card 2: area alerts — summary + switch + edit/remove
        val swArea = findViewById<SwitchCompat>(R.id.sw_area_alerts)
        swArea.setOnCheckedChangeListener(null)
        swArea.isChecked = prefs.alertsForArea
        swArea.setOnCheckedChangeListener { _, checked ->
            prefs.alertsForArea = checked
            if (checked) editorOpen = true
            bind()
        }
        findViewById<TextView>(R.id.area_summary).text = areaSummaryText()
        val removeBtn = findViewById<Button>(R.id.area_remove)
        removeBtn.visibility = if (prefs.alertsForArea) View.VISIBLE else View.GONE
        removeBtn.setOnClickListener {
            prefs.alertsForArea = false
            editorOpen = false
            Toast.makeText(this, "Area alerts removed. Your counties and settings are kept if you turn them back on.", Toast.LENGTH_LONG).show()
            bind()
        }
        val editor = findViewById<View>(R.id.area_editor)
        editor.visibility = if (editorOpen) View.VISIBLE else View.GONE
        findViewById<Button>(R.id.area_edit).setOnClickListener {
            editorOpen = !editorOpen
            editor.visibility = if (editorOpen) View.VISIBLE else View.GONE
        }

        // Counties (inside the editor): summary + searchable picker.
        val monitored = prefs.monitoredCounties
        findViewById<TextView>(R.id.county_summary).text = when {
            monitored.isEmpty() -> "No counties selected yet — pick at least one to watch."
            monitored.size <= 3 -> "${monitored.size} ${if (monitored.size == 1) "county" else "counties"}: " +
                monitored.sorted().joinToString(", ")
            else -> "${monitored.size} counties: " +
                monitored.sorted().take(3).joinToString(", ") + " and ${monitored.size - 3} more"
        }
        findViewById<Button>(R.id.choose_counties).setOnClickListener { showCountyPicker() }

        // Threshold — plain language, number always visible.
        val thrLabel = findViewById<TextView>(R.id.threshold_label)
        val thrSlider = findViewById<SeekBar>(R.id.threshold_slider)
        thrLabel.text = "Alert me when a new score drops below ${prefs.threshold}"
        val thrClamped = prefs.threshold.coerceIn(60, 99)
        if (thrSlider.progress != thrClamped) thrSlider.progress = thrClamped
        thrSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, progress: Int, fromUser: Boolean) {
                thrLabel.text = "Alert me when a new score drops below $progress"
            }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {
                prefs.threshold = thrSlider.progress
                bind()
            }
        })

        // Area center: current label + preset toggles + device location.
        findViewById<TextView>(R.id.home_label).text = "Area center: ${prefs.homeLabel}"
        val presetBox = findViewById<GridLayout>(R.id.preset_box)
        presetBox.removeAllViews()
        for ((label, la, ln) in HOME_PRESETS) {
            val chip = ToggleButton(this).apply {
                minHeight = (48f * resources.displayMetrics.density).toInt()
                textOn = label
                textOff = label
                text = label
                isChecked = prefs.homeLabel == label
                setBackgroundResource(R.drawable.chip_toggle)
                setTextColor(
                    ContextCompat.getColorStateList(this@AlertsActivity, R.color.chip_text)
                )
                textSize = 12.5f
                isAllCaps = false
                setOnClickListener {
                    prefs.homeLat = la; prefs.homeLng = ln; prefs.homeLabel = label
                    bind()
                }
            }
            presetBox.addView(chip, GridLayout.LayoutParams().apply {
                width = 0
                columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                setMargins(0, 0, 10, 8)
            })
        }
        findViewById<Button>(R.id.use_location).setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
            ) {
                useMyLocation()
            } else {
                locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }

        // Radius — plain language.
        val radLabel = findViewById<TextView>(R.id.radius_label)
        val radSlider = findViewById<SeekBar>(R.id.radius_slider)
        radLabel.text = "Watch places within ${prefs.radiusMiles.toInt()} miles of my area center"
        val radClamped = prefs.radiusMiles.coerceIn(1.0, 50.0).roundToInt()
        if (radSlider.progress != radClamped) radSlider.progress = radClamped
        radSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, progress: Int, fromUser: Boolean) {
                radLabel.text = "Watch places within $progress miles of my area center"
            }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {
                prefs.radiusMiles = radSlider.progress.toDouble()
                bind()
            }
        })

        bindInbox()
    }

    /** Whether notifications can actually reach this device, with a way
     *  to fix it when they can't. Pre-33 there's no runtime gate. */
    private fun bindDelivery() {
        val granted = Build.VERSION.SDK_INT < 33 ||
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        findViewById<TextView>(R.id.notif_status).text =
            if (granted) getString(R.string.notif_on)
            else getString(R.string.notif_off)
        val btn = findViewById<Button>(R.id.notif_enable)
        btn.visibility = if (granted) View.GONE else View.VISIBLE
        btn.setOnClickListener {
            if (Build.VERSION.SDK_INT >= 33 &&
                shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)
            ) {
                // Denied once already — the system dialog won't re-show;
                // go straight to this app's notification settings.
                startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                )
            } else if (Build.VERSION.SDK_INT >= 33) {
                notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
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
                bind()
            } else {
                Toast.makeText(this, "No location fix yet — try again outdoors or pick a preset", Toast.LENGTH_LONG).show()
            }
        } catch (e: SecurityException) {
            Toast.makeText(this, "Location permission not granted", Toast.LENGTH_SHORT).show()
        }
    }

    /** The area rule, in one plain-language sentence. */
    private fun areaSummaryText(): String {
        val prefs = app.prefs
        if (!prefs.alertsForArea) {
            return "Off. Turn on to get alerts when a restaurant in your counties scores below your threshold."
        }
        val counties = prefs.monitoredCounties
        val countyPart = when {
            counties.isEmpty() -> "no counties picked yet"
            counties.size <= 2 -> "Watching " + counties.sorted().joinToString(" and ") { "$it County" }
            else -> "Watching ${counties.size} counties"
        }
        return "$countyPart · alert me when a new score drops below ${prefs.threshold} · " +
            "within ${prefs.radiusMiles.toInt()} miles of ${prefs.homeLabel}."
    }

    // ------------------------------------------------------- county picker

    /** Searchable multi-select county picker. Changes apply only on
     *  Done — Cancel leaves the rule untouched. */
    private fun showCountyPicker() {
        val all = app.repository.counties("us-al")
        val working = app.prefs.monitoredCounties.toMutableSet()
        val dialog = Dialog(this)
        dialog.setContentView(R.layout.dialog_county_picker)
        dialog.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            (resources.displayMetrics.heightPixels * 0.88).toInt()
        )
        val countLabel = dialog.findViewById<TextView>(R.id.picker_count)
        val listView = dialog.findViewById<ListView>(R.id.picker_list)
        var shown: List<String> = all

        fun refreshCount() {
            countLabel.text = "${working.size} of ${all.size} counties selected"
        }
        fun refreshList() {
            listView.adapter = ArrayAdapter(
                this, android.R.layout.simple_list_item_multiple_choice, shown
            )
            shown.forEachIndexed { i, name -> listView.setItemChecked(i, working.contains(name)) }
            refreshCount()
        }
        listView.setOnItemClickListener { _, _, pos, _ ->
            val name = shown[pos]
            if (!working.add(name)) working.remove(name)
            listView.setItemChecked(pos, working.contains(name))
            refreshCount()
        }
        dialog.findViewById<EditText>(R.id.picker_search).addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                val q = s?.toString()?.trim() ?: ""
                shown = if (q.isEmpty()) all else all.filter { it.contains(q, ignoreCase = true) }
                refreshList()
            }
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
        })
        dialog.findViewById<Button>(R.id.picker_all).setOnClickListener {
            working.addAll(all)
            refreshList()
        }
        dialog.findViewById<Button>(R.id.picker_clear).setOnClickListener {
            working.clear()
            refreshList()
        }
        dialog.findViewById<Button>(R.id.picker_cancel).setOnClickListener { dialog.dismiss() }
        dialog.findViewById<Button>(R.id.picker_done).setOnClickListener {
            app.prefs.monitoredCounties = working
            dialog.dismiss()
            bind()
        }
        refreshList()
        dialog.show()
    }

    // -------------------------------------------------------------- inbox

    private fun bindInbox() {
        val inbox = app.prefs.inbox
        findViewById<TextView>(R.id.inbox_empty).visibility =
            if (inbox.isEmpty()) View.VISIBLE else View.GONE
        findViewById<TextView>(R.id.inbox_count)?.let { badge ->
            badge.visibility = if (inbox.isEmpty()) View.GONE else View.VISIBLE
            badge.text = inbox.size.toString()
        }
        val inboxBox = findViewById<LinearLayout>(R.id.inbox_box)
        inboxBox.removeAllViews()
        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()
        for (a in inbox) {
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundResource(R.drawable.card_bg)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(4), 0, dp(4)) }
                setOnClickListener {
                    startActivity(
                        Intent(this@AlertsActivity, DetailActivity::class.java)
                            .putExtra(DetailActivity.EXTRA_PLACE_ID, a.placeId)
                    )
                }
            }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
            }
            val icon = ImageView(this).apply {
                setImageResource(if (a.lowScore) R.drawable.ic_warning else R.drawable.ic_notifications)
                setColorFilter(
                    ContextCompat.getColor(
                        this@AlertsActivity,
                        if (a.lowScore) R.color.kyron_red else R.color.kyron_primary
                    )
                )
                layoutParams = LinearLayout.LayoutParams(dp(24), dp(24))
            }
            val col = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(10), 0, 0, 0)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            col.addView(TextView(this).apply {
                text = a.title
                textSize = 14.5f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(
                    ContextCompat.getColor(
                        this@AlertsActivity,
                        if (a.lowScore) R.color.kyron_red else R.color.ink
                    )
                )
            })
            col.addView(TextView(this).apply { text = a.body; textSize = 13f })
            col.addView(TextView(this).apply {
                text = DateFormat.getDateTimeInstance().format(Date(a.whenMs))
                textSize = 11.5f
                setTextColor(ContextCompat.getColor(this@AlertsActivity, R.color.muted))
            })
            row.addView(icon)
            row.addView(col)
            card.addView(row)
            inboxBox.addView(card)
        }
    }
}
