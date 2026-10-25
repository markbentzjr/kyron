"""Per-source configuration + row normalizers for the Socrata city/county
harvest (NYC DOHMH, Chicago CDPH, Public Health — Seattle & King County).

Each normalizer turns the source's raw Socrata rows (one row per violation,
or per inspection for Chicago) into Kyron's compact place records — the
same shape harvest/de_socrata/normalize_de.py emits:

  {id, n, a, c, z, ct, st, jur, src, du, lat, lng, gs, ga, gp, gm,
   s, d, disp, origin, insp: [{d, t, s, disp, v: [{p, c, r}]}]}

Nothing is invented: a score is only set when the source publishes one,
`disp` only carries the source's own grade/result text, and coordinates
are only shipped when the source itself publishes non-zero lat/lng.
"""

import hashlib
import re

NO_SCORE = -1


def _iso(d):
    return (d or "")[:10]


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _coord(lat, lng):
    a, b = None, None
    try:
        a, b = float(lat), float(lng)
    except (TypeError, ValueError):
        return None, None
    if a == 0 or b == 0:
        return None, None  # NYC publishes 0/0 for un-geocoded rows
    return round(a, 6), round(b, 6)


def _pid(src, key):
    return f"{src}_{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def _place(cfg, key, name, addr, city, zip_, county, lat, lng, du):
    has = lat is not None and lng is not None
    return {
        "id": _pid(cfg["source_id"], key), "n": name.strip(),
        "a": addr.strip(), "c": city.strip(), "z": (zip_ or "")[:5],
        "ct": county, "st": cfg["state"], "jur": cfg["jurisdiction"],
        "src": cfg["source_id"], "du": du,
        "lat": lat if has else None, "lng": lng if has else None,
        "gs": "ACCEPTED" if has else "UNRESOLVED",
        "ga": "ADDRESS_RANGE" if has else "NONE",
        "gp": f"{cfg['source_id']}-socrata-latlng" if has else "",
        "gm": "", "s": NO_SCORE, "d": "", "disp": "",
        "origin": f"socrata-{cfg['dataset']}", "_insp": {},
    }


def _finish(places):
    out = []
    for p in places.values():
        insp = sorted(p.pop("_insp").values(), key=lambda i: i["d"],
                      reverse=True)
        for i in insp:
            i.pop("_seen", None)
        p["insp"] = insp
        if insp:
            p["d"], p["s"], p["disp"] = insp[0]["d"], insp[0]["s"], insp[0]["disp"]
        out.append(p)
    out.sort(key=lambda p: p["id"])
    return out


# ------------------------------------------------------------------ NYC
NYC_BORO_COUNTY = {"Manhattan": "New York", "Brooklyn": "Kings",
                   "Queens": "Queens", "Bronx": "Bronx",
                   "Staten Island": "Richmond"}


def normalize_nyc(rows, cfg):
    """PENALTY_LOW: NYC inspection `score` is violation points (lower is
    better). The letter grade (A/B/C, or Z/P/N pending) rides in `disp`
    as 'Grade A' when the source assigned one to that inspection."""
    places = {}
    for r in rows:
        camis = r.get("camis")
        d = _iso(r.get("inspection_date"))
        if not camis or not r.get("dba"):
            continue
        p = places.get(camis)
        if p is None:
            lat, lng = _coord(r.get("latitude"), r.get("longitude"))
            boro = r.get("boro") or ""
            p = places[camis] = _place(
                cfg, camis, r["dba"],
                f"{r.get('building', '')} {r.get('street', '')}".strip(),
                "New York" if boro == "Manhattan" else boro,
                r.get("zipcode"), NYC_BORO_COUNTY.get(boro, ""), lat, lng,
                "https://a816-health.nyc.gov/ABCEatsRestaurants/#!/Search/"
                + camis)
        if d.startswith("1900"):
            continue  # NYC sentinel: permitted, not yet inspected
        key = (d, r.get("inspection_type") or "")
        insp = p["_insp"].get(key)
        if insp is None:
            s = _int(r.get("score"))
            insp = p["_insp"][key] = {"d": d, "t": key[1],
                                      "s": s if s is not None and s >= 0 else NO_SCORE,
                                      "disp": "", "v": [], "_seen": set()}
        g = (r.get("grade") or "").strip()
        if g and not insp["disp"]:
            insp["disp"] = f"Grade {g}"
        code = r.get("violation_code")
        if code and code not in insp["_seen"]:
            insp["_seen"].add(code)
            insp["v"].append({"p": 0,
                              "c": (r.get("critical_flag") or "") == "Critical",
                              "r": f"{code}: {r.get('violation_description') or ''}".strip()})
    return _finish(places)


