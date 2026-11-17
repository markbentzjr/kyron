"""Per-state configuration for the generic healthinspections.us
("DHD", Tyler Digital Health Department) adapter — harvest/dhd.

Same API family as the GA adapter:
  <host>/<path>/API/index.cfm
    /filters           -> partition + program filter metadata
    /clientData        -> portal description
    /search/<urljson>/<page>          -> 5 records/page
    /inspectionsData/<b64-facilityID> -> recent inspections + violation
                                       narratives

  host/path   deployment origin + path token ("stateofgeorgia", "ri")
  state/name  USPS code + display name
  region/jur  Kyron region id + jurisdiction code
  source_id   registry source id
  agency      agency name in its own words
  model       registry result model
  cities      municipality names used to split the flat mapAddress
              "STREET CITY ST ZIP" — RI publishes 39 municipalities;
              longest-suffix match before "<ST> <zip>" decides
  partitions  "filters" = discover County-style values from /filters;
              "statewide" = single empty-county partition

verified notes (2026-11-16 probes):
  * ri.healthinspections.us: /filters returns only the date filter;
    search pages stream ~10k facilities; inspectionsData returns
    inspection date/purpose/license type + item-numbered violation
    narratives ("10 - adequate handwashing sinks...") — newest-first.
  * dc: no deployment found at /dc, /stateofdc or /districtofcolumbia
    (404) — the DC portal may sit on a different path or platform;
    disabled until a live path is verified.
"""

STATES = {
    "ri": {
        "host": "https://ri.healthinspections.us",
        "path": "ri",
        "state": "RI", "name": "Rhode Island",
        "region": "us-ri", "jur": "RI-DOH", "source_id": "ri-doh",
        "agency": "Rhode Island Department of Health — Center for "
                  "Food Protection",
        "model": "VIOLATIONS_ONLY",
        "partitions": "statewide",
        "permit_type": "",
        "cities": [
            "Barrington", "Bristol", "Burrillville", "Central Falls",
            "Charlestown", "Coventry", "Cranston", "Cumberland",
            "East Greenwich", "East Providence", "Exeter", "Foster",
            "Glocester", "Hopkinton", "Jamestown", "Johnston",
            "Lincoln", "Little Compton", "Middletown", "Narragansett",
            "New Shoreham", "Newport", "North Kingstown",
            "North Providence", "North Smithfield", "Pawtucket",
            "Portsmouth", "Providence", "Richmond", "Scituate",
            "Smithfield", "South Kingstown", "Tiverton", "Warren",
            "Warwick", "West Greenwich", "West Warwick", "Westerly",
            "Woonsocket",
        ],
        "enabled": True,
    },
    "la": {
        "host": "https://la.healthinspections.us",
        "path": "",  # root deployment — API at /API/index.cfm
        "state": "LA", "name": "Louisiana",
        "region": "us-la", "jur": "LA-LDH", "source_id": "la-ldh",
        "agency": "Louisiana Department of Health — Retail Food "
                  "Inspections (la.healthinspections.us)",
        "model": "VIOLATIONS_ONLY",
        "partitions": "statewide",  # 'county' (parish) filter ignored
                                    # server-side — verified 2026-11-17
        "permit_type": "",
        "cities": [],  # stubs carry structured "City:"/"Parish:" columns
        "enabled": True,
    },
    "dc": {
        "host": "https://dc.healthinspections.us",
        "path": "dc",
        "state": "DC", "name": "District of Columbia",
        "region": "us-dc", "jur": "DC-DOH", "source_id": "dc-doh",
        "agency": "DC Health — Food Safety & Hygiene Inspection "
                  "Services",
        "model": "VIOLATIONS_ONLY",
        "partitions": "statewide",
        "permit_type": "",
        "cities": ["Washington"],
        "enabled": False,  # no live API path verified
    },
}
