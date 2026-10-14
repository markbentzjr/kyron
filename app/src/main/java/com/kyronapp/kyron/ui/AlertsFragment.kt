package com.kyronapp.kyron.ui

import android.app.Dialog
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.slider.Slider
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Backup
import com.kyronapp.kyron.source.SourceRegistry
import kotlin.math.roundToInt
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date

/**
 * Alerts (2.1 redesign): alert rules are readable cards, not a settings
 * form. Favorites alerts are a one-tap switch; area alerts summarize
 * themselves in plain language ("Watching Jefferson County · alert me
 * when a new score drops below 85 · within 10 miles of Downtown
 * Birmingham") with Edit / Remove actions. Editing happens in a
 * collapsible editor whose centerpiece is a SEARCHABLE county picker —
 * the 67-checkbox wall is gone. All rule semantics (Prefs/UserStore)
 * are unchanged from LF-2/LF-4.
 */
class AlertsFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var root: View
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var editorOpen: Boolean = false

    private val exportLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri == null || !::app.isInitialized) return@registerForActivityResult
        scope.launch {
            val json = withContext(Dispatchers.IO) {
                Backup.export(app.prefs.store, "2.1", java.time.Instant.now().toString()).toString(2)
            }
            runCatching {
                requireContext().contentResolver.openOutputStream(uri)?.use { it.write(json.toByteArray()) }
            }.onSuccess {
                backupStatus("Backup saved. Keep it somewhere safe — it's the only copy besides this phone.")
            }.onFailure {
                backupStatus("Export failed: ${it.message}")
            }
        }
    }

    private val importLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri == null || !::app.isInitialized) return@registerForActivityResult
        scope.launch {
            val report = withContext(Dispatchers.IO) {
                runCatching {
                    val text = requireContext().contentResolver.openInputStream(uri)
                        ?.bufferedReader()?.readText() ?: error("could not read file")
                    Backup.import(app.prefs.store, JSONObject(text)) { id -> app.repository.placeExists(id) }
                }
            }
            report.onSuccess { r ->
                val extra = if (r.unresolvablePlaceIds.isNotEmpty())
                    " ${r.unresolvablePlaceIds.size} favorite(s) point at places not in this device's catalog (kept anyway for when that region is added)." else ""
                backupStatus("Import done: ${r.inserted} added, ${r.updated} updated, ${r.skipped} already up to date.$extra")
                bind()
            }.onFailure {
                backupStatus("Import failed: ${it.message}")
            }
        }
    }

    private fun backupStatus(msg: String) {
        if (::root.isInitialized) root.findViewById<TextView>(R.id.backup_status)?.text = msg
        Toast.makeText(requireContext(), msg, Toast.LENGTH_LONG).show()
    }

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

    /** Re-bind after external state changes (e.g. a sync finished in MainActivity). */
    fun refresh() {
        if (::root.isInitialized && view != null) bind()
    }

    private fun bind() {
        val prefs = app.prefs
        // Normalize legacy/imported values into the controls' ranges:
        // backups can carry a threshold up to 100 (the pre-2.1 SeekBar's
        // max) or an unbounded radius; the Sliders would throw on those.
        if (prefs.threshold !in 60..99) prefs.threshold = prefs.threshold.coerceIn(60, 99)
        // Radius must also be a whole number: the Slider is discrete
        // (step 1) and throws on fractional values from imported backups.
        val r0 = prefs.radiusMiles
        if (r0 !in 1.0..50.0 || r0 % 1.0 != 0.0) {
            prefs.radiusMiles = r0.coerceIn(1.0, 50.0).roundToInt().toDouble()
        }

        // Profile
        val nameField = root.findViewById<EditText>(R.id.profile_name)
        // Never clobber an unsaved name the user is still typing.
        if (nameField.text.toString() != prefs.profileName && !nameField.hasFocus()) {
            nameField.setText(prefs.profileName)
        }
        root.findViewById<MaterialButton>(R.id.save_profile).setOnClickListener {
            prefs.profileName = nameField.text.toString()
            Toast.makeText(requireContext(), "Profile saved", Toast.LENGTH_SHORT).show()
        }

        // Rule card 1: favorites (one-tap quick-pick)
        val swFav = root.findViewById<MaterialSwitch>(R.id.sw_fav_alerts)
        swFav.setOnCheckedChangeListener(null)
        swFav.isChecked = prefs.alertsForFavorites
        swFav.setOnCheckedChangeListener { _, checked ->
            prefs.alertsForFavorites = checked
            bind()
        }

        // Rule card 2: area alerts — summary + switch + edit/remove
        val swArea = root.findViewById<MaterialSwitch>(R.id.sw_area_alerts)
        swArea.setOnCheckedChangeListener(null)
        swArea.isChecked = prefs.alertsForArea
        swArea.setOnCheckedChangeListener { _, checked ->
            prefs.alertsForArea = checked
            if (checked) editorOpen = true
            bind()
        }
        root.findViewById<TextView>(R.id.area_summary).text = areaSummaryText()
        val removeBtn = root.findViewById<MaterialButton>(R.id.area_remove)
        removeBtn.visibility = if (prefs.alertsForArea) View.VISIBLE else View.GONE
        removeBtn.setOnClickListener {
            prefs.alertsForArea = false
            editorOpen = false
            Toast.makeText(requireContext(), "Area alerts removed. Your counties and settings are kept if you turn them back on.", Toast.LENGTH_LONG).show()
            bind()
        }
        val editor = root.findViewById<View>(R.id.area_editor)
        editor.visibility = if (editorOpen) View.VISIBLE else View.GONE
        root.findViewById<MaterialButton>(R.id.area_edit).setOnClickListener {
            editorOpen = !editorOpen
            editor.visibility = if (editorOpen) View.VISIBLE else View.GONE
        }

        // Counties (inside the editor): summary + searchable picker.
        // LF-4: county alert sync runs against Alabama's ADPH (the only
        // live sync source until a region grows its own, K-06), so this
        // list is Alabama's counties regardless of the browsed region.
        val monitored = prefs.monitoredCounties
        root.findViewById<TextView>(R.id.county_summary).text = when {
            monitored.isEmpty() -> "No counties selected yet — pick at least one to watch."
            monitored.size <= 3 -> "${monitored.size} ${if (monitored.size == 1) "county" else "counties"}: " +
                monitored.sorted().joinToString(", ")
            else -> "${monitored.size} counties: " +
                monitored.sorted().take(3).joinToString(", ") + " and ${monitored.size - 3} more"
        }
        root.findViewById<MaterialButton>(R.id.choose_counties).setOnClickListener { showCountyPicker() }

        // Threshold — plain language, number always visible.
        val thrLabel = root.findViewById<TextView>(R.id.threshold_label)
        val thrSlider = root.findViewById<Slider>(R.id.threshold_slider)
        thrLabel.text = "Alert me when a new score drops below ${prefs.threshold}"
        // Clamp: the pre-2.1 SeekBar allowed up to 100; the Slider range is 60..99
        // and setting an out-of-range value throws.
        val thrClamped = prefs.threshold.coerceIn(60, 99).toFloat()
        if (thrSlider.value != thrClamped) thrSlider.value = thrClamped
        thrSlider.clearOnChangeListeners()
        thrSlider.addOnChangeListener { _, value, _ ->
            thrLabel.text = "Alert me when a new score drops below ${value.toInt()}"
        }
        thrSlider.clearOnSliderTouchListeners()
        thrSlider.addOnSliderTouchListener(object : Slider.OnSliderTouchListener {
            override fun onStartTrackingTouch(slider: Slider) {}
            override fun onStopTrackingTouch(slider: Slider) {
                prefs.threshold = slider.value.toInt()
                bind()
            }
        })

        // Area center: current label + preset chips + device location.
        root.findViewById<TextView>(R.id.home_label).text = "Area center: ${prefs.homeLabel}"
        val presetBox = root.findViewById<ChipGroup>(R.id.preset_box)
        presetBox.removeAllViews()
        for ((label, la, ln) in HOME_PRESETS) {
            val chip = Chip(requireContext()).apply {
                chipMinHeight = 48f * resources.displayMetrics.density
                text = label
                isCheckable = true
                isChecked = prefs.homeLabel == label
                setOnClickListener {
                    prefs.homeLat = la; prefs.homeLng = ln; prefs.homeLabel = label
                    bind()
                }
            }
            presetBox.addView(chip)
        }
        root.findViewById<MaterialButton>(R.id.use_location).setOnClickListener {
            (activity as? MainActivity)?.requestLocation()
        }

        // Radius — plain language.
        val radLabel = root.findViewById<TextView>(R.id.radius_label)
        val radSlider = root.findViewById<Slider>(R.id.radius_slider)
        radLabel.text = "Watch places within ${prefs.radiusMiles.toInt()} miles of my area center"
        val radClamped = prefs.radiusMiles.coerceIn(1.0, 50.0).roundToInt().toFloat()
        if (radSlider.value != radClamped) radSlider.value = radClamped
        radSlider.clearOnChangeListeners()
        radSlider.addOnChangeListener { _, value, _ ->
            radLabel.text = "Watch places within ${value.toInt()} miles of my area center"
        }
        radSlider.clearOnSliderTouchListeners()
        radSlider.addOnSliderTouchListener(object : Slider.OnSliderTouchListener {
            override fun onStartTrackingTouch(slider: Slider) {}
            override fun onStopTrackingTouch(slider: Slider) {
                prefs.radiusMiles = slider.value.toDouble()
                bind()
            }
        })

        // Sync
        val syncStatus = root.findViewById<TextView>(R.id.sync_status)
        syncStatus.text = if (prefs.lastSyncMs > 0)
            "Last synced: ${DateFormat.getDateTimeInstance().format(Date(prefs.lastSyncMs))}"
        else
            "Not synced yet — the app ships with a statewide snapshot and refreshes itself."
        val main = activity as? MainActivity
        val syncBtn = root.findViewById<MaterialButton>(R.id.sync_now)
        syncBtn.isEnabled = main?.syncing != true
        syncBtn.text = if (main?.syncing == true) "Syncing…" else "Sync now"
        syncBtn.setOnClickListener { main?.startSync(includeCounties = true) }
        root.findViewById<TextView>(R.id.sync_report).text = main?.lastReport ?: ""

        // Backup / restore
        root.findViewById<MaterialButton>(R.id.export_backup).setOnClickListener {
            exportLauncher.launch("kyron-backup.json")
        }
        root.findViewById<MaterialButton>(R.id.import_backup).setOnClickListener {
            importLauncher.launch(arrayOf("application/json", "text/plain"))
        }

        // Sources
        root.findViewById<TextView>(R.id.sources_text).text = SourceRegistry.all.joinToString("\n\n") { s ->
            "${s.displayName} — ${s.regionLabel}\nViolation detail: ${if (s.hasViolations) "yes — full why-summaries" else "no — score & date only"} · History: ${if (s.hasHistory) "yes" else "latest only"}"
        }

        bindInbox()
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

    /** Searchable multi-select county picker (2.1). Type to filter, tap
     *  to toggle; the selected count is always visible. Changes apply
     *  only on Done — Cancel leaves the rule untouched. */
    private fun showCountyPicker() {
        val all = app.repository.counties("us-al")
        val working = app.prefs.monitoredCounties.toMutableSet()
        val dialog = Dialog(requireContext())
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
                requireContext(), android.R.layout.simple_list_item_multiple_choice, shown
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
        dialog.findViewById<MaterialButton>(R.id.picker_all).setOnClickListener {
            working.addAll(all)
            refreshList()
        }
        dialog.findViewById<MaterialButton>(R.id.picker_clear).setOnClickListener {
            working.clear()
            refreshList()
        }
        dialog.findViewById<MaterialButton>(R.id.picker_cancel).setOnClickListener { dialog.dismiss() }
        dialog.findViewById<MaterialButton>(R.id.picker_done).setOnClickListener {
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
        root.findViewById<TextView>(R.id.inbox_empty).visibility =
            if (inbox.isEmpty()) View.VISIBLE else View.GONE
        val inboxBox = root.findViewById<LinearLayout>(R.id.inbox_box)
        inboxBox.removeAllViews()
        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()
        for (a in inbox) {
            val card = MaterialCardView(requireContext()).apply {
                radius = dp(10).toFloat()
                cardElevation = dp(1).toFloat()
                setCardBackgroundColor(0xFFFFFFFF.toInt())
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(4), 0, dp(4)) }
                setOnClickListener { (activity as? MainActivity)?.openPlace(a.placeId) }
            }
            val row = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
            }
            val icon = ImageView(requireContext()).apply {
                setImageResource(if (a.lowScore) R.drawable.ic_warning else R.drawable.ic_notifications)
                setColorFilter(
                    ContextCompat.getColor(
                        requireContext(),
                        if (a.lowScore) R.color.kyron_red else R.color.kyron_primary
                    )
                )
                layoutParams = LinearLayout.LayoutParams(dp(24), dp(24))
            }
            val col = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(10), 0, 0, 0)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            col.addView(TextView(requireContext()).apply {
                text = a.title
                textSize = 14.5f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(
                    ContextCompat.getColor(
                        requireContext(),
                        if (a.lowScore) R.color.kyron_red else R.color.ink
                    )
                )
            })
            col.addView(TextView(requireContext()).apply { text = a.body; textSize = 13f })
            col.addView(TextView(requireContext()).apply {
                text = DateFormat.getDateTimeInstance().format(Date(a.whenMs))
                textSize = 11.5f
                setTextColor(ContextCompat.getColor(requireContext(), R.color.muted))
            })
            row.addView(icon)
            row.addView(col)
            card.addView(row)
            inboxBox.addView(card)
        }
    }

    override fun onDestroyView() {
        scope.cancel()
        super.onDestroyView()
    }
}
