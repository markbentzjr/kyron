package com.kyronapp.kyron.ui

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import android.widget.ToggleButton
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.ExploreState
import com.kyronapp.kyron.data.NationalCoverage
import com.kyronapp.kyron.data.PlaceQuery
import com.kyronapp.kyron.data.Regions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Browse (LF-2/LF-3): results come from targeted SQLite queries
 * (FTS text search + structured filters + SQL sort) instead of an
 * in-memory scan of the whole catalog. Every control change is also
 * published to [ExploreState], so the Map applies the identical query —
 * one search drives both surfaces (Presentation Spec priority 1).
 *
 * LF4FIX2: classic Views controls (search field, band toggle row,
 * county/sort spinners, refresh button, guidance card) — the widget
 * family of the device-proven LF-3 build. Query logic is unchanged
 * from LF-4, including the honest-refresh contract: a refresh runs the
 * real sync and the completion callback re-queries.
 */
class BrowseFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var adapter: PlaceAdapter
    private lateinit var listView: RecyclerView
    private lateinit var refreshBtn: Button
    private lateinit var emptyBox: View
    private lateinit var loadingBox: View
    private lateinit var countLabel: TextView
    private lateinit var countyInput: Spinner
    private lateinit var sortInput: Spinner
    private lateinit var bandButtons: Map<Int, ToggleButton>
    private lateinit var searchField: EditText

    private var dataLoaded: Boolean = false
    private var queryJob: Job? = null
    private var query: String = ""
    private var county: String = "All counties"
    private var band: String = "All scores"
    private var sort: String = "Worst first"

    /** LF-N: the active region's result model. Band chip labels, band
     *  semantic, and sort order all follow it (a penalty-scale state's
     *  chips are demerit ranges; a disposition state hides the chips). */
    private var regionModel: String = NationalCoverage.MODEL_SCORE_100_HIGH

    /** LF-4: Browse is scoped to the active region. When the region
     *  changes (Coverage screen), filters that belonged to the old region
     *  (county, score band) are reset — a Jefferson County filter must
     *  never silently follow the user into Florida. */
    private var activeRegionId: String = Regions.ALABAMA.regionId
    private var boundRegionId: String? = null

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var uiPrefs: android.content.SharedPreferences? = null
    private var guideCard: View? = null
    private var boundCounties: List<String> = listOf("All counties")

    companion object {
        private const val PAGE_LIMIT = 1000
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val v = inflater.inflate(R.layout.fragment_browse, container, false)

        listView = v.findViewById(R.id.list)
        refreshBtn = v.findViewById(R.id.refresh_btn)
        emptyBox = v.findViewById(R.id.empty_box)
        loadingBox = v.findViewById(R.id.loading_box)
        countLabel = v.findViewById(R.id.count_label)
        countyInput = v.findViewById(R.id.county_input)
        sortInput = v.findViewById(R.id.sort_input)
        bandButtons = listOf(R.id.band_all, R.id.band_low, R.id.band_mid, R.id.band_high)
            .associateWith { v.findViewById<ToggleButton>(it) }
        searchField = v.findViewById(R.id.search)

        adapter = PlaceAdapter(
            onOpen = { p -> (activity as? MainActivity)?.openPlace(p.id) },
            onToggleFavorite = { p ->
                app.prefs.toggleFavorite(p.id)
                applyFilters()
            }
        )
        listView.layoutManager = LinearLayoutManager(requireContext())
        listView.adapter = adapter

        // First-run guidance card (dismissal remembered on this device).
        val prefs2 = requireContext().getSharedPreferences("kyron_ui", Context.MODE_PRIVATE)
        uiPrefs = prefs2
        val guide = v.findViewById<View>(R.id.guide_card)
        guideCard = guide
        guide.visibility = if (prefs2.getBoolean("guide_dismissed", false)) View.GONE else View.VISIBLE
        v.findViewById<View>(R.id.guide_dismiss).setOnClickListener {
            prefs2.edit().putBoolean("guide_dismissed", true).apply()
            guide.visibility = View.GONE
        }

        searchField.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) { query = s?.toString() ?: ""; applyFilters() }
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
        })

        // Band toggles behave as a radio group: exactly one is always
        // selected, and tapping the selected one keeps it selected.
        bandButtons.forEach { (id, btn) ->
            btn.setOnClickListener {
                selectBand(id)
                band = bandLabel(id)
                applyFilters()
            }
        }
        // LF-N: chip labels are region-model specific; the default first
        // bind happens in bindRegion().
        selectBand(R.id.band_all)

        // Default adapters immediately, so the spinners are never empty
        // in the window before the region's data binds. Selection
        // callbacks only act when the value actually changes, which
        // makes programmatic re-syncs (bindRegion, clearFilters) safe.
        sortInput.adapter = spinnerAdapter(
            listOf("Worst first", "Best first", "Most recent", "Name A–Z")
        )
        countyInput.adapter = spinnerAdapter(boundCounties)
        countyInput.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, pos: Int, id: Long) {
                val value = parent.getItemAtPosition(pos)?.toString() ?: "All counties"
                if (value != county) {
                    county = value
                    applyFilters()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }
        sortInput.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, pos: Int, id: Long) {
                val value = parent.getItemAtPosition(pos)?.toString() ?: "Worst first"
                if (value != sort) {
                    sort = value
                    applyFilters()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }
        syncSpinner(countyInput, county)
        syncSpinner(sortInput, sort)

        v.findViewById<View>(R.id.empty_clear).setOnClickListener { clearFilters() }

        refreshBtn.setOnClickListener {
            val act = activity as? MainActivity
            if (act != null) {
                // Honest refresh (the pull-to-refresh contract, kept):
                // the button shows progress until the sync completes,
                // then the follow-up query re-renders the list.
                refreshBtn.isEnabled = false
                refreshBtn.text = "Refreshing…"
                act.startSync(includeCounties = false) {
                    if (isAdded) {
                        refreshBtn.isEnabled = true
                        refreshBtn.text = "Refresh"
                        applyFilters()
                    }
                }
            } else {
                applyFilters()
            }
        }

        updateLoadState()
        scope.launch {
            app.repository.load()
            dataLoaded = true
            bindRegion()
            updateLoadState()
            applyFilters()
        }
        return v
    }

    private fun spinnerAdapter(items: List<String>): ArrayAdapter<String> =
        ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, items)
            .apply { setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item) }

    /** Point a spinner at [value] (no-op when absent). The selection
     *  listeners ignore values equal to the current state, so syncing
     *  never re-fires a query by itself. */
    private fun syncSpinner(spinner: Spinner, value: String) {
        val adapter = spinner.adapter ?: return
        for (i in 0 until adapter.count) {
            if (adapter.getItem(i)?.toString() == value) {
                if (spinner.selectedItemPosition != i) spinner.setSelection(i)
                return
            }
        }
    }

    private fun bandLabel(id: Int): String {
        // LF-N: chip labels come from the ACTIVE region's own result
        // model ("Below 85" on a 0–100 scale; "10–19" penalty points on
        // an Alabama-forbidden demerit scale, etc.). The band vocabulary
        // is shared with PlaceRepository.searchPlaces and MapFragment.
        val bands = NationalCoverage.bands(regionModel)
        return when (id) {
            R.id.band_low -> bands.getOrElse(1) { "All scores" }
            R.id.band_mid -> bands.getOrElse(2) { "All scores" }
            R.id.band_high -> bands.getOrElse(3) { "All scores" }
            else -> "All scores"
        }
    }

    /** Radio behavior for the band toggle row. */
    private fun selectBand(selectedId: Int) {
        if (!::bandButtons.isInitialized) return
        bandButtons.forEach { (id, btn) -> btn.isChecked = id == selectedId }
    }

    private fun clearFilters() {
        query = ""
        searchField.setText("")
        county = "All counties"
        syncSpinner(countyInput, county)
        band = "All scores"
        selectBand(R.id.band_all)
        applyFilters()
    }

    /** (Re)bind controls to the active region: county list, and — for
     *  regions whose jurisdiction does not publish numeric 0–100-style
     *  scores — adapter chip labels or hide the band row entirely, and
     *  swap score sorts for sorts that make sense in the model. */
    private fun bindRegion() {
        val regionId = app.regions.activeRegionId()
        activeRegionId = regionId
        // LF-N hardening: the region's model resolves from the REGISTRY
        // (per-source semantics live there), never from the legacy
        // two-value Regions mapping alone — but the legacy mapping stays
        // as the fallback when the registry hasn't loaded in this process.
        val states = com.kyronapp.kyron.data.NationalCoverage.cached()
            ?: runCatching {
                com.kyronapp.kyron.data.NationalCoverage.load(requireContext())
            }.getOrDefault(emptyList())
        regionModel = com.kyronapp.kyron.data.NationalCoverage
            .byRegionId(states, regionId)?.resultModel
            ?: Regions.nationalModel(app.regions.activeInfo())
        // Always re-sync the spinners with the fragment's own state first:
        // after a view recreation (rotation, process restore) the views
        // are recreated empty while these vars hold the truth — and the
        // adapters live in the (recreated) view, not here.
        if (::countyInput.isInitialized) {
            if (countyInput.adapter == null) {
                countyInput.adapter = spinnerAdapter(boundCounties)
            }
            syncSpinner(countyInput, county)
        }
        if (::sortInput.isInitialized) syncSpinner(sortInput, sort)
        if (boundRegionId == regionId) return
        boundRegionId = regionId
        county = "All counties"
        syncSpinner(countyInput, county)
        val info = app.regions.activeInfo()
        view?.findViewById<TextView>(R.id.loading_label)?.text =
            "Loading ${info.displayName} restaurants…"
        val numeric = NationalCoverage.isNumeric(regionModel)
        val chipRow = view?.findViewById<View>(R.id.band_scroll)
        if (numeric) {
            chipRow?.visibility = View.VISIBLE
            // Re-label the chips for this region's model (penalty scales
            // get demerit ranges; 0–100 scales keep their labels).
            val bands = NationalCoverage.bands(regionModel)
            bandButtons[R.id.band_low]?.text = bands.getOrElse(1) { "" }
            bandButtons[R.id.band_mid]?.text = bands.getOrElse(2) { "" }
            bandButtons[R.id.band_high]?.text = bands.getOrElse(3) { "" }
            if (band == "All scores") selectBand(R.id.band_all)
        } else {
            chipRow?.visibility = View.GONE
            band = "All scores"
            selectBand(R.id.band_all)
            if (sort == "Worst first" || sort == "Best first") sort = "Most recent"
        }
        val sorts = if (numeric) {
            val worst = NationalCoverage.scoreSortLabel(regionModel)
            val best = if (regionModel == NationalCoverage.MODEL_PENALTY_LOW)
                "Fewest penalty points first" else "Best first"
            listOf(worst, best, "Most recent", "Name A–Z")
        } else listOf("Most recent", "Name A–Z")
        sortInput.adapter = spinnerAdapter(sorts)
        syncSpinner(sortInput, sort)
        scope.launch {
            val counties = listOf("All counties") + app.repository.counties(regionId)
            if (!isAdded) return@launch
            boundCounties = counties
            countyInput.adapter = spinnerAdapter(counties)
            syncSpinner(countyInput, county)
        }
    }

    private fun updateLoadState() {
        if (!::loadingBox.isInitialized) return
        loadingBox.visibility = if (dataLoaded) View.GONE else View.VISIBLE
        if (!dataLoaded) emptyBox.visibility = View.GONE
    }

    private fun applyFilters() {
        if (!::adapter.isInitialized) return
        val spec = PlaceQuery(
            text = query,
            county = if (county == "All counties") null else county,
            band = band,
            sort = sort,
            limit = PAGE_LIMIT
        )
        // One query drives both surfaces.
        ExploreState.update(spec)
        val loaded = dataLoaded
        val regionId = activeRegionId
        queryJob?.cancel()
        queryJob = scope.launch {
            try {
                val list = app.repository.searchPlaces(spec, regionId, regionModel)
                if (!isAdded) return@launch
                adapter.submit(list, app.prefs.favorites)
                countLabel.text = if (loaded) {
                    if (list.size >= PAGE_LIMIT) "${list.size}+ places" else "${list.size} places"
                } else ""
                emptyBox.visibility = if (loaded && list.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // A failed query keeps the current list. (Refresh-button
                // state is owned by the sync completion callback, not by
                // individual queries.)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Guide visibility comes from the pref alone, never from any
        // framework-restored view state.
        guideCard?.visibility =
            if (uiPrefs?.getBoolean("guide_dismissed", false) == true) View.GONE else View.VISIBLE
        if (dataLoaded) bindRegion()
        applyFilters()
    }

    override fun onDestroyView() {
        scope.cancel()
        super.onDestroyView()
    }
}
