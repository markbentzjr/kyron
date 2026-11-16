"""Per-state configuration for the generic SafeFoodInspection (SFI)
adapter — harvest/sfi.

Seven jurisdictions run the same ASP.NET WebForms app
("Food Safety 5.x", PublicInspectionSearch.aspx): a date-ranged search
POST yields the gvInspections master grid — one row per establishment
with the in-window latest inspection (date/type/score-or-compliance)
plus a nested gvPastInspections carrying the establishment's complete
published history. Per-inspection detail arrives two ways:

  * a "Violation(s) N" lnkViolations LinkButton -> synchronous
    postback -> wucPublicInspectionViolations panel populated inline
    in the re-rendered page (code, explanation, inspector comments);
    verified on SD 2026-11-16.
  * a btnInspectionReport ImageButton -> postback returns a page whose
    window.open('/Common/ExternalFileViewer.aspx?ID=..&Key=..') URL
    serves the official report PDF; verified on VT 2026-11-16.

Fields:

  url         absolute PublicInspectionSearch.aspx URL (AR/PA deploy
              under /Web/, the rest under /Inspection/)
  state/name  USPS code + display name
  region/jur  Kyron region id + jurisdiction code
  source_id   registry source id (matches us_national_registry.json)
  agency      agency name in its own words
  model       registry result model for this jurisdiction
  score_col   "numeric" = Score column carries 0-100 (VT/SD/IA);
              "compliance" = column carries In/Out (PA) or similar
              text -> result_text, score stays NO_SCORE
  viols       "lnk" = lnkViolations links render in the grid;
              "pdf" = violations only via report PDFs
  start_year  first inspection year published on the portal
  enabled     probe-verified deployment

verified notes (2026-11-16 probes):
  * VT: Score column numeric (89 observed); no lnkViolations in rows —
    violations ride in the PDF report only.
  * SD: Score column numeric (100 observed); past-rows render
    "Violation(s) N" lnkViolations anchors; violations panel carries
    SD codified cites (44:02:07:xx) + inspector comments.
  * PA: "Compliance" column (In/Out) + Jurisdiction column (borough);
    past-rows carry "Violation(s) N" links.
  * AK/AR/IA/WY: same app shell live; column mix verified at fetch
    time per deployment (the grid header names are parsed, not
    assumed).
"""

STATES = {
    "vt": {
        "url": "https://vtdoh.safefoodinspection.com/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "VT", "name": "Vermont",
        "region": "us-vt", "jur": "VT-VDH", "source_id": "vt-vdh",
        "agency": "Vermont Department of Health — Food and Lodging "
                  "Program",
        "model": "SCORE_100_HIGH",
        "score_col": "numeric", "viols": "pdf",
        "start_year": 2016, "enabled": True,
    },
    "ia": {
        "url": "https://iowa.safefoodinspection.com/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "IA", "name": "Iowa",
        "region": "us-ia", "jur": "IA-DIA", "source_id": "ia-dia",
        "agency": "Iowa Dept. of Inspections, Appeals & Licensing — "
                  "Food & Consumer Safety",
        "model": "VIOLATIONS_ONLY",
        "score_col": "auto", "viols": "auto",
        "start_year": 2015, "enabled": True,
    },
    "sd": {
        "url": "https://sddoh.safefoodinspection.com/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "SD", "name": "South Dakota",
        "region": "us-sd", "jur": "SD-DOH", "source_id": "sd-doh",
        "agency": "South Dakota Department of Health — Office of "
                  "Health Protection (excl. Sioux Falls)",
        "model": "PASS_FAIL",
        "score_col": "numeric", "viols": "lnk",
        "start_year": 2015, "enabled": True,
    },
    "wy": {
        "url": "https://wda.safefoodinspection.com/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "WY", "name": "Wyoming",
        "region": "us-wy", "jur": "WY-WDA", "source_id": "wy-wda",
        "agency": "Wyoming Department of Agriculture — Consumer "
                  "Health Services (excl. 5 local jurisdictions)",
        "model": "PASS_FAIL",
        "score_col": "auto", "viols": "auto",
        "start_year": 2015, "enabled": True,
    },
    "ak": {
        "url": "https://adec.safefoodinspection.com/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "AK", "name": "Alaska",
        "region": "us-ak", "jur": "AK-DEC", "source_id": "ak-dec",
        "agency": "Alaska DEC — Food Safety & Sanitation "
                  "(excl. Municipality of Anchorage)",
        "model": "VIOLATIONS_ONLY",
        "score_col": "auto", "viols": "auto",
        "start_year": 2015, "enabled": True,
    },
    "ar": {
        "url": "https://foodserviceprod.adh.arkansas.gov/Web/"
               "inspection/publicinspectionsearch.aspx",
        "state": "AR", "name": "Arkansas",
        "region": "us-ar", "jur": "AR-ADH", "source_id": "ar-adh",
        "agency": "Arkansas Department of Health — Environmental "
                  "Health / Food Service",
        "model": "VIOLATIONS_ONLY",
        "score_col": "auto", "viols": "auto",
        "start_year": 2015, "enabled": True,
    },
    "pa": {
        "url": "https://www.pafoodsafety.pa.gov/Web/Inspection/"
               "PublicInspectionSearch.aspx",
        "state": "PA", "name": "Pennsylvania",
        "region": "us-pa", "jur": "PA-PDA", "source_id": "pa-pda",
        "agency": "Pennsylvania Department of Agriculture — Bureau of "
                  "Food Safety (excl. Philadelphia & Allegheny Co.)",
        "model": "PASS_FAIL",
        "score_col": "compliance", "viols": "lnk",
        "start_year": 2015, "enabled": True,
    },
}
