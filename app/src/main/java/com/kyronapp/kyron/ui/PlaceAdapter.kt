package com.kyronapp.kyron.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.WhySummary

class PlaceAdapter(
    private val onOpen: (Place) -> Unit,
    private val onToggleFavorite: (Place) -> Unit
) : RecyclerView.Adapter<PlaceAdapter.VH>() {

    var items: List<Place> = emptyList()
    var favorites: Set<String> = emptySet()

    fun submit(list: List<Place>, favs: Set<String>) {
        items = list
        favorites = favs
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context).inflate(R.layout.item_place, parent, false)
        return VH(v)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(h: VH, position: Int) {
        val p = items[position]
        if (p.hasNumericScore) {
            h.score.textSize = 19f
            h.score.text = p.score.toString()
            h.score.setBackgroundResource(
                when {
                    p.score >= 95 -> R.drawable.score_green
                    p.score >= 85 -> R.drawable.score_lime
                    else -> R.drawable.score_amber
                }
            )
        } else {
            // Disposition regions: the badge is the jurisdiction's own
            // result in compact form, colored by tone — never a number
            // Kyron invented. The full native text is in the meta line.
            h.score.textSize = 10f
            h.score.text = p.badgeText
            h.score.setBackgroundResource(
                when (p.resultTone) {
                    1 -> R.drawable.score_green
                    2 -> R.drawable.score_amber
                    3 -> R.drawable.score_red
                    else -> R.drawable.score_gray
                }
            )
        }
        h.score.setTextColor(0xFFFFFFFF.toInt())
        h.name.text = p.name
        h.addr.text = "${p.address} · ${p.city}"
        h.meta.text = if (p.hasNumericScore) {
            "${p.bandLabel} · inspected ${p.date} · ${p.county} Co."
        } else {
            buildString {
                append(p.nativeResult.ifBlank { "No inspection on file" })
                if (p.date.isNotBlank()) append(" · inspected ${p.date}")
                append(" · ${p.county} Co.")
            }
        }
        // Only claim a "why" when the source actually published violations —
        // score-only sources (ADPH, MCHD) carry dated scores without detail.
        // Disposition places get their latest native result restated, which
        // is all the source claims — nothing derived.
        val firstInsp = p.inspections.firstOrNull()
        val why = when {
            !p.hasNumericScore -> firstInsp
                ?.takeIf { it.nativeResult.isNotBlank() }
                ?.let { "Latest result: ${it.nativeResult} (${it.date})" }
            else -> firstInsp
                ?.takeIf { it.violations.isNotEmpty() }
                ?.let { WhySummary.summarize(it) }
        }
        if (why != null) {
            h.why.visibility = View.VISIBLE
            h.why.text = why
        } else {
            h.why.visibility = View.GONE
        }
        val fav = favorites.contains(p.id)
        val ctx = h.itemView.context
        h.star.setImageResource(if (fav) R.drawable.ic_star else R.drawable.ic_star_border)
        h.star.setColorFilter(
            ContextCompat.getColor(ctx, if (fav) R.color.star_on else R.color.muted)
        )
        h.star.contentDescription = ctx.getString(
            if (fav) R.string.cd_watching else R.string.cd_watch
        )
        h.itemView.setOnClickListener { onOpen(p) }
        h.star.setOnClickListener { onToggleFavorite(p) }
    }

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val score: TextView = v.findViewById(R.id.score)
        val name: TextView = v.findViewById(R.id.name)
        val addr: TextView = v.findViewById(R.id.addr)
        val meta: TextView = v.findViewById(R.id.meta)
        val why: TextView = v.findViewById(R.id.why)
        val star: ImageButton = v.findViewById(R.id.star)
    }
}
