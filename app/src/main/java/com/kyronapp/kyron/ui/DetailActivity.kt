package com.kyronapp.kyron.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.WhySummary
import com.kyronapp.kyron.source.SourceRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_PLACE_ID = "place_id"
    }

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var placeId: String? = null
    private var inspIdx: Int = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        app = application as KyronApplication
        setContentView(R.layout.activity_detail)
        placeId = intent?.getStringExtra(EXTRA_PLACE_ID)
        findViewById<TextView>(R.id.back).setOnClickListener { finish() }
        scope.launch {
            app.repository.load()
            render()
        }
    }

    private fun currentPlace(): Place? = placeId?.let { app.repository.byId(it) }

    private fun render() {
        val place = currentPlace() ?: run {
            findViewById<TextView>(R.id.d_name).text = "Place not found"
            return
        }
        val scoreView = findViewById<TextView>(R.id.d_score)
        scoreView.text = place.score.toString()
        scoreView.setBackgroundResource(
            when {
                place.score >= 95 -> R.drawable.score_green
                place.score >= 85 -> R.drawable.score_lime
                else -> R.drawable.score_amber
            }
        )
        findViewById<TextView>(R.id.d_name).text = place.name
        findViewById<TextView>(R.id.d_addr).text = place.fullAddress()
        findViewById<TextView>(R.id.d_meta).text = "${place.bandLabel} · last inspected ${place.date}"
        findViewById<TextView>(R.id.d_source).text =
            "Source: ${SourceRegistry.byId(place.source)?.displayName ?: place.source}"

        val isFav = app.prefs.favorites.contains(place.id)
        val favBtn = findViewById<Button>(R.id.d_fav)
        favBtn.text = if (isFav) "★ Watching" else "☆ Watch this place"
        favBtn.setOnClickListener {
            app.prefs.toggleFavorite(place.id)
            render()
        }
        findViewById<Button>(R.id.d_directions).setOnClickListener {
            val uri = Uri.parse("geo:0,0?q=${Uri.encode(place.fullAddress())}")
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        }
        findViewById<TextView>(R.id.d_watch_note).text = when {
            isFav && app.prefs.alertsForFavorites -> "🔔 You'll be alerted when this place gets a new score."
            isFav -> "★ Favorite (favorite alerts are off in Alerts settings)."
            else -> ""
        }

        val insps = place.inspections
        val histTitle = findViewById<TextView>(R.id.d_history_title)
        val histLine = findViewById<TextView>(R.id.d_history_line)
        val histScroll = findViewById<View>(R.id.d_history_scroll)
        val chips = findViewById<LinearLayout>(R.id.d_history_chips)
        if (insps.size > 1) {
            histTitle.visibility = View.VISIBLE
            histLine.visibility = View.VISIBLE
            histScroll.visibility = View.VISIBLE
            histLine.text = insps.joinToString(" → ") { it.score.toString() } + "  (newest first)"
            chips.removeAllViews()
            insps.forEachIndexed { i, ins ->
                val b = Button(this).apply {
                    text = "${ins.score} · ${ins.date}"
                    isAllCaps = false
                    setBackgroundResource(if (i == inspIdx) R.drawable.tab_selected else android.R.color.transparent)
                    setOnClickListener { inspIdx = i; render() }
                }
                chips.addView(b)
            }
        } else {
            histTitle.visibility = View.GONE
            histLine.visibility = View.GONE
            histScroll.visibility = View.GONE
        }

        val cur = insps.getOrNull(minOf(inspIdx, maxOf(insps.size - 1, 0)))
        val whyTitle = findViewById<TextView>(R.id.d_why_title)
        val whyText = findViewById<TextView>(R.id.d_why)
        val violCard = findViewById<View>(R.id.d_viol_card)
        val violBox = findViewById<LinearLayout>(R.id.d_viol_box)
        val loadBtn = findViewById<Button>(R.id.d_load)
        val loadMsg = findViewById<TextView>(R.id.d_load_msg)

        // Score-only sources (ADPH, MCHD) never publish violations, so an empty
        // list there means "not published", never "clean inspection".
        val sourceHasViolations = SourceRegistry.byId(place.source)?.hasViolations == true
        if (cur != null) {
            whyTitle.text = "Why a ${cur.score}?"
            whyText.text = when {
                cur.violations.isNotEmpty() -> WhySummary.summarize(cur)
                sourceHasViolations -> WhySummary.summarize(cur)
                else -> WhySummary.bandExplainer(cur.score) +
                    "\n\n${SourceRegistry.byId(place.source)?.displayName ?: "This source"} publishes scores and dates only — the violation detail stays on the paper report posted inside the restaurant, so no item-by-item breakdown is available online."
            }
            violCard.visibility = if (sourceHasViolations) View.VISIBLE else View.GONE
            loadBtn.visibility = View.GONE
            violBox.removeAllViews()
            if (cur.violations.isEmpty() && sourceHasViolations) {
                violBox.addView(TextView(this).apply {
                    text = "No violations recorded on this inspection."
                    setTextColor(0xFF6B7885.toInt())
                })
            }
            for (v in cur.violations) {
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, 14, 0, 14)
                }
                val pts = TextView(this).apply {
                    text = "−${v.points}"
                    setBackgroundResource(R.drawable.pts_bg)
                    setTextColor(0xFFA33A3A.toInt())
                    textSize = 13f
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setPadding(14, 6, 14, 6)
                }
                val col = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(24, 0, 0, 0)
                }
                col.addView(TextView(this).apply { text = v.ruleText; textSize = 13.5f })
                if (v.critical) {
                    col.addView(TextView(this).apply {
                        text = "CRITICAL"
                        setTextColor(0xFFA33A3A.toInt())
                        textSize = 11f
                        setTypeface(typeface, android.graphics.Typeface.BOLD)
                    })
                }
                if (v.inspectorNote.isNotBlank()) {
                    col.addView(TextView(this).apply {
                        text = "Inspector: “${v.inspectorNote}”"
                        setTextColor(0xFF6B7885.toInt())
                        textSize = 12.5f
                    })
                }
                row.addView(pts)
                row.addView(col)
                violBox.addView(row)
            }
        } else {
            whyTitle.text = "Why a ${place.score}?"
            whyText.text = WhySummary.bandExplainer(place.score)
            violCard.visibility = View.GONE
            if (place.detailUrl != null) {
                loadBtn.visibility = View.VISIBLE
                loadBtn.setOnClickListener {
                    loadBtn.isEnabled = false
                    loadBtn.text = "Loading inspection details…"
                    loadMsg.text = ""
                    scope.launch {
                        runCatching { SourceRegistry.jcdh.fetchDetail(place) }
                            .onSuccess { fetched ->
                                if (fetched.isNotEmpty()) {
                                    app.repository.updatePlace(place.copy(inspections = fetched))
                                    inspIdx = 0
                                    render()
                                } else {
                                    loadMsg.text = "The county page didn't include details this time — try again later."
                                }
                            }
                            .onFailure {
                                loadMsg.text = "Couldn't load details (${it.message ?: "network error"}). The county site may be busy."
                            }
                        loadBtn.isEnabled = true
                        loadBtn.text = "Load full inspection details"
                    }
                }
            } else {
                loadBtn.visibility = View.GONE
            }
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
