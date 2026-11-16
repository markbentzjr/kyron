package com.kyronapp.kyron.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.ExploreState
import com.kyronapp.kyron.data.NationalCoverage
import com.kyronapp.kyron.data.Regions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Landing tab: greeting + region context, a hero search that routes into
 * Browse with the query pre-filled, honest per-region stats, and shortcut
 * cards into the other tabs / Coverage. Read-only — every action navigates.
 */
class HomeFragment : Fragment() {

    private lateinit var greeting: TextView
    private lateinit var regionSub: TextView
    private lateinit var search: EditText
    private lateinit var statPlaces: TextView
    private lateinit var statWatched: TextView
    private lateinit var statSync: TextView
    private lateinit var modelTitle: TextView
    private lateinit var modelBody: TextView

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_home, container, false)

    override fun onViewCreated(v: View, savedInstanceState: Bundle?) {
        greeting = v.findViewById(R.id.home_greeting)
        regionSub = v.findViewById(R.id.home_region_sub)
        search = v.findViewById(R.id.home_search)
        statPlaces = v.findViewById(R.id.stat_places)
        statWatched = v.findViewById(R.id.stat_watched)
        statSync = v.findViewById(R.id.stat_sync)
        modelTitle = v.findViewById(R.id.home_model_title)
        modelBody = v.findViewById(R.id.home_model_body)

        search.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                openBrowse(search.text.toString().trim())
                true
            } else false
        }

        val act = activity as? MainActivity
        v.findViewById<View>(R.id.action_browse).setOnClickListener { openBrowse("") }
        v.findViewById<View>(R.id.action_map).setOnClickListener { act?.selectTab(2) }
        // The watch list lives on this screen now; this card routes to
        // the alert rules + inbox tab.
        v.findViewById<View>(R.id.action_watch).setOnClickListener { act?.selectTab(3) }
        v.findViewById<View>(R.id.action_regions).setOnClickListener {
            startActivity(Intent(requireContext(), CoverageActivity::class.java))
        }
    }

    override fun onResume() {
        super.onResume()
        val app = (activity?.application as? KyronApplication) ?: return
        val info = app.regions.activeInfo()

        greeting.text = when (java.util.Calendar.getInstance()
            .get(java.util.Calendar.HOUR_OF_DAY)) {
            in 5..11 -> getString(R.string.home_greeting_morning)
            in 12..16 -> getString(R.string.home_greeting_afternoon)
            else -> getString(R.string.home_greeting_evening)
        }
        regionSub.text = getString(R.string.home_region_sub, info.displayName)

        val model = Regions.nationalModel(info)
        modelTitle.text = getString(R.string.home_model_title, info.displayName)
        modelBody.text = getString(
            when (model) {
                NationalCoverage.MODEL_SCORE_100_HIGH -> R.string.home_model_score
                NationalCoverage.MODEL_PENALTY_LOW -> R.string.home_model_penalty
                NationalCoverage.MODEL_LETTER_GRADE -> R.string.home_model_grade
                NationalCoverage.MODEL_PASS_FAIL -> R.string.home_model_passfail
                NationalCoverage.MODEL_DISPOSITION -> R.string.home_model_disposition
                NationalCoverage.MODEL_VIOLATIONS_ONLY -> R.string.home_model_violations
                else -> R.string.home_model_unknown
            }
        )

        statWatched.text = "%,d".format(app.prefs.favorites.size)
        val syncMs = app.prefs.lastSyncMs
        statSync.text = if (syncMs <= 0L) getString(R.string.home_sync_never)
        else {
            val hrs = (System.currentTimeMillis() - syncMs) / 3_600_000L
            when {
                hrs < 1 -> getString(R.string.home_sync_lt1h)
                hrs < 48 -> getString(R.string.home_sync_hours, hrs)
                else -> getString(R.string.home_sync_days, hrs / 24)
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            val places = withContext(Dispatchers.IO) {
                app.repository.regionPlaceCount(info.regionId)
            }
            statPlaces.text = "%,d".format(places)
        }

        // "Watching": the integrated Favorites surface — starred places
        // with their current result, worst-looking first.
        val watched = app.repository.places.value
            .filter { app.prefs.favorites.contains(it.id) }
            .sortedWith(compareBy { if (it.hasNumericScore) it.score else Int.MAX_VALUE })
        bindWatch(watched, model)

        // "Needs attention": the region's worst current results, sorted
        // model-aware (highest demerits / lowest scores first).
        viewLifecycleOwner.lifecycleScope.launch {
            val worst = withContext(Dispatchers.IO) {
                app.repository.searchPlaces(
                    com.kyronapp.kyron.data.PlaceQuery(limit = 5),
                    info.regionId, model
                )
            }
            bindNeeds(worst, info.displayName, model)
        }
    }

    private fun bindWatch(
        places: List<com.kyronapp.kyron.data.Place>,
        model: String
    ) {
        val block = view?.findViewById<View>(R.id.home_watch_block) ?: return
        val list = view?.findViewById<android.widget.LinearLayout>(R.id.home_watch_list) ?: return
        list.removeAllViews()
        if (places.isEmpty()) {
            block.visibility = View.GONE
            return
        }
        block.visibility = View.VISIBLE
        view?.findViewById<TextView>(R.id.home_watch_title)?.text =
            getString(R.string.home_watch_title, places.size)
        places.take(8).forEach { p ->
            list.addView(placeRow(p, model))
        }
    }

    private fun bindNeeds(
        places: List<com.kyronapp.kyron.data.Place>,
        regionName: String,
        model: String
    ) {
        val block = view?.findViewById<View>(R.id.home_needs_block) ?: return
        val list = view?.findViewById<android.widget.LinearLayout>(R.id.home_needs_list) ?: return
        list.removeAllViews()
        if (places.isEmpty()) {
            block.visibility = View.GONE
            return
        }
        block.visibility = View.VISIBLE
        view?.findViewById<TextView>(R.id.home_needs_title)?.text =
            getString(R.string.home_needs_title, regionName)
        places.forEach { p ->
            list.addView(placeRow(p, model))
        }
    }

    /** Compact place row: colored status strip + name + result/date/city,
     *  tap → Detail. Shared by the Watching and Needs-attention lists. */
    private fun placeRow(
        p: com.kyronapp.kyron.data.Place,
        model: String
    ): View {
        val dp = resources.displayMetrics.density
        val row = android.widget.LinearLayout(requireContext()).apply {
                orientation = android.widget.LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                setBackgroundResource(R.drawable.card_bg)
                setPadding(0, 0, (14 * dp).toInt(), 0)
                isClickable = true; isFocusable = true
                stateListAnimator = android.animation.AnimatorInflater
                    .loadStateListAnimator(context, R.animator.press_scale)
                setOnClickListener {
                    (activity as? MainActivity)?.openPlace(p.id)
                }
            }
            // Left status strip: model-aware worst color.
            val strip = View(requireContext()).apply {
                setBackgroundColor(worstColor(p, model))
            }
            row.addView(strip, android.widget.LinearLayout.LayoutParams((5 * dp).toInt(), -1).apply {
                marginEnd = (12 * dp).toInt()
            })
            val texts = android.widget.LinearLayout(requireContext()).apply {
                orientation = android.widget.LinearLayout.VERTICAL
                setPadding(0, (12 * dp).toInt(), 0, (12 * dp).toInt())
            }
            texts.addView(TextView(requireContext()).apply {
                text = p.name
                setTextColor(androidx.core.content.ContextCompat.getColor(context, R.color.ink))
                textSize = 14f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
            })
            val badge = if (p.hasNumericScore) p.score.toString()
            else com.kyronapp.kyron.data.Place.shortResultLabel(p.nativeResult)
            texts.addView(TextView(requireContext()).apply {
                text = buildString {
                    append(badge)
                    if (p.date.isNotBlank()) append(" · ${p.date}")
                    if (p.city.isNotBlank()) append(" · ${p.city}")
                }
                setTextColor(androidx.core.content.ContextCompat.getColor(context, R.color.muted))
                textSize = 12f
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
            })
        row.addView(texts, android.widget.LinearLayout.LayoutParams(0, -2, 1f))
        row.layoutParams = android.widget.LinearLayout.LayoutParams(-1, -2).apply {
            bottomMargin = (8 * dp).toInt()
        }
        return row
    }

    /** Worst-first strip color, model-aware (mirrors MapFragment's pin scale). */
    private fun worstColor(p: com.kyronapp.kyron.data.Place, model: String): Int {
        if (!p.hasNumericScore) return when (p.resultTone) {
            1 -> 0xFF2E9E4F.toInt()
            2 -> 0xFFE8A13A.toInt()
            3 -> 0xFFD9534F.toInt()
            else -> 0xFF8A97A5.toInt()
        }
        return when (model) {
            NationalCoverage.MODEL_PENALTY_LOW -> when {
                p.score <= 13 -> 0xFF2E9E4F.toInt()
                p.score <= 27 -> 0xFFE8A13A.toInt()
                else -> 0xFFD9534F.toInt()
            }
            else -> when {
                p.score >= 95 -> 0xFF2E9E4F.toInt()
                p.score >= 85 -> 0xFF7AB648.toInt()
                else -> 0xFFE8A13A.toInt()
            }
        }
    }

    /** Routes into Browse (tab index 1) with the query staged in
     *  [ExploreState.pendingSearch]; Browse applies it on show. */
    private fun openBrowse(q: String) {
        ExploreState.pendingSearch = q
        (activity as? MainActivity)?.selectTab(1)
    }
}
