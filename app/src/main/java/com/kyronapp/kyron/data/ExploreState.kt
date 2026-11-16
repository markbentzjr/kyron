package com.kyronapp.kyron.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * One query drives both Browse and Map (Presentation Spec priority 1).
 * Browse owns the controls (search text, county, score band, sort); every
 * change is published here, and the Map applies the same text/county/band
 * filters to its viewport results — so the two tabs can never disagree
 * about what "the current search" is.
 */
object ExploreState {
    private val _query = MutableStateFlow(PlaceQuery())
    val query: StateFlow<PlaceQuery> = _query

    /** One-way handoff for the Home hero search: Home stages the text here,
     *  switches to the Browse tab, and Browse applies + clears it on show.
     *  Volatile (not part of the flow) — Browse remains the publisher. */
    var pendingSearch: String? = null

    fun update(q: PlaceQuery) {
        _query.value = q
    }

    fun current(): PlaceQuery = _query.value
}
