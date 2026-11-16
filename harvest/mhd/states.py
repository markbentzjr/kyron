"""Per-state configuration for the generic MyHealthDepartment (MHD)
adapter — harvest/mhd.

Every state on inspections.myhealthdepartment.com shares the same
{"task":"searchInspections"} POST API proved by the TN adapter; what
differs per deployment is the path token, the program vocabulary that
identifies food inspections, whether inspection detail pages are
server-rendered (older template) or SPA-shell (client-rendered only),
which stub field (if any) carries county, and which field carries the
jurisdiction's native result text.

  path          MHD path token ("virginia" -> /virginia/)
  state/name    USPS code + display name
  region/jur    Kyron region id + jurisdiction code
  source_id     registry source id (matches us_national_registry.json)
  agency        agency name in its own words
  model         registry result model for this jurisdiction
  food_program  lowercase substrings; a stub counts as a food
                inspection when programName OR permitType contains one
  county_field  stub field holding the county name, or None
  detail        "server" = /<path>/inspection/?inspectionID= renders
                full HTML (parseable); "none" = SPA shell only, ship
                stub-level inspections
  score_field   True only when the stub `score` is a real published
                value (never true here — none of these jurisdictions
                publishes a 0-100 score)
  disp_field    stub field holding the native result text
                (scoreDisplay carries "Pass" on CO, "" on WI/VA, the
                literal "None" on MT/HI — treated as empty)
  purposes      seed purpose vocabulary for the 1-day-floor partition
                fallback (observed values are added at runtime)

verified notes (2026-11-16 probes):
  * wisconsin-datcp: server-rendered 65KB detail pages with the full
    TN-class checklist + observations (same parse contract).
  * colorado / montana / soh: server-rendered ~9KB pages (permit link,
    "Score & Grade" strongs carrying result text like "Pass",
    printable-PDF pKey link) — violations sections may be empty; the
    PDF carries the report body.
  * virginia: /<path>/inspection/ returns the 10KB SPA shell — details
    are client-rendered, so ships stub-level (places + inspection
    dates/types + comments), no violations.
  * oregon: the /oregon path exists (200) but searchInspections
    answers [] for every unfiltered window probed — its deployment
    gates results behind a county/district GUID filter whose values
    are not enumerable from the public API. enabled=False until the
    district-GUID map is recovered (same story as TN's hand-built
    work/counties.json, but undiscovered here).
"""

STATES = {
    "va": {
        "path": "virginia", "state": "VA", "name": "Virginia",
        "region": "us-va", "jur": "VA-VDH", "source_id": "va-vdh",
        "agency": "Virginia Department of Health — Food Establishment "
                  "inspections (inspections.myhealthdepartment.com/virginia)",
        "model": "VIOLATIONS_ONLY",
        "food_program": ["food"],
        "county_field": None, "detail": "none",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Risk Factor", "Routine", "Follow-Up", "Complaint",
                     "Inspection", "Other"],
        "enabled": True,
    },
    "wi": {
        "path": "wisconsin-datcp", "state": "WI", "name": "Wisconsin",
        "region": "us-wi", "jur": "WI-DATCP", "source_id": "wi-datcp",
        "agency": "Wisconsin Dept. of Agriculture, Trade & Consumer "
                  "Protection — state-inspected retail food facilities",
        "model": "PASS_FAIL",
        "food_program": ["food"],
        "county_field": None, "detail": "server",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Routine", "Reinspection", "Follow-Up", "Complaint",
                     "Pre-License", "Other"],
        "enabled": True,
    },
    "co": {
        "path": "colorado", "state": "CO", "name": "Colorado",
        "region": "us-co", "jur": "CO-CDPHE", "source_id": "co-cdphe",
        "agency": "Colorado Dept. of Public Health & Environment + "
                  "delegated counties (Retail Food)",
        "model": "PASS_FAIL",
        "food_program": ["food"],
        "county_field": "ADCounty", "detail": "server",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Routine", "Follow-Up", "Complaint", "Reinspection",
                     "Other"],
        "enabled": True,
    },
    "mt": {
        "path": "montana", "state": "MT", "name": "Montana",
        "region": "us-mt", "jur": "MT-DPHHS", "source_id": "mt-dphhs",
        "agency": "Montana DPHHS — Retail Food / Wholesale Food "
                  "inspections (state-endorsed portal)",
        "model": "VIOLATIONS_ONLY",
        "food_program": ["food"],
        "county_field": None, "detail": "server",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Routine", "Follow-Up", "Complaint", "Other"],
        "enabled": True,
    },
    "hi": {
        "path": "soh", "state": "HI", "name": "Hawaii",
        "region": "us-hi", "jur": "HI-DOH", "source_id": "hi-doh",
        "agency": "Hawaii Dept. of Health — Food Safety Branch "
                  "(SoH Food Inspection)",
        "model": "PASS_FAIL",
        "food_program": ["food"],
        "county_field": None, "detail": "server",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Routine", "Follow-Up", "Complaint", "Other"],
        "enabled": True,
    },
    "or": {
        "path": "oregon", "state": "OR", "name": "Oregon",
        "region": "us-or", "jur": "OR-OHA", "source_id": "or-oha",
        "agency": "Oregon Health Authority — statewide (county-run) "
                  "inspections",
        "model": "PASS_FAIL",
        "food_program": ["food"],
        "county_field": None, "detail": "server",
        "score_field": False, "disp_field": "scoreDisplay",
        "purposes": ["Routine", "Follow-Up", "Complaint", "Other"],
        "enabled": False,  # path answers [] — county/district GUID map undiscovered
    },
}
