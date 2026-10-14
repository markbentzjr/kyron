package com.kyronapp.kyron

import android.os.Bundle
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ListView
import android.widget.TextView
import androidx.fragment.app.FragmentActivity
import androidx.recyclerview.widget.RecyclerView
import com.kyronapp.kyron.ui.AlertsFragment
import com.kyronapp.kyron.ui.BrowseFragment
import com.kyronapp.kyron.ui.FavoritesFragment
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowDialog

/**
 * Kyron 2.1 fragment-host tests. The two AppCompat activities cannot
 * complete onCreate in this rig (AppCompat's abc_vector_test self-check
 * hits Robolectric's known binary-resource gap — the resource is proven
 * present in the APK by aapt2 + zip listing, and the same AppCompat
 * version runs on device). Fragments are therefore hosted in a plain
 * FragmentActivity with the real app theme, which exercises their full
 * logic: repository queries, filter controls, the county picker dialog,
 * switches and sliders. Activity layouts are inflation-tested too.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = TestKyronApplication::class, manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml")
class HostTest {

    class HostActivity : FragmentActivity() {
        override fun onCreate(savedInstanceState: Bundle?) {
            setTheme(R.style.Theme_Kyron)
            super.onCreate(savedInstanceState)
            val frame = FrameLayout(this)
            frame.id = CONTAINER_ID
            setContentView(frame)
        }
        companion object { const val CONTAINER_ID = 0x5EED }
    }

    private fun pump(ms: Long) {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(100)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
    }

    private fun host(fragment: androidx.fragment.app.Fragment): HostActivity {
        val controller = Robolectric.buildActivity(HostActivity::class.java).setup()
        val activity = controller.get()
        activity.supportFragmentManager.beginTransaction()
            .add(HostActivity.CONTAINER_ID, fragment, "hosted")
            .commitNow()
        return activity
    }

    @Test
    fun allLayoutsInflateWithMaterialTheme() {
        val controller = Robolectric.buildActivity(HostActivity::class.java).setup()
        val activity = controller.get()
        val inflater = LayoutInflater.from(activity)
        for (layout in listOf(
            R.layout.activity_main, R.layout.fragment_browse, R.layout.item_place,
            R.layout.fragment_favorites, R.layout.activity_detail,
            R.layout.fragment_alerts, R.layout.activity_coverage,
            R.layout.dialog_county_picker
        )) {
            val v = inflater.inflate(layout, null)
            assertNotNull("layout $layout failed to inflate", v)
        }
        // The bottom nav must carry all four labeled destinations.
        val main = inflater.inflate(R.layout.activity_main, null)
        val nav = main.findViewById<com.google.android.material.bottomnavigation.BottomNavigationView>(R.id.bottom_nav)
        assertEquals(4, nav.menu.size())
        println("KYRONTEST inflation OK")
        controller.pause().stop().destroy()
    }

    @Test
    fun browseFragmentQueriesAndFilters() {
        val frag = BrowseFragment()
        val activity = host(frag)
        pump(6000)
        val rv = activity.findViewById<RecyclerView>(R.id.list)
        assertNotNull(rv?.adapter)
        assertTrue("seed places loaded", (rv?.adapter?.itemCount ?: 0) > 0)
        val search = activity.findViewById<EditText>(R.id.search)
        search.setText("zzznomatchqqq")
        pump(1500)
        assertEquals(0, rv.adapter?.itemCount ?: -1)
        assertEquals(View.VISIBLE, activity.findViewById<View>(R.id.empty_box).visibility)
        // Clear-filters button in the empty state restores results.
        activity.findViewById<View>(R.id.empty_clear).performClick()
        pump(1500)
        assertTrue((rv.adapter?.itemCount ?: 0) > 0)
        // Band chip: "Below 85" must only keep sub-85 places.
        activity.findViewById<View>(R.id.band_low).performClick()
        pump(1500)
        val app = activity.application as KyronApplication
        val adapter = rv.adapter as com.kyronapp.kyron.ui.PlaceAdapter
        assertTrue(adapter.items.all { !it.hasNumericScore || it.score < 85 })
        println("KYRONTEST browse host OK (${adapter.items.size} below-85 places)")
    }

    @Test
    fun alertsFragmentRulesAndCountyPicker() {
        val frag = AlertsFragment()
        val activity = host(frag)
        pump(2000)
        val app = activity.application as KyronApplication
        // Favorites quick-pick switch flips the stored rule.
        val swFav = activity.findViewById<com.google.android.material.materialswitch.MaterialSwitch>(R.id.sw_fav_alerts)
        val before = app.prefs.alertsForFavorites
        swFav.performClick()
        pump(500)
        assertEquals(!before, app.prefs.alertsForFavorites)
        // Editor opens; the searchable picker lists all 67 counties.
        activity.findViewById<View>(R.id.area_edit).performClick()
        pump(500)
        assertEquals(View.VISIBLE, activity.findViewById<View>(R.id.area_editor).visibility)
        activity.findViewById<View>(R.id.choose_counties).performClick()
        pump(1000)
        val dialog = ShadowDialog.getLatestDialog()
        assertNotNull("county picker dialog missing", dialog)
        assertTrue(dialog.isShowing)
        val list = dialog.findViewById<ListView>(R.id.picker_list)
        assertEquals(67, list.adapter.count)
        dialog.findViewById<EditText>(R.id.picker_search).setText("Jeff")
        pump(800)
        assertEquals(1, list.adapter.count)
        list.performItemClick(list.getChildAt(0), 0, 0)
        pump(300)
        assertTrue(dialog.findViewById<TextView>(R.id.picker_count).text.toString().contains("1 of 67"))
        dialog.findViewById<View>(R.id.picker_done).performClick()
        pump(500)
        assertTrue(app.prefs.monitoredCounties.contains("Jefferson"))
        assertTrue(activity.findViewById<TextView>(R.id.county_summary).text.toString().contains("Jefferson"))
        // Threshold slider: plain-language label tracks the value.
        val slider = activity.findViewById<com.google.android.material.slider.Slider>(R.id.threshold_slider)
        slider.value = 70f
        pump(300)
        assertTrue(activity.findViewById<TextView>(R.id.threshold_label).text.toString().contains("below 70"))
        println("KYRONTEST alerts host OK")
    }

    @Test
    fun favoritesFragmentEmptyState() {
        val frag = FavoritesFragment()
        val activity = host(frag)
        pump(3000)
        assertEquals(View.VISIBLE, activity.findViewById<View>(R.id.fav_empty_box).visibility)
        assertNotNull(activity.findViewById<View>(R.id.fav_browse_btn))
        println("KYRONTEST favorites host OK")
    }

    @Test
    fun detailLayoutBindsPlaceData() {
        // DetailActivity is AppCompat (rig-blocked at the delegate self-check),
        // so verify its layout + the favorite store contract it relies on.
        val controller = Robolectric.buildActivity(HostActivity::class.java).setup()
        val activity = controller.get()
        val app = activity.application as KyronApplication
        pump(4000)
        val view = LayoutInflater.from(activity).inflate(R.layout.activity_detail, null)
        for (id in listOf(R.id.d_toolbar, R.id.d_score, R.id.d_name, R.id.d_fav,
            R.id.d_directions, R.id.d_share, R.id.d_why_title, R.id.d_history_chips)) {
            assertNotNull("detail view $id missing", view.findViewById<View>(id))
        }
        val place = app.repository.places.value.first()
        assertFalse(app.prefs.favorites.contains(place.id))
        assertTrue(app.prefs.toggleFavorite(place.id))
        assertTrue(app.prefs.favorites.contains(place.id))
        println("KYRONTEST detail layout OK")
        controller.pause().stop().destroy()
    }
}