# -------------------------------------------------------------- Chicago
def normalize_chicago(rows, cfg):
    """PASS_FAIL: no score exists; `results` (Pass / Pass w/ Conditions /
    Fail / Out of Business / No Entry / Not Ready) rides in `disp`.
    The `violations` field is ' | '-separated '<n>. TITLE - Comments: …'."""
    places = {}
    for r in rows:
        lic = r.get("license_") or ""
        name = r.get("dba_name") or r.get("aka_name") or ""
        if not name:
            continue
        key = lic if lic and lic != "0" else f"{name}|{r.get('address', '')}"
        p = places.get(key)
        if p is None:
            lat, lng = _coord(r.get("latitude"), r.get("longitude"))
            p = places[key] = _place(
                cfg, key, name, r.get("address") or "",
                (r.get("city") or "CHICAGO").title(), r.get("zip"), "Cook",
                lat, lng, "https://data.cityofchicago.org/d/4ijn-s7e5")
        iid = r.get("inspection_id") or f"{r.get('inspection_date')}"
        viol = []
        for part in (r.get("violations") or "").split(" | "):
            part = part.strip()
            if part:
                m = re.match(r"(\d+)\.", part)
                n = int(m.group(1)) if m else 0
                # CDPH numbering since 7/1/2018: 1–14 priority, 15–29
                # priority-foundation, 30+ core. Only 'priority' -> critical.
                viol.append({"p": 0, "c": 1 <= n <= 14, "r": part[:1000]})
        p["_insp"][iid] = {"d": _iso(r.get("inspection_date")),
                           "t": r.get("inspection_type") or "",
                           "s": NO_SCORE,
                           "disp": (r.get("results") or "").strip(), "v": viol}
    return _finish(places)


# ---------------------------------------------------------- King County
def normalize_kingco(rows, cfg):
    """PENALTY_LOW: `inspection_score` is red+blue violation points
    (lower is better). `inspection_result` (Satisfactory/Unsatisfactory/
    Complete…) and the establishment's food-safety rating (`grade`:
    Excellent/Good/Okay/Needs to Improve) ride in `disp`. The public
    dataset has no coordinates."""
    places = {}
    for r in rows:
        bid = r.get("business_id")
        if not bid or not r.get("name"):
            continue
        p = places.get(bid)
        if p is None:
            p = places[bid] = _place(
                cfg, bid, r["name"], r.get("address") or "",
                (r.get("city") or "").title(), r.get("zip_code"), "King",
                None, None, "https://kingcounty.gov/en/dept/dph/health-safety/"
                "food-safety/search-restaurant-safety-ratings")
        key = r.get("inspection_serial_num") or _iso(r.get("inspection_date"))
        insp = p["_insp"].get(key)
        if insp is None:
            s = _int(r.get("inspection_score"))
            res = (r.get("inspection_result") or "").strip()
            rating = (r.get("grade") or "").strip()
            disp = "; ".join(x for x in (res, f"Rating: {rating}" if rating else "") if x)
            insp = p["_insp"][key] = {"d": _iso(r.get("inspection_date")),
                                      "t": r.get("inspection_type") or "",
                                      "s": s if s is not None and s >= 0 else NO_SCORE,
                                      "disp": disp, "v": []}
        if r.get("violation_description"):
            insp["v"].append({"p": _int(r.get("violation_points")) or 0,
                              "c": (r.get("violation_type") or "").upper() == "RED",
                              "r": r["violation_description"].strip()})
    return _finish(places)


SOURCES = {
    "nyc": {
        "region": "us-ny", "state": "NY", "name": "New York (NYC)",
        "domain": "data.cityofnewyork.us", "dataset": "43nn-pn8j",
        "date_field": "inspection_date", "window_days": None,  # source is already ~3 yrs
        "source_id": "ny-nyc-dohmh", "jurisdiction": "NY-NYC-DOHMH",
        "jur_name": "NYC Department of Health & Mental Hygiene",
        "model": "PENALTY_LOW", "normalize": normalize_nyc,
        "attribution": "NYC Department of Health and Mental Hygiene — DOHMH New York "
                       "City Restaurant Inspection Results, NYC Open Data (43nn-pn8j). "
                       "Public data; NYC Open Data Terms of Use.",
    },
    "chicago": {
        "region": "us-il", "state": "IL", "name": "Illinois (Chicago)",
        "domain": "data.cityofchicago.org", "dataset": "4ijn-s7e5",
        "date_field": "inspection_date", "window_days": 730,
        "source_id": "il-chicago", "jurisdiction": "IL-CHICAGO-CDPH",
        "jur_name": "Chicago Department of Public Health",
        "model": "PASS_FAIL", "normalize": normalize_chicago,
        "attribution": "City of Chicago — Food Inspections, Chicago Data Portal "
                       "(4ijn-s7e5). Data provided by the City of Chicago; subject "
                       "to the City of Chicago Data Portal Terms of Use.",
    },
    "kingco": {
        "region": "us-wa", "state": "WA", "name": "Washington (King County)",
        "domain": "data.kingcounty.gov", "dataset": "r878-4sxa",
        "date_field": "inspection_date", "window_days": 730,
        "source_id": "wa-kingcounty", "jurisdiction": "WA-KING-PHSKC",
        "jur_name": "Public Health — Seattle & King County",
        "model": "PENALTY_LOW", "normalize": normalize_kingco,
        "attribution": "Public Health — Seattle & King County — Food Establishment "
                       "Inspection Data, King County Open Data (r878-4sxa). Public "
                       "data; King County open data terms of use.",
    },
}
