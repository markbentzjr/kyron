package com.kyronapp.kyron.source

import com.kyronapp.kyron.data.Inspection
import com.kyronapp.kyron.data.Place
import com.kyronapp.kyron.data.Violation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import java.util.concurrent.TimeUnit

/**
 * A Kyron data source = one jurisdiction's official publication of food
 * inspection scores. Coverage grows by adding an adapter here and an entry
 * in [SourceRegistry] — the US has no single national database, so each
 * state/county publishes its own and Kyron adapts per jurisdiction.
 */
interface PlaceSource {
    val id: String
    val displayName: String
    val regionLabel: String
    /** True when the source publishes violation-level detail (enables full "why" summaries). */
    val hasViolations: Boolean
    /** True when the source publishes more than the latest inspection per place. */
    val hasHistory: Boolean
}

object Http {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(100, TimeUnit.SECONDS)
        .build()

    suspend fun get(url: String): String = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url)
            .header("User-Agent", "KyronHealthApp/2.0 (Android)")
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw java.io.IOException("HTTP ${resp.code} for $url")
            resp.body?.string() ?: throw java.io.IOException("Empty body for $url")
        }
    }

    suspend fun postForm(url: String, fields: Map<String, String>): String = withContext(Dispatchers.IO) {
        val body = okhttp3.FormBody.Builder().apply {
            fields.forEach { (k, v) -> add(k, v) }
        }.build()
        val req = Request.Builder().url(url)
            .header("User-Agent", "KyronHealthApp/2.0 (Android)")
            .post(body)
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw java.io.IOException("HTTP ${resp.code} for $url")
            resp.body?.string() ?: throw java.io.IOException("Empty body for $url")
        }
    }
}

// ---------------------------------------------------------------------------
// Jefferson County, AL — Jefferson County Department of Health (jcdh.org)
// Publishes latest inspections + per-inspection violation detail pages.
// ---------------------------------------------------------------------------
class JcdhSource : PlaceSource {
    override val id = "JCDH"
    override val displayName = "Jefferson County Dept. of Health"
    override val regionLabel = "Jefferson County, AL"
    override val hasViolations = true
    override val hasHistory = true

    private val listUrl =
        "https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/Food/FoodServScores.aspx"

    /** The county's most recent inspections (the public list shows the latest ~50). */
    suspend fun fetchLatest(): List<Place> {
        val html = Http.get(listUrl)
        val doc = Jsoup.parse(html, "https://www.jcdh.org")
        val table = doc.selectFirst("table#MainContent_gvFoodScores") ?: return emptyList()
        val out = mutableListOf<Place>()
        val blobRe = Regex("^(.*?)\\s+(\\d+\\s+.+?)\\s+Smoke Free:.*$", RegexOption.DOT_MATCHES_ALL)
        for (row in table.select("tr")) {
            val cells = row.select("td")
            if (cells.size < 4) continue
            val permit = cells[0].text().trim()
            val score = cells[1].text().trim().toIntOrNull() ?: continue
            val blob = cells[2].text().trim()
            val date = cells[3].text().trim()
            val m = blobRe.find(blob)
            val name = (m?.groupValues?.get(1) ?: blob).trim()
            val address = (m?.groupValues?.get(2) ?: "").trim()
            val link = row.selectFirst("a[href*=FoodServScoreDetails]")?.absUrl("href")
            val (street, city, zip) = splitAddress(address)
            out += Place(
                id = "jcdh_$permit",
                name = name.lowercase().replace(Regex("\\b\\w")) { it.value.uppercase() },
                address = street, city = city, zip = zip,
                county = "Jefferson", score = score, date = normalizeDate(date),
                source = id, detailUrl = link
            )
        }
        return out
    }

    /** Fetch the detail page for a place: up to 4 inspections with violations. */
    suspend fun fetchDetail(place: Place): List<Inspection> {
        val url = place.detailUrl ?: return emptyList()
        val html = Http.get(url)
        val doc = Jsoup.parse(html, "https://www.jcdh.org")
        return parseDetail(doc)
    }

