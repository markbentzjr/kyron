#!/usr/bin/env python3
"""
Kyron national coverage pipeline (LF-N nationwide expansion).

Single source of truth for Kyron's nationwide coverage registry:
  registry()          -> the structured registry data (all 50 US states +
                         Washington, D.C. as a separate jurisdiction)
  write_json(path)    -> renders the app asset
                         app/src/main/assets/coverage/us_national_registry.json
  validate(path)      -> coverage gate: exactly 50 unique states + D.C.,
                         required fields, status/access vocabularies, region
                         id format, unique source ids
  render_matrix(path) -> the human-readable 50-state source/coverage matrix
                         (docs/Kyron-National-Coverage-Matrix.md)

Run from the repo root:
    python tools/coverage/coverage_pipeline.py build     # regenerate JSON asset
    python tools/coverage/coverage_pipeline.py gate      # validate the JSON asset
    python tools/coverage/coverage_pipeline.py matrix    # regenerate the matrix doc

Statuses (honest, mutually distinct — do not conflate):
  integrated          data ships in the app today (bundled seed / live sync)
  pack-built          verified ingestion + validated pack artifact built;
                      publication state is tracked SEPARATELY (pack_host_status)
  source-verified     official endpoint fetched by a human (HTTP 200 with real
                      content) — no ingestion pipeline yet
  official-link-only  official portal known; NOT integrated, NOT verified
                      reproducible; must never count as restaurant data
  blocked             integration attempted/considered; a named blocker prevents it

Verification dates record when the URL was last verified by direct fetch or
verified web research; "" means unverified (allowed only for
official-link-only statuses).
"""

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSET = REPO / "app" / "src" / "main" / "assets" / "coverage" / "us_national_registry.json"
MATRIX = REPO / "docs" / "Kyron-National-Coverage-Matrix.md"

STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
    ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
    ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

VALID_STATUS = {"integrated", "pack-built", "source-verified", "official-link-only", "blocked"}
VALID_ACCESS = {"live-sync", "html", "bulk-csv", "api", "pdf", "official-link-only"}
VALID_VIOLATIONS = {"full", "partial", "none", "unverified"}
VALID_HISTORY = {"latest-only", "some-history", "full-history", "unverified"}
VALID_MODELS = {"SCORE_100_HIGH", "PENALTY_LOW", "LETTER_GRADE", "PASS_FAIL",
                "DISPOSITION", "VIOLATIONS_ONLY"}
VALID_PACK_STATUS = {"bundled", "published", "built", "none"}
VALID_PACK_AVAILABILITY = {"bundled", "downloadable-verified", "declared-only",
                           "staged-local", "none"}
VALID_HOST_STATUS = {"reachable", "unreachable-404", "unreachable", "not-published", ""}


def region_id(code):
    name = dict((c, n) for c, n in STATES)[code]
    return "us-dc" if code == "DC" else "us-" + code.lower()


# Coarse centroids (registry DATA, not UI decisions): the midpoint of each
# state's bounding box, used only to anchor a fallback map view / synthesized
# region descriptor. Bounds mirrored from app Regions.kt STATE_BOUNDS.
_CENTERS = {
    "AL": (32.58, -86.68), "AK": (61.28, -154.99), "AZ": (34.17, -111.93),
    "AR": (34.75, -92.13), "CA": (37.27, -119.27), "CO": (39.00, -105.55),
    "CT": (41.52, -72.76), "DE": (39.15, -75.42), "FL": (27.70, -83.72),
    "GA": (32.68, -83.23), "HI": (20.58, -157.53), "ID": (45.50, -114.14),
    "IL": (39.74, -87.52), "IN": (39.77, -86.46), "IA": (41.94, -93.83),
    "KS": (38.50, -98.32), "KY": (37.90, -85.77), "LA": (30.98, -91.43),
    "ME": (45.26, -69.02), "MD": (38.81, -77.27), "MA": (41.99, -71.43),
    "MI": (45.00, -86.27), "MN": (46.44, -93.41), "MS": (32.38, -89.88),
    "MO": (38.31, -92.70), "MT": (46.68, -110.05), "NE": (41.50, -98.68),
    "NV": (38.50, -117.03), "NH": (44.01, -71.64), "NJ": (40.15, -74.73),
    "NM": (34.17, -106.03), "NY": (42.76, -75.81), "NC": (35.22, -79.19),
    "ND": (47.47, -100.57), "OH": (40.19, -82.67), "OK": (35.31, -98.72),
    "OR": (44.14, -120.52), "PA": (41.00, -77.61), "RI": (41.67, -71.49),
    "SC": (33.63, -80.96), "SD": (44.22, -100.26), "TN": (35.83, -85.98),
    "TX": (31.17, -100.08), "UT": (39.50, -111.55), "VT": (43.87, -72.45),
    "VA": (38.01, -79.48), "WA": (47.27, -120.83), "WV": (38.92, -80.18),
    "WI": (44.79, -89.85), "WY": (43.00, -107.56),
    "DC": (38.90, -77.03),
}


# ---------------------------------------------------------------------------
# Registry data.
# Sources carried over from docs/Kyron-USA-Source-Registry.md (verified
# Oct 13 2026 by live web research) keep verified="2026-10-13". Sources
# verified during the LF-N expansion (2026-10-22, direct HTTP GET by the
# research pass) keep verified="2026-10-22" with the HTTP result in notes.
#package
def src(sid, agency, coverage, access, website, violations, history, status,
        result_model, verified="", blocker="", restrictions="", refresh="",
        last_refresh="", notes=""):
    return {
        "id": sid,
        "agency": agency,
        "coverage": coverage,
        "access": access,
        "website": website,
        "violations": violations,
        "history": history,
        "result_model": result_model,
        "status": status,
        "verified": verified,
        "blocker": blocker,
        "restrictions": restrictions,
        "refresh": refresh,
        "last_refresh": last_refresh,
        "notes": notes,
    }


def link_only(sid, agency, website, notes, state_model="VIOLATIONS_ONLY"):
    """The clearly-labeled official-link-only fallback for states with no
    verified reproducible access today. NEVER counts as restaurant data."""
    return src(sid, agency, "Statewide (not verified)", "official-link-only",
               website, "unverified", "unverified", "official-link-only", state_model,
               restrictions="No reproducible automated access verified; official link "
                            "only — NOT integrated restaurant data.",
               notes=notes)


