#!/usr/bin/env python3
"""Kyron APK static audit: every type referenced by the dex bytecode must
either be defined in the dex or belong to the Android platform / JDK.
Catches the missing-dependency class of launch crashes (Kyron 2.0 saga).
Usage: audit_apk.py <apk>"""
import re, subprocess, sys, zipfile, os

APK = sys.argv[1]
BT = os.path.expanduser('~/kyron-build/android-sdk/build-tools/34.0.0')
z = zipfile.ZipFile(APK)
names = z.namelist()
dexes = [n for n in names if re.fullmatch(r'classes\d*\.dex', n)]
print(f'dex files: {dexes}')
defined, refs = set(), set()
TYPE = re.compile(r'L[a-zA-Z0-9_/$]+;')
import tempfile
for d in dexes:
    with tempfile.NamedTemporaryFile(suffix='.dex', delete=False) as f:
        f.write(z.read(d)); path = f.name
    out = subprocess.run([f'{BT}/dexdump', path], capture_output=True).stdout.decode('utf-8', 'replace')
    os.unlink(path)
    cur_class = None
    for line in out.splitlines():
        m = re.search(r"Class descriptor\s+:\s+'(L[^']+;)'", line)
        if m: defined.add(m.group(1))
        for t in TYPE.findall(line):
            refs.add(t)
PLATFORM = ('Ljava/', 'Ljavax/', 'Landroid/', 'Landroidx/annotation/',
            'Ldalvik/', 'Lorg/xml/', 'Lorg/w3c/', 'Lorg/json/JSONObject',
            'Lorg/json/JSONArray', 'Lorg/json/JSONException')
missing = sorted(r for r in refs - defined
                 if not r.startswith(PLATFORM)
                 and not r.startswith('Lorg/json/')
                 and '$' not in r.rsplit('/', 1)[-1].replace('R$', ''))
# inner classes of defined classes count as defined via their outer check below
missing = [m for m in missing if m.split('$')[0] + ';' not in defined or m not in defined and '$' in m and (m.split('$')[0] + ';') not in defined]
missing = [m for m in missing if not (('$' in m) and (m.split('$')[0] + ';') in defined)]
print(f'defined classes: {len(defined)}')
print(f'referenced types: {len(refs)}')
print(f'MISSING (referenced, not defined, non-platform): {len(missing)}')
for m in missing[:40]: print('  MISSING', m)
r = [c for c in defined if '/R;' in c or '/R$' in c]
print(f'R classes: {len(r)} | app R: {"Lcom/kyronapp/kyron/R;" in defined} | material R: {"Lcom/google/android/material/R;" in defined} | appcompat R: {"Landroidx/appcompat/R;" in defined}')
print('coroutines services:', [n for n in names if 'META-INF/services' in n])
print('seed asset:', [n for n in names if n.startswith('assets/')])
sys.exit(1 if missing else 0)
