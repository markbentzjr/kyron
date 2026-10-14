package com.kyronapp.kyron

import android.os.Bundle
import android.os.Looper
import android.widget.TextView
import androidx.fragment.app.FragmentActivity
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.kyronapp.kyron.ui.BrowseFragment
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows
import org.robolectric.annotation.Config

/**
 * P0 pass-2: first-frame execution for the LF-4 build on pre-LF4 data.
 * AppCompatActivity cannot complete onCreate in this rig (AppCompat's
 * abc_vector_test probe hits Robolectric's binary-resource gap; the
 * resource is proven present in the APK), so activity_main is hosted in
 * a plain FragmentActivity with the real app theme — this inflates the
 * full real hierarchy (MaterialToolbar, region chip MaterialButton,
 * BottomNavigationView + its menu) and then runs the real
 * BrowseFragment (tab 0) against the upgraded catalog.
 */
@RunWith(RobolectricTestRunner::class)
@Config(
    sdk = [34],
    application = FixtureApplication::class,
    manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml"
)
class StartupHostTest {

    class HostActivity : FragmentActivity() {
        override fun onCreate(savedInstanceState: Bundle?) {
            setTheme(R.style.Theme_Kyron)
            super.onCreate(savedInstanceState)
            setContentView(R.layout.activity_main)
        }
    }

    private fun pump(ms: Long) {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(50)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
    }

    @Test
    fun activityMainInflatesAndChipCasts() {
        val controller = Robolectric.buildActivity(HostActivity::class.java).create()
        val act = controller.get()
        val chip = act.findViewById<TextView>(R.id.region_chip)
        assertNotNull("region_chip missing", chip)
        println("KYRONTEST region_chip runtime class: ${chip!!.javaClass.name}")
        assertTrue(chip is MaterialButton)
        assertNotNull("bottom_nav missing", act.findViewById<TextView>(R.id.bottom_nav))
        assertNotNull("container missing", act.findViewById<TextView>(R.id.container))
        println("KYRONTEST activity_main hierarchy inflated OK")
    }

    @Test
    fun browseFragmentFirstFrameOnUpgradeData() {
        val controller = Robolectric.buildActivity(HostActivity::class.java).create().start().resume()
        val act = controller.get()
        val frag = BrowseFragment()
        act.supportFragmentManager.beginTransaction()
            .add(R.id.container, frag, "tab0")
            .commitNow()
        pump(4000)
        val list = frag.view?.findViewById<RecyclerView>(R.id.list)
        assertNotNull("browse list missing", list)
        val count = list!!.adapter?.itemCount ?: -1
        println("KYRONTEST browse adapter itemCount after load: $count")
        // The fixture holds 150 places in the upgraded v1 catalog; the
        // first-frame query must return rows, not crash and not be empty.
        assertTrue("expected browse rows from upgraded catalog, got $count", count > 0)
        assertEquals(150, (act.application as KyronApplication).repository.count())
        println("KYRONTEST browse first frame OK")
    }
}
