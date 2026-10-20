"""Stage 1 of the Kyron geocoding pipeline (Gameplan draft section 3.3).

Reads the bundled places seed, creates one `addresses` record per unique
normalized physical address, and maps every place to its address_id.

Outputs (tools/geocode/out/):
  addresses.json        unique addresses: raw + normalized + flags
  place_address.json    { place_id: address_id }
  extract_report.json   counts by flag / disposition
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geocode_common import normalize_address, address_id  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "..", "..", "src", "main", "assets", "places_seed.json")
OUT = os.path.join(HERE, "out")


def main():
    os.makedirs(OUT, exist_ok=True)
    places = json.load(open(SEED))
    addresses = {}
    place_map = {}
    flag_counts = Counter()
    submittable_places = 0

    for p in places:
        norm = normalize_address(p.get("a", ""), p.get("c", ""), p.get("z", ""))
        aid = address_id(norm)
        for f in norm["flags"]:
            flag_counts[f] += 1
        if aid not in addresses:
            addresses[aid] = {
                "address_id": aid,
                "raw_street": p.get("a", ""),
                "raw_city": p.get("c", ""),
                "raw_zip": p.get("z", ""),
                "street": norm["street"],
                "street_expanded": norm["street_expanded"],
                "city": norm["city"],
                "state": "AL",
                "zip": norm["zip"],
                "county": p.get("ct", ""),
                "flags": norm["flags"],
                "submittable": norm["submittable"],
                "place_count": 0,
            }
        addresses[aid]["place_count"] += 1
        place_map[p["id"]] = aid
        if norm["submittable"]:
            submittable_places += 1

    addr_list = sorted(addresses.values(), key=lambda a: a["address_id"])
    json.dump(addr_list, open(os.path.join(OUT, "addresses.json"), "w"), indent=1)
    json.dump(place_map, open(os.path.join(OUT, "place_address.json"), "w"))
    report = {
        "places": len(places),
        "unique_addresses": len(addr_list),
        "submittable_addresses": sum(1 for a in addr_list if a["submittable"]),
        "unsubmittable_addresses": sum(1 for a in addr_list if not a["submittable"]),
        "submittable_places": submittable_places,
        "place_flag_counts": dict(flag_counts),
        "max_places_per_address": max(a["place_count"] for a in addr_list),
    }
    json.dump(report, open(os.path.join(OUT, "extract_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
