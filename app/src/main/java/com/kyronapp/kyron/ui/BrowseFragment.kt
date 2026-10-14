package com.kyronapp.kyron.ui

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.chip.ChipGroup
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.ExploreState
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
 * 2.1: Material 3 controls — outlined search field, filter chips,
 * exposed-dropdown county/sort pickers, cards, pull-to-refresh, and a
 * first-run guidance card. Query logic is unchanged from LF-4.
 */
class BrowseFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var adapter: PlaceAdapter
    private lateinit var listView: RecyclerView
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var emptyBox: View
    private lateinit var loadingBox: View
    private lateinit var countLabel: TextView
    private lateinit var countyInput: MaterialAutoCompleteTextView
    private lateinit var sortInput: MaterialAutoCompleteTextView
    private lateinit var bandGroup: ChipGroup
    private lateinit var searchField: EditText

    private var dataLoaded: Boolean = false
    private var queryJob: Job? = null
    private var query: String = ""
    private var county: String = "All counties"
    private var band: String = "All scores"
    private var sort: String = "Worst first"

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
        swipe = v.findViewById(R.id.swipe)
        emptyBox = v.findViewById(R.id.empty_box)
        loadingBox = v.findViewById(R.id.loading_box)
        countLabel = v.findViewById(R.id.count_label)
        countyInput = v.findViewById(R.id.county_input)
        sortInput = v.findViewById(R.id.sort_input)
        bandGroup = v.findViewById(R.id.band_group)
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

        bandGroup.setOnCheckedStateChangeListener { _, checkedIds ->
            band = when (checkedIds.firstOrNull()) {
                R.id.band_low -> "Below 85"
                R.id.band_mid -> "85–94"
                R.id.band_high -> "95+"
                else -> "All scores"
            }
            applyFilters()
        }
        bandGroup.check(R.id.band_all)

        // Default adapters immediately, so the dropdowns are never empty
        // in the window before the region's data binds.
        sortInput.setAdapter(
            ArrayAdapter(requireContext(), android.R.layout.simple_dropdown_item_1line,
                listOf("Worst first", "Best first", "Most recent", "Name A–Z"))
        )
        countyInput.setAdapter(
            ArrayAdapter(requireContext(), android.R.layout.simple_dropdown_item_1line, boundCounties)
        )
        countyInput.setOnItemClickListener { parent, _, pos, _ ->
            county = parent.adapter.getItem(pos)?.toString() ?: "All counties"
            applyFilters()
        }
        sortInput.setOnItemClickListener { parent, _, pos, _ ->
            sort = parent.adapter.getItem(pos)?.toString() ?: "Worst first"
            applyFilters()
        }
        countyInput.setText(county, false)
        sortInput.setText(sort, false)

        v.findViewById<View>(R.id.empty_clear).setOnClickListener { clearFilters() }

        swipe.setOnRefreshListener {
            val act = activity as? MainActivity
            if (act != null) {
                // Re-query when the sync lands; the spinner stops when
                // that query completes (see applyFilters' finally).
                act.startSync(includeCounties = false) { if (isAdded) applyFilters() }
            } else {
                swipe.isRefreshing = false
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

    private fun clearFilters() {
        query = ""
        searchField.setText("")
        county = "All counties"
        countyInput.setText(county, false)
        band = "All scores"
        bandGroup.check(R.id.band_all)
        applyFilters()
    }

    /** (Re)bind controls to the active region: county list, and — for
     *  regions whose jurisdiction publishes outcomes instead of scores —
     *  hide the score-band chips and score sorts, which would otherwise
     *  be filters over a number that doesn't exist there. */
    private fun bindRegion() {
        val regionId = app.regions.activeRegionId()
        activeRegionId = regionId
        // Always re-sync the dropdowns with the fragment's own state first:
        // after a view recreation (rotation, process restore) the framework
        // can restore stale text into the fields while these vars hold the
        // truth — and the adapters live in the (recreated) view, not here.
        if (::countyInput.isInitialized) {
            countyInput.setText(county, false)
            if (countyInput.adapter == null) {
                countyInput.setAdapter(
                    ArrayAdapter(requireContext(), android.R.layout.simple_dropdown_item_1line, boundCounties)
                )
            }
        }
        if (::sortInput.isInitialized) sortInput.setText(sort, false)
        if (boundRegionId == regionId) return
        boundRegionId = regionId
        county = "All counties"
        countyInput.setText(county, false)
        val info = app.regions.activeInfo()
        view?.findViewById<TextView>(R.id.loading_label)?.text =
            "Loading ${info.displayName} restaurants…"
        val disposition = info.scoreModel == Regions.MODEL_DISPOSITION
        view?.findViewById<View>(R.id.band_scroll)?.visibility =
            if (disposition) View.GONE else View.VISIBLE
        if (disposition) {
            band = "All scores"
            bandGroup.check(R.id.band_all)
            if (sort == "Worst first" || sort == "Best first") sort = "Most recent"
        }
        val sorts = if (disposition) listOf("Most recent", "Name A–Z")
        else listOf("Worst first", "Best first", "Most recent", "Name A–Z")
        sortInput.setAdapter(
            ArrayAdapter(requireContext(), android.R.layout.simple_dropdown_item_1line, sorts)
        )
        sortInput.setText(sort, false)
        scope.launch {
            val counties = listOf("All counties") + app.repository.counties(regionId)
            if (!isAdded) return@launch
            boundCounties = counties
            countyInput.setAdapter(
                ArrayAdapter(requireContext(), android.R.layout.simple_dropdown_item_1line, counties)
            )
            countyInput.setText(county, false)
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
                val list = app.repository.searchPlaces(spec, regionId)
                if (!isAdded) return@launch
                adapter.submit(list, app.prefs.favorites)
                countLabel.text = if (loaded) {
                    if (list.size >= PAGE_LIMIT) "${list.size}+ places" else "${list.size} places"
                } else ""
                emptyBox.visibility = if (loaded && list.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // A failed query keeps the current list; the spinner must
                // still stop (finally below).
            } finally {
                if (::swipe.isInitialized) swipe.isRefreshing = false
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
