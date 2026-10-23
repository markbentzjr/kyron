#!/usr/bin/env python3
"""Kyron canary gate (Workstream D, Oct 2026) — wired into build_manual.sh
beside validate_pathdata.py and validate_seed.py.

WHY: validate_seed.py proves the dataset is internally clean, but nothing
proved it was COMPLETE. The Chelsea McDonald's (adph_750e13236c) was in the
seed the whole time, yet three real establishments were silently missing
(JCDH permits whose fused name+street blobs defeat the splitters) and the
current seed builder would silently DROP a fourth (jcdh_22521) that the
shipped seed carries correctly. Cleanliness gates cannot see absence;
canaries can. This gate fails the build when:

  1. any canary record is MISSING from the seed,
  2. a canary's name/city/county no longer match the curated values
     (identity drift — e.g. a normalizer regression re-splitting a name),
  3. an expected="pinned" canary has lost its coordinates (pin regression),
  4. an expected="accounted" canary lacks its signed-off reason in
     canaries.json (an undocumented exception), or
  5. any data-level SEARCH canary fails: the listed query, run through the
     FIX5 search semantics (apostrophe-normalized FTS index + query, the
     staged FIX5 construction), does not resolve to the expected place id.

The search simulation uses SQLite FTS4 with the stock tokenizer — the same
engine the app queries — over the seed being built. It validates the DATA
supports the canary queries under the fixed search layer; the Kotlin
SearchCanaryTest validates the app code itself.

Usage: canary_gate.py [seed.json] [canaries.json]
Defaults: the production asset + the canaries.json beside this script.
Exit 0 = PASS, 1 = FAIL (every failure printed, canary ids named).
NEVER edit canaries.json to make a failing build pass; fix the dataset or
the normalizer, or re-curate with a documented reason.
"""
import json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SEED = os.path.join(HERE, '..', 'app', 'src', 'main', 'assets', 'places_seed_geocoded.json')
DEFAULT_CANARIES = os.path.join(HERE, 'canaries.json')


def strip_apos(s):
    return s.replace("'", '').replace('\u2019', '')


def fts_name(name):
    a = strip_apos(name)
    return name if a == name else f"{name} {a}"


def fts_query(text):
    """The FIX5 ftsIds construction: apostrophes stripped, whitespace-split
    tokens, each a quoted prefix phrase, ANDed."""
    toks = [t for t in re.split(r'\s+', strip_apos(text).strip()) if t]
    return ' '.join('"' + t.replace('"', '""') + '"*' for t in toks)


def main(argv):
    seed_path = argv[1] if len(argv) > 1 else DEFAULT_SEED
    can_path = argv[2] if len(argv) > 2 else DEFAULT_CANARIES
    seed = json.load(open(seed_path, encoding='utf-8'))
    doc = json.load(open(can_path, encoding='utf-8'))
    by_id = {p['id']: p for p in seed}
    failures = []

    canaries = doc['canaries']
    n_pinned = n_accounted = 0
    for c in canaries:
        rec = by_id.get(c['id'])
        if rec is None:
            failures.append(f"{c['id']}: canary record MISSING from seed "
                            f"({c['name']}, {c['city']}, {c['county']} Co.)")
            continue
        if rec['n'].strip() != c['name'].strip():
            failures.append(f"{c['id']}: name drift — canary '{c['name']}' vs seed '{rec['n']}'")
        if rec['c'].strip().lower() != c['city'].strip().lower():
            failures.append(f"{c['id']}: city drift — canary '{c['city']}' vs seed '{rec['c']}'")
        if rec['ct'].strip().lower() != c['county'].strip().lower():
            failures.append(f"{c['id']}: county drift — canary '{c['county']}' vs seed '{rec['ct']}'")
        if c['expected'] == 'pinned':
            n_pinned += 1
            if rec.get('lat') is None or rec.get('lng') is None:
                failures.append(f"{c['id']}: PIN REGRESSION — expected pinned, seed lat/lng are null "
                                f"({c['name']}, {c['city']})")
        elif c['expected'] == 'accounted':
            n_accounted += 1
            if not (c.get('reason') or '').strip():
                failures.append(f"{c['id']}: expected='accounted' but canaries.json carries no "
                                f"signed-off reason ({c['name']}, {c['city']})")
        else:
            failures.append(f"{c['id']}: unknown expected status '{c['expected']}'")

    # Data-level search canaries under the FIX5 semantics.
    n_search = 0
    try:
        con = sqlite3.connect(':memory:')
        con.execute("CREATE VIRTUAL TABLE f USING fts4(place_id UNINDEXED, name, city, address, zip, county)")
        for p in seed:
            con.execute("INSERT INTO f VALUES (?,?,?,?,?,?)",
                        (p['id'], fts_name(p['n']), p['c'], p['a'], p['z'], p['ct']))
        for sc in doc.get('search_canaries', []):
            n_search += 1
            try:
                got = {r[0] for r in con.execute("SELECT place_id FROM f WHERE f MATCH ?",
                                                 (fts_query(sc['query']),))}
            except sqlite3.Error as e:
                failures.append(f"search canary '{sc['query']}': FTS error {e}")
                continue
            if sc['expect_id'] not in got:
                failures.append(f"search canary '{sc['query']}': does not resolve to "
                                f"{sc['expect_id']} under the FIX5 search semantics")
    except sqlite3.Error as e:
        failures.append(f"search canary setup failed (FTS4 unavailable?): {e}")

    print(f"canary gate: {len(canaries)} canaries ({n_pinned} pinned, {n_accounted} accounted) "
          f"+ {n_search} search canaries over {len(seed)} seed places")
    if failures:
        print(f"GATE: FAIL ({len(failures)} failures)")
        for f in failures:
            print("  FAIL:", f)
        return 1
    print("GATE: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