    internal fun parseDetail(doc: Document): List<Inspection> {
        val grids = doc.select("table[id*=GVScoreDetails]")
        val inspections = mutableListOf<Inspection>()
        for (gv in grids) {
            val rows = gv.select("tr")
            if (rows.size < 2) continue
            val header = rows[0].select("td, th").map { it.text().trim() }
            val hasCritical = header.any { it.equals("Critical", true) }
            val viols = mutableListOf<Violation>()
            for (r in rows.drop(1)) {
                val cs = r.select("td").map { it.text().trim() }
                if (cs.isEmpty()) continue
                val pts = cs[0].toIntOrNull() ?: continue
                val crit = hasCritical && cs.getOrNull(1)?.equals("Yes", true) == true
                val remarks = if (hasCritical) cs.getOrNull(2) ?: "" else cs.getOrNull(1) ?: ""
                viols += Violation(pts, crit, remarks)
            }
            inspections += Inspection(score = 0, date = "", violations = viols)
        }
        // Pair each grid with its summary block ("NN Score ... Inspected Date M/D/YYYY")
        val blockRe = Regex("^(\\d{2,3}) Score Smoke Free \\w+ Inspection Type (.+?) Inspected Date ([\\d/]+)$")
        val blocks = mutableListOf<Triple<Int, String, String>>()
        for (t in doc.select("table")) {
            val m = blockRe.find(t.text().trim()) ?: continue
            val b = Triple(m.groupValues[1].toInt(), m.groupValues[3], m.groupValues[2])
            if (blocks.none { it.first == b.first && it.second == b.second }) blocks += b
        }
        return inspections.mapIndexed { i, insp ->
            val b = blocks.getOrNull(i)
            if (b != null) insp.copy(score = b.first, date = normalizeDate(b.second), type = b.third) else insp
        }.filter { it.score > 0 }
    }

    companion object {
        fun normalizeDate(d: String): String {
            // JCDH list uses 2-digit years (10/09/26); detail pages use 4-digit.
            val parts = d.trim().split("/")
            if (parts.size != 3) return d.trim()
            val y = parts[2].let { if (it.length == 2) "20$it" else it }
            return "${parts[0]}/${parts[1]}/$y"
        }

        /** "1435 BANKHEAD HWY GRAYSVILLE 35073" -> street / city / zip (last token city heuristic). */
        fun splitAddress(raw: String): Triple<String, String, String> {
            val zipM = Regex("(\\d{5})\\s*$").find(raw) ?: return Triple(raw, "", "")
            val zip = zipM.groupValues[1]
            val rest = raw.substring(0, zipM.range.first).trim()
            val multi = listOf("VESTAVIA HILLS", "MOUNTAIN BROOK", "CENTER POINT", "PLEASANT GROVE", "SYLVAN SPRINGS")
            for (mc in multi) {
                if (rest.uppercase().endsWith(" $mc")) {
                    return Triple(rest.dropLast(mc.length).trim(), mc.lowercase().replace(Regex("\\b\\w")) { it.value.uppercase() }, zip)
                }
            }
            val idx = rest.lastIndexOf(' ')
            if (idx < 0) return Triple(rest, "", zip)
            val city = rest.substring(idx + 1).lowercase().replace(Regex("\\b\\w")) { it.value.uppercase() }
            return Triple(rest.substring(0, idx).trim(), city, zip)
        }
    }
}

// ---------------------------------------------------------------------------
// State of Alabama — Alabama Dept. of Public Health (foodscores.state.al.us)
// Statewide ASP.NET search: name / city / county. Publishes score + date only.
// ---------------------------------------------------------------------------
class AdphSource : PlaceSource {
    override val id = "ADPH"
    override val displayName = "Alabama Dept. of Public Health"
    override val regionLabel = "Statewide, AL"
    override val hasViolations = false
    override val hasHistory = false

    private val base = "https://foodscores.state.al.us/default.aspx"

    suspend fun fetchCounty(county: String): List<Place> = search(name = "", city = "", county = county)
    suspend fun fetchByName(name: String): List<Place> = search(name = name, city = "", county = "")

