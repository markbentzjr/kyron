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

# --- street-anchored name/street splitting (Workstream B fix, Oct 2026) ---
# The JCDH list blob is ONE fused string: "NAME STREET CITY ZIP". The old
# splitter cut the name at its first digit token, so any name containing a
# number ("HOME 2 SUITES", "PIGGLY WIGGLY # 263 PRODUCE", "THE 3 DELIGHTS")
# was truncated and the rest of the name was fused onto the street address
# (58 shipped records). The splitter below instead anchors on the STREET:
# it finds the split point where the remainder is a complete street
# (house number + street-name token + suffix). Mirrors the canonical gate
# in manual/tools/validate_seed.py — keep the two in sync.
_STREET_SUF = {
    'AVE', 'AVENUE', 'ST', 'STREET', 'RD', 'ROAD', 'DR', 'DRIVE', 'BLVD',
    'HWY', 'HIGHWAY', 'LN', 'LANE', 'CT', 'COURT', 'CIR', 'CIRCLE', 'PKWY',
    'PARKWAY', 'WAY', 'PL', 'PLACE', 'TRL', 'TRAIL', 'TER', 'TERRACE', 'SQ',
    'SQUARE', 'LOOP', 'CV', 'COVE', 'PT', 'POINT', 'XING', 'CROSSING', 'ALY',
    'ALLEY', 'EXPY', 'FWY', 'RUN', 'ROW', 'PATH', 'WALK', 'PLAZA', 'PLZ',
    'VILLAGE', 'VLG', 'GALLERIA', 'TRCE', 'TRACE', 'PARK', 'COMMONS',
    'LANDING', 'HTS', 'HEIGHTS', 'VLY', 'VALLEY', 'BND', 'BEND',
}
_STREET_DIR = {'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW',
               'NORTH', 'SOUTH', 'EAST', 'WEST',
               'NORTHEAST', 'NORTHWEST', 'SOUTHEAST', 'SOUTHWEST'}
_SUITE_TOKENS = {'STE', 'SUITE', 'APT', 'UNIT', 'BLDG'}

def _complete_street(toks):
    """True when toks form a complete street: house number, >=1 street-name
    token, and a street-suffix token. ('151 HWY' is NOT complete: no name
    token between the number and the suffix.)"""
    if len(toks) < 3:
        return False
    if not re.fullmatch(r'\d+', toks[0]):
        return False
    body = [t.strip('.,') for t in toks[1:]]
    if not any(t in _STREET_SUF for t in body):
        return False
    name_toks = [t for t in body if t not in _STREET_SUF and t not in _STREET_DIR]
    return len(name_toks) >= 1

def _tail_clean(seg):
    """A name tail (tokens the split moves back into the name) must not
    contain street debris: ordinal street names (29TH) or suite markers —
    their presence means the candidate split cuts into the street itself
    (e.g. the suite-interleaved '1830 29TH Ste . 150 -160 -175 AVE')."""
    for t in seg:
        tt = t.strip('.,()').upper()
        if re.fullmatch(r'\d+(ST|ND|RD|TH)', tt):
            return False
        if tt in _SUITE_TOKENS:
            return False
    return True

def split_name_street(rest):
    """Split 'NAME STREET' (city/zip already removed) at the street anchor.
    Returns (name, street). Falls back to the legacy first-digit split when
    no complete-street anchor exists (suffix-less streets like
    '800 LAKESHORE'), preserving prior behavior for those records."""
    toks = rest.split()
    cands = [i for i in range(1, len(toks)) if _complete_street(toks[i:])]
    if cands:
        base = cands[0]
        chosen = base
        for i in cands[1:]:
            if _tail_clean(toks[base:i]):
                chosen = i
            else:
                break
        return ' '.join(toks[:chosen]), ' '.join(toks[chosen:])
    for i in range(1, len(toks)):
        if re.fullmatch(r'\d+', toks[i]):
            return ' '.join(toks[:i]), ' '.join(toks[i:])
    return rest, ""

def street_has_fused_tail(street):
    """True when a produced street still begins with a name fragment:
    a complete street appears as a proper suffix. Used as a build-time
    assertion so a fused record can never ship silently again."""
    toks = street.split()
    for i in range(1, len(toks)):
        if _complete_street(toks[i:]):
            tail = [t.strip('.,') for t in toks[:i]]
            alpha = [t for t in tail
                     if t not in _STREET_DIR and not re.fullmatch(r'\d+', t)]
            if not alpha and tail and tail[-1] in _STREET_DIR:
                return False  # '<house#> <directional>' street prefix
            return True
    return False

