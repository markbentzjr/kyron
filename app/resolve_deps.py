#!/usr/bin/env python3
"""Minimal Maven dependency resolver for the Kyron manual build.

Computes the full compile/runtime transitive closure from POMs (Google Maven
for androidx, Maven Central for the rest) starting from the artifacts already
in deps/, then downloads every artifact file that is missing. Handles the
Kotlin-multiplatform split by probing -android / -jvm variant artifactIds and
keeping the variant that actually contains classes.
"""
import os, re, sys, zipfile
import xml.etree.ElementTree as ET
import requests

DEPS = os.path.expanduser('~/kyron-build/manual/deps')
CACHE = os.path.expanduser('~/kyron-build/maven-cache')
os.makedirs(CACHE, exist_ok=True)
os.makedirs(DEPS, exist_ok=True)

REPOS = [
    'https://dl.google.com/dl/android/maven2',
    'https://repo1.maven.org/maven2',
    'https://plugins.gradle.org/m2',
]
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}
session = requests.Session()
session.headers['User-Agent'] = 'KyronDepResolver/1.0'


def fetch(url):
    cache_name = re.sub(r'[^A-Za-z0-9_.-]', '_', url.replace('https://', ''))
    path = os.path.join(CACHE, cache_name)
    if os.path.exists(path):
        return open(path, 'rb').read()
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60)
            if r.status_code == 200:
                open(path, 'wb').write(r.content)
                return r.content
            return None
        except Exception:
            pass
    return None


def pom_url(g, a, v):
    return f"/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.pom"


def get_pom(g, a, v):
    for repo in REPOS:
        data = fetch(repo + pom_url(g, a, v))
        if data:
            try:
                return ET.fromstring(data)
            except Exception:
                return None
    return None


def text(el, tag):
    c = el.find(f'm:{tag}', NS)
    return c.text.strip() if c is not None and c.text else None


def resolve_props(value, props, depth=0):
    if value is None or depth > 5:
        return value
    def rep(m):
        key = m.group(1)
        return props.get(key, m.group(0))
    out = re.sub(r'\$\{([^}]+)\}', rep, value)
    return resolve_props(out, props, depth + 1) if '${' in out else out


def parse_pom(root, g, a, v):
    props = {'project.version': v, 'pom.version': v, 'project.groupId': g, 'groupId': g}
    pel = root.find('m:properties', NS)
    if pel is not None:
        for child in pel:
            tag = child.tag.split('}')[-1]
            props[tag] = (child.text or '').strip()
    parent = {}
    par = root.find('m:parent', NS)
    if par is not None:
        parent = {'g': text(par, 'groupId'), 'a': text(par, 'artifactId'), 'v': text(par, 'version')}
    # dependencyManagement versions
    managed = {}
    dm = root.find('m:dependencyManagement/m:dependencies', NS)
    if dm is not None:
        for dep in dm.findall('m:dependency', NS):
            dg, da = text(dep, 'groupId'), text(dep, 'artifactId')
            dv = resolve_props(text(dep, 'version'), props)
            if dg and da and dv:
                managed[(dg, da)] = dv
    deps = []
    deps_el = root.find('m:dependencies', NS)
    if deps_el is not None:
        for dep in deps_el.findall('m:dependency', NS):
            dg = resolve_props(text(dep, 'groupId'), props)
            da = resolve_props(text(dep, 'artifactId'), props)
            dv = resolve_props(text(dep, 'version'), props) or managed.get((dg, da))
            scope = text(dep, 'scope') or 'compile'
            optional = text(dep, 'optional') == 'true'
            typ = text(dep, 'type') or 'jar'
            if not dg or not da or not dv:
                continue
            if scope in ('test', 'provided', 'system', 'import') or optional:
                continue
            if typ == 'pom':
                continue
            deps.append((dg, da, dv))
    return deps, parent, props


