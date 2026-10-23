package com.kyronapp.kyron.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.kyronapp.kyron.data.db.CatalogDb
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.util.zip.GZIPInputStream

/** A pack operation was refused. The catalog and the working region are
 *  always left exactly as they were when this is thrown. */
class PackException(message: String) : Exception(message)

/**
 * One region's entry in the coverage manifest (Free/LocalFirst plan §2.2).
 * The manifest is the ONLY thing the app trusts about a pack before
 * installing it: region, dataset version, expected place count, schema
 * version, and the SHA-256 of the pack file.
 */
data class PackManifest(
    val regionId: String,
    val displayName: String,
    val state: String,
    val datasetVersion: String,
    val generatedAt: String,
    val placeCount: Int,
    val schemaVersion: Int,
    val fullFile: String,
    val fullBytes: Long,
    val fullSha256: String,
    val deltaFromVersion: String? = null,
    val deltaFile: String? = null,
    val deltaBytes: Long = 0,
    val deltaSha256: String? = null,
    val raw: JSONObject
) {
    companion object {
        fun fromJson(o: JSONObject): PackManifest {
            val full = o.getJSONObject("full")
            val delta = if (o.isNull("delta")) null else o.optJSONObject("delta")
            return PackManifest(
                regionId = o.getString("regionId"),
                displayName = o.optString("displayName"),
                state = o.optString("state"),
                datasetVersion = o.getString("datasetVersion"),
                generatedAt = o.optString("generatedAt"),
                placeCount = o.getInt("placeCount"),
                schemaVersion = o.optInt("schemaVersion", CatalogDb.SUPPORTED_PACK_SCHEMA),
                fullFile = full.optString("file"),
                fullBytes = full.optLong("bytes", 0),
                fullSha256 = full.getString("sha256").lowercase(),
                deltaFromVersion = delta?.optString("fromVersion")?.ifBlank { null },
                deltaFile = delta?.optString("file")?.ifBlank { null },
                deltaBytes = delta?.optLong("bytes", 0) ?: 0,
                deltaSha256 = delta?.optString("sha256")?.ifBlank { null }?.lowercase(),
                raw = o
            )
        }
    }
}

data class PackInstallResult(
    val regionId: String,
    val datasetVersion: String,
    val placeCount: Int
)

/**
 * Region pack installer (LF-4, Free/LocalFirst plan §2.2/§2.4).
 *
 * A pack is a prebuilt SQLite database (gzip-compressed for transport)
 * with the catalog's own places/inspections schema plus a `pack_meta`
 * table, accompanied by a [PackManifest]. Install discipline:
 *
 *  1. The pack file's SHA-256 (and size) must match the manifest —
 *     verified BEFORE anything is opened or written. A corrupt or
 *     truncated download is rejected and the working region is untouched.
 *  2. The pack's own metadata must agree with the manifest (region,
 *     schema version this app understands, exact place count).
 *  3. The currently installed pack artifact is rotated to N−1
 *     (`<region>.prev.db.gz`) so [rollback] can restore it.
 *  4. Rows swap inside ONE catalog transaction (delete region → copy
 *     pack rows → rebuild that region's FTS rows). Any failure rolls the
 *     transaction back: a half-installed region is impossible.
 *
 * Deltas are per-region JSON change sets (upserts + deletion ids) that
 * apply only on top of their exact base version, parsed fully before any
 * write (the QA BUG-2 lesson). The user store is a different database
 * file; nothing here can touch favorites, areas, rules, or the inbox.
 */
class PackManager(context: Context, private val catalog: CatalogDb) {

    private val appContext = context.applicationContext

    fun packsDir(): File = File(appContext.filesDir, "packs").apply { mkdirs() }

    private fun artifact(regionId: String) = File(packsDir(), "$regionId.db.gz")

    /** The manifest that describes [artifact]'s actual contents, written
     *  when the artifact was promoted (F-2). Kept as a sibling file —
     *  NOT read from the live catalog meta — because a delta advances
     *  the meta past the artifact: the artifact still holds the
     *  pre-delta full pack, and only this file labels it truthfully. */
    private fun artifactManifestFile(regionId: String) = File(packsDir(), "$regionId.manifest.json")
    private fun prevArtifact(regionId: String) = File(packsDir(), "$regionId.prev.db.gz")
    private fun prevManifestFile(regionId: String) = File(packsDir(), "$regionId.prev.manifest.json")

