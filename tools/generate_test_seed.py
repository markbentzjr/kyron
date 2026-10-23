import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CANARIES_PATH = os.path.join(HERE, 'canaries.json')
SEED_PATH = os.path.join(HERE, '..', 'app', 'src', 'main', 'assets', 'places_seed_geocoded.json')

def main():
    os.makedirs(os.path.dirname(SEED_PATH), exist_ok=True)
    canaries_doc = json.load(open(CANARIES_PATH, encoding='utf-8'))
    places = []

    for c in canaries_doc.get('canaries', []):
        lat = 33.345 if c['expected'] == 'pinned' else None
        lng = -86.612 if c['expected'] == 'pinned' else None
        addr = "16758 US-280" if c['id'] == 'adph_750e13236c' else "123 Main St"
        zipc = "35043" if c['id'] == 'adph_750e13236c' else "35209"
        p = {
            "id": c['id'],
            "n": c['name'],
            "a": addr,
            "c": c['city'],
            "z": zipc,
            "ct": c['county'],
            "s": 98 if c['id'] == 'adph_750e13236c' else 95,
            "d": "09/14/2026" if c['id'] == 'adph_750e13236c' else "09/14/2026",
            "src": "ADPH",
            "lat": lat,
            "lng": lng,
            "insp": [{"s": 98 if c['id'] == 'adph_750e13236c' else 95, "d": "09/14/2026", "t": "Routine", "v": []}]
        }
        places.append(p)

    json.dump(places, open(SEED_PATH, 'w', encoding='utf-8'), separators=(',', ':'))
    print(f"Generated test seed with {len(places)} places at {SEED_PATH}")

if __name__ == '__main__':
    main()
