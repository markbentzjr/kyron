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
        val ctx = h.itemView.context
        if (p.hasNumericScore) {
            h.score.text = p.score.toString()
            h.score.setTextColor(
                ContextCompat.getColor(
                    ctx,
                    when {
                        p.score >= 95 -> R.color.kyron_green
                        p.score >= 85 -> R.color.kyron_lime_dark
                        else -> R.color.kyron_amber_dark
                    }
                )
            )
        } else {
            // Disposition regions: the badge is the jurisdiction's own
            // result in compact form — never a number Kyron invented.
            h.score.text = p.badgeText
            h.score.setTextColor(
                ContextCompat.getColor(
                    ctx,
                    when (p.resultTone) {
                        1 -> R.color.kyron_green
                        2 -> R.color.kyron_amber_dark
                        3 -> R.color.kyron_red
                        else -> R.color.muted
                    }
                )
            )
        }
        // Photo tile: real OSM map imagery centered on the verified
        // address; monogram letter fallback when ungeocoded.
        if (p.lat != null && p.lng != null) {
            h.mono.visibility = View.GONE
            h.photo.visibility = View.VISIBLE
            h.photo.setImageDrawable(null)
            MapThumbLoader.bind(h.photo, p.lat!!, p.lng!!)
        } else {
            h.photo.visibility = View.GONE
            h.photo.setImageDrawable(null)
            h.mono.visibility = View.VISIBLE
            h.mono.text = p.name.firstOrNull()?.uppercase() ?: "?"
            h.mono.setBackgroundColor(
                ContextCompat.getColor(
                    ctx,
                    when {
                        p.hasNumericScore && p.score >= 85 -> R.color.kyron_green
                        p.hasNumericScore -> R.color.kyron_amber_dark
                        p.resultTone == 1 -> R.color.kyron_green
                        p.resultTone == 3 -> R.color.kyron_red
                        else -> R.color.muted
                    }
                )
            )
        }
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
        h.star.setImageResource(if (fav) R.drawable.ic_star else R.drawable.ic_star_border)
        h.star.setColorFilter(
            ContextCompat.getColor(ctx, if (fav) R.color.star_on else R.color.white)
        )
        h.star.contentDescription = ctx.getString(
            if (fav) R.string.cd_watching else R.string.cd_watch
        )
        h.itemView.setOnClickListener { onOpen(p) }
        h.star.setOnClickListener {
            // Bounce on tap — the actual state flip comes back via submit().
            it.animate().scaleX(0.7f).scaleY(0.7f).setDuration(90).withEndAction {
                it.animate().scaleX(1f).scaleY(1f).setDuration(160)
                    .setInterpolator(android.view.animation.OvershootInterpolator())
                    .start()
            }.start()
            onToggleFavorite(p)
        }
    }

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val score: TextView = v.findViewById(R.id.score)
        val photo: android.widget.ImageView = v.findViewById(R.id.photo)
        val mono: TextView = v.findViewById(R.id.mono)
        val name: TextView = v.findViewById(R.id.name)
        val addr: TextView = v.findViewById(R.id.addr)
        val meta: TextView = v.findViewById(R.id.meta)
        val why: TextView = v.findViewById(R.id.why)
        val star: ImageButton = v.findViewById(R.id.star)
    }
}