def collect():
    # roots: artifacts already present in deps/ (filename -> g:a:v guesses)
    roots = []
    group_hints = {
        'okhttp': 'com.squareup.okhttp3', 'okio-jvm': 'com.squareup.okio',
        'jsoup': 'org.jsoup', 'kotlin-stdlib': 'org.jetbrains.kotlin',
        'kotlinx-coroutines-android': 'org.jetbrains.kotlinx',
        'kotlinx-coroutines-core-jvm': 'org.jetbrains.kotlinx',
        'osmdroid-android': 'org.osmdroid', 'json': 'org.json',
        'material': 'com.google.android.material',
    }
    for f in sorted(os.listdir(DEPS)):
        m = re.match(r'^(.+?)-(\d[\w.\-]*)\.(aar|jar)$', f)
        if not m:
            continue
        art, ver = m.group(1), m.group(2)
        if art in group_hints:
            g = group_hints[art]
        elif art.startswith(('lifecycle', 'collection', 'annotation', 'core', 'activity',
                              'fragment', 'appcompat', 'recyclerview', 'work', 'room',
                              'sqlite', 'savedstate', 'startup', 'tracing', 'emoji2',
                              'vectordrawable', 'drawerlayout', 'customview', 'cursoradapter',
                              'interpolator', 'versionedparcelable', 'profileinstaller',
                              'concurrent-futures', 'listenablefuture', 'resourceinspection')):
            base = art.split('-')[0]
            g = {'lifecycle': 'androidx.lifecycle', 'collection': 'androidx.collection',
                 'annotation': 'androidx.annotation'}.get(base, f'androidx.{base}')
            if art.startswith('core'):
                g = 'androidx.core'
            if art.startswith('work'):
                g = 'androidx.work'
            if art.startswith('room'):
                g = 'androidx.room'
            if art.startswith('sqlite'):
                g = 'androidx.sqlite'
            if art.startswith('emoji2'):
                g = 'androidx.emoji2'
            if art.startswith('concurrent'):
                g = 'androidx.concurrent'
            if art.startswith('listenablefuture'):
                g = 'com.google.guava'
        else:
            g = 'androidx.' + art.split('-')[0]
        roots.append((g, art, ver))
    seen = {}
    queue = list(roots)
    while queue:
        g, a, v = queue.pop(0)
        if (g, a) in seen:
            continue
        seen[(g, a)] = v
        pom = get_pom(g, a, v)
        if pom is None:
            print(f'  NO POM {g}:{a}:{v}')
            continue
        deps, parent, _ = parse_pom(pom, g, a, v)
        if parent.get('g') and (parent['g'], parent['a']) not in seen:
            queue.append((parent['g'], parent['a'], parent['v']))
        for dg, da, dv in deps:
            if (dg, da) not in seen:
                queue.append((dg, da, dv))
    return seen


def class_count(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if path.endswith('.aar'):
                if 'classes.jar' not in names:
                    return 0
                import io
                inner = zipfile.ZipFile(io.BytesIO(z.read('classes.jar')))
                return sum(1 for n in inner.namelist() if n.endswith('.class'))
            return sum(1 for n in names if n.endswith('.class'))
    except Exception:
        return -1


def artifact_file(g, a, v, ext):
    for repo in REPOS:
        url = f"{repo}/{g.replace('.', '/')}/{a}/{v}/{a}-{v}.{ext}"
        data = fetch(url)
        if data:
            return data, ext
    return None, None


def download_all(artifacts):
    have = set(os.listdir(DEPS))
    added = []
    for (g, a), v in sorted(artifacts.items()):
        candidates = [(a, 'aar'), (a + '-android', 'aar'), (a, 'jar'), (a + '-jvm', 'jar')]
        got = False
        for art, ext in candidates:
            fname = f'{art}-{v}.{ext}'
            if fname in have:
                # present; but check it is not an empty KMP stub for the base artifact
                if art == a and class_count(os.path.join(DEPS, fname)) == 0:
                    continue
                got = True
                break
            data, _ = artifact_file(g, art, v, ext)
            if data:
                path = os.path.join(DEPS, fname)
                open(path, 'wb').write(data)
                cc = class_count(path)
                if cc == 0 and art == a:
                    # empty stub (KMP metadata) — keep probing variants
                    os.remove(path)
                    continue
                have.add(fname)
                added.append(f'{fname} ({cc} classes)')
                got = True
                break
        if not got:
            print(f'  MISSING FILE {g}:{a}:{v}')
    return added


if __name__ == '__main__':
    print('resolving closure...')
    arts = collect()
    print(f'closure size: {len(arts)} artifacts')
    added = download_all(arts)
    print(f'downloaded {len(added)} new files:')
    for line in added:
        print('  +', line)
