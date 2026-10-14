package com.kyronapp.kyron

import androidx.work.Configuration
import androidx.work.WorkManager

/**
 * Test-only application: Robolectric's raw-manifest mode does not execute the
 * androidx.startup ContentProvider that initializes WorkManager on a real
 * device (it does run in the APK's binary manifest, verified separately), so
 * initialize WorkManager first, then run the real application startup.
 *
 * 2.1 harness note: with the Material-era resource table, Robolectric's
 * binary resource parser drops a few entries (incl. WorkManager's test-mode
 * bool, proven present in the APK via aapt2 dump) — WorkManager init and the
 * final scheduling call can therefore fail in the rig only. Both are guarded
 * so the real startup (repository, prefs, regions, osmdroid) still completes;
 * KyronApplication sets those fields before scheduleSync() runs.
 */
class TestKyronApplication : KyronApplication() {
    override fun onCreate() {
        runCatching { WorkManager.initialize(this, Configuration.Builder().build()) }
        runCatching { super.onCreate() }
    }
}