    // ------------------------------------------------------------ state

    /** Dataset version currently installed for a region, or null. */
    fun installedVersion(db: SQLiteDatabase, regionId: String): String? =
        catalog.metaGet(db, "pack_version:$regionId")

    fun installedManifest(db: SQLiteDatabase, regionId: String): PackManifest? =
        catalog.metaGet(db, "pack_manifest:$regionId")?.let {
            runCatching { PackManifest.fromJson(JSONObject(it)) }.getOrNull()
        }

    fun hasRollback(regionId: String): Boolean =
        prevArtifact(regionId).exists() && prevManifestFile(regionId).exists()

    // ------------------------------------------------------------- full

    /**
     * LF-N hardening: an explicit, registry-derived pack-install eligibility
     * check that REPLACES the legacy hard-coded "Unknown region" refusal.
     *
     * A pack may only be installed when:
     *  1. the region ships with the app (States.KNOWN / bundled), or
     *  2. the bundled national registry lists the jurisdiction with a
     *     pack-capable pack_status (bundled | published | built).
     *
     * A source-verified state (pack_status "none") can NEVER be turned
     * installable merely by staging a file — the refusal is explicit:
     * "verified source data" and "installable pack" are distinct concepts.
     * The manifest/pack identity checks (region/schema/version/count) below
     * apply to every accepted install regardless of path.
     */
    private fun checkPackEligibility(regionId: String) {
        if (Regions.byId(regionId) != null) return
        val jur = com.kyronapp.kyron.data.NationalCoverage.byRegionId(
            runCatching {
                com.kyronapp.kyron.data.NationalCoverage.load(appContext)
            }.getOrDefault(emptyList()),
            regionId
        ) ?: throw PackException("Unknown region $regionId")
        if (!com.kyronapp.kyron.data.NationalCoverage.packInstallable(jur)) {
            throw PackException(
                "Refusing pack for $regionId — its registry pack_status is " +
                    "'${jur.packStatus}'; verified sources do not make a pack installable"
            )
        }
    }

    /** Meta key recording the dataset version this region was BASELINED at
     *  (first full install). The first sync after a baseline treats its
     *  old==null events as initial population, never as incidents. */
    private fun baselineKey(regionId: String) = "alerts_baseline:$regionId"

    /**
     * Install a full region pack from a local file (already downloaded).
     * Throws [PackException] on any refusal; the catalog is unchanged then.
     */
    fun installFullPack(db: SQLiteDatabase, packFile: File, manifest: PackManifest): PackInstallResult {
        val regionId = manifest.regionId
        checkPackEligibility(regionId)
        if (!packFile.exists()) throw PackException("Pack file missing: ${packFile.name}")
        if (manifest.fullBytes > 0 && packFile.length() != manifest.fullBytes) {
            throw PackException(
                "Pack size mismatch for $regionId (expected ${manifest.fullBytes} bytes, " +
                    "got ${packFile.length()}) — download rejected, current data unchanged"
            )
        }
        val sha = sha256(packFile)
        if (sha != manifest.fullSha256) {
            throw PackException(
                "Pack checksum mismatch for $regionId — file is corrupt or tampered; " +
                    "rejected before install, current data unchanged"
            )
        }

        // Decompress (if gzipped) and validate the pack's own metadata
        // against the manifest before touching anything.
        val tmpDb = File(packsDir(), "tmp-$regionId.db")
        tmpDb.delete()
        try {
            ungzipTo(packFile, tmpDb)
            validatePackDb(tmpDb, manifest)

            // Rotate the current artifact to N−1 (rollback target).
            val cur = artifact(regionId)
            val prev = prevArtifact(regionId)
            val prevManifest = prevManifestFile(regionId)
            val hadCurrent = cur.exists()
            // F-2: pair the artifact with the manifest that describes
            // ITS contents — its own manifest file. The live meta is
            // only a fallback for artifacts installed before the
            // pairing file existed; after a delta the meta is ahead of
            // the artifact and would mislabel the rollback target.
            val currentManifestJson = artifactManifestFile(regionId)
                .takeIf { it.exists() }?.readText()
                ?: catalog.metaGet(db, "pack_manifest:$regionId")
            if (hadCurrent && currentManifestJson != null) {
                prev.delete()
                cur.copyTo(prev, overwrite = true)
                prevManifest.writeText(currentManifestJson)
            } else {
                prev.delete(); prevManifest.delete()
            }

            var swapped = false
            try {
                swapRegionRows(db, tmpDb, regionId)
                swapped = true
            } finally {
                if (!swapped) {
                    // Catalog kept the old rows; keep the artifacts in step.
                    if (hadCurrent) {
                        prev.copyTo(cur, overwrite = true)
                    }
                }
            }
            catalog.metaPut(db, "pack_version:$regionId", manifest.datasetVersion)
            catalog.metaPut(db, "pack_manifest:$regionId", manifest.raw.toString())
            // baseline = THIS dataset version (LF-N alerts): the very first
            // sync that observes only this version treats its old==null
            // events as initial population, never as incidents. A region
            // that already had a baseline keeps its old marker.
            if (catalog.metaGet(db, baselineKey(regionId)) == null) {
                catalog.metaPut(db, baselineKey(regionId), manifest.datasetVersion)
            }

            // Promote the verified artifact to the canonical slot, and
            // record the manifest that describes it (F-2 pairing).
            cur.delete()
            packFile.copyTo(cur, overwrite = true)
            artifactManifestFile(regionId).writeText(manifest.raw.toString())
            return PackInstallResult(regionId, manifest.datasetVersion, manifest.placeCount)
        } finally {
            tmpDb.delete()
        }
    }

