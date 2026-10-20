"""Stage 4: fold adjudicated geocode results into a NEW places seed.

- The original seed is preserved untouched at out/places_seed_original.json
  (and a copy stays recoverable from the previously delivered APK).
- The new seed is written to src/main/assets/places_seed_geocoded.json and
  the old asset file is removed from assets/ so the APK ships one seed.
- Every place gains provenance fields:
    gs  geocode status (ACCEPTED / TIE / NO_MATCH / NEEDS_REVIEW / ...)
    ga  accuracy class (ADDRESS_RANGE for Census, NONE when unresolved)
    gp  provider (CENSUS | HARVEST | "")
    gm  match type (EXACT / NON_EXACT / "")
  Places whose address has no accepted geocode get lat/lng = null:
  NO centroid or jittered coordinate is ever written as a place location.
- Residual addresses (anything not accepted) go to out/residual_queue.csv
  for the future Geocodio free-tier pass (Gameplan section 3.1 stage 2).
"""
import csv
import json
import os
import shutil
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ASSETS = os.path.join(HERE, "..", "..", "src", "main", "assets")
OLD_SEED = os.path.join(ASSETS, "places_seed.json")
NEW_SEED = os.path.join(ASSETS, "places_seed_geocoded.json")


def main():
    backup = os.path.join(OUT, "places_seed_original.json")
    if not os.path.exists(backup):
        shutil.copyfile(OLD_SEED, backup)
        print(f"original seed preserved -> {backup}")

    places = json.load(open(backup))
    adjudicated = json.load(open(os.path.join(OUT, "adjudicated.json")))
    addresses = {a["address_id"]: a for a in json.load(open(os.path.join(OUT, "addresses.json")))}
    place_map = json.load(open(os.path.join(OUT, "place_address.json")))

    stats = Counter()
    by_source = {}
    for p in places:
        adj = adjudicated[place_map[p["id"]]]
        src = p.get("src", "?")
        by_source.setdefault(src, Counter())
        if adj["status"] == "ACCEPTED":
            p["lat"], p["lng"] = adj["lat"], adj["lng"]
            p["gs"], p["ga"], p["gp"] = "ACCEPTED", adj["acc"], "CENSUS"
            p["gm"] = (adj["match"] or "").upper()
            stats["accepted_census"] += 1
            by_source[src]["accepted"] += 1
        elif p.get("lat") is not None:
            # Previously harvested coordinates (JCDH harvest, Nominatim).
            # Kept, with honest provenance; Census had no accepted result.
            p["gs"], p["ga"], p["gp"], p["gm"] = "ACCEPTED", "ADDRESS_RANGE", "HARVEST", ""
            stats["accepted_harvest_kept"] += 1
            by_source[src]["accepted"] += 1
        else:
            p["lat"], p["lng"] = None, None
            p["gs"], p["ga"], p["gp"], p["gm"] = adj["status"], "NONE", "", ""
            stats["unresolved_" + adj["status"]] += 1
            by_source[src]["unresolved"] += 1
        by_source[src]["total"] += 1

    json.dump(places, open(NEW_SEED, "w"), separators=(",", ":"))
    print(f"new seed -> {NEW_SEED} ({os.path.getsize(NEW_SEED)} bytes)")

    # Residual queue for the Geocodio free-tier pass: every address that is
    # not accepted, worst (most places) first.
    rows = []
    for aid, a in addresses.items():
        adj = adjudicated[aid]
        if adj["status"] != "ACCEPTED":
            rows.append({
                "address_id": aid,
                "street": a["street"], "city": a["city"], "zip": a["zip"],
                "county": a["county"], "status": adj["status"],
                "reason": adj["note"], "place_count": a["place_count"],
                "flags": ",".join(a["flags"]),
            })
    rows.sort(key=lambda r: -r["place_count"])
    with open(os.path.join(OUT, "residual_queue.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    residual_places = sum(r["place_count"] for r in rows)

    report = {
        "places_total": len(places),
        "places_with_real_coords": stats["accepted_census"] + stats["accepted_harvest_kept"],
        "accepted_census": stats["accepted_census"],
        "accepted_harvest_kept": stats["accepted_harvest_kept"],
        "unresolved_by_status": {k[11:]: v for k, v in stats.items() if k.startswith("unresolved_")},
        "residual_addresses": len(rows),
        "residual_places": residual_places,
        "by_source": {s: dict(c) for s, c in sorted(by_source.items())},
    }
    json.dump(report, open(os.path.join(OUT, "seed_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))

    if os.path.exists(OLD_SEED):
        os.remove(OLD_SEED)
        print("old seed asset removed from assets/ (preserved in out/)")


if __name__ == "__main__":
    main()
