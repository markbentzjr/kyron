#!/usr/bin/env python3
"""Fetch Robolectric + JUnit + android-all for the Kyron launch test."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_deps as R

R.DEPS = os.path.expanduser('~/kyron-build/test/deps')
os.makedirs(R.DEPS, exist_ok=True)

ROOTS = [
    ('org.robolectric', 'robolectric', '4.14.1'),
    ('junit', 'junit', '4.13.2'),
]
seen = {}
queue = list(ROOTS)
while queue:
    g, a, v = queue.pop(0)
    if (g, a) in seen:
        continue
    seen[(g, a)] = v
    pom = R.get_pom(g, a, v)
    if pom is None:
        print(f'  NO POM {g}:{a}:{v}')
        continue
    deps, parent, _ = R.parse_pom(pom, g, a, v)
    if parent.get('g') and (parent['g'], parent['a']) not in seen:
        queue.append((parent['g'], parent['a'], parent['v']))
    for dg, da, dv in deps:
        if (dg, da) not in seen:
            queue.append((dg, da, dv))
print('closure:', len(seen))
added = R.download_all(seen)
print('downloaded:', len(added))
for a in added:
    print('  +', a)

# android-all-instrumented for SDK 34 (API 14): robolectric 4.14 uses this build
import requests
url = ('https://repo1.maven.org/maven2/org/robolectric/android-all-instrumented/'
       '14-robolectric-10818077-i6/android-all-instrumented-14-robolectric-10818077-i6.jar')
dest = os.path.expanduser('~/kyron-build/test/android-all/android-all-instrumented-14-robolectric-10818077-i6.jar')
os.makedirs(os.path.dirname(dest), exist_ok=True)
if not os.path.exists(dest):
    print('downloading android-all...')
    r = requests.get(url, timeout=600, headers={'User-Agent': 'KyronTest/1.0'})
    print('android-all HTTP', r.status_code, len(r.content), 'bytes')
    if r.status_code == 200:
        open(dest, 'wb').write(r.content)
print('done')
