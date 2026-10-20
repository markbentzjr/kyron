"""Shared address normalization for the Kyron offline geocoding pipeline.

Rules follow Kyron-Gameplan-Draft.md section 3.3: preserve the raw source
address, normalize conservatively for the geocode key, dedupe by normalized
address (never by place name), route PO Boxes / intersections / blanks to
explicit exception flags instead of submitting them.
"""
import hashlib
import re

SUFFIX_CANON = {
    "STREET": "ST", "ST": "ST", "STR": "ST",
    "AVENUE": "AVE", "AVE": "AVE", "AV": "AVE",
    "BOULEVARD": "BLVD", "BLVD": "BLVD",
    "ROAD": "RD", "RD": "RD",
    "DRIVE": "DR", "DR": "DR",
    "LANE": "LN", "LN": "LN",
    "COURT": "CT", "CT": "CT",
    "PLACE": "PL", "PL": "PL",
    "CIRCLE": "CIR", "CIR": "CIR",
    "PARKWAY": "PKWY", "PKWY": "PKWY",
    "HIGHWAY": "HWY", "HWY": "HWY",
    "TRAIL": "TRL", "TRL": "TRL",
    "WAY": "WAY",
    "ALLEY": "ALY", "ALY": "ALY",
    "TERRACE": "TER", "TER": "TER",
    "PLAZA": "PLZ", "PLZ": "PLZ",
    "SQUARE": "SQ", "SQ": "SQ",
    "EXTENSION": "EXT", "EXT": "EXT",
    "LOOP": "LOOP",
}
SUFFIX_EXPAND = {v: k for k, v in SUFFIX_CANON.items() if k == v or len(k) > len(v)}
# full-word forms for the repair-round variant
SUFFIX_FULL = {
    "ST": "STREET", "AVE": "AVENUE", "BLVD": "BOULEVARD", "RD": "ROAD",
    "DR": "DRIVE", "LN": "LANE", "CT": "COURT", "PL": "PLACE",
    "CIR": "CIRCLE", "PKWY": "PARKWAY", "HWY": "HIGHWAY", "TRL": "TRAIL",
    "ALY": "ALLEY", "TER": "TERRACE", "PLZ": "PLAZA", "SQ": "SQUARE",
    "EXT": "EXTENSION",
}
DIRECTIONALS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
                "NORTH", "SOUTH", "EAST", "WEST",
                "NORTHEAST", "NORTHWEST", "SOUTHEAST", "SOUTHWEST"}
DIR_CANON = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
             "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE",
             "SOUTHWEST": "SW"}

UNIT_RE = re.compile(
    r"\b(STE|SUITE|UNIT|APT|BLDG|BUILDING|DEPT|RM|ROOM|SPACE|SPC|LOT)\s*\.?\s*[A-Z0-9-]+\b")
HASH_UNIT_RE = re.compile(r"#\s*[A-Z0-9-]+\b")
POBOX_RE = re.compile(r"\bP\.?\s*O\.?\s*BOX\b|\bPOST\s+OFFICE\s+BOX\b")
INTERSECTION_RE = re.compile(r"\s&\s|\sAT\s|\s/\s")


def clean(s: str) -> str:
    s = (s or "").upper()
    s = s.replace(".", " ").replace(",", " ")
    s = re.sub(r"[^A-Z0-9#&/\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_unit(street_clean: str):
    """Remove unit designators from the geocode key; return (street, unit)."""
    unit = ""
    m = UNIT_RE.search(street_clean) or HASH_UNIT_RE.search(street_clean)
    if m:
        unit = m.group(0)
        street_clean = (street_clean[:m.start()] + " " + street_clean[m.end():])
        street_clean = re.sub(r"\s+", " ", street_clean).strip(" -")
    return street_clean, unit


def canon_street(street_clean: str, expand: bool = False) -> str:
    """Canonicalize the trailing street suffix + directionals.

    expand=True produces the repair-round variant with full-word suffixes.
    """
    toks = street_clean.split(" ")
    if not toks:
        return street_clean
    # trailing directional after suffix, e.g. "MAIN ST N"
    postdir = ""
    if len(toks) >= 3 and toks[-1] in DIRECTIONALS and toks[-2] in SUFFIX_CANON:
        postdir = DIR_CANON.get(toks.pop(), toks[-1])
    if toks and toks[-1] in SUFFIX_CANON:
        canon = SUFFIX_CANON[toks[-1]]
        toks[-1] = SUFFIX_FULL.get(canon, canon) if expand else canon
    # pre-directional, e.g. "N MAIN ST" / "NORTH MAIN ST"
    if len(toks) >= 3 and toks[0] in DIRECTIONALS:
        toks[0] = DIR_CANON.get(toks[0], toks[0])
    out = " ".join(toks)
    if postdir:
        out = out + " " + postdir
    return out


def zip5(z: str) -> str:
    m = re.search(r"\d{5}", z or "")
    return m.group(0) if m else ""


def normalize_address(raw_street: str, raw_city: str, raw_zip: str):
    """Return dict with normalized key fields + flags, or raise on empty."""
    street_clean = clean(raw_street)
    city = clean(raw_city)
    z5 = zip5(raw_zip)
    flags = []

    if not street_clean:
        flags.append("NO_STREET")
    if not z5:
        flags.append("NO_ZIP")
    if POBOX_RE.search(street_clean):
        flags.append("PO_BOX")
    if INTERSECTION_RE.search(street_clean) and not street_clean[0].isdigit():
        flags.append("INTERSECTION")

    no_unit, unit = split_unit(street_clean)
    street = canon_street(no_unit)
    street_expanded = canon_street(no_unit, expand=True)

    return {
        "street": street,
        "street_expanded": street_expanded,
        "unit_removed": unit,
        "city": city,
        "state": "AL",
        "zip": z5,
        "flags": flags,
        "submittable": not any(f in flags for f in ("NO_STREET", "PO_BOX", "INTERSECTION")),
    }


def address_id(norm: dict) -> str:
    key = "|".join([norm["street"], norm["city"], norm["state"], norm["zip"]])
    return "addr_" + hashlib.sha256(key.encode()).hexdigest()[:20]
