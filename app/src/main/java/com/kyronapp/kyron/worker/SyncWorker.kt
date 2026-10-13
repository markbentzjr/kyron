package com.kyronapp.kyron.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.kyronapp.kyron.KyronApplication

class SyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as KyronApplication
        return try {
            val report = SyncEngine.run(applicationContext, app.repository, app.prefs, includeCounties = false)
            // Retry only when every source failed (matches the v1 fix-pack policy)
            if (report.sourcesOk.isEmpty() && report.sourcesFailed.isNotEmpty()) Result.retry()
            else Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