def registry():
    r = []

    def add(code, name, model, sources, pack="none", manifest=None,
            host="", host_checked="", availability=None, artifact_verified="",
            jtype=None, summary=""):
        # Availability must always be explicit-or-derived: a publication
        # claim with no verified artifact is REGISTERED but NOT available.
        if availability is None:
            if pack == "bundled":
                availability = "bundled"
            elif pack == "published":
                availability = "downloadable-verified" if artifact_verified else "declared-only"
            elif pack == "built":
                availability = "staged-local"
            else:
                availability = "none"
        c = _CENTERS[code]
        r.append({
            "regionId": region_id(code),
            "state": code,
            "name": name,
            "type": jtype or ("federal-district" if code == "DC" else "state"),
            "result_model": model,
            "summary": summary,
            "pack_status": pack,
            "pack_manifest_url": manifest,
            "pack_availability": availability,
            "artifact_verified": artifact_verified,
            "pack_host_status": host,
            "pack_host_checked": host_checked,
            "center": {"lat": c[0], "lng": c[1]},
            "sources": sources,
        })

    # ------------------------------------------------------------- ALABAMA
    add("AL", "Alabama", "SCORE_100_HIGH", [
        src("al-jcdh", "Jefferson County Department of Health", "Jefferson County",
            "live-sync", "https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/Food/FoodServScores.aspx",
            "full", "full-history", "integrated", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="In-app live adapter (every ~12 h) + bundled seed",
            notes="Scores plus full violation detail and per-place inspection history."),
        src("al-adph", "Alabama Department of Public Health", "Statewide (65 counties)",
            "html", "https://foodscores.state.al.us/default.aspx",
            "none", "latest-only", "integrated", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="In-app live adapter (county re-checks ~20 h) + bundled seed",
            notes="ASP.NET statewide search; latest score + inspection date only. "
                  "Tallapoosa County upstream HTTP 500 (README caveat).",
            restrictions="Jefferson and Mobile are NOT served by ADPH — separate agencies."),
        src("al-mchd", "Mobile County Health Department", "Mobile County",
            "html", "https://mchd.org/",
            "none", "some-history", "integrated", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="In-app live adapter (admin-ajax table)",
            notes="Up to 4 dated inspections per establishment; no violation detail."),
    ], pack="bundled",
        summary="Shipped bundled in the APK; three live sync sources.")

    # ------------------------------------------------------------- FLORIDA
    add("FL", "Florida", "DISPOSITION", [
        src("fl-dbpr", "Florida Department of Business & Professional Regulation (DBPR), Hotels & Restaurants",
            "Statewide", "bulk-csv",
            "https://www2.myfloridalicense.com/hotels-restaurants/",
            "full", "latest-only", "pack-built", "DISPOSITION",
            verified="2026-10-13",
            refresh="Harvest pipeline harvest/fl_dbpr -> tools/packs/build_pack.py",
            notes="No numeric score: outcomes are dispositions (met standards, warning, "
                  "closure…). District CSV extracts + inspection detail pages. Pack built "
                  "and app-verified (70,051 places)."),
    ], pack="published",
        manifest="https://markbentzjr.github.io/kyron/data/us-fl.manifest.json",
        host="unreachable-404", host_checked="2026-10-22",
        availability="declared-only",
        summary="Pack built and registered in-app; the PUBLICATION is declared but "
                "the pack host returned HTTP 404 on 2026-10-22 — the download is NOT "
                "verified available until it is republished (declared-only).")

    # ------------------------------------------------------------ GEORGIA
    add("GA", "Georgia", "SCORE_100_HIGH", [
        src("ga-dph", "Georgia Department of Public Health",
            "Statewide (excl. Gwinnett/Newton/Rockdale)",
            "html", "https://ga.healthinspections.us/stateofgeorgia/",
            "full", "some-history", "pack-built", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="Harvest pipeline harvest/ga -> tools/packs/build_pack.py",
            notes="100-point scale with A/B/C/U grades; full inspector notes.",
            restrictions="Gwinnett, Newton and Rockdale counties are NOT in the statewide search."),
    ], pack="published",
        manifest="https://markbentzjr.github.io/kyron/data/us-ga.manifest.json",
        host="unreachable-404", host_checked="2026-10-22",
        availability="declared-only",
        summary="Pack verified end-to-end in the rig and registered in-app; the "
                "publication is declared but the host returned HTTP 404 on "
                "2026-10-22 (declared-only, not verified downloadable).")

    # ---------------------------------------------------------- TENNESSEE
    add("TN", "Tennessee", "SCORE_100_HIGH", [
        src("tn-tdh", "Tennessee Department of Health",
            "Statewide", "html",
            "https://inspections.myhealthdepartment.com/tennessee",
            "full", "some-history", "pack-built", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="Harvest pipeline harvest/tn",
            notes="Statewide scores with per-violation observation text (HealthSpace "
                  "platform). Place dataset built (122,091 detail pages); pack staged, "
                  "not yet published."),
    ], pack="built",
        availability="staged-local",
        summary="Ingestion verified (138 MB place dataset, QA crosscheck pass); "
                "pack staged locally — blocked on publishing infrastructure.")

    # ------------------------------------------------------- SOUTH CAROLINA
    add("SC", "South Carolina", "SCORE_100_HIGH", [
        src("sc-dhec", "South Carolina DHEC — Food Grades",
            "Statewide", "html",
            "https://apps.dhec.sc.gov/Environment/FoodGrades/",
            "full", "some-history", "pack-built", "SCORE_100_HIGH",
            verified="2026-10-13",
            refresh="Harvest pipeline harvest/sc",
            notes="Points-based (A >87); full inspection report as PDF. 35,862 places "
                  "harvested; pack staged, not yet published."),
    ], pack="built",
        availability="staged-local",
        summary="Ingestion verified (35,862 places, QA all-pass); pack staged "
                "locally — blocked on publishing infrastructure.")

    # ------------------------------------------------------- NORTH CAROLINA
    add("NC", "North Carolina", "SCORE_100_HIGH", [
        src("nc-dhhs", "North Carolina DHHS — Environmental Health Inspections",
            "Statewide (county-run inspections, statewide front-end)", "html",
            "https://epi.ncdhhs.gov/inspections/search",
            "full", "latest-only", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-13",
            notes="100-pt scores with A/B/C grade cards; violations as written by the "
                  "inspector. Harvest adapters exist (harvest/nc) but no pack yet."),
    ], summary="Statewide web front-end over county inspections.")

    # ------------------------------------------------------ REST of tier 1
    add("MS", "Mississippi", "LETTER_GRADE", [
        src("ms-msdh", "Mississippi State Department of Health", "Statewide", "html",
            "https://msdh.ms.gov/page/43,0,231,203.html",
            "partial", "full-history", "source-verified", "LETTER_GRADE",
            verified="2026-10-13",
            notes="Letter grades A/B/C only (no numeric score); full inspection "
                  "history per facility (apps.msdh.ms.gov/food/FacilityRecord.aspx)."),
    ], summary="Letter grades only — the registry's Kyron model is LETTER_GRADE; "
               "numeric Alabama bands do NOT apply.")

    add("VA", "Virginia", "VIOLATIONS_ONLY", [
        src("va-vdh", "Virginia Department of Health", "Statewide (health districts)", "html",
            "https://inspections.myhealthdepartment.com/virginia/districts",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-13",
            notes="Violations with critical/non-critical flags and corrective "
                  "actions; no score or grade of any kind."),
    ], summary="Violations-only jurisdiction — alerts are new-result notices, never "
               "threshold violations.")

    add("AR", "Arkansas", "VIOLATIONS_ONLY", [
        src("ar-adh", "Arkansas Department of Health", "Statewide", "html",
            "https://foodserviceprod.adh.arkansas.gov/Web/inspection/publicinspectionsearch.aspx",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-13",
            notes="In/out-of-compliance model with per-report observation detail."),
    ], summary="In/out-of-compliance model.")

    add("LA", "Louisiana", "VIOLATIONS_ONLY", [
        src("la-ldh", "Louisiana Department of Health (EatSafe)", "Statewide", "html",
            "https://eatsafe.la.gov/",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-13",
            notes="Updated daily; violations (critical vs non-critical) + corrective "
                  "actions; historically pelican-icon ratings rather than numbers."),
    ], summary="Violation-based; icon ratings are jurisdiction presentation, not a "
               "numeric Kyron score.")

    add("PA", "Pennsylvania", "PASS_FAIL", [
        src("pa-pda", "Pennsylvania Department of Agriculture", "Statewide (excl. some city/county programs)",
            "html", "https://www.pafoodsafety.pa.gov/Web/Inspection/PublicInspectionSearch.aspx",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-13",
            notes="Violations + inspector comments in full report view.",
            restrictions="Covers state-inspected facilities; Philadelphia and Allegheny "
                         "County run their own programs."),
    ], summary="Pass/fail with published violation reports.")

    # ------------------------------------------------------- verified cities
    add("NY", "New York", "PENALTY_LOW", [
        src("ny-nyc-dohmh", "NYC Department of Health & Mental Hygiene",
            "New York City", "api",
            "https://data.cityofnewyork.us/Health/DOHMH-New-York-City-Restaurant-Inspection-Results/43nn-pn8j",
            "full", "full-history", "pack-built", "PENALTY_LOW",
            verified="2026-10-25", last_refresh="2026-10-25",
            refresh="Harvest pipeline harvest/socrata_cities (nyc)",
            notes="Socrata API (resource/43nn-pn8j.json): one row per violation "
                  "citation; score = violation points (LOWER is better; A=0-13, "
                  "B=14-27, C=28+), letter grade carried as result text. Pack BUILT "
                  "locally 2026-10-25 (31,368 places / 92,713 inspections / "
                  "287,206 violations). Attribution: NYC DOHMH via NYC Open Data.",
            restrictions="NYC only — the rest of New York State is fragmented by county."),
        link_only("ny-statewide", "Rest of New York State (county health departments)",
                  "https://www.health.ny.gov/food_safety/",
                  "No statewide public portal verified; county-level publication."),
    ], pack="built", availability="staged-local", artifact_verified="2026-10-25",
        summary="NYC pack built + validated locally (penalty points + letter grade); "
               "upstate is county-fragmented.")

    add("IL", "Illinois", "PASS_FAIL", [
        src("il-chicago", "Chicago Department of Public Health", "Chicago", "api",
            "https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5",
            "full", "some-history", "pack-built", "PASS_FAIL",
            verified="2026-10-25", last_refresh="2026-10-25",
            refresh="Harvest pipeline harvest/socrata_cities (chicago)",
            notes="Socrata (SODA) API; pass / pass-with-conditions / fail; violations "
                  "field with codes and inspector comments. Pack BUILT locally "
                  "2026-10-25 over a 2-year window (14,823 places / 36,070 "
                  "inspections). Attribution: City of Chicago Data Portal.",
            restrictions="Chicago only; the rest of Illinois is fragmented."),
        link_only("il-statewide", "Rest of Illinois (local health departments)",
                  "https://dph.illinois.gov/topics-services/food-safety.html",
                  "No statewide results portal verified."),
    ], pack="built", availability="staged-local", artifact_verified="2026-10-25",
        summary="Chicago pack built + validated locally (pass/fail); statewide coverage "
                "is county-by-county.")

    add("CA", "California", "SCORE_100_HIGH", [
        src("ca-lacounty", "Los Angeles County Department of Public Health",
            "Los Angeles County (excl. Pasadena/Long Beach/Vernon)", "api",
            "https://data.lacounty.gov/Health/LOS-ANGELES-COUNTY-RESTAURANT-AND-MARKET-INSPECTIO/6ni6-h5kp",
            "full", "full-history", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-13",
            notes="Inspections + separate violations dataset (8jyd-4pv9); numeric "
                  "score + letter grade.",
            restrictions="Excludes Pasadena, Long Beach and Vernon (own health departments)."),
        src("ca-sf", "San Francisco Department of Public Health", "San Francisco", "api",
            "https://data.sfgov.org/resource/pyih-qa8i.json",
            "full", "some-history", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-13",
            notes="Numeric 0-100 score plus dedicated violations dataset (f29f-c3np)."),
        link_only("ca-statewide", "California Department of Public Health (Retail Food Program)",
                  "https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/RetailFoodProgram.aspx",
                  "CalCode makes 60+ county EHDs the publishers; no statewide portal, "
                  "bulk download, or API (AFDO index lists counties only; CDPH page "
                  "fetch-blocked on 2026-10-22)."),
    ], summary="County-fragmented by design (CalCode). LA County + SF datasets "
               "cover a big population share.")

    add("MA", "Massachusetts", "PASS_FAIL", [
        src("ma-boston", "City of Boston Inspectional Services", "Boston", "bulk-csv",
            "https://data.boston.gov/dataset/food-establishment-inspections",
            "full", "full-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="Analyze Boston CKAN, daily refresh, per-violation rows with "
                  "inspector comments (fetched 200 with data 2026-10-22)."),
        src("ma-dph", "Massachusetts DPH Food Protection Program", "State-inspected facilities", "html",
            "https://dphanalytics.hhs.mass.gov/ibmcognos/bi/?pathRef=MEPHTN/inspections/food-protection/food-protection-list",
            "unverified", "unverified", "blocked", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            blocker="Cognos JS report serves an empty body to non-browser fetches; "
                    "municipal boards inpublish independently.",
            notes="~350 municipal health boards are the real publishers."),
    ], summary="Boston has a strong open dataset; the rest is municipal.")

    add("WA", "Washington", "PENALTY_LOW", [
        src("wa-kingcounty", "Public Health — Seattle & King County", "King County (incl. Seattle)", "api",
            "https://data.kingcounty.gov/Health-Wellness/Food-Establishment-Inspection-Data/r878-4sxa",
            "full", "some-history", "pack-built", "PENALTY_LOW",
            verified="2026-10-25", last_refresh="2026-10-25",
            refresh="Harvest pipeline harvest/socrata_cities (kingco)",
            notes="Socrata r878-4sxa (old gkhn-e8mn now requires login): one row per "
                  "violation, red (critical)/blue points; score = inspection points "
                  "(LOWER is better); result + Excellent/Good/Okay/Needs to Improve "
                  "rating as result text. No coordinates published. Pack BUILT "
                  "locally 2026-10-25 (12,167 places / 32,971 inspections, 2-year window).",
            restrictions="King County only; other counties publish separately."),
        link_only("wa-statewide", "Washington State DOH + county health departments",
                  "https://doh.wa.gov/you-and-your-family/food-safety",
                  "No statewide results portal verified."),
    ], pack="built", availability="staged-local", artifact_verified="2026-10-25",
        summary="King County pack built + validated locally (penalty points + rating); "
                "statewide is fragmented.")

    # ------------------------------------------------- verified statewide (LF-N research pass)
    add("OR", "Oregon", "SCORE_100_HIGH", [
        src("or-oha", "Oregon Health Authority (statewide, county-run inspections)", "Statewide", "html",
            "https://inspections.myhealthdepartment.com/oregon",
            "full", "full-history", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-22",
            refresh="HealthSpace/MyHealthDepartment statewide search (fetched 200 OK)",
            notes="Restaurant 100-pt scale: priority items deduct 5, priority-foundation 3; "
                  "< 70 fails. One of the cleanest candidate integrations in the country."),
    ], summary="Statewide, scored, full history — top integration candidate.")

    add("WI", "Wisconsin", "PASS_FAIL", [
        src("wi-datcp", "Wisconsin DATCP (state-inspected facilities)", "Statewide (state-inspected)", "html",
            "https://inspections.myhealthdepartment.com/wisconsin-datcp",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="DATCP publishes directly (fetched 200 OK); ~130 agency-managed local "
                  "health departments publish separately in HealthSpace.",
            restrictions="State-inspected jurisdictions only; agency-delegated ones are a "
                  "second source.",
            blocker=""),
    ], summary="Dual-vendor state (DATCP + HealthSpace local agencies).")

    add("OK", "Oklahoma", "VIOLATIONS_ONLY", [
        src("ok-phin", "Oklahoma State Department of Health — Consumer Protection",
            "Statewide (77 counties)", "html", "https://www.phin.state.ok.us/inspections/",
            "unverified", "unverified", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Legacy ASP.NET form (fetched 200 OK), county+name search; report "
                  "records are form-post downloads. Tulsa and OKC-County also publish "
                  "their own."),
    ], summary="Statewide form-based search on a legacy ASP.NET site.")

    add("VT", "Vermont", "SCORE_100_HIGH", [
        src("vt-vdh", "Vermont Department of Health — Food & Lodging Program",
            "Statewide", "html", "https://vtdoh.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx",
            "full", "full-history", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-22",
            notes="'Food Safety 5.5' platform; numeric inspection score (44-item "
                  "checklist) + critical flags since May 2016. ASP.NET POST needed."),
    ], summary="Single-state agency; numeric score + violations; same platform family "
               "as SD/WY/PA.")

    add("SD", "South Dakota", "PASS_FAIL", [
        src("sd-doh", "South Dakota Department of Health", "Statewide (excl. Sioux Falls)", "html",
            "https://sddoh.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="'Food Safety 5.5' platform (fetched 200 OK); each inspection is a "
                  "report/PDF; Sioux Falls inspects separately."),
    ], summary="Statewide report platform; Sioux Falls separate.")

    add("WY", "Wyoming", "PASS_FAIL", [
        src("wy-wda", "Wyoming Department of Agriculture — Consumer Health Services",
            "Statewide (excl. 5 local jurisdictions)", "html",
            "https://wda.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="'Food Safety 5.5' platform (fetched 200 OK); in/out-of-compliance "
                  "with violation explanation; excludes Laramie, Natrona, Sublette, "
                  "Sweetwater, Teton + City of Laramie."),
    ], summary="Statewide compliance platform minus a handful of local jurisdictions.")

    add("RI", "Rhode Island", "VIOLATIONS_ONLY", [
        src("ri-ridoh", "Rhode Island Department of Health — Center for Food Protection",
            "Statewide", "html", "https://ri.healthinspections.us/ri/",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Official portal (linked from health.ri.gov/food-safety, fetched 200); "
                  "Tyler-hosted JS/postback app — parsing needs the postback, not "
                  "plain links."),
    ], summary="Statewide; reachable but JS-postback heavy.")

    add("NJ", "New Jersey", "DISPOSITION", [
        src("nj-burlington", "Burlington County Health Department (HDGov pattern)",
            "Burlington County", "html", "https://bcnj.co.burlington.nj.us/Views/HealthInspections/",
            "partial", "some-history", "source-verified", "DISPOSITION",
            verified="2026-10-22",
            notes="Satisfactory / Conditionally Satisfactory / Unsatisfactory "
                  "dispositions; XLSX export; the HDGov 'Views/HealthInspections' app "
                  "recurs across NJ counties (Camden, Cape May, Gloucester, Ocean)."),
        link_only("nj-statewide", "New Jersey Department of Health (local agencies)",
                  "https://www.nj.gov/health/ceohs/food-safety-defense/",
                  "~110 delegated local agencies publish in their own formats; no "
                  "statewide public database."),
    ], summary="Fragmented into local agencies; dispositions are the common currency.")

    add("NV", "Nevada", "DISPOSITION", [
        src("nv-snhd", "Southern Nevada Health District (Clark County / Las Vegas)",
            "Southern Nevada", "bulk-csv",
            "https://www.southernnevadahealthdistrict.org/permits-and-regulations/restaurant-inspections/restaurant-inspection-search/",
            "full", "full-history", "source-verified", "DISPOSITION",
            verified="2026-10-22",
            notes="Nightly developer CSV download (restaurants.zip + SQL schema; both "
                  "pages fetched 200) — ~5-day posting lag. Also demerit-style detail; "
                  "no portal 0-100 number.",
            restrictions="Southern Nevada only; Washoe County and rural DPBH counties are "
                         "separate."),
    ], summary="SNHD's nightly CSV is best-in-class bulk data.")

    add("TX", "Texas", "SCORE_100_HIGH", [
        src("tx-austin", "Austin Public Health", "Austin", "api",
            "https://data.austintexas.gov/resource/ecmv-9xxi.json",
            "partial", "full-history", "source-verified", "SCORE_100_HIGH",
            verified="2026-10-22",
            notes="Socrata API (fetched 200 JSON): numeric 0-100 with color bands."),
        src("tx-dshs", "Texas DSHS Retail Food Safety Unit", "Where no local program exists", "official-link-only",
            "https://www.dshs.texas.gov/retail-food-establishments",
            "unverified", "unverified", "official-link-only", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="DSHS (fetched 200) publishes no public results search — only an "
                  "ArcGIS jurisdiction map and open-records requests.",
            restrictions="DSHS inspects only where no local program exists; Houston/Dallas/"
                         "San Antonio/El Paso publish their own (Dallas/SOCRATA unverified-cited)."),
    ], summary="Big-city open-data APIs (Austin verified); no statewide results search.")

    add("UT", "Utah", "VIOLATIONS_ONLY", [
        src("ut-slco", "Salt Lake County Health Department", "Salt Lake County", "html",
            "https://public.cdpehs.com/UTEnvPbl/VW_EST_PUBLIC/ShowVW_EST_PUBLICTablePage.aspx",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Live ASP.NET search incl. closures (fetched 200 OK)."),
        link_only("ut-statewide", "Utah's 13 local health districts",
                  "https://coronavirus-response.health.utah.gov/",
                  "No statewide public search; Utah, Davis, Weber, Cache counties are "
                  "separate integrations."),
    ], summary="13 local districts; Salt Lake County portal verified.")

    add("MI", "Michigan", "VIOLATIONS_ONLY", [
        src("mi-mdard", "Michigan Dept. of Agriculture & Rural Development — MiSafe",
            "Grocery/processor facilities ONLY (NOT restaurants)", "html",
            "https://www2.mda.state.mi.us/MiSafe/Default",
            "full", "full-history", "blocked", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            blocker="MiSafe (fetched 200 OK) explicitly EXCLUDES restaurants — those are "
                    "inspected by ~45 local health agencies with their own portals.",
            notes="Do not count MiSafe as restaurant data; Kent County et al. are the real "
                  "restaurant publishers."),
    ], summary="State portal covers groceries only; restaurants are local agencies.")

    add("MD", "Maryland", "VIOLATIONS_ONLY", [
        src("md-montgomery", "Montgomery County", "Montgomery County", "api",
            "https://data.montgomerycountymd.gov/resource/5pue-gfbe.json",
            "partial", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Socrata (fetched 200 with data): per-item In/Out of Compliance rows."),
        link_only("md-statewide", "Maryland DHMH Office of Food Protection (24 LHDs)",
                  "https://health.maryland.gov/phpa/pages/ofp.aspx",
                  "Statewide search vsi.maryland.gov was unreachable on 2026-10-22 "
                  "(3 attempts); many counties publish by records request."),
    ], summary="County APIs verified (Montgomery); statewide portal at present "
               "unreachable.")

    add("MO", "Missouri", "DISPOSITION", [
        src("mo-stl", "City of St. Louis Department of Health", "City of St. Louis", "html",
            "https://www.stlouis-mo.gov/government/departments/health/environmental-health/food-control/restaurant-ratings-search.cfm",
            "partial", "some-history", "source-verified", "DISPOSITION",
            verified="2026-10-22",
            notes="Lookup runs on HealthSpace (fetched 200). Kansas City (Socrata, "
                  "dataset unconfirmed), Springfield-Greene, Joplin also publish."),
        link_only("mo-statewide", "Missouri DHSS", "https://health.mo.gov/",
                  "No statewide public restaurant-inspection portal."),
    ], summary="City-level sources (St. Louis verified); state publishes nothing "
               "centrally.")

    add("MN", "Minnesota", "VIOLATIONS_ONLY", [
        src("mn-mdh", "Minnesota Department of Health (FPLS)", "Statewide-program page only", "official-link-only",
            "https://www.health.state.mn.us/communities/environment/food/index.html",
            "none", "unverified", "official-link-only", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            restrictions="No reproducible automated access verified; official link "
                         "only — NOT integrated restaurant data.",
            notes="Page fetched 200 but confirms: no online inspection portal; reports "
                  "by request. Minneapolis open-data lookup is the big-population "
                  "coverage (dashboard fetch failed 2026-10-22)."),
    ], summary="State page verified absent of portal; Minneapolis open data recommended "
               "next.")

    add("MT", "Montana", "VIOLATIONS_ONLY", [
        src("mt-dphhs", "Montana DPHHS Environmental Health & Food Safety",
            "~30 counties", "html", "https://dphhs.mt.gov/publichealth/ehfs/",
            "partial", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="DPHHS page (fetched 200) links the state-endorsed "
                  "myhealthdepartment.com/montana dashboard; ~26 other counties run "
                  "their own."),
    ], summary="State-endorsed vendor dashboard plus ~26 independent counties.")

    add("NE", "Nebraska", "VIOLATIONS_ONLY", [
        src("ne-nda", "Nebraska Department of Agriculture", "Statewide", "html",
            "https://ecmp.nebraska.gov/agr-fspav/index.html",
            "unverified", "unverified", "blocked", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            blocker="Portal fetched 200 but renders a JS-only search app; result "
                    "model and history could not be confirmed by plain HTTP GET.",
            notes="Lincoln-Lancaster and Douglas/Omaha (biggest populations) publish "
                  "separately."),
    ], summary="JS-only state app; can't be confirmed without a browser session.")

    add("NH", "New Hampshire", "VIOLATIONS_ONLY", [
        src("nh-dhhs", "NH DHHS Food Protection Section", "Statewide", "official-link-only",
            "https://www.dhhs.nh.gov/programs-services/environmental-health-and-you/food-protection/learn-about-food-inspections-view",
            "none", "latest-only", "blocked", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            blocker="DHHS page 403s automated fetches and confirms there is NO online "
                    "inspection database — records by email request; a few cities "
                    "(Keene) publish their own lookups.",
            notes="Do not present NH as covered; official email-request path only."),
    ], summary="No public online database; records by email request.")

    add("NM", "New Mexico", "VIOLATIONS_ONLY", [
        link_only("nm-nmed", "New Mexico Environment Department — Food Program",
                  "https://env.nm.gov/food-program/",
                  "NMED states inspection records are public but publishes no "
                  "searchable portal (AFDO-cited; not fetched this session) — "
                  "records custodian path; Albuquerque has its own lookup."),
    ], summary="Records-on-request at state level; city of Albuquerque has a lookup.")

    add("ND", "North Dakota", "VIOLATIONS_ONLY", [
        src("nd-doh", "North Dakota Department of Health & Human Services (local food programs)", "Statewide", "official-link-only",
            "https://www.hhs.nd.gov/food-beverage/",
            "unverified", "unverified", "official-link-only", "VIOLATIONS_ONLY",
            verified="",
            restrictions="No reproducible automated access verified; official link "
                         "only — NOT integrated restaurant data.",
            notes="Not fetch-verified in the LF-N research pass; ND is expected to ride "
                  "the 'Food Safety 5.5' platform family alongside SD/VT/WY/IL/IA but "
                  "that is UNCONFIRMED — verify before integration work."),
    ], summary="Unverified in this pass; platform-family membership suspected only.")

    add("WV", "West Virginia", "VIOLATIONS_ONLY", [
        link_only("wv-oehs", "WV Bureau for Public Health — Office of Environmental Health Services",
                  "https://oehs.wvdhhr.org/phs/food-safety/",
                  "No consolidated portal; ~50 county/subcounty departments publish in "
                  "their own formats (AFDO lists no state entry) — highest integration "
                  "burden in the batch."),
    ], summary="~50 separate county publishers; no statewide portal.")

    # ------------------------------------------------- official-link-only batch
    add("AZ", "Arizona", "LETTER_GRADE", [
        src("az-maricopa", "Maricopa County Environmental Health", "Maricopa County (~4.6M, incl. Phoenix)", "html",
            "https://envapp.maricopa.gov/EnvironmentalHealth/FoodInspections",
            "full", "some-history", "source-verified", "LETTER_GRADE",
            verified="2026-10-22",
            notes="Fetched 200 OK; letter grade cards ('A' for Food Safety) + full "
                  "reports — NOT a numeric-score jurisdiction."),
        src("az-pima", "Pima County Health", "Pima County (Tucson)", "html",
            "https://healthinspect.pima.gov/portal/",
            "unverified", "unverified", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="Fetched 200 OK; JS portal app."),
        link_only("az-rest", "Arizona ADHS + smaller counties",
                  "https://www.azdhs.gov/preparedness/epidemiology-disease-control/food-safety-environmental-services/index.php",
                  "ADHS (fetched 200) has NO statewide results search — records "
                  "requests only; ~15 county/city departments publish separately "
                  "(Coconino, Yavapai, …)."),
    ], summary="County-run; Maricopa letter grades verified; no statewide search.")

    add("CO", "Colorado", "PASS_FAIL", [
        src("co-cdphe", "Colorado CDPHE + delegated counties (shared platform)", "Statewide (some counties opt out)", "html",
            "https://inspections.myhealthdepartment.com/colorado/",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="Fetched 200 OK (linked from CDPHE page; CDPHE plain fetch is 403). "
                  "Results are Pass / Re-Inspection Required / Closed with risk-index "
                  "points (Pass 0–49; Re-inspect 50–109; Closed 110+) — NOT a 0–100 "
                  "score or letter grade."),
        src("co-denver", "Denver Department of Public Health & Environment", "City & County of Denver", "html",
            "https://www.denvergov.org/restaurantinspections",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="Fetched 200 OK. Inspections after 9/6/24 moved to Accela "
                  "(aca-prod.accela.com/DENVER); Denver self-inspects."),
    ], summary="Shared state platform + Denver's own program; risk-index points, "
               "no 0–100 score.")

    add("AK", "Alaska", "VIOLATIONS_ONLY", [
        src("ak-dec", "Alaska DEC — Food Safety & Sanitation", "Statewide (excl. Anchorage)", "html",
            "https://adec.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="DEC-run ASP.NET portal fetched 200 OK; FDA Food Code citations, no "
                  "score/grade. dec.alaska.gov program page 403s automated fetches.",
            restrictions="Municipality of Anchorage runs its own program and is NOT in "
                         "the state portal."),
    ], summary="State portal verified (safefood platform); Anchorage excluded.")

    add("HI", "Hawaii", "PASS_FAIL", [
        src("hi-doh", "Hawaii DOH — Food Safety Branch (Sanitation)", "Statewide (all islands)", "html",
            "https://inspections.myhealthdepartment.com/soh",
            "full", "some-history", "source-verified", "PASS_FAIL",
            verified="2026-10-22",
            notes="DOH-branded portal fetched 200 (linked from health.hawaii.gov/san, "
                  "200). Results are condition placards: green pass / yellow "
                  "conditional / red closure, with cited violations in reports — there "
                  "is NO numeric score; Alabama bands do NOT apply."),
    ], summary="Statewide placard system; no numeric score.")

    add("CT", "Connecticut", "VIOLATIONS_ONLY", [
        src("ct-dph", "Connecticut DPH Food Protection Program", "Statewide program page", "official-link-only",
            "https://portal.ct.gov/dph/food-protection-program/food-service-inspections",
            "none", "unverified", "official-link-only", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Page fetched 200 contains only the blank inspection form — NO "
                  "statewide results portal; consumers go town-by-town. ~60 local "
                  "departments; some towns (e.g. Farmington Valley HD) publish 0–100 "
                  "scores higher-is-better.",
            restrictions="Publication left to ~60 local health departments."),
    ], summary="No statewide portal (verified negative finding); town-by-town.")

    add("DE", "Delaware", "VIOLATIONS_ONLY", [
        src("de-dph", "Delaware Division of Public Health — Office of Food Protection",
            "Statewide", "api", "https://data.delaware.gov/Health/Food-Establishment-Inspection-Violations/384s-wygj",
            "full", "some-history", "pack-built", "VIOLATIONS_ONLY",
            verified="2026-10-22", last_refresh="2026-10-22",
            refresh="Harvest pipeline harvest/de_socrata",
            notes="Socrata open-data API (resource 384s-wygj): one row per violation, "
                  "geocoded, ~2-year rolling window. Pack BUILT and validated locally "
                  "(3,731 places / 9,202 inspections / 32,570 violations; sha256 "
                  "536e54a6…92835); staged, NOT published. Violations-ONLY extract: "
                  "zero-violation establishments are absent from the source dataset."),
    ], pack="built",
        availability="staged-local",
        artifact_verified="2026-10-22",
        summary="Pack built + validated locally (datasetVersion 2026-10-23.1; window "
                "2024-10-14..2026-12-03); staged — blocked on publishing infrastructure. "
                "No scores exist in this data (violations-only model).")

    add("ID", "Idaho", "VIOLATIONS_ONLY", [
        src("id-dhw", "Idaho DHW + 7 Public Health Districts", "Statewide via 7 districts", "official-link-only",
            "https://healthandwelfare.idaho.gov/health-wellness/community-health/food-safety",
            "none", "unverified", "official-link-only", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="State page (fetched 200) has no results tool; the 7 independent "
                  "district portals are the publishers — pages verified: "
                  "phd5.idaho.gov/inspections (200), eiph.id.gov program page (200), "
                  "cdh.idaho.gov program page (fetch 200, portal 403 Cloudflare); the "
                  "underlying search apps are cited, not fetch-verified. ~7 integrations.",
            restrictions="Seven independent districts; Central District Health (Boise "
                         "~700k) is the biggest."),
    ], summary="7 independent district portals; state page verified without results.")

    add("IA", "Iowa", "VIOLATIONS_ONLY", [
        src("ia-dial", "Iowa Department of Inspections, Appeals & Licensing (DIAL)",
            "Statewide", "html", "https://iowa.safefoodinspection.com/Inspection/PublicInspectionSearch.aspx",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="BOTH portals fetched 200: legacy USFS search (reports through Oct 14, "
                  "2026) and the going-forward SAFHER SPA "
                  "(safher-portal.dial.iowa.gov/safher-portal). MID-TRANSITION Oct 2026 — "
                  "archive coverage must be confirmed before relying on history."),
    ], summary="Statewide agency; two live portals in an Oct 2026 transition.")

    add("KS", "Kansas", "VIOLATIONS_ONLY", [
        src("ks-kda", "Kansas Department of Agriculture — Food Safety & Lodging", "Statewide", "html",
            "https://portal.kda.ks.gov/Food/FoodInspectionSearch",
            "full", "full-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="New portal fetched 200 (launched ~Jul 2026): 'updated nightly, free & "
                  "no sign-in'; In/Out-of-compliance + cited violations, date-range "
                  "filters. Old foodsafety.kda.ks.gov retired July 2026 (fetched 500)."),
    ], summary="Statewide nightly-updated public record search (new portal).")

    add("ME", "Maine", "VIOLATIONS_ONLY", [
        src("me-hip", "Maine DHHS / Maine CDC — Health Inspection Program", "Statewide (incl. MUN municipal licenses)", "html",
            "https://apps.web.maine.gov/online/hip_search/health-inspection-search.html",
            "full", "some-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="Search app fetched 200 (linked from maine.gov HIP page, 200): name/"
                  "city/county/ZIP/type/date-range. Pass/fail via critical (C) and "
                  "non-critical (NC) counts (failed >3 C or >10 NC); ~3-year history."),
    ], summary="Statewide search app; pass/fail via C/NC counts.")

    add("KY", "Kentucky", "SCORE_100_HIGH", [
        link_only("ky-fragmented", "Kentucky local health departments",
                  "https://www.fdacs.gov/",
                  "Fragmented (verified in US registry doc 2026-10-13): Louisville, "
                  "Lexington, Northern Kentucky, Jessamine and others publish their own "
                  "scores/violations on different sites."),
    ], summary="County-fragmented (registry doc research).")

    add("IN", "Indiana", "VIOLATIONS_ONLY", [
        link_only("in-fragmented", "Indiana local health departments",
                  "https://www.in.gov/health/food-protection/",
                  "Fragmented (registry doc 2026-10-13): counties use varied platforms; "
                  "Marion County/Indianapolis publishes via hhcwebfood.hhcorp.org."),
    ], summary="County-fragmented (registry doc research).")

    add("OH", "Ohio", "VIOLATIONS_ONLY", [
        link_only("oh-odh", "Ohio Department of Health + local health districts",
                  "https://odh.ohio.gov/know-our-programs/food-safety/",
                  "Fragmented (registry doc 2026-10-13): a state database exists but "
                  "public access is via ~local health districts, many on HealthSpace; "
                  "many jurisdictions publish violations without an overall score."),
    ], summary="Local-district publication (registry doc research).")

    # D.C. — a federal district, NOT a state. Registered as its own type.
    add("DC", "District of Columbia", "VIOLATIONS_ONLY", [
        src("dc-dchealth", "DC Health — Food Safety & Hygiene Inspection Services Division",
            "District of Columbia (all inspections state-run)", "html",
            "https://dc.healthinspections.us/?a=Inspections",
            "full", "full-history", "source-verified", "VIOLATIONS_ONLY",
            verified="2026-10-22",
            notes="DC-run healthinspections.us instance fetched 200 OK: name/inspection-"
                  "type search, FDA Food Code citation-level detail, history stated to "
                  "cover 2007→current. Help page "
                  "dchealth.dc.gov/service/understanding-food-establishment-inspections "
                  "confirmed 200."),
    ], jtype="federal-district",
        summary="Registered as a jurisdiction, explicitly NOT one of the 50 states.")
# addTo=
    return r


def write_json() -> dict:
    payload = {
        "schema": 2,
        "generated": date.today().isoformat(),
        "license_note": "Registry data describes OFFICIAL public sources; it carries "
                        "no restaurant records, scores, or violations.",
        "jurisdiction_types": {"state": "one of the 50 states",
                               "federal-district": "Washington, D.C. (NOT a state)"},
        "pack_availability_vocabulary": {
            "bundled": "data ships inside the APK (no download exists)",
            "downloadable-verified": "manifest + artifact fetched and hash-verified — "
                                     "the ONLY state in which a download may be offered",
            "declared-only": "a publication is declared but the artifact could not be "
                             "verified downloadable — NO download may be offered",
            "staged-local": "pack built and validated locally; not published",
            "none": "no pack exists",
        },
        "jurisdictions": registry(),
    }
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    ASSET.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# Primary-tier assignment (machine-derived, one tier per jurisdiction —
# ordered, first match wins; D.C. is always the separate federal-district row
# and never folded into 50-state tallies).
def primary_tier(j: dict) -> str:
    statuses = [s.get("status") for s in j.get("sources", [])]
    if j.get("pack_status") == "bundled" or "integrated" in statuses:
        return "Integrated (live in app)"
    if j.get("pack_availability") == "downloadable-verified":
        return "Pack downloadable (artifact verified)"
    if j.get("pack_status") in ("published", "built"):
        return "Pack built/declared — NOT verified downloadable"
    if "source-verified" in statuses:
        return "Source verified (no ingestion yet)"
    return "Official-link-only / blocked"


def gate(payload: dict) -> int:
    errors = []
    js = payload.get("jurisdictions", [])
    states = [j for j in js if j.get("type") == "state"]
    dcs = [j for j in js if j.get("type") == "federal-district"]

    if len(js) != 51:
        errors.append(f"expected 51 jurisdictions (50 states + D.C.), got {len(js)}")
    if len(states) != 50:
        errors.append(f"expected exactly 50 states, got {len(states)}")
    if len(dcs) != 1 or dcs[0].get("state") != "DC":
        errors.append("Washington D.C. must be present as a separate federal-district jurisdiction")

    state_codes = [j.get("state") for j in states]
    for code, name in STATES:
        if code == "DC":
            continue
        n = state_codes.count(code)
        if n != 1:
            errors.append(f"state {code} appears {n} times, expected exactly 1")

    seen_regions, seen_sources = set(), set()
    for j in js:
        rid = j.get("regionId", "")
        if rid in seen_regions:
            errors.append(f"duplicate regionId {rid}")
        seen_regions.add(rid)
        if rid != region_id(j.get("state", "")):
            errors.append(f"{j.get('state')}: regionId {rid} != expected {region_id(j.get('state'))}")
        if j.get("result_model") not in VALID_MODELS:
            errors.append(f"{rid}: invalid result_model {j.get('result_model')}")
        if j.get("pack_status") not in VALID_PACK_STATUS:
            errors.append(f"{rid}: invalid pack_status {j.get('pack_status')}")
        if j.get("pack_availability") not in VALID_PACK_AVAILABILITY:
            errors.append(f"{rid}: invalid pack_availability {j.get('pack_availability')}")
        if j.get("pack_host_status") not in VALID_HOST_STATUS:
            errors.append(f"{rid}: invalid pack_host_status {j.get('pack_host_status')}")
        # Consistency laws between publication, availability, and host:
        if j.get("pack_manifest_url") and not j["pack_manifest_url"].startswith("https://"):
            errors.append(f"{rid}: manifest URL must be https")
        if j.get("pack_availability") == "downloadable-verified":
            if j.get("pack_status") != "published" or not j.get("pack_manifest_url"):
                errors.append(f"{rid}: downloadable-verified requires pack_status=published + manifest")
            if not j.get("artifact_verified"):
                errors.append(f"{rid}: downloadable-verified requires artifact_verified date")
        if j.get("pack_availability") == "declared-only":
            if j.get("pack_status") != "published" or not j.get("pack_manifest_url"):
                errors.append(f"{rid}: declared-only requires pack_status=published + manifest")
            if j.get("pack_host_status") in ("reachable", ""):
                errors.append(f"{rid}: declared-only with no verified artifact requires "
                              f"a failing host state, got '{j.get('pack_host_status')}'")
        if j.get("pack_availability") == "staged-local" and j.get("pack_status") != "built":
            errors.append(f"{rid}: staged-local requires pack_status=built")
        if j.get("pack_status") == "published" and not j.get("pack_manifest_url"):
            errors.append(f"{rid}: published pack requires a manifest URL")
        if not j.get("sources"):
            errors.append(f"{rid}: no sources registered")
        for s in j.get("sources", []):
            if s["id"] in seen_sources:
                errors.append(f"duplicate source id {s['id']} (state {rid})")
            seen_sources.add(s["id"])
            if not s["id"].startswith(j["state"].lower() + "-"):
                errors.append(f"{rid}: source id {s['id']} is not parent-state namespaced")
            if s.get("status") not in VALID_STATUS:
                errors.append(f"{rid}/{s['id']}: invalid status {s.get('status')}")
            if s.get("access") not in VALID_ACCESS:
                errors.append(f"{rid}/{s['id']}: invalid access {s.get('access')}")
            if s.get("result_model") not in VALID_MODELS:
                errors.append(f"{rid}/{s['id']}: invalid source result_model "
                              f"{s.get('result_model')} (a source publishes under ONE "
                              f"real result scale; missing language is not a scale)")
            if s.get("violations") not in VALID_VIOLATIONS:
                errors.append(f"{rid}/{s['id']}: invalid violations {s.get('violations')}")
            if s.get("history") not in VALID_HISTORY:
                errors.append(f"{rid}/{s['id']}: invalid history {s.get('history')}")
            if not s.get("id") or not s.get("agency") or not s.get("coverage") or not s.get("website"):
                errors.append(f"{rid}/{s['id']}: agency/coverage/website required")
            if s.get("status") in {"integrated", "pack-built", "source-verified"} and not s.get("verified"):
                errors.append(f"{rid}/{s['id']}: {s['status']} requires a verified date")
            if s.get("status") == "official-link-only" and s.get("restrictions") in (None, ""):
                errors.append(f"{rid}/{s['id']}: official-link-only must state its limitation")
            if s.get("status") == "blocked" and s.get("blocker") in (None, ""):
                errors.append(f"{rid}/{s['id']}: blocked requires a named blocker")

    for e in errors:
        print("FAIL:", e)
    if not errors:
        print(f"GATE PASS: {len(states)} unique states + 1 D.C.; "
              f"{len(seen_sources)} unique sources; all vocabularies valid.")
        return 0
    return 1


def render_matrix(payload: dict) -> None:
    lines = [
        "# Kyron National Coverage Matrix",
        "",
        f"Generated from `tools/coverage/coverage_pipeline.py` on {date.today().isoformat()}.",
        "",
        "**Status vocabulary (distinct, do not conflate):**",
        "- **integrated** — data ships in the app (bundled seed and/or live sync).",
        "- **pack-built** — verified ingestion + validated pack built; publication",
        "  state tracked separately.",
        "- **source-verified** — official endpoint DIRECTLY verified reachable with",
        "  real content; no ingestion yet. Still not user-facing data.",
        "- **official-link-only** — official portal known; NOT integrated and never",
        "  counted as restaurant data.",
        "- **blocked** — a named blocker prevents integration.",
        "",
        "**Pack download vocabulary:** `downloadable-verified` (manifest + artifact",
        "fetched and hash-checked) is the ONLY state in which the app may offer a",
        "download. `declared-only` = publication claimed but the artifact could not",
        "be verified (e.g. host 404). `staged-local` = built locally, not published.",
        "",
        "Each of the 50 states is assigned to EXACTLY ONE primary tier below",
        "(first matching rule: integrated → pack downloadable → pack built/declared",
        "→ source verified → link-only/blocked); D.C. is reported as its own",
        "federal-district row and is not folded into the 50-state tallies.",
        "",
    ]
    for j in payload["jurisdictions"]:
        flag = "" if j["type"] == "state" else "  (*federal district, not a state*)"
        lines.append(f"## {j['name']} ({j['state']}) — `{j['regionId']}`{flag}")
        lines.append("")
        lines.append(f"**Primary tier:** {primary_tier(j)} · **Result model:** {j['result_model']}"
                     f" · **Pack:** {j['pack_status']} ({j.get('pack_availability', 'none')})"
                     + (f" · **Pack host:** {j['pack_host_status']} (checked {j['pack_host_checked']})"
                        if j.get("pack_host_status") else "")
                     + (f" · **Artifact verified:** {j['artifact_verified']}"
                        if j.get("artifact_verified") else ""))
        if j.get("summary"):
            lines.append("")
            lines.append(j["summary"])
        if j.get("sources"):
            lines.append("")
            lines.append("| Source | Agency | Coverage | Access | Violations | History | Status | Verified | Notes |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for s in j["sources"]:
                notes = s.get("notes", "")
                if s.get("blocker"):
                    notes = (notes + " — BLOCKER: " + s["blocker"]).strip(" —")
                lines.append(
                    "| {id} | {agency} | {cov} | {acc} | {vio} | {hist} | {st} | {ver} | {notes} |".format(
                        id=s["id"], agency=s["agency"], cov=s["coverage"], acc=s["access"],
                        vio=s["violations"], hist=s["history"], st=s["status"],
                        ver=s.get("verified") or "—", notes=notes.replace("|", "\\|")))
        lines.append("")
    # Tier tally: states only, each exactly once.
    tally = {}
    for j in payload["jurisdictions"]:
        if j["type"] == "state":
            tally[primary_tier(j)] = tally.get(primary_tier(j), 0) + 1
    dc = [j for j in payload["jurisdictions"] if j["type"] == "federal-district"]
    lines.append("## Tier tally (50 states, each assigned once)")
    lines.append("")
    total = 0
    for tier, n in tally.items():
        lines.append(f"- {tier}: **{n}**")
        total += n
    lines.append(f"- **States total: {total}** (must equal 50)")
    lines.append("")
    if total != 50:
        raise SystemExit(f"MATRIX ERROR: tier tally {total} != 50 states")
    if dc:
        d = dc[0]
        lines.append(f"**Separate federal-district row:** {d['name']} "
                     f"(primary tier: {primary_tier(d)}) — not counted above.")
    lines.append("")
    MATRIX.write_text("\n".join(lines), encoding="utf-8")
    print(f"matrix written -> {MATRIX}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        payload = write_json()
        sys.exit(gate(payload))
    elif cmd == "gate":
        payload = json.loads(ASSET.read_text(encoding="utf-8"))
        sys.exit(gate(payload))
    elif cmd == "matrix":
        payload = json.loads(ASSET.read_text(encoding="utf-8"))
        render_matrix(payload)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
