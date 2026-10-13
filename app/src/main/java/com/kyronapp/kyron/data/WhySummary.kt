package com.kyronapp.kyron.data

/**
 * Turns structured inspection violations into the plain-language
 * "Why this score?" summary. Rules-based and deterministic: it only
 * restates the deductions the health department recorded.
 */
object WhySummary {

    private val categories: List<Pair<Regex, String>> = listOf(
        Regex("3-501\\.16|41 F or below|135 F|cold holding|hot holding", RegexOption.IGNORE_CASE) to "food temperature control",
        Regex("6-301\\.|paper towels|handwashing|hand soap", RegexOption.IGNORE_CASE) to "handwashing supplies",
        Regex("6-501\\.112|dead or trapped|pest", RegexOption.IGNORE_CASE) to "pest control",
        Regex("5-205|plumbing", RegexOption.IGNORE_CASE) to "plumbing",
        Regex("5-501|dumpster|refuse", RegexOption.IGNORE_CASE) to "trash & dumpster upkeep",
        Regex("3-304|3-501|wiping cloths|food-contact|food contact|single-service|single-use|employee food|2-401", RegexOption.IGNORE_CASE) to "food storage & handling",
        Regex("4-60[12]|non-food contact|nonfood contact", RegexOption.IGNORE_CASE) to "equipment & surface cleaning",
        Regex("4-302|thermometer", RegexOption.IGNORE_CASE) to "missing required equipment",
        Regex("4-501|equipment in good repair|gasket", RegexOption.IGNORE_CASE) to "equipment repair",
        Regex("6-501|clean facilities|physical facilities", RegexOption.IGNORE_CASE) to "facility cleanliness & repair",
        Regex("8-403|post current inspection", RegexOption.IGNORE_CASE) to "paperwork / posting"
    )

    fun categoryOf(remarks: String): String =
        categories.firstOrNull { it.first.containsMatchIn(remarks) }?.second ?: "other violations"

    fun summarize(insp: Inspection): String {
        if (insp.violations.isEmpty()) {
            return "Scored ${insp.score} with no violations recorded — a clean inspection."
        }
        val lost = insp.violations.sumOf { it.points }
        val sorted = insp.violations.sortedByDescending { it.points }
        val top = sorted.first()
        val topEvidence = top.inspectorNote.ifBlank { top.ruleText }
        val sb = StringBuilder()
        sb.append("Scored ${insp.score} — lost $lost point${if (lost == 1) "" else "s"} across ")
        sb.append("${insp.violations.size} item${if (insp.violations.size == 1) "" else "s"}. ")
        sb.append("Biggest deduction: ${categoryOf(top.remarks)} (−${top.points} pts): ")
        sb.append(topEvidence.take(180))
        val rest = sorted.drop(1)
            .groupBy { categoryOf(it.remarks) }
            .mapValues { e -> e.value.sumOf { it.points } }
            .entries.sortedByDescending { it.value }
        if (rest.isNotEmpty()) {
            sb.append(" Also: ")
            sb.append(rest.joinToString(", ") { "${it.key} (−${it.value})" })
            sb.append(".")
        }
        return sb.toString()
    }

    /** What a score band means, for places whose source publishes no violation detail. */
    fun bandExplainer(score: Int): String = when {
        score >= 95 -> "A score of $score is excellent — at its last inspection this establishment was meeting food-safety standards with at most minor deductions. (This source publishes the score and date only, not the violation list.)"
        score >= 85 -> "A score of $score is in Alabama's passing range, but points were deducted for food-safety problems found at inspection. (This source publishes the score and date only, not the violation list.)"
        else -> "A score of $score is below 85, Alabama's reinspection line: the health department requires a follow-up inspection, usually within 60 days. Scores this low typically involve problems like unsafe food temperatures or sanitation failures. (This source publishes the score and date only, not the violation list.)"
    }
}