    private fun validatePackDb(packDbFile: File, manifest: PackManifest) {
        val pdb = SQLiteDatabase.openDatabase(packDbFile.path, null, SQLiteDatabase.OPEN_READONLY)
        try {
            val meta = HashMap<String, String>()
            pdb.rawQuery("SELECT k,v FROM pack_meta", null).use { c ->
                while (c.moveToNext()) meta[c.getString(0)] = c.getString(1) ?: ""
            }
            if (meta["region_id"] != manifest.regionId) {
                throw PackException(
                    "Pack region mismatch (manifest ${manifest.regionId}, pack ${meta["region_id"]}) — rejected"
                )
            }
            val schema = meta["schema_version"]?.toIntOrNull()
                ?: throw PackException("Pack has no schema_version — rejected")
            if (schema > CatalogDb.SUPPORTED_PACK_SCHEMA) {
                throw PackException(
                    "Pack schema v$schema is newer than this app understands " +
                        "(v${CatalogDb.SUPPORTED_PACK_SCHEMA}) — update the app to refresh this region"
                )
            }
            val actual = pdb.rawQuery("SELECT COUNT(*) FROM places", null).use { c ->
                if (c.moveToFirst()) c.getInt(0) else -1
            }
            if (actual != manifest.placeCount || actual != (meta["place_count"]?.toIntOrNull() ?: -1)) {
                throw PackException(
                    "Pack place count mismatch (manifest ${manifest.placeCount}, pack $actual) — rejected"
                )
            }
            // F-1 (LF-4 pass-2 QA): the pack's own dataset version must
            // be the version the manifest advertises. A pack relabelled
            // under a newer manifest must not slip through on a
            // matching place count alone.
            val packVersion = meta["dataset_version"]
                ?: throw PackException("Pack has no dataset_version — rejected")
            if (packVersion != manifest.datasetVersion) {
                throw PackException(
                    "Pack dataset version mismatch (manifest ${manifest.datasetVersion}, " +
                        "pack $packVersion) — rejected"
                )
            }
            // F-1, row level: every place must belong to this region
            // (and state, when the manifest names one), and every
            // inspection must point at a place inside the pack. Checked
            // here so a mislabelled or spliced pack is refused before
            // the swap — swapRegionRows additionally filters its copy
            // to this region as a second line of defence.
            val foreignRegion = pdb.rawQuery(
                "SELECT COUNT(*) FROM places WHERE COALESCE(region_id,'') != ?",
                arrayOf(manifest.regionId)
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else -1 }
            if (foreignRegion != 0) {
                throw PackException(
                    "Pack has $foreignRegion place(s) outside region ${manifest.regionId} — rejected"
                )
            }
            if (manifest.state.isNotBlank()) {
                val foreignState = pdb.rawQuery(
                    "SELECT COUNT(*) FROM places WHERE COALESCE(state,'') != ?",
                    arrayOf(manifest.state)
                ).use { c -> if (c.moveToFirst()) c.getInt(0) else -1 }
                if (foreignState != 0) {
                    throw PackException(
                        "Pack has $foreignState place(s) outside state ${manifest.state} — rejected"
                    )
                }
            }
            val orphans = pdb.rawQuery(
                "SELECT COUNT(*) FROM inspections WHERE place_id NOT IN (SELECT id FROM places)",
                null
            ).use { c -> if (c.moveToFirst()) c.getInt(0) else -1 }
            if (orphans != 0) {
                throw PackException(
                    "Pack has $orphans inspection(s) with no matching place — rejected"
                )
            }
        } finally {
            pdb.close()
        }
    }