# --- ADPH statewide ---
adph = {}
adph_rejects = []
for path in sorted(glob.glob(os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/adph/*.json')):
    for r in json.load(open(path)):
        # Workstream B gate rule: a score that cannot be attached to a
        # named place AT a street address must not ship. ADPH publishes a
        # few permits with no street address at all (verified: exactly 2 in
        # the Oct 2026 harvest); never invent one — exclude and log loudly.
        if not (r.get('address') or '').strip():
            adph_rejects.append(r)
            continue
        if not (r.get('name') or '').strip():
            adph_rejects.append(r)
            continue
        key = match_key(r['name'], r['zip'][:5], r['address'])
        adph[key] = {
            "id": "adph_" + hashlib.md5(key.encode()).hexdigest()[:10],
            "n": r['name'], "a": r['address'], "c": r['city'], "z": r['zip'][:5],
            "ct": r['county'], "s": r['score'], "d": r['date'], "src": "ADPH",
            "lat": None, "lng": None, "du": None, "insp": []
        }
print("ADPH places:", len(adph))
if adph_rejects:
    rej_path = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/adph_rejects.json'
    json.dump(adph_rejects, open(rej_path, 'w'), indent=1)
    print(f"ADPH REJECTS (score without name/street address): {len(adph_rejects)} -> {rej_path}")

# --- JCDH detail-rich places ---
# Optional legacy JCDH detail extracts (not public); skipped when absent.
_PROTO = os.environ.get('KYRON_JCDH_PROTO', '')
_RAW = os.environ.get('KYRON_JCDH_RAW', '')
proto = {p['permit']: p for p in json.load(open(_PROTO))} if os.path.exists(_PROTO) else {}
raw = json.load(open(_RAW)) if os.path.exists(_RAW) else []
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
    # Workstream B: the prototype extract was built with the same fused
    # first-digit split as the enum path; if its street still carries a
    # name tail, re-split the recombined string at the street anchor.
    pname, pstreet = pp['name'], pp['street']
    if street_has_fused_tail(pstreet):
        pname, pstreet = split_name_street(f"{pname} {pstreet}")
        pname = title_case(pname)
    rec = {
        "id": f"jcdh_{permit}",
        "n": pname, "a": pstreet, "c": pp['city'], "z": pp['zip'],
        "ct": "Jefferson", "s": pp['score'], "d": normalize_date(pp['date']), "src": "JCDH",
        "lat": pp.get('lat'), "lng": pp.get('lng'),
        "du": ("https://www.jcdh.org" + rp['detail_path']) if rp.get('detail_path') else None,
        "insp": insps
    }
    key = match_key(pname, pp['zip'], pstreet)
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
enum_path = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/jcdh_enum.json'
n_enum = n_dup = n_bad = 0
if os.path.exists(enum_path):
    for r in json.load(open(enum_path)):
        rid = f"jcdh_{r['permit']}"
        if rid in existing_ids:
            n_dup += 1
            continue
        # The blob is one fused string: "NAME STREET CITY ZIP Smoke Free:".
        # City/ZIP come off the tail (split_address), then NAME/STREET are
        # separated at the street anchor (split_name_street) — NOT at the
        # first digit, which truncated any name containing a number and
        # fused its tail onto the street (Workstream B root cause).
        body = r['blob'].strip().split(' Smoke Free:')[0].strip()
        rest, city, zipc = split_address(body)
        if not zipc:
            n_bad += 1
            continue
        name_raw, street = split_name_street(rest)
        name = title_case(name_raw.strip())
        # Never ship a fused/fragmented record silently again: a name that
        # is still a fragment (bare '#', lone article) or a street that
        # still carries a name tail is rejected as unparseable instead.
        if (not name or name.endswith('#')
                or name.upper() in ('THE', 'A', 'AN')
                or street_has_fused_tail(street)):
            n_bad += 1
            print(f"JCDH enum REJECT (fragmented name/street): permit={r['permit']} name={name!r} street={street!r}")
            continue
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
mchd_path = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/mchd_rows.json'
n_mchd = n_mchd_bad = 0
if os.path.exists(mchd_path):
    insp_re = re.compile(r'^(\d{1,2}/\d{1,2}/\d{4}),\s*Score:\s*(\d+)')
    for row in json.load(open(mchd_path)):
        name, address, csz = (row + ["", "", ""])[:3]
        name = name.strip()
        if not name or not (address or "").strip():
            # Workstream B gate rule: no score without a name AND a street
            # address (see the ADPH guard above).
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
out = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/manual/src/main/assets/places_seed.json'
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(places, open(out, 'w'), separators=(',', ':'))
n_insp = sum(1 for p in places if p['insp'])
n_geo = sum(1 for p in places if p['lat'])
print(f"SEED total={len(places)} with_inspections={n_insp} geocoded={n_geo} bytes={os.path.getsize(out)}")
from collections import Counter
print("top counties:", Counter(p['ct'] for p in places).most_common(8))
