#!/usr/bin/env python3
"""Kyron seed / region-pack validation gate (Workstream B, Oct 2026).

Fails a dataset (exit 1) when any of these ship-blockers are present:

  G1  a result-bearing place has a blank / whitespace-only name
  G2  a result-bearing place has a blank / whitespace-only street address
  G3  an inspection references a place_id that does not exist
      (flat layouts), or an embedded inspection carries a place_id that
      disagrees with its parent place
  G4  a place name matches the placeholder / header blocklist, or ends
      with a bare '#' (the truncation marker of a fused name split)
  G5  a fused name/street split is detected: the street field begins
      with a fragment of the establishment's name followed by a complete
      street address (the JCDH enum-regex defect class)
  G6  duplicate place ids

"Result-bearing" means the record carries something the app renders as a
result: a numeric score >= 0 (place level or on any inspection), a
native-result / disposition string, or any inspection rows.

Accepts the compact seed format (list of dicts with n/a/s/insp keys)
and the long pack format (n/a/disp/insp). Usage:

    python3 validate_seed.py <dataset.json> [--quiet]

Exit 0 = PASS, 1 = FAIL (violations printed, grouped by check).
"""

import json
import re
import sys

# ---------------------------------------------------------------- fused split
SUF = {
    'AVE', 'AVENUE', 'ST', 'STREET', 'RD', 'ROAD', 'DR', 'DRIVE', 'BLVD',
    'HWY', 'HIGHWAY', 'LN', 'LANE', 'CT', 'COURT', 'CIR', 'CIRCLE', 'PKWY',
    'PARKWAY', 'WAY', 'PL', 'PLACE', 'TRL', 'TRAIL', 'TER', 'TERRACE', 'SQ',
    'SQUARE', 'LOOP', 'CV', 'COVE', 'PT', 'POINT', 'XING', 'CROSSING', 'ALY',
    'ALLEY', 'EXPY', 'FWY', 'RUN', 'ROW', 'PATH', 'WALK', 'PLAZA', 'PLZ',
    'VILLAGE', 'VLG', 'GALLERIA', 'TRCE', 'TRACE', 'PARK', 'COMMONS',
    'LANDING', 'HTS', 'HEIGHTS', 'VLY', 'VALLEY', 'BND', 'BEND',
}
DIR = {'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW',
       'NORTH', 'SOUTH', 'EAST', 'WEST',
       'NORTHEAST', 'NORTHWEST', 'SOUTHEAST', 'SOUTHWEST'}


def _collapse(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def _complete_street(toks):
    """True when toks form a complete street: house number, >=1 street-name
    token, and a street-suffix token. ('151 HWY' is NOT complete: no name
    token between the number and the suffix.)"""
    if len(toks) < 3:
        return False
    if not re.fullmatch(r'\d+', toks[0]):
        return False
    body = [t.strip('.,') for t in toks[1:]]
    if not any(t in SUF for t in body):
        return False
    name_toks = [t for t in body if t not in SUF and t not in DIR]
    return len(name_toks) >= 1


def fused_split(addr):
    """Return (name_tail, street) when addr = <name fragment> + <complete
    street>, else None. A tail that is only '<digits> <directional>' is a
    legitimate street prefix (e.g. '1842 EAST 3 NOTCH STREET'), not a
    name fragment."""
    toks = _collapse(addr).split(' ')
    for i in range(1, len(toks)):
        if _complete_street(toks[i:]):
            tail = toks[:i]
            alpha = [t.strip('.,') for t in tail
                     if t.strip('.,') not in DIR and not re.fullmatch(r'\d+', t.strip('.,'))]
            if not alpha and tail and tail[-1].strip('.,') in DIR:
                return None
            return ' '.join(tail), ' '.join(toks[i:])
    return None


# ------------------------------------------------------------------- blocklist
PLACEHOLDER_NAMES = {
    '', 'unknown', 'n/a', 'na', 'none', 'null', 'tbd', 'total', 'subtotal',
    'establishment', 'facility', 'facility name', 'food service', 'name',
    'business name', 'unnamed', 'test', 'restaurant', 'the', '-', '--',
    'see remarks', 'county health department', 'health department',
}


def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == '')


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def result_bearing(p):
    s = p.get('s')
    if _is_num(s) and s >= 0:
        return True
    if not _blank(p.get('disp')):
        return True
    insp = p.get('insp') or []
    if insp:
        # FL-style inspections carry dispositions, AL-style carry scores;
        # either way the place renders results.
        return True
    return False


def has_scored_inspection(p):
    for ins in p.get('insp') or []:
        s = ins.get('s')
        if _is_num(s) and s >= 0:
            return True
        if not _blank(ins.get('disp')):
            return True
    return False


def load_places(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, []
    if isinstance(data, dict):
        return data.get('places', []), data.get('inspections', [])
    raise ValueError('unrecognized dataset shape')


def validate(path):
    places, flat_inspections = load_places(path)
    violations = {k: [] for k in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6')}

    ids = [p.get('id') for p in places]
    id_set = set(ids)
    seen = set()
    for pid in ids:
        if pid in seen:
            violations['G6'].append(str(pid))
        seen.add(pid)

    for p in places:
        pid = str(p.get('id'))
        name = p.get('n')
        addr = p.get('a')
        bearing = result_bearing(p) or has_scored_inspection(p)

        if bearing and _blank(name):
            violations['G1'].append(pid)
        if bearing and _blank(addr):
            violations['G2'].append(pid)

        nname = _collapse(name).lower() if isinstance(name, str) else ''
        if nname in PLACEHOLDER_NAMES or (isinstance(name, str) and name.rstrip().endswith('#')):
            violations['G4'].append(pid)

        if isinstance(addr, str) and addr.strip():
            fs = fused_split(addr)
            if fs is not None:
                violations['G5'].append(pid)

        for ins in p.get('insp') or []:
            ref = ins.get('place_id', ins.get('pid', ins.get('placeId')))
            if ref is not None and str(ref) != pid:
                violations['G3'].append(f'{pid} (embedded insp -> {ref})')

    for ins in flat_inspections:
        ref = ins.get('place_id', ins.get('pid', ins.get('placeId')))
        if ref is not None and str(ref) not in id_set:
            violations['G3'].append(f'inspection {ins.get("id")} -> {ref}')

    return violations, len(places)


CHECKS = {
    'G1': 'result-bearing place with blank name',
    'G2': 'result-bearing place with blank street address',
    'G3': 'inspection referencing a nonexistent / wrong place',
    'G4': 'placeholder / header / truncated (#) place name',
    'G5': 'fused name/street split (name fragment inside street field)',
    'G6': 'duplicate place id',
}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    quiet = '--quiet' in argv
    violations, n = validate(path)
    total = sum(len(v) for v in violations.values())
    if not quiet:
        print(f'dataset: {path}  places: {n}')
        for k in sorted(violations):
            v = violations[k]
            print(f'  {k} {CHECKS[k]}: {len(v)}')
            for item in v:
                print(f'      {item}')
    if total:
        print(f'GATE: FAIL ({total} violations)')
        return 1
    print('GATE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
