package com.kyronapp.kyron

import android.app.Application
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.kyronapp.kyron.data.PlaceRepository
import com.kyronapp.kyron.data.Prefs
import com.kyronapp.kyron.data.RegionManager
import com.kyronapp.kyron.worker.Notifier
import com.kyronapp.kyron.worker.SyncWorker
import org.osmdroid.config.Configuration
import java.io.File
import java.util.concurrent.TimeUnit

open class KyronApplication : Application() {

    lateinit var repository: PlaceRepository
        private set
    lateinit var prefs: Prefs
        private set
    lateinit var regions: RegionManager
        private set

    override fun onCreate() {
        super.onCreate()
        repository = PlaceRepository(this)
        prefs = Prefs(this)
        regions = RegionManager(this)
        Notifier.ensureChannel(this)

        // osmdroid (OpenStreetMap) — no API key needed
        val osmPrefs = getSharedPreferences("osmdroid", MODE_PRIVATE)
        Configuration.getInstance().load(this, osmPrefs)
        Configuration.getInstance().userAgentValue = packageName
        Configuration.getInstance().osmdroidTileCache = File(cacheDir, "osmdroid")

        scheduleSync()
    }

    private fun scheduleSync() {
        // Startup hardening (LF-4 pass-2 QA, P0 cold-start hunt):
        // periodic-sync scheduling is not needed to show the first frame
        // and must never be able to take down Application.onCreate,
        // whatever state a device's WorkManager database is in. A failure
        // here is logged; sync is retried from MainActivity as before.
        runCatching {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(12, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.MINUTES)
                .build()
            // UPDATE (not KEEP) so interval/constraint changes reach installed devices
            WorkManager.getInstance(this).enqueueUniquePeriodicWork(
                "SyncDataWork", ExistingPeriodicWorkPolicy.UPDATE, request
            )
        }.onFailure {
            android.util.Log.w("Kyron", "scheduleSync deferred: ${it.message}")
        }
    }
}
