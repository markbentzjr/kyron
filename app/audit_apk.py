#!/usr/bin/env python3
"""Kyron APK static audit: every type referenced by the dex bytecode must
either be defined in the dex or belong to the Android platform / JDK.
Catches the missing-dependency class of launch crashes (Kyron 2.0 saga).
Usage: audit_apk.py <apk>"""
import re, subprocess, sys, zipfile, os

APK = sys.argv[1]
def _find_build_tools():
    env = os.environ.get('KYRON_BUILD_TOOLS')
    if env: return env
    hosts = [
        os.path.expanduser('~/kyron-build/android-sdk/build-tools'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk', 'build-tools'),
    ]
    for base in hosts:
        if base and os.path.isdir(base):
            versions = sorted(os.listdir(base), reverse=True)
            for v in versions:
                if os.path.isfile(os.path.join(base, v, 'dexdump.exe' if os.name == 'nt' else 'dexdump')):
                    return os.path.join(base, v)
    raise SystemExit('build-tools with dexdump not found; set KYRON_BUILD_TOOLS')
BT = _find_build_tools()
z = zipfile.ZipFile(APK)
names = z.namelist()
dexes = [n for n in names if re.fullmatch(r'classes\d*\.dex', n)]
print(f'dex files: {dexes}')
defined, refs = set(), set()
ref_by_class = {}   # referenced type -> set of classes that reference it
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
        if m:
            defined.add(m.group(1))
            cur_class = m.group(1)
        elif cur_class is not None:
            for t in TYPE.findall(line):
                refs.add(t)
                ref_by_class.setdefault(t, set()).add(cur_class)
PLATFORM = ('Ljava/', 'Ljavax/', 'Landroid/', 'Landroidx/annotation/',
            'Ldalvik/', 'Lorg/xml/', 'Lorg/w3c/', 'Lorg/json/JSONObject',
            'Lorg/json/JSONArray', 'Lorg/json/JSONException',
            # Provided by the Android runtime itself (on the boot classpath):
            # org.xmlpull is the platform's pull-parser API and org.kxml2 is
            # its implementation (both resolvable on-device even though
            # android.jar / compile SDK hides them, so dexdump sees none).
            'Lorg/xmlpull/', 'Lorg/kxml2/',
            # ART exposes a sun.misc stub (Unsafe/Signal...); the only referrer
            # here is coroutines' debug/AgentPremain code, never loaded on
            # Android.
            'Lsun/',
            # OkHttp 4.x references these inside its add-on platform probes;
            # the probes run only on the JVM, never on Android (try/catch'd),
            # so the classes never resolve at runtime. Exempt + documented.
            'Lorg/bouncycastle/', 'Lorg/conscrypt/')
missing = sorted(r for r in refs - defined
                 if r.count('/') >= 1
                 and not r.startswith(PLATFORM)
                 and not r.startswith('Lorg/json/')
                 and '$' not in r.rsplit('/', 1)[-1].replace('R$', ''))
# inner classes of defined classes count as defined via their outer check below
missing = [m for m in missing if m.split('$')[0] + ';' not in defined or m not in defined and '$' in m and (m.split('$')[0] + ';') not in defined]
missing = [m for m in missing if not (('$' in m) and (m.split('$')[0] + ';') in defined)]
print(f'defined classes: {len(defined)}')
print(f'referenced types: {len(refs)}')
print(f'MISSING (referenced, not defined, non-platform): {len(missing)}')
for m in missing[:40]:
    print('  MISSING', m)
    for c in sorted(ref_by_class.get(m, ())):
        print(f'    referenced by {c}')
r = [c for c in defined if '/R;' in c or '/R$' in c]
print(f'R classes: {len(r)} | app R: {"Lcom/kyronapp/kyron/R;" in defined} | material R: {"Lcom/google/android/material/R;" in defined} | appcompat R: {"Landroidx/appcompat/R;" in defined}')
print('coroutines services:', [n for n in names if 'META-INF/services' in n])
print('seed asset:', [n for n in names if n.startswith('assets/')])
sys.exit(1 if missing else 0)
