package com.kyronapp.kyron.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
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
    private lateinit var emptyBox: View

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        val root = inflater.inflate(R.layout.fragment_favorites, container, false)
        emptyBox = root.findViewById(R.id.fav_empty_box)
        val list = root.findViewById<RecyclerView>(R.id.fav_list)

        adapter = PlaceAdapter(
            onOpen = { p -> (activity as? MainActivity)?.openPlace(p.id) },
            onToggleFavorite = { p -> app.prefs.toggleFavorite(p.id); refresh() }
        )
        list.layoutManager = LinearLayoutManager(requireContext())
        list.adapter = adapter

        root.findViewById<View>(R.id.fav_browse_btn).setOnClickListener {
            (activity as? MainActivity)?.selectTab(0)
        }

        scope.launch {
            app.repository.places.collectLatest { refresh() }
        }
        return root
    }

    private fun refresh() {
        if (!::adapter.isInitialized) return
        val favs = app.repository.places.value
            .filter { app.prefs.favorites.contains(it.id) }
            // No-score (disposition) favorites sort last, not first:
            // the NO_SCORE sentinel (-1) is not a bad score.
            .sortedWith(compareBy { if (it.hasNumericScore) it.score else Int.MAX_VALUE })
        adapter.submit(favs, app.prefs.favorites)
        emptyBox.visibility = if (favs.isEmpty()) View.VISIBLE else View.GONE
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
