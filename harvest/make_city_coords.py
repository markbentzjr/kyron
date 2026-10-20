#!/usr/bin/env python3
"""Build src/main/assets/city_coords.json from the US Census Bureau's
2023 Gazetteer files (public domain) — internal points for every Alabama
place and county, used by GeoFallback for approximate map pins.

Downloads:
  https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip
  https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip

Column indices (tab-separated, verified against the file headers):
  place:   INTPTLAT = 10, INTPTLONG = 11
  counties: INTPTLAT = 8, INTPTLONG = 9
(An earlier version of this script read the water-area columns by mistake;
the sanity asserts below exist so that can never ship again.)
"""
import json, re, sys, os

def norm(s):
    s = s.upper().strip()
    s = re.sub(r'\s+(CITY|TOWN|CDP)$', '', s)
    return re.sub(r'\s+', ' ', s)

def main(place_txt, counties_txt, out_path):
    cities = {}
    for line in open(place_txt, encoding='utf-8', errors='replace'):
        p = line.rstrip('\n').split('\t')
        if len(p) < 12 or p[0].strip() != 'AL':
            continue
        cities.setdefault(norm(p[3]), (float(p[10]), float(p[11])))
    counties = {}
    for line in open(counties_txt, encoding='utf-8', errors='replace'):
        p = line.rstrip('\n').split('\t')
        if len(p) < 10 or p[0].strip() != 'AL':
            continue
        name = re.sub(r'\s+County$', '', p[3].strip())
        counties[name] = (float(p[8]), float(p[9]))
    for k, (la, ln) in list(cities.items()) + list(counties.items()):
        assert 29.9 < la < 35.3 and -88.7 < ln < -84.6, (k, la, ln)
    assert len(counties) == 67, len(counties)
    out = {'cities': {k: [round(v[0], 5), round(v[1], 5)] for k, v in cities.items()},
           'counties': {k: [round(v[0], 5), round(v[1], 5)] for k, v in counties.items()}}
    json.dump(out, open(out_path, 'w'), separators=(',', ':'))
    print(f'wrote {out_path}: {len(cities)} places, {len(counties)} counties')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else
         os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src/main/assets/city_coords.json'))
