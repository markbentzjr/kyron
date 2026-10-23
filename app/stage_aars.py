#!/usr/bin/env python3
"""Stage fully-extracted AARs for the Kyron manual build.

Rebuilds ~/kyron-build/manual/work/aars from ~/kyron-build/manual/deps so each
staged AAR dir carries the COMPLETE upstream content set: AndroidManifest.xml,
res/**, assets/**, classes.jar and libs/**.

Root cause this fixes: earlier one-off repair scripts copied only classes.jar
out of some artifacts, silently dropping res/ and real manifests. That broke
library R-class generation in aapt2 link (e.g. missing
androidx.lifecycle.runtime.R$id in lifecycle-runtime 2.8.4, whose res/
declares the id view_tree_lifecycle_owner) -> NoClassDefFoundError crash at
AppCompatActivity.setContentView on the first launch.

Behavior:
  * Every artifact in the resolved closure is classified:
      - pom metadata (parent/BOM) -> skipped, no staging
      - jar-only artifact         -> kept as deps file, no staging dir needed
      - Android AAR               -> staged one dir per artifact, fully
                                     extracted from the first content-bearing
                                     upstream variant of [base, -android]
      - empty marker AAR          -> still staged (manifest + res if any)
  * After staging, any work/aars dir that no longer corresponds to a staged
    artifact is REMOVED (stale dirs from pruned artifacts).
  * Idempotent: re-running produces the same dir set.
"""
import io, os, re, shutil, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_deps as rd  # same dir; provides collect()/fetch()/artifact_file()

DEPS = rd.DEPS
AARS = os.path.expanduser('~/kyron-build/manual/work/aars')

# artifactIds whose upstream is pom metadata (never has files)
POM_ONLY = {
    ('com.google.guava', 'guava-parent'), ('com.google.errorprone', 'error_prone_parent'),
    ('org.sonatype.oss', 'oss-parent'), ('org.sonatype.oss', 'oss-parent-7'),
}
# artifactIds known to be jar-file only on every repo we use (kept as deps .jar)
JAR_ONLY_HINTS = {
    'jsoup', 'kotlin-stdlib', 'kotlin-stdlib-common', 'kotlin-stdlib-jdk7', 'kotlin-stdlib-jdk8',
    'kotlinx-coroutines-core', 'kotlinx-coroutines-core-jvm', 'kotlinx-coroutines-android',
    'kotlinx-coroutines-guava', 'atomicfu', 'atomicfu-jvm', 'okhttp', 'okio', 'okio-jvm',
    'okhttp-urlconnection', 'annotations', 'error_prone_annotations', 'annotation-jvm',
    'collection-jvm', 'lifecycle-common-jvm', 'concurrent-futures', 'constraintlayout-core',
    'paging-common', 'listenablefuture', 'resourceinspection-annotation', 'room-common',
}

def z_class_count(z):
    if z is None or 'classes.jar' not in z.namelist():
        return 0
    inner = zipfile.ZipFile(io.BytesIO(z.read('classes.jar')))
    return sum(1 for n in inner.namelist() if n.endswith('.class'))

def z_has(j):
    return z_class_count(j[0]) > 0

