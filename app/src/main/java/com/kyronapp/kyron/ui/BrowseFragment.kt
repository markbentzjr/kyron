package com.kyronapp.kyron.ui

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
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Place
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class BrowseFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var adapter: PlaceAdapter
    private lateinit var listView: RecyclerView
    private lateinit var emptyLabel: TextView
    private lateinit var countLabel: TextView
    private lateinit var countySpinner: Spinner
    private lateinit var sortSpinner: Spinner

    private var allPlaces: List<Place> = emptyList()
    private var query: String = ""
    private var county: String = "All counties"
    private var band: String = "All scores"
    private var sort: String = "Worst first"
    private val bandButtons = mutableListOf<Pair<String, Button>>()

    private val dateFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("M/d/yyyy")
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val v = inflater.inflate(R.layout.fragment_browse, container, false)

        listView = v.findViewById(R.id.list)
        emptyLabel = v.findViewById(R.id.empty_label)
        countLabel = v.findViewById(R.id.count_label)
        countySpinner = v.findViewById(R.id.county_spinner)
        sortSpinner = v.findViewById(R.id.sort_spinner)

        adapter = PlaceAdapter(
            onOpen = { p -> (activity as? com.kyronapp.kyron.MainActivity)?.openPlace(p.id) },
            onToggleFavorite = { p ->
                app.prefs.toggleFavorite(p.id)
                applyFilters()
            }
        )
        listView.layoutManager = LinearLayoutManager(requireContext())
        listView.adapter = adapter

        val search = v.findViewById<EditText>(R.id.search)
        search.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) { query = s?.toString() ?: ""; applyFilters() }
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
        })

        val bandRow = v.findViewById<LinearLayout>(R.id.band_row)
        listOf("All scores", "Below 85", "85–94", "95+").forEach { b ->
            val btn = Button(requireContext()).apply {
                text = b
                isAllCaps = false
                setOnClickListener { band = b; styleBandButtons(); applyFilters() }
            }
            bandButtons += b to btn
            bandRow.addView(btn)
        }
        styleBandButtons()

        sortSpinner.adapter = ArrayAdapter(
            requireContext(), android.R.layout.simple_spinner_dropdown_item,
            listOf("Worst first", "Best first", "Most recent", "Name A–Z")
        )
        sortSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, pos: Int, id: Long) {
                sort = parent?.getItemAtPosition(pos)?.toString() ?: "Worst first"
                applyFilters()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        countySpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, pos: Int, id: Long) {
                county = parent?.getItemAtPosition(pos)?.toString() ?: "All counties"
                applyFilters()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        scope.launch {
            app.repository.places.collectLatest { places ->
                allPlaces = places
                val counties = listOf("All counties") + places.map { it.county }.distinct().sorted()
                val current = countySpinner.selectedItem?.toString()
                countySpinner.adapter = ArrayAdapter(
                    requireContext(), android.R.layout.simple_spinner_dropdown_item, counties
                )
                val idx = counties.indexOf(current ?: county)
                if (idx >= 0) countySpinner.setSelection(idx)
                applyFilters()
            }
        }
        return v
    }

    private fun styleBandButtons() {
        bandButtons.forEach { (b, btn) ->
            val selected = b == band
            btn.setBackgroundResource(if (selected) R.drawable.tab_selected else android.R.color.transparent)
        }
    }

    private fun parseDateMs(d: String): Long = runCatching {
        LocalDate.parse(d, dateFmt).toEpochDay() * 86_400_000L
    }.getOrDefault(0L)

    private fun applyFilters() {
        if (!::adapter.isInitialized) return
        var list = allPlaces.filter { p ->
            (county == "All counties" || p.county == county) &&
                (when (band) {
                    "Below 85" -> p.score < 85
                    "85–94" -> p.score in 85..94
                    "95+" -> p.score >= 95
                    else -> true
                }) &&
                (query.isBlank() || p.name.contains(query, true) ||
                    p.city.contains(query, true) || p.address.contains(query, true))
        }
        list = when (sort) {
            "Worst first" -> list.sortedBy { it.score }
            "Best first" -> list.sortedByDescending { it.score }
            "Most recent" -> list.sortedByDescending { parseDateMs(it.date) }
            else -> list.sortedBy { it.name.lowercase() }
        }
        adapter.submit(list, app.prefs.favorites)
        countLabel.text = "${list.size} places"
        emptyLabel.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }

    override fun onResume() {
        super.onResume()
        applyFilters()
    }

    override fun onDestroyView() {
        scope.cancel()
        super.onDestroyView()
    }
}
