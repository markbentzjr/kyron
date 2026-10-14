package com.kyronapp.kyron

import android.content.Intent
import android.os.Looper
import android.view.View
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.bottomnavigation.BottomNavigationView
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
 * Kyron 2.1 pass-1 interaction tests (Robolectric): bottom navigation,
 * tab-state preservation, detail + favorite toggle, searchable county
 * picker — the exact behaviors Mark's acceptance gates name.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = TestKyronApplication::class, manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml")
class UiTest {

    private fun pump(ms: Long) {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(100)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
    }

    @Test
    fun bottomNavSwitchesTabsAndPreservesBrowseState() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        pump(6000)
        val app = activity.application as KyronApplication
        val rv = activity.findViewById<RecyclerView>(R.id.list)
        assertNotNull("browse list missing", rv?.adapter)
        assertTrue("seed places loaded", (rv?.adapter?.itemCount ?: 0) > 0)

        // A query with no matches shows the designed empty state.
        val search = activity.findViewById<EditText>(R.id.search)
        search.setText("zzznomatchqqq")
        pump(1500)
        assertEquals(0, rv.adapter?.itemCount ?: -1)
        assertEquals(View.VISIBLE, activity.findViewById<View>(R.id.empty_box).visibility)

        // A real query filters, then survives a tab round-trip (gate 3).
        val probe = app.repository.places.value.first().name.take(5)
        search.setText(probe)
        pump(1500)
        assertTrue("query '$probe' should match", (rv.adapter?.itemCount ?: 0) > 0)

        val nav = activity.findViewById<BottomNavigationView>(R.id.bottom_nav)
        nav.selectedItemId = R.id.nav_alerts
        pump(1000)
        assertNotNull("alerts favorites switch missing",
            activity.findViewById<View>(R.id.sw_fav_alerts))
        assertNotNull("area rule summary missing",
            activity.findViewById<View>(R.id.area_summary))

        nav.selectedItemId = R.id.nav_favorites
        pump(1000)
        assertEquals("favorites empty state should show",
            View.VISIBLE, activity.findViewById<View>(R.id.fav_empty_box).visibility)

        nav.selectedItemId = R.id.nav_browse
        pump(1000)
        assertEquals("browse query must survive tab switches", probe,
            activity.findViewById<EditText>(R.id.search).text.toString())
        controller.pause().stop().destroy()
        println("KYRONTEST nav+state OK")
    }

    @Test
    fun detailOpensAndFavoriteToggles() {
        val main = Robolectric.buildActivity(MainActivity::class.java).setup()
        val app = main.get().application as KyronApplication
        pump(6000)
        val place = app.repository.places.value.first()
        val intent = Intent(main.get(), com.kyronapp.kyron.ui.DetailActivity::class.java)
            .putExtra(com.kyronapp.kyron.ui.DetailActivity.EXTRA_PLACE_ID, place.id)
        val controller = Robolectric.buildActivity(com.kyronapp.kyron.ui.DetailActivity::class.java, intent).setup()
        val detail = controller.get()
        pump(3000)
        assertEquals(place.name, detail.findViewById<TextView>(R.id.d_name).text.toString())
        assertNotNull("share action missing", detail.findViewById<View>(R.id.d_share))
        val favBtn = detail.findViewById<View>(R.id.d_fav)
        assertFalse(app.prefs.favorites.contains(place.id))
        favBtn.performClick()
        pump(500)
        assertTrue("favorite should be stored", app.prefs.favorites.contains(place.id))
        favBtn.performClick()
        pump(500)
        assertFalse("favorite should toggle off", app.prefs.favorites.contains(place.id))
        controller.pause().stop().destroy()
        main.pause().stop().destroy()
        println("KYRONTEST detail+favorite OK")
    }

    @Test
    fun countyPickerFiltersAndSelects() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        pump(6000)
        val app = activity.application as KyronApplication
        val nav = activity.findViewById<BottomNavigationView>(R.id.bottom_nav)
        nav.selectedItemId = R.id.nav_alerts
        pump(1000)
        activity.findViewById<View>(R.id.area_edit).performClick()
        pump(500)
        assertEquals(View.VISIBLE, activity.findViewById<View>(R.id.area_editor).visibility)
        activity.findViewById<View>(R.id.choose_counties).performClick()
        pump(1000)
        val dialog = ShadowDialog.getLatestDialog()
        assertNotNull("county picker dialog missing", dialog)
        assertTrue(dialog.isShowing)
        val list = dialog.findViewById<ListView>(R.id.picker_list)
        assertEquals("Alabama has 67 counties", 67, list.adapter.count)
        dialog.findViewById<EditText>(R.id.picker_search).setText("Jeff")
        pump(800)
        assertEquals("filter should narrow to Jefferson", 1, list.adapter.count)
        list.performItemClick(list.getChildAt(0), 0, 0)
        pump(300)
        assertTrue(
            dialog.findViewById<TextView>(R.id.picker_count).text.toString().contains("1 of 67")
        )
        dialog.findViewById<View>(R.id.picker_done).performClick()
        pump(500)
        assertFalse(dialog.isShowing)
        assertTrue(app.prefs.monitoredCounties.contains("Jefferson"))
        assertTrue(
            activity.findViewById<TextView>(R.id.county_summary).text.toString().contains("Jefferson")
        )
        controller.pause().stop().destroy()
        println("KYRONTEST county picker OK")
    }

    @Test
    fun mapTabCreates() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        pump(6000)
        val nav = activity.findViewById<BottomNavigationView>(R.id.bottom_nav)
        nav.selectedItemId = R.id.nav_map
        pump(4000)
        assertNotNull("map view missing", activity.findViewById<View>(R.id.map))
        assertNotNull("map locate FAB missing", activity.findViewById<View>(R.id.map_locate))
        controller.pause().stop().destroy()
        println("KYRONTEST map tab OK")
    }
}
