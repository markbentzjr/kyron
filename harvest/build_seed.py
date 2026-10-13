import json, os, glob, re, hashlib

def match_key(name, zipc, address):
    n = re.sub(r'[^A-Z0-9 ]', '', name.upper())
    n = re.sub(r'\s+', ' ', n).strip()
    num = (address.strip().split(' ') or [''])[0]
    return f"{n}|{zipc}|{num}"

def app_id(prefix, key):
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"{prefix}_{h}"

def title_case(s):
    return re.sub(r'\b\w', lambda m: m.group(0).upper(), s.lower())

MULTI_CITIES = ["VESTAVIA HILLS", "MOUNTAIN BROOK", "CENTER POINT", "PLEASANT GROVE", "SYLVAN SPRINGS"]

def split_address(raw):
    m = re.search(r'(\d{5})\s*$', raw)
    if not m:
        return raw, "", ""
    zipc = m.group(1)
    rest = raw[:m.start()].strip()
    for mc in MULTI_CITIES:
        if rest.upper().endswith(" " + mc):
            return rest[:len(rest) - len(mc)].strip(), title_case(mc), zipc
    idx = rest.rfind(' ')
    if idx < 0:
        return rest, "", zipc
    return rest[:idx].strip(), title_case(rest[idx + 1:]), zipc

def normalize_date(d):
    parts = d.strip().split('/')
    if len(parts) != 3:
        return d.strip()
    y = parts[2]
    if len(y) == 2:
        y = "20" + y
    return f"{parts[0]}/{parts[1]}/{y}"

# --- ADPH statewide ---
adph = {}
for path in sorted(glob.glob('/home/hatch/kyron-build/harvest/adph/*.json')):
    for r in json.load(open(path)):
        key = match_key(r['name'], r['zip'][:5], r['address'])
        adph[key] = {
            "id": "adph_" + hashlib.md5(key.encode()).hexdigest()[:10],
            "n": r['name'], "a": r['address'], "c": r['city'], "z": r['zip'][:5],
            "ct": r['county'], "s": r['score'], "d": r['date'], "src": "ADPH",
            "lat": None, "lng": None, "du": None, "insp": []
        }
print("ADPH places:", len(adph))

# --- JCDH detail-rich places ---
proto = {p['permit']: p for p in json.load(open('/home/hatch/workspace/kyron-prototype/data.json'))}
raw = json.load(open('/home/hatch/workspace/goals/kyron-free-food-safety-app-on-the-play-store/hidden_files/jcdh_dataset.json'))
merged = 0
for rp in raw:
    permit = rp['permit']
    pp = proto.get(permit)
    if not pp: continue
    insps = []
    for ins in rp.get('inspections', []):
        if 'score' not in ins: continue
        vs = [{"p": v['points'], "c": v.get('critical') == 'Yes', "r": v['remarks']} for v in ins.get('violations', [])]
        insps.append({"s": ins['score'], "d": normalize_date(ins['date']), "t": ins.get('type', ''), "v": vs})
    rec = {
        "id": f"jcdh_{permit}",
        "n": pp['name'], "a": pp['street'], "c": pp['city'], "z": pp['zip'],
        "ct": "Jefferson", "s": pp['score'], "d": normalize_date(pp['date']), "src": "JCDH",
        "lat": pp.get('lat'), "lng": pp.get('lng'),
        "du": ("https://www.jcdh.org" + rp['detail_path']) if rp.get('detail_path') else None,
        "insp": insps
    }
    key = match_key(pp['name'], pp['zip'], pp['street'])
    if key in adph:
        del adph[key]
        merged += 1
    adph[rec['id']] = rec  # keyed separately to avoid collision overwrite
print("JCDH merged over ADPH duplicates:", merged)

COUNTY_FIX = {"Dekalb": "DeKalb", "St.Clair": "St. Clair"}
for p in adph.values():
    if p['ct'] in COUNTY_FIX:
        p['ct'] = COUNTY_FIX[p['ct']]

# --- JCDH catalog enumeration (list-level: score/date + detail link) ---
existing_ids = {p['id'] for p in adph.values()}
enum_path = '/home/hatch/kyron-build/harvest/jcdh_enum.json'
n_enum = n_dup = n_bad = 0
if os.path.exists(enum_path):
    blob_re = re.compile(r'^(.*?)\s+(\d+\s+.+?)\s+Smoke Free:.*$', re.S)
    for r in json.load(open(enum_path)):
        rid = f"jcdh_{r['permit']}"
        if rid in existing_ids:
            n_dup += 1
            continue
        m = blob_re.match(r['blob'].strip())
        if not m:
            n_bad += 1
            continue
        name = title_case(m.group(1).strip())
        street, city, zipc = split_address(m.group(2).strip())
        try:
            score = int(r['score'])
        except (TypeError, ValueError):
            n_bad += 1
            continue
        rec = {
            "id": rid,
            "n": name, "a": street, "c": city, "z": zipc,
            "ct": "Jefferson", "s": score, "d": normalize_date(r['date']),
            "src": "JCDH", "lat": None, "lng": None,
            "du": ("https://www.jcdh.org" + r['detail_path']) if r.get('detail_path') else None,
            "insp": []
        }
        key = match_key(name, zipc, street)
        if key in adph:
            del adph[key]
        adph[rid] = rec
        existing_ids.add(rid)
        n_enum += 1
print(f"JCDH enum added: {n_enum} (dup permits skipped: {n_dup}, unparseable: {n_bad})")

# --- MCHD (Mobile County) — scores + up to 4 dated inspections, no violations ---
mchd_path = '/home/hatch/kyron-build/harvest/mchd_rows.json'
n_mchd = n_mchd_bad = 0
if os.path.exists(mchd_path):
    insp_re = re.compile(r'^(\d{1,2}/\d{1,2}/\d{4}),\s*Score:\s*(\d+)')
    for row in json.load(open(mchd_path)):
        name, address, csz = (row + ["", "", ""])[:3]
        name = name.strip()
        if not name:
            n_mchd_bad += 1
            continue
        city = csz.split(',')[0].strip()
        zm = re.search(r'(\d{5})', csz)
        zipc = zm.group(1) if zm else ""
        insps = []
        for cell in row[3:7]:
            m = insp_re.match((cell or "").strip())
            if m:
                insps.append({"s": int(m.group(2)), "d": m.group(1), "t": "", "v": []})
        if not insps:
            n_mchd_bad += 1
            continue
        key = match_key(name, zipc, address)
        rec = {
            "id": "mchd_" + hashlib.md5(key.encode()).hexdigest()[:10],
            "n": name, "a": address.strip(), "c": city, "z": zipc,
            "ct": "Mobile", "s": insps[0]["s"], "d": insps[0]["d"], "src": "MCHD",
            "lat": None, "lng": None, "du": None, "insp": insps
        }
        adph[rec['id']] = rec
        n_mchd += 1
print(f"MCHD added: {n_mchd} (skipped: {n_mchd_bad})")

places = list(adph.values())
places.sort(key=lambda p: (p['ct'], p['n'].lower()))
out = '/home/hatch/kyron-build/manual/src/main/assets/places_seed.json'
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(places, open(out, 'w'), separators=(',', ':'))
n_insp = sum(1 for p in places if p['insp'])
n_geo = sum(1 for p in places if p['lat'])
print(f"SEED total={len(places)} with_inspections={n_insp} geocoded={n_geo} bytes={os.path.getsize(out)}")
from collections import Counter
print("top counties:", Counter(p['ct'] for p in places).most_common(8))
