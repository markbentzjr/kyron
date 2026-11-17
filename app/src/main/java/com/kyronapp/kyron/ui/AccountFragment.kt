package com.kyronapp.kyron.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import com.kyronapp.kyron.KyronApplication
import com.kyronapp.kyron.MainActivity
import com.kyronapp.kyron.R
import com.kyronapp.kyron.data.Backup
import com.kyronapp.kyron.source.SourceRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date

/**
 * Account — the fourth tab. Everything that is "mine on this device":
 * profile, data sync, backup/restore, and the official data sources
 * the catalog is built from. Alert rules and the inbox live on the
 * Notifications screen (Home card → AlertsActivity); this tab is
 * deliberately account-shaped, not alerts-shaped.
 */
class AccountFragment : Fragment() {

    private lateinit var app: KyronApplication
    private lateinit var root: View
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val exportLauncher = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri == null || !::app.isInitialized) return@registerForActivityResult
        scope.launch {
            val json = withContext(Dispatchers.IO) {
                Backup.export(app.prefs.store, "2.1", java.time.Instant.now().toString()).toString(2)
            }
            runCatching {
                requireContext().contentResolver.openOutputStream(uri)?.use { it.write(json.toByteArray()) }
            }.onSuccess {
                backupStatus("Backup saved. Keep it somewhere safe — it's the only copy besides this phone.")
            }.onFailure {
                backupStatus("Export failed: ${it.message}")
            }
        }
    }

    private val importLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri == null || !::app.isInitialized) return@registerForActivityResult
        scope.launch {
            val report = withContext(Dispatchers.IO) {
                runCatching {
                    val text = requireContext().contentResolver.openInputStream(uri)
                        ?.bufferedReader()?.readText() ?: error("could not read file")
                    Backup.import(app.prefs.store, JSONObject(text)) { id -> app.repository.placeExists(id) }
                }
            }
            report.onSuccess { r ->
                val extra = if (r.unresolvablePlaceIds.isNotEmpty())
                    " ${r.unresolvablePlaceIds.size} favorite(s) point at places not in this device's catalog (kept anyway for when that region is added)." else ""
                backupStatus("Import done: ${r.inserted} added, ${r.updated} updated, ${r.skipped} already up to date.$extra")
                bind()
            }.onFailure {
                backupStatus("Import failed: ${it.message}")
            }
        }
    }

    private fun backupStatus(msg: String) {
        if (::root.isInitialized) root.findViewById<TextView>(R.id.backup_status)?.text = msg
        Toast.makeText(requireContext(), msg, Toast.LENGTH_LONG).show()
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        app = requireActivity().application as KyronApplication
        root = inflater.inflate(R.layout.fragment_account, container, false)
        bind()
        return root
    }

    override fun onResume() {
        super.onResume()
        if (::root.isInitialized) bind()
    }

    /** Re-bind after external state changes (e.g. a sync finished in MainActivity). */
    fun refresh() {
        if (::root.isInitialized && view != null) bind()
    }

    private fun bind() {
        val prefs = app.prefs

        // Profile
        val nameField = root.findViewById<EditText>(R.id.profile_name)
        // Never clobber an unsaved name the user is still typing.
        if (nameField.text.toString() != prefs.profileName && !nameField.hasFocus()) {
            nameField.setText(prefs.profileName)
        }
        root.findViewById<Button>(R.id.save_profile).setOnClickListener {
            prefs.profileName = nameField.text.toString()
            Toast.makeText(requireContext(), "Profile saved", Toast.LENGTH_SHORT).show()
        }

        // Sync
        val syncStatus = root.findViewById<TextView>(R.id.sync_status)
        syncStatus.text = if (prefs.lastSyncMs > 0)
            "Last synced: ${DateFormat.getDateTimeInstance().format(Date(prefs.lastSyncMs))}"
        else
            "Not synced yet — the app ships with a statewide snapshot and refreshes itself."
        val main = activity as? MainActivity
        val syncBtn = root.findViewById<Button>(R.id.sync_now)
        syncBtn.isEnabled = main?.syncing != true
        syncBtn.text = if (main?.syncing == true) "Syncing…" else "Sync now"
        syncBtn.setOnClickListener { main?.startSync(includeCounties = true) }
        root.findViewById<TextView>(R.id.sync_report).text = main?.lastReport ?: ""

        // Backup / restore
        root.findViewById<Button>(R.id.export_backup).setOnClickListener {
            exportLauncher.launch("kyron-backup.json")
        }
        root.findViewById<Button>(R.id.import_backup).setOnClickListener {
            importLauncher.launch(arrayOf("application/json", "text/plain"))
        }

        // Sources
        root.findViewById<TextView>(R.id.sources_text).text = SourceRegistry.all.joinToString("\n\n") { s ->
            "${s.displayName} — ${s.regionLabel}\nViolation detail: ${if (s.hasViolations) "yes — full why-summaries" else "no — score & date only"} · History: ${if (s.hasHistory) "yes" else "latest only"}"
        }
    }

    override fun onDestroyView() {
        scope.cancel()
        super.onDestroyView()
    }
}
