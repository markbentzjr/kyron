package com.kyronapp.kyron

import android.os.Looper
import com.google.android.material.bottomnavigation.BottomNavigationView
import androidx.recyclerview.widget.RecyclerView
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.Shadows

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = TestKyronApplication::class, manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml")
class LaunchTest {

    private fun pump(ms: Long) {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(100)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
    }

    @Test
    fun mainActivityLaunchesAndLoadsData() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        pump(6000)
        val rv = activity.findViewById<RecyclerView>(R.id.list)
        println("KYRONTEST browse adapter count = ${rv?.adapter?.itemCount}")
        assertNotNull("browse RecyclerView adapter missing", rv?.adapter)
        assertTrue("expected restaurants loaded from seed", (rv?.adapter?.itemCount ?: 0) > 0)

        val nav = activity.findViewById<BottomNavigationView>(R.id.bottom_nav)
        nav.selectedItemId = R.id.nav_favorites
        pump(500)
        println("KYRONTEST favorites tab OK")

        nav.selectedItemId = R.id.nav_alerts
        pump(500)
        println("KYRONTEST alerts tab OK")

        nav.selectedItemId = R.id.nav_browse
        pump(500)
        println("KYRONTEST back to browse OK")
        controller.pause().stop().destroy()
    }
}
