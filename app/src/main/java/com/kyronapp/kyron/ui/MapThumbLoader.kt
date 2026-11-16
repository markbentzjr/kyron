package com.kyronapp.kyron.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.widget.ImageView
import com.kyronapp.kyron.source.Http
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.tan

/** Loads a small real-map thumbnail (OSM tile imagery) centered on a
 *  place's verified coordinates — the same tile source MapFragment uses.
 *  Tiles are cached on disk and decoded crops in memory; a recycled
 *  ImageView only gets its own bitmap (checked via tag). */
object MapThumbLoader {
    private const val ZOOM = 16
    private const val TILE = 256
    private const val CROP = 128
    private val mem = LruCache<String, Bitmap>(96)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private data class TileRef(val x: Int, val y: Int, val px: Int, val py: Int)

    private fun tileFor(lat: Double, lng: Double): TileRef {
        val n = 2.0.pow(ZOOM.toDouble())
        val xt = (lng + 180.0) / 360.0 * n
        val latRad = Math.toRadians(lat)
        val yt = (1.0 - ln(tan(latRad) + 1.0 / cos(latRad)) / PI) / 2.0 * n
        return TileRef(
            floor(xt).toInt(), floor(yt).toInt(),
            ((xt - floor(xt)) * TILE).toInt(), ((yt - floor(yt)) * TILE).toInt()
        )
    }

    fun bind(img: ImageView, lat: Double, lng: Double) {
        val t = tileFor(lat, lng)
        val key = "$ZOOM/${t.x}/${t.y}/${t.px}/${t.py}"
        img.tag = key
        mem.get(key)?.let { img.setImageBitmap(it); return }
        val ctx = img.context.applicationContext
        scope.launch {
            val bmp = fetchCrop(ctx, t)
            if (bmp != null) {
                mem.put(key, bmp)
                withContext(Dispatchers.Main) {
                    if (img.tag == key) img.setImageBitmap(bmp)
                }
            }
        }
    }

    private fun fetchCrop(ctx: Context, t: TileRef): Bitmap? {
        val dir = File(ctx.filesDir, "maptiles").apply { mkdirs() }
        val f = File(dir, "${ZOOM}_${t.x}_${t.y}.png")
        val raw = if (f.exists() && f.length() > 0) {
            f.readBytes()
        } else {
            val url = "https://tile.openstreetmap.org/$ZOOM/${t.x}/${t.y}.png"
            val bytes = runCatching {
                Http.client.newCall(
                    okhttp3.Request.Builder().url(url)
                        .header("User-Agent", "KyronHealthApp/2.0 (Android)")
                        .build()
                ).execute().use { if (it.isSuccessful) it.body?.bytes() else null }
            }.getOrNull() ?: return null
            runCatching { f.writeBytes(bytes) }
            bytes
        }
        val tile = BitmapFactory.decodeByteArray(raw, 0, raw.size) ?: return null
        val size = CROP.coerceAtMost(tile.width)
        val left = (t.px - size / 2).coerceIn(0, (tile.width - size).coerceAtLeast(0))
        val top = (t.py - size / 2).coerceIn(0, (tile.height - size).coerceAtLeast(0))
        return Bitmap.createBitmap(tile, left, top, size, size)
    }
}
