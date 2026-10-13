package com.kyronapp.kyron.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
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
        h.score.text = p.score.toString()
        h.score.setBackgroundResource(
            when {
                p.score >= 95 -> R.drawable.score_green
                p.score >= 85 -> R.drawable.score_lime
                else -> R.drawable.score_amber
            }
        )
        h.name.text = p.name
        h.addr.text = "${p.address} · ${p.city}"
        h.meta.text = "${p.bandLabel} · inspected ${p.date} · ${p.county} Co."
        // Only claim a "why" when the source actually published violations —
        // score-only sources (ADPH, MCHD) carry dated scores without detail.
        val why = p.inspections.firstOrNull()
            ?.takeIf { it.violations.isNotEmpty() }
            ?.let { WhySummary.summarize(it) }
        if (why != null) {
            h.why.visibility = View.VISIBLE
            h.why.text = why
        } else {
            h.why.visibility = View.GONE
        }
        val fav = favorites.contains(p.id)
        h.star.text = if (fav) "★" else "☆"
        h.star.setTextColor(if (fav) 0xFFF2B01E.toInt() else 0xFFB9C4CE.toInt())
        h.itemView.setOnClickListener { onOpen(p) }
        h.star.setOnClickListener { onToggleFavorite(p) }
    }

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val score: TextView = v.findViewById(R.id.score)
        val name: TextView = v.findViewById(R.id.name)
        val addr: TextView = v.findViewById(R.id.addr)
        val meta: TextView = v.findViewById(R.id.meta)
        val why: TextView = v.findViewById(R.id.why)
        val star: TextView = v.findViewById(R.id.star)
    }
}