    /** Replace one region's catalog rows with the pack's, atomically. */
    private fun swapRegionRows(db: SQLiteDatabase, packDbFile: File, regionId: String) {
        val escaped = packDbFile.absolutePath.replace("'", "''")
        db.execSQL("ATTACH DATABASE '$escaped' AS packsrc")
        try {
            db.beginTransaction()
            try {
                catalog.deleteRegionRows(db, regionId)
                // F-1 defence in depth: copy ONLY this region's rows,
                // even if a pack somehow passed validation with foreign
                // rows mixed in (validatePackDb refuses such packs, so
                // this filter should never actually remove a row).
                val rid = regionId.replace("'", "''")
                db.execSQL(
                    """INSERT INTO places
                       (id,name,name_lc,address,city,zip,county,score,date,date_key,source,
                        lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url,
                        state,jurisdiction,region_id,result_text)
                       SELECT id,name,name_lc,address,city,zip,county,score,date,date_key,source,
                        lat,lng,geo_status,geo_acc,geo_prov,geo_match,detail_url,
                        state,jurisdiction,region_id,result_text FROM packsrc.places
                       WHERE region_id = '$rid'"""
                )
                db.execSQL(
                    """INSERT INTO inspections (place_id,idx,score,date,type,violations_json,result_text)
                       SELECT place_id,idx,score,date,type,violations_json,result_text FROM packsrc.inspections
                       WHERE place_id IN (SELECT id FROM packsrc.places WHERE region_id = '$rid')"""
                )
                if (catalog.ftsAvailable) {
                    // Workstream D / FIX5: FTS rows carry the apostrophe-
                    // stripped search alias (CatalogDb.ftsName) — the same
                    // construction importSeed/upsertPlace/reconcileFts use.
                    db.execSQL(
                        """INSERT INTO places_fts (place_id,name,city,address,zip,county)
                           SELECT id, ${CatalogDb.FTS_NAME_SQL}, city, address, zip, county FROM packsrc.places
                           WHERE region_id = '$rid'"""
                    )
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        } finally {
            db.execSQL("DETACH DATABASE packsrc")
        }
    }

    // ------------------------------------------------------------- delta

    /**
     * Apply a delta change set on top of its exact base version.
     * The whole file is parsed and validated BEFORE any write, so a
     * malformed delta changes nothing (QA BUG-2 lesson, applied to packs).
     */
    fun applyDelta(db: SQLiteDatabase, deltaFile: File, manifest: PackManifest): PackInstallResult {
        val regionId = manifest.regionId
        val fromVersion = manifest.deltaFromVersion
            ?: throw PackException("Manifest for $regionId carries no delta")
        val expectedSha = manifest.deltaSha256
            ?: throw PackException("Manifest delta for $regionId carries no checksum")
        if (!deltaFile.exists()) throw PackException("Delta file missing: ${deltaFile.name}")
        if (manifest.deltaBytes > 0 && deltaFile.length() != manifest.deltaBytes) {
            throw PackException("Delta size mismatch for $regionId — rejected, current data unchanged")
        }
        if (sha256(deltaFile) != expectedSha) {
            throw PackException("Delta checksum mismatch for $regionId — rejected, current data unchanged")
        }
        val installed = installedVersion(db, regionId)
        if (installed != fromVersion) {
            throw PackException(
                "Delta for $regionId builds on v$fromVersion but v$installed is installed — full pack required"
            )
        }

        val text = readPossiblyGzipped(deltaFile)
        val root = JSONObject(text)
        if (root.optString("regionId") != regionId) {
            throw PackException("Delta region mismatch — rejected")
        }
        if (root.optString("toVersion") != manifest.datasetVersion) {
            throw PackException("Delta target version mismatch — rejected")
        }
        // Parse-first: build every row in memory before opening a write.
        val upserts = mutableListOf<Place>()
        val upArr = root.optJSONArray("upserts") ?: JSONArray()
        for (i in 0 until upArr.length()) {
            val p = Place.fromJson(upArr.getJSONObject(i))
            if (p.regionId != regionId) {
                throw PackException("Delta upsert ${p.id} belongs to ${p.regionId}, not $regionId — rejected")
            }
            upserts += p
        }
        val deletions = mutableListOf<String>()
        val delArr = root.optJSONArray("deletions") ?: JSONArray()
        for (i in 0 until delArr.length()) deletions += delArr.getString(i)

        // F-2: freeze the artifact↔manifest pairing BEFORE the write
        // below advances the meta. The stored full-pack artifact keeps
        // holding the PRE-delta data; its own manifest file (written at
        // install time, or captured here from the still-current meta
        // for artifacts installed before the pairing file existed) is
        // what a later rotation pairs it with — never the post-delta
        // meta. An artifact that cannot be paired is dropped, so
        // rollback fails closed instead of mislabelling old data.
        val art = artifact(regionId)
        val artManifest = artifactManifestFile(regionId)
        if (art.exists() && !artManifest.exists()) {
            val metaManifest = catalog.metaGet(db, "pack_manifest:$regionId")
            if (metaManifest != null) {
                artManifest.writeText(metaManifest)
            } else {
                art.delete()
            }
        }

        db.beginTransaction()
        try {
            for (id in deletions) catalog.deletePlace(db, id)
            for (p in upserts) catalog.upsertPlace(db, p)
            catalog.metaPut(db, "pack_version:$regionId", manifest.datasetVersion)
            catalog.metaPut(db, "pack_manifest:$regionId", manifest.raw.toString())
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return PackInstallResult(regionId, manifest.datasetVersion, catalog.regionPlaceCount(db, regionId))
    }

    // ---------------------------------------------------- rollback/remove

    /**
     * Restore the N−1 pack artifact kept by the last full install.
     * Rolling back twice toggles back (install rotates artifacts again).
     * Returns false when no rollback target exists.
     */
    fun rollback(db: SQLiteDatabase, regionId: String): Boolean {
        if (!hasRollback(regionId)) return false
        val prevManifest = PackManifest.fromJson(JSONObject(prevManifestFile(regionId).readText()))
        installFullPack(db, prevArtifact(regionId), prevManifest)
        return true
    }

    /** Delete a downloaded region's rows + artifacts. Bundled regions and
     *  the user store are never touched. */
    fun removeRegion(db: SQLiteDatabase, regionId: String) {
        // LF-N: removal obeys the same registry-derived eligibility as
        // install (avoid removing a region only the registry vouches for,
        // and never silently "remove" something unknown).
        val jur = com.kyronapp.kyron.data.NationalCoverage.byRegionId(
            runCatching {
                com.kyronapp.kyron.data.NationalCoverage.load(appContext)
            }.getOrDefault(emptyList()),
            regionId
        )
        val info = Regions.byId(regionId)
            ?: (if (com.kyronapp.kyron.data.NationalCoverage.packInstallable(jur))
                Regions.fromRegistry(appContext, regionId) else null)
        if (info == null) throw PackException("Unknown region $regionId")
        if (info.bundled) throw PackException("${info.displayName} ships with the app and can't be removed")
        db.beginTransaction()
        try {
            catalog.deleteRegionRows(db, regionId)
            catalog.metaDelete(db, "pack_version:$regionId")
            catalog.metaDelete(db, "pack_manifest:$regionId")
            catalog.metaDelete(db, baselineKey(regionId))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        artifact(regionId).delete()
        artifactManifestFile(regionId).delete()
        prevArtifact(regionId).delete()
        prevManifestFile(regionId).delete()
    }

    // ------------------------------------------------------------ helpers

    companion object {
        fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            FileInputStream(file).use { input ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    digest.update(buf, 0, n)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }

        private fun isGzip(file: File): Boolean =
            FileInputStream(file).use { it.read() == 0x1f && it.read() == 0x8b }

        private fun ungzipTo(src: File, dst: File) {
            if (!isGzip(src)) {
                src.copyTo(dst, overwrite = true)
                return
            }
            GZIPInputStream(FileInputStream(src)).use { input ->
                dst.outputStream().use { out -> input.copyTo(out) }
            }
        }

        private fun readPossiblyGzipped(file: File): String =
            if (isGzip(file)) {
                GZIPInputStream(FileInputStream(file)).use { it.readBytes().toString(Charsets.UTF_8) }
            } else {
                file.readText()
            }
    }
}
