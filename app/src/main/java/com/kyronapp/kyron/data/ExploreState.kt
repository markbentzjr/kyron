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

    fun update(q: PlaceQuery) {
        _query.value = q
    }

    fun current(): PlaceQuery = _query.value
}
