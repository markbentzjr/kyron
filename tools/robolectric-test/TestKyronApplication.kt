package com.kyronapp.kyron

import androidx.work.Configuration
import androidx.work.WorkManager

/**
 * Test-only application: Robolectric's raw-manifest mode does not execute the
 * androidx.startup ContentProvider that initializes WorkManager on a real
 * device (it does run in the APK's binary manifest, verified separately), so
 * initialize WorkManager first, then run the real application startup.
 */
class TestKyronApplication : KyronApplication() {
    override fun onCreate() {
        WorkManager.initialize(this, Configuration.Builder().build())
        super.onCreate()
    }
}