def stage_dir_from_zip(z, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    for n in [x for x in z.namelist() if not x.endswith('/')]:
        if n == 'AndroidManifest.xml' or n.startswith(('res/', 'assets/', 'libs/')) or n == 'classes.jar':
            out = os.path.join(dest, n.replace('/', os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'wb') as f:
                f.write(z.read(n))

def stage_artifact(g, a, v):
    """Stage one artifact; returns (staged_dir_name_or_None, action)."""
    if (g, a) in POM_ONLY or a in JAR_ONLY_HINTS:
        return None, f'skip ({"pom metadata" if (g, a) in POM_ONLY else "jar-only: stays as deps file"})'
    if '[' in v or '$' in v or '!' in v:
        return None, 'skip (unresolved dynamic version placeholder from a pom)'
    deps_file = None
    for f in os.listdir(DEPS):
        if f.startswith(a + '-') and (f.endswith('.jar') or f.endswith('.aar')):
            deps_file = f
    for art in (a, a + '-android'):
        data, ext = rd.artifact_file(g, art, v, 'aar')
        if not data:
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except Exception:
            continue
        cc = z_class_count(z)
        chosen = art if cc > 0 else (art if 'AndroidManifest.xml' in z.namelist() else None)
        if chosen is None:
            continue
        dest = os.path.join(AARS, f'{chosen}-{v}')
        stage_dir_from_zip(z, dest)
        return f'{chosen}-{v}', f'staged ({cc} classes, res={"yes" if any(n.startswith("res/") for n in z.namelist()) else "no"})'
    if deps_file and os.path.isfile(os.path.join(DEPS, deps_file)):
        return None, f'skip (no upstream aar; handled by deps file {deps_file})'
    return None, 'no upstream aar found and no deps file (verify manually)'

def normalize_staged(staged_names):
    """Recreate the documented styleable-collision resolution from
    docs/Kyron-Dev-Update-2026-10-13-2.1.md (also used by
    tools/build_release_app.py):

      1. appcompat + material both declare <declare-styleable
         name="SearchView">. Neither Android widget is used by Kyron.
         Keep material's copy; unwrap appcompat's (attr definitions are
         preserved; android:* refs in the attr list are dropped because they
         cannot be promoted to global attrs).
      2. constraintlayout + material both declare <declare-styleable
         name="Carousel">. Keep material's copy; rename constraintlayout's
         to ConstraintCarousel.
    """
    def read(p):
        with open(p, encoding='utf-8') as f:
            return f.read()

    def write(p, c):
        with open(p, 'w', encoding='utf-8') as f:
            f.write(c)

    ac = os.path.join(AARS, 'appcompat-1.7.0', 'res', 'values', 'values.xml')
    if 'appcompat-1.7.0' in staged_names and os.path.isfile(ac):
        c = read(ac)
        def _unwrap(m):
            inner = m.group(1)
            return re.sub(r'<attr\s+name="android:[^"]+"\s*/>', '', inner)
        c2 = re.sub(r'<declare-styleable\s+name="SearchView">(.*?)</declare-styleable>',
                    _unwrap, c, flags=re.DOTALL)
        if c2 != c:
            write(ac, c2)
            print('  normalized: appcompat SearchView styleable unwrapped (material\'s wins; documented precedent)')
    cl = os.path.join(AARS, 'constraintlayout-2.1.4', 'res', 'values', 'values.xml')
    if 'constraintlayout-2.1.4' in staged_names and os.path.isfile(cl):
        c = read(cl)
        c2 = c.replace('name="Carousel"', 'name="ConstraintCarousel"')
        if c2 != c:
            write(cl, c2)
            print('  normalized: constraintlayout Carousel renamed to ConstraintCarousel (material\'s wins; documented precedent)')


def main():
    print('resolving closure of deps ...')
    arts = rd.collect()
    print(f'closure size: {len(arts)}')
    expected = set()
    skipped = []
    failed = []
    for (g, a), v in sorted(arts.items()):
        folder, act = stage_artifact(g, a, v)
        if folder:
            expected.add(folder)
        elif act.startswith(('skip',)):
            skipped.append(f'{g}:{a}:{v} {act}')
        elif act.startswith('staged'):
            # empty/selective marker, dir issued but no classes: still expected
            pass
        else:
            failed.append(f'{g}:{a}:{v} -> {act}')
    # wipe any dir we did not just stage (stale legacy dirs)
    for d in sorted(os.listdir(AARS)):
        full = os.path.join(AARS, d)
        if os.path.isdir(full) and d not in expected:
            shutil.rmtree(full)
            print(f'  removed stale dir {d}')
    normalize_staged(expected)
    print('\nsummary:')
    print(f'  staged dirs: {len(os.listdir(AARS))}')
    for s in skipped:
        print('  skip:', s)
    for f in failed:
        print('  ISSUE:', f)
    if failed:
        sys.exit(1)
    print('STAGE OK')

if __name__ == '__main__':
    main()
