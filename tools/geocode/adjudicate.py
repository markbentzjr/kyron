"""Stage 3: adjudicate Census batch results (Gameplan draft section 3.5).

Never accepts a result just because coordinates came back:
  Match/Exact  -> accept only if the matched house number equals the input
                  number, ZIP5 agrees (or city agrees, noted), and the
                  coordinates fall inside Alabama's envelope.
  Match/Non_Exact -> accept only when number + ZIP + city all agree
                  ("strong"); otherwise it goes to the repair round.
  Tie          -> never resolved silently; residual queue.
  No_Match     -> repair round (expanded-suffix variant), then queue.
  Coordinates outside the Alabama envelope are rejected outright.

Outputs (out/):
  adjudicated.json   address_id -> {status, acc, match, lat, lng, note}
  residual_queue.csv addresses for the future Geocodio free-tier pass
  adjudicate_report.json  counts by class / source / county + truth check
"""
import csv
import json
import math
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RESULTS = os.path.join(OUT, "results")

AL_LAT = (30.1, 35.05)
AL_LNG = (-88.5, -84.85)


def in_al(lat, lng):
    return AL_LAT[0] <= lat <= AL_LAT[1] and AL_LNG[0] <= lng <= AL_LNG[1]


def lead_number(s):
    parts = (s or "").strip().split(" ")
    return parts[0] if parts and parts[0].isdigit() else ""


def parse_results():
    """address_id -> list of result rows (a later repair result overrides)."""
    results = {}
    order = sorted(os.listdir(RESULTS)) if os.path.isdir(RESULTS) else []
    # repair results must win over the original submission for the same id
    order.sort(key=lambda n: ("repair" in n, n))
    for fn in order:
        if not fn.endswith(".csv"):
            continue
        with open(os.path.join(RESULTS, fn)) as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                # Census omits trailing empty fields on Tie/No_Match rows.
                row = row + [""] * (8 - len(row))
                aid = row[0]
                rec = {
                    "match": row[2].strip(),
                    "match_type": row[3].strip(),
                    "matched_address": row[4].strip(),
                    "coords": row[5].strip() if len(row) > 5 else "",
                    "batch": fn,
                }
                results[aid] = rec
    return results


def matched_parts(matched_address):
    # "1101 3RD AVE N, BIRMINGHAM, AL, 35203"
    parts = [p.strip() for p in matched_address.split(",")]
    street = parts[0] if parts else ""
    city = parts[1] if len(parts) > 1 else ""
    zip5 = parts[3] if len(parts) > 3 else (parts[2] if len(parts) > 2 else "")
    return street, city, zip5


def adjudicate_one(addr, rec):
    """Return (status, acc_class, match_type, lat, lng, note)."""
    if rec is None:
        return ("NOT_SUBMITTED", "NONE", "", None, None, "no result row")
    if rec["match"] == "Tie":
        return ("TIE", "NONE", "TIE", None, None, "census tie - never auto-resolved")
    if rec["match"] == "No_Match":
        return ("NO_MATCH", "NONE", "NO_MATCH", None, None, "census no match")
    # Match
    try:
        lng_s, lat_s = rec["coords"].split(",")
        lat, lng = float(lat_s), float(lng_s)
    except Exception:
        return ("REJECTED", "NONE", rec["match_type"], None, None, "unparseable coords")
    if not in_al(lat, lng):
        return ("REJECTED", "NONE", rec["match_type"], None, None,
                f"coords outside Alabama envelope: {lat},{lng}")
    m_street, m_city, m_zip = matched_parts(rec["matched_address"])
    num_ok = lead_number(m_street) == lead_number(addr["street"]) and lead_number(addr["street"]) != ""
    zip_ok = (m_zip[:5] == addr["zip"]) if addr["zip"] else False
    city_ok = m_city.upper() == addr["city"].upper()
    if rec["match_type"] == "Exact":
        if num_ok and zip_ok:
            return ("ACCEPTED", "ADDRESS_RANGE", "EXACT", lat, lng, "exact; number+zip agree")
        if num_ok and city_ok:
            return ("ACCEPTED", "ADDRESS_RANGE", "EXACT", lat, lng,
                    "exact; number+city agree, zip differs (boundary)")
        return ("NEEDS_REVIEW", "NONE", "EXACT", None, None,
                f"exact but evidence disagrees (num_ok={num_ok} zip_ok={zip_ok} city_ok={city_ok})")
    # Non_Exact
    if num_ok and zip_ok and city_ok:
        return ("ACCEPTED", "ADDRESS_RANGE", "NON_EXACT", lat, lng,
                "non-exact but number+zip+city all agree")
    return ("NEEDS_REVIEW", "NONE", "NON_EXACT", None, None,
            f"non-exact, weak evidence (num_ok={num_ok} zip_ok={zip_ok} city_ok={city_ok})")


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    addrs = {a["address_id"]: a for a in json.load(open(os.path.join(OUT, "addresses.json")))}
    results = parse_results()
    out = {}
    counts = Counter()
    for aid, a in addrs.items():
        if not a["submittable"]:
            status = "PO_BOX" if "PO_BOX" in a["flags"] else "INSUFFICIENT_ADDRESS"
            out[aid] = {"status": status, "acc": "NONE", "match": "",
                        "lat": None, "lng": None, "note": "not submittable: " + ",".join(a["flags"])}
            counts[status] += 1
            continue
        status, acc, match, lat, lng, note = adjudicate_one(a, results.get(aid))
        out[aid] = {"status": status, "acc": acc, "match": match,
                    "lat": lat, "lng": lng, "note": note,
                    "matched_address": results.get(aid, {}).get("matched_address", "")}
        counts[status] += 1
        counts["match_" + (match or "NONE")] += 1
    json.dump(out, open(os.path.join(OUT, "adjudicated.json"), "w"))

    # Ground truth: distance from Census coords to the previously stored
    # coordinates for places that had them (harvested earlier).
    seed = json.load(open(os.path.join(HERE, "..", "..", "src", "main", "assets", "places_seed.json")))
    place_map = json.load(open(os.path.join(OUT, "place_address.json")))
    truth = []
    for p in seed:
        if p.get("lat") is not None:
            adj = out[place_map[p["id"]]]
            if adj["status"] == "ACCEPTED":
                d = haversine_m(p["lat"], p["lng"], adj["lat"], adj["lng"])
                truth.append({"place": p["n"], "id": p["id"], "dist_m": round(d, 1)})
    dists = sorted(t["dist_m"] for t in truth)
    report = {
        "addresses": len(addrs),
        "status_counts": {k: v for k, v in counts.items() if not k.startswith("match_")},
        "match_counts": {k[6:]: v for k, v in counts.items() if k.startswith("match_")},
        "truth_compared": len(truth),
        "truth_dist_median": dists[len(dists) // 2] if dists else None,
        "truth_dist_max": dists[-1] if dists else None,
        "truth_over_250m": [t for t in truth if t["dist_m"] > 250],
    }
    json.dump(report, open(os.path.join(OUT, "adjudicate_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
