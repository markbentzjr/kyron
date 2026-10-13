import com.kyronapp.kyron.data.WhySummary
import com.kyronapp.kyron.source.AdphSource
import com.kyronapp.kyron.source.JcdhSource
import org.jsoup.Jsoup
import java.io.File

fun main() {
    val H = "/home/hatch/kyron-build/harvest"

    println("== ADPH parseResults (Madison Co. page, real Kotlin parser) ==")
    val adphDoc = Jsoup.parse(File("$H/test_adph_madison.html"), "UTF-8", "https://foodscores.state.al.us/")
    val adph = AdphSource().parseResults(adphDoc, "Madison")
    println("places parsed: ${adph.size}")
    println("missing dates: ${adph.count { it.date.isBlank() }}")
    adph.take(3).forEach { println("  ${it.name} | ${it.address}, ${it.city} ${it.zip} | score ${it.score} | '${it.date}'") }
    check(adph.size > 100) { "ADPH parse too small" }
    check(adph.count { it.date.isBlank() } == 0) { "ADPH dates still missing!" }

    println("== JCDH detail parse (permit 29433, real Kotlin parser) ==")
    val detDoc = Jsoup.parse(File("$H/test_jcdh_detail.html"), "UTF-8", "https://www.jcdh.org")
    val insps = JcdhSource().parseDetail(detDoc)
    println("inspections parsed: ${insps.size}")
    for (ins in insps) {
        val pts = ins.violations.sumOf { it.points }
        println("  ${ins.date} score=${ins.score} violations=${ins.violations.size} pointsLost=$pts (100-score=${100 - ins.score})")
        println("    why: ${WhySummary.summarize(ins).take(170)}")
    }
    check(insps.isNotEmpty()) { "JCDH detail parse empty" }

    println("== JCDH list parse (same selectors/regex as JcdhSource.fetchLatest) ==")
    val listDoc = Jsoup.parse(File("$H/test_jcdh_list.html"), "UTF-8", "https://www.jcdh.org")
    val table = listDoc.selectFirst("table#MainContent_gvFoodScores")
    check(table != null) { "list table not found" }
    val blobRe = Regex("^(.*?)\\s+(\\d+\\s+.+?)\\s+Smoke Free:.*$", RegexOption.DOT_MATCHES_ALL)
    var rows = 0
    var parsed = 0
    for (row in table!!.select("tr")) {
        val cells = row.select("td")
        if (cells.size < 4) continue
        rows++
        val score = cells[1].text().trim().toIntOrNull() ?: continue
        val m = blobRe.find(cells[2].text().trim()) ?: continue
        val (street, city, zip) = JcdhSource.splitAddress(m.groupValues[2].trim())
        if (rows <= 3) println("  ${m.groupValues[1].trim()} | $street, $city $zip | score $score | ${JcdhSource.normalizeDate(cells[3].text().trim())}")
        parsed++
    }
    println("rows: $rows, parsed: $parsed")
    check(parsed >= 40) { "JCDH list parse too small" }

    println("== MCHD mapping (same regexes as MchdSource) ==")
    val inspRe = Regex("^(\\d{1,2}/\\d{1,2}/\\d{4}),\\s*Score:\\s*(\\d+)")
    val arr = org.json.JSONArray(File("$H/mchd_rows.json").readText())
    var ok = 0
    var withHistory = 0
    for (r in 0 until arr.length()) {
        val row = arr.getJSONArray(r)
        var n = 0
        for (c in 3..6) {
            val cell = if (c < row.length()) row.optString(c, "").trim() else ""
            if (inspRe.find(cell) != null) n++
        }
        if (n > 0) ok++
        if (n > 1) withHistory++
    }
    println("rows: ${arr.length()}, with latest inspection: $ok, with history>1: $withHistory")
    check(ok == arr.length()) { "MCHD rows without a parseable latest inspection" }

    println("ALL OFFLINE HARNESS CHECKS PASSED")
}
