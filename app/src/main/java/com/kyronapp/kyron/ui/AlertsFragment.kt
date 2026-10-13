package com.kyronapp.kyron.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.source.SourceRegistry
import java.text.DateFormat
import java.util.Date

class AlertsFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var root: View

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

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        root = inflater.inflate(R.layout.fragment_alerts, container, false)
        bind()
        return root
    }

    override fun onResume() {
        super.onResume()
        if (::root.isInitialized) bind()
    }

    private fun bind() {
        val prefs = app.prefs

        // Profile
        val nameField = root.findViewById<EditText>(R.id.profile_name)
        if (nameField.text.toString() != prefs.profileName) nameField.setText(prefs.profileName)
        root.findViewById<Button>(R.id.save_profile).setOnClickListener {
            prefs.profileName = nameField.text.toString()
            Toast.makeText(requireContext(), "Profile saved", Toast.LENGTH_SHORT).show()
        }

        // Rules
        val swFav = root.findViewById<Switch>(R.id.sw_fav_alerts)
        swFav.isChecked = prefs.alertsForFavorites
        swFav.setOnCheckedChangeListener { _, checked -> prefs.alertsForFavorites = checked }
        val swArea = root.findViewById<Switch>(R.id.sw_area_alerts)
        swArea.isChecked = prefs.alertsForArea
        swArea.setOnCheckedChangeListener { _, checked -> prefs.alertsForArea = checked }

        val thrLabel = root.findViewById<TextView>(R.id.threshold_label)
        val thrSeek = root.findViewById<SeekBar>(R.id.threshold_seek)
        thrLabel.text = "Bad-score threshold: below ${prefs.threshold}"
        thrSeek.progress = prefs.threshold - 60
        thrSeek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, progress: Int, fromUser: Boolean) {
                thrLabel.text = "Bad-score threshold: below ${progress + 60}"
            }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {
                prefs.threshold = (sb?.progress ?: 25) + 60
            }
        })

        // Counties
        val countyBox = root.findViewById<LinearLayout>(R.id.county_box)
        countyBox.removeAllViews()
        val monitored = prefs.monitoredCounties
        for (c in app.repository.counties()) {
            val cb = CheckBox(requireContext()).apply {
                text = "$c County"
                isChecked = monitored.contains(c)
                setOnCheckedChangeListener { _, checked ->
                    val cur = prefs.monitoredCounties.toMutableSet()
                    if (checked) cur.add(c) else cur.remove(c)
                    prefs.monitoredCounties = cur
                }
            }
            countyBox.addView(cb)
        }

        // Home presets
        root.findViewById<TextView>(R.id.home_label).text = "My area center: ${prefs.homeLabel}"
        val presetBox = root.findViewById<LinearLayout>(R.id.preset_box)
        presetBox.removeAllViews()
        HOME_PRESETS.chunked(3).forEach { rowPresets ->
            val rowLayout = LinearLayout(requireContext()).apply { orientation = LinearLayout.HORIZONTAL }
            rowPresets.forEach { (label, la, ln) ->
                val b = Button(requireContext()).apply {
                    text = label
                    isAllCaps = false
                    textSize = 12f
                    setOnClickListener {
                        prefs.homeLat = la; prefs.homeLng = ln; prefs.homeLabel = label
                        bind()
                    }
                }
                rowLayout.addView(b)
            }
            presetBox.addView(rowLayout)
        }
        root.findViewById<Button>(R.id.use_location).setOnClickListener {
            (activity as? MainActivity)?.requestLocation()
        }

        val radLabel = root.findViewById<TextView>(R.id.radius_label)
        val radSeek = root.findViewById<SeekBar>(R.id.radius_seek)
        radLabel.text = "Area radius: ${prefs.radiusMiles.toInt()} miles"
        radSeek.progress = prefs.radiusMiles.toInt() - 1
        radSeek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, progress: Int, fromUser: Boolean) {
                radLabel.text = "Area radius: ${progress + 1} miles"
            }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {
                prefs.radiusMiles = ((sb?.progress ?: 9) + 1).toDouble()
            }
        })

        // Sync
        val syncStatus = root.findViewById<TextView>(R.id.sync_status)
        syncStatus.text = if (prefs.lastSyncMs > 0)
            "Last synced: ${DateFormat.getDateTimeInstance().format(Date(prefs.lastSyncMs))}"
        else
            "Not synced yet — the app ships with a statewide snapshot and refreshes itself."
        val main = activity as? MainActivity
        val syncBtn = root.findViewById<Button>(R.id.sync_now)
        syncBtn.isEnabled = main?.syncing != true
        syncBtn.text = if (main?.syncing == true) "Syncing…" else "Sync now"
        syncBtn.setOnClickListener { main?.startSync(includeCounties = true) }
        root.findViewById<TextView>(R.id.sync_report).text = main?.lastReport ?: ""

        // Sources
        root.findViewById<TextView>(R.id.sources_text).text = SourceRegistry.all.joinToString("\n\n") { s ->
            "${s.displayName} — ${s.regionLabel}\nViolation detail: ${if (s.hasViolations) "yes — full why-summaries" else "no — score & date only"} · History: ${if (s.hasHistory) "yes" else "latest only"}"
        }

        // Inbox
        val inbox = prefs.inbox
        root.findViewById<TextView>(R.id.inbox_empty).visibility =
            if (inbox.isEmpty()) View.VISIBLE else View.GONE
        val inboxBox = root.findViewById<LinearLayout>(R.id.inbox_box)
        inboxBox.removeAllViews()
        for (a in inbox) {
            val card = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundResource(R.drawable.card_bg)
                setPadding(28, 20, 28, 20)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, 8, 0, 8) }
                setOnClickListener { (activity as? MainActivity)?.openPlace(a.placeId) }
            }
            card.addView(TextView(requireContext()).apply {
                text = a.title
                textSize = 14.5f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(if (a.lowScore) 0xFFA33A3A.toInt() else 0xFF2E7D32.toInt())
            })
            card.addView(TextView(requireContext()).apply { text = a.body; textSize = 13f })
            card.addView(TextView(requireContext()).apply {
                text = DateFormat.getDateTimeInstance().format(Date(a.whenMs))
                textSize = 11.5f
                setTextColor(0xFF6B7885.toInt())
            })
            inboxBox.addView(card)
        }
    }
}
