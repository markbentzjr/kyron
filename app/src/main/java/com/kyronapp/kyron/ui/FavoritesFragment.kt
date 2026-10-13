package com.kyronapp.kyron.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class FavoritesFragment : Fragment() {

    private lateinit var app: KyronApplication
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var adapter: PlaceAdapter
    private lateinit var emptyLabel: TextView

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val root = LinearLayout(requireContext()).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        emptyLabel = TextView(requireContext()).apply {
            text = "No favorites yet.\n\nTap the ☆ on any place and Kyron will watch it for you — when it gets a new inspection score, you'll get an alert."
            setPadding(36, 36, 36, 36)
            textSize = 14f
            visibility = View.GONE
        }
        val list = RecyclerView(requireContext()).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        root.addView(emptyLabel)
        root.addView(list)

        adapter = PlaceAdapter(
            onOpen = { p -> (activity as? MainActivity)?.openPlace(p.id) },
            onToggleFavorite = { p -> app.prefs.toggleFavorite(p.id); refresh() }
        )
        list.layoutManager = LinearLayoutManager(requireContext())
        list.adapter = adapter

        scope.launch {
            app.repository.places.collectLatest { refresh() }
        }
        return root
    }

    private fun refresh() {
        if (!::adapter.isInitialized) return
        val favs = app.repository.places.value
            .filter { app.prefs.favorites.contains(it.id) }
            .sortedBy { it.score }
        adapter.submit(favs, app.prefs.favorites)
        emptyLabel.visibility = if (favs.isEmpty()) View.VISIBLE else View.GONE
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    override fun onDestroyView() {
        scope.cancel()
        super.onDestroyView()
    }
}