    private suspend fun search(name: String, city: String, county: String): List<Place> =
        withContext(Dispatchers.IO) {
            // 1) GET the form (cookieless session URL + ViewState)
            val getReq = Request.Builder().url(base)
                .header("User-Agent", "KyronHealthApp/2.0 (Android)").build()
            val (sessionUrl, formDoc) = Http.client.newCall(getReq).execute().use { resp ->
                val body = resp.body?.string() ?: throw java.io.IOException("ADPH empty form")
                resp.request.url.toString() to Jsoup.parse(body)
            }
            fun hidden(n: String): String =
                formDoc.selectFirst("input[name=$n]")?.attr("value") ?: ""
            val countyValue: String = if (county.isBlank()) "Select County" else {
                val sel = formDoc.selectFirst("select[name=ctl00\$ContentPlaceHolder1\$DrpCnty]")
                val want = county.uppercase().replace(Regex("[^A-Z]"), "")
                sel?.select("option")?.firstOrNull {
                    it.text().trim().uppercase().replace(Regex("[^A-Z]"), "") == want
                }?.attr("value")
                    ?: "Select County"
            }
            val typeValue = formDoc.selectFirst("select[name=ctl00\$ContentPlaceHolder1\$DrpEstdType]")
                ?.select("option")?.firstOrNull()?.attr("value") ?: "All"
            val form = FormBody.Builder()
                .add("__VIEWSTATE", hidden("__VIEWSTATE"))
                .add("__VIEWSTATEGENERATOR", hidden("__VIEWSTATEGENERATOR"))
                .add("__EVENTVALIDATION", hidden("__EVENTVALIDATION"))
                .add("ctl00\$ContentPlaceHolder1\$TxtEstdNm", name)
                .add("ctl00\$ContentPlaceHolder1\$DrpEstdType", typeValue)
                .add("ctl00\$ContentPlaceHolder1\$txtCity", city)
                .add("ctl00\$ContentPlaceHolder1\$DrpCnty", countyValue)
                .add("ctl00\$ContentPlaceHolder1\$BtnSearch.x", "10")
                .add("ctl00\$ContentPlaceHolder1\$BtnSearch.y", "10")
                .build()
            val postReq = Request.Builder().url(sessionUrl).post(form)
                .header("User-Agent", "KyronHealthApp/2.0 (Android)").build()
            val html = Http.client.newCall(postReq).execute().use { resp ->
                if (!resp.isSuccessful) throw java.io.IOException("ADPH HTTP ${resp.code}")
                resp.body?.string() ?: throw java.io.IOException("ADPH empty results")
            }
            parseResults(Jsoup.parse(html), county)
        }

    internal fun parseResults(doc: Document, countyHint: String): List<Place> {
        val dtList = doc.getElementById("ctl00_ContentPlaceHolder1_DtList") ?: return emptyList()
        val out = mutableListOf<Place>()
        for (cell in dtList.select("td")) {
            val withBreaks = cell.html().replace(Regex("(?i)<br[^>]*>"), "|")
            val text = Jsoup.parseBodyFragment(withBreaks).text()
            if (!text.contains("Establishment Name:")) continue
            val fields = mutableMapOf<String, String>()
            val segments = text.split("|").map { it.trim() }.filter { it.isNotEmpty() }
            val labelRe = Regex("^(Establishment Name|Address|City|Zip Code|Score|Smoke Free|Inspection date):\\s*(.*)$")
            var i = 0
            while (i < segments.size) {
                val labelMatch = labelRe.find(segments[i])
                if (labelMatch != null) {
                    val label = labelMatch.groupValues[1]
                    var value = labelMatch.groupValues[2]
                    // Blank values (e.g. an empty "Smoke Free:") must not swallow the
                    // next label as their value — that used to eat the inspection date.
                    if (value.isBlank() && i + 1 < segments.size && !labelRe.containsMatchIn(segments[i + 1])) {
                        value = segments[i + 1]; i++
                    }
                    fields[label] = value
                }
                i++
            }
            val nm = fields["Establishment Name"] ?: continue
            val sc = fields["Score"]?.toIntOrNull() ?: continue
            val addr = fields["Address"] ?: ""
            val cty = fields["City"] ?: ""
            val zip = (fields["Zip Code"] ?: "").take(5)
            out += Place(
                id = "adph_" + Integer.toHexString(Place.matchKey(nm, zip, addr).hashCode()),
                name = nm, address = addr, city = cty, zip = zip,
                county = countyHint.ifBlank { "" },
                score = sc, date = fields["Inspection date"] ?: "",
                source = id
            )
        }
        return out
    }
}

