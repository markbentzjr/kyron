import os, sys
sys.path.insert(0, os.path.expanduser('~/kyron-build/manual'))
import resolve_deps as R
ROOTS = [
    ('com.google.android.material', 'material', '1.12.0'),
    ('androidx.cardview', 'cardview', '1.0.1'),
    ('androidx.swiperefreshlayout', 'swiperefreshlayout', '1.1.0'),
    ('androidx.viewpager2', 'viewpager2', '1.1.0'),
]
seen, queue = {}, list(ROOTS)
while queue:
    g, a, v = queue.pop(0)
    if (g, a) in seen: continue
    seen[(g, a)] = v
    pom = R.get_pom(g, a, v)
    if pom is None:
        print(f'  NO POM {g}:{a}:{v}'); continue
    deps, parent, _ = R.parse_pom(pom, g, a, v)
    if parent.get('g') and (parent['g'], parent['a']) not in seen:
        queue.append((parent['g'], parent['a'], parent['v']))
    for dg, da, dv in deps:
        if (dg, da) not in seen: queue.append((dg, da, dv))
print('closure:', len(seen))
added = R.download_all(seen)
print('downloaded:', len(added))
for a in added: print('  +', a)
