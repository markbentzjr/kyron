package com.kyronapp.kyron

import android.graphics.drawable.VectorDrawable
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = "/home/hatch/kyron-build/test/robo-apk/AndroidManifest.xml")
class ProbeTest {
    @Test
    fun probeResources() {
        val res = RuntimeEnvironment.getApplication().resources
        val pkg = "com.kyronapp.kyron"
        fun probe(label: String, block: () -> Any?) {
            try { println("PROBE $label -> ${block()}") }
            catch (e: Throwable) { println("PROBE $label FAILED: ${e.javaClass.simpleName}: ${e.message}") }
        }
        probe("bool workmanager flag 0x7f040005") { res.getBoolean(0x7f040005) }
        probe("drawable abc_vector_test by name") {
            val id = res.getIdentifier("abc_vector_test", "drawable", "androidx.appcompat")
            val d = res.getDrawable(id, null)
            "id=$id class=${d?.javaClass?.simpleName} isVector=${d is VectorDrawable}"
        }
        probe("layout activity_main inflate id") { res.getLayout(R.layout.activity_main).toString() }
        probe("app drawable card_bg") { res.getDrawable(R.drawable.card_bg, null)?.javaClass?.simpleName }
    }
}