// ---------------------------------------------------------------------------
// Mobile County, AL — Mobile County Health Dept. (mchd.org)
// Mobile is one of Alabama's two independent county health departments and is
// NOT in the ADPH feed. Its ratings page is a WordPress Data Access table
// backed by a public admin-ajax endpoint; each row carries up to four dated
// inspection scores (latest + three previous). No violation detail.
// ---------------------------------------------------------------------------
class MchdSource : PlaceSource {
    override val id = "MCHD"
    override val displayName = "Mobile County Health Dept."
    override val regionLabel = "Mobile County, AL"
    override val hasViolations = false
    override val hasHistory = true

    private val endpoint = "https://mchd.org/wp-admin/admin-ajax.php"
    private val columns = listOf("EST_NAME", "EST_ADDRESS", "EST_CSZ", "INS_ONE", "INS_TWO", "INS_THREE", "INS_FOUR")
    private val inspRe = Regex("^(\\d{1,2}/\\d{1,2}/\\d{4}),\\s*Score:\\s*(\\d+)")
    private val zipRe = Regex("(\\d{5})")

    suspend fun fetchAll(): List<Place> {
        val fields = LinkedHashMap<String, String>()
        fields["action"] = "wpda_datatables"
        fields["wpnonce"] = "e3fc94ab8e" // publication id embedded in the public ratings page
        fields["pubid"] = "1"
        fields["filter_field_name"] = ""
        fields["filter_field_value"] = ""
        fields["nl2br"] = ""
        fields["draw"] = "1"
        fields["start"] = "0"
        fields["length"] = "5000"
        fields["search[value]"] = ""
        fields["search[regex]"] = "false"
        fields["order[0][column]"] = "0"
        fields["order[0][dir]"] = "asc"
        columns.forEachIndexed { i, c ->
            fields["columns[$i][data]"] = i.toString()
            fields["columns[$i][name]"] = c
            fields["columns[$i][searchable]"] = "true"
            fields["columns[$i][orderable]"] = "true"
            fields["columns[$i][search][value]"] = ""
            fields["columns[$i][search][regex]"] = "false"
        }
        val json = Http.postForm(endpoint, fields)
        val root = org.json.JSONObject(json)
        val data = root.getJSONArray("data")
        val out = mutableListOf<Place>()
        for (r in 0 until data.length()) {
            val row = data.getJSONArray(r)
            fun cell(i: Int): String = if (i < row.length()) row.optString(i, "").trim() else ""
            val name = cell(0)
            if (name.isBlank()) continue
            val address = cell(1)
            val csz = cell(2)
            val city = csz.substringBefore(",").trim()
            val zip = zipRe.find(csz)?.groupValues?.get(1) ?: ""
            val insps = mutableListOf<com.kyronapp.kyron.data.Inspection>()
            for (c in 3..6) {
                val m = inspRe.find(cell(c)) ?: continue
                val sc = m.groupValues[2].toIntOrNull() ?: continue
                insps += com.kyronapp.kyron.data.Inspection(sc, m.groupValues[1], "", emptyList())
            }
            val latest = insps.firstOrNull() ?: continue
            out += Place(
                id = "mchd_" + Integer.toHexString(Place.matchKey(name, zip, address).hashCode()),
                name = name, address = address, city = city, zip = zip,
                county = "Mobile", score = latest.score, date = latest.date,
                source = id, inspections = insps
            )
        }
        return out
    }
}

/** The registry of live sources. Adding a state = adding an adapter + one entry here. */
object SourceRegistry {
    val jcdh = JcdhSource()
    val adph = AdphSource()
    val mchd = MchdSource()
    val all: List<PlaceSource> = listOf(jcdh, adph, mchd)

    fun byId(id: String): PlaceSource? = all.firstOrNull { it.id == id }
}
