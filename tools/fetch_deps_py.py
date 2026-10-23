import os, urllib.request

DEPS = os.path.expanduser('~/kyron-build/manual/deps')
os.makedirs(DEPS, exist_ok=True)

G = 'https://dl.google.com/dl/android/maven2'
C = 'https://repo1.maven.org/maven2'

ITEMS = [
    (C, 'org.jetbrains.kotlin', 'kotlin-stdlib', '2.0.20', 'jar'),
    (C, 'org.jetbrains.kotlinx', 'kotlinx-coroutines-android', '1.8.1', 'jar'),
    (C, 'org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm', '1.8.1', 'jar'),
    (C, 'com.squareup.okhttp3', 'okhttp', '4.12.0', 'jar'),
    (C, 'com.squareup.okio', 'okio-jvm', '3.6.0', 'jar'),
    (C, 'org.jsoup', 'jsoup', '1.18.1', 'jar'),
    (C, 'org.osmdroid', 'osmdroid-android', '6.1.18', 'aar'),
    (C, 'com.google.guava', 'listenablefuture', '9999.0-empty-to-avoid-conflict-with-guava', 'jar'),

    (G, 'androidx.core', 'core', '1.13.1', 'aar'),
    (G, 'androidx.core', 'core-ktx', '1.13.1', 'aar'),
    (G, 'androidx.appcompat', 'appcompat', '1.7.0', 'aar'),
    (G, 'androidx.appcompat', 'appcompat-resources', '1.7.0', 'aar'),
    (G, 'androidx.fragment', 'fragment', '1.8.3', 'aar'),
    (G, 'androidx.activity', 'activity', '1.9.2', 'aar'),
    (G, 'androidx.activity', 'activity-ktx', '1.9.2', 'aar'),
    (G, 'androidx.lifecycle', 'lifecycle-runtime', '2.8.4', 'aar'),
    (G, 'androidx.lifecycle', 'lifecycle-common', '2.8.4', 'jar'),
    (G, 'androidx.lifecycle', 'lifecycle-livedata-core', '2.8.4', 'aar'),
    (G, 'androidx.lifecycle', 'lifecycle-viewmodel', '2.8.4', 'aar'),
    (G, 'androidx.lifecycle', 'lifecycle-viewmodel-savedstate', '2.8.4', 'aar'),
    (G, 'androidx.lifecycle', 'lifecycle-process', '2.8.4', 'aar'),
    (G, 'androidx.savedstate', 'savedstate', '1.2.1', 'aar'),
    (G, 'androidx.savedstate', 'savedstate-ktx', '1.2.1', 'aar'),
    (G, 'androidx.annotation', 'annotation', '1.8.2', 'jar'),
    (G, 'androidx.annotation', 'annotation-experimental', '1.4.1', 'aar'),
    (G, 'androidx.collection', 'collection', '1.4.4', 'jar'),
    (G, 'androidx.collection', 'collection-ktx', '1.4.4', 'jar'),
    (G, 'androidx.recyclerview', 'recyclerview', '1.3.2', 'aar'),
    (G, 'androidx.customview', 'customview', '1.1.0', 'aar'),
    (G, 'androidx.cursoradapter', 'cursoradapter', '1.0.0', 'aar'),
    (G, 'androidx.drawerlayout', 'drawerlayout', '1.2.0', 'aar'),
    (G, 'androidx.vectordrawable', 'vectordrawable', '1.1.0', 'aar'),
    (G, 'androidx.vectordrawable', 'vectordrawable-animated', '1.1.0', 'aar'),
    (G, 'androidx.emoji2', 'emoji2', '1.4.0', 'aar'),
    (G, 'androidx.emoji2', 'emoji2-views-helper', '1.4.0', 'aar'),
    (G, 'androidx.resourceinspection', 'resourceinspection-annotation', '1.0.1', 'jar'),
    (G, 'androidx.work', 'work-runtime', '2.9.0', 'aar'),
    (G, 'androidx.work', 'work-runtime-ktx', '2.9.0', 'aar'),
    (G, 'androidx.room', 'room-runtime', '2.6.1', 'aar'),
    (G, 'androidx.room', 'room-common', '2.6.1', 'jar'),
    (G, 'androidx.sqlite', 'sqlite', '2.4.0', 'aar'),
    (G, 'androidx.sqlite', 'sqlite-framework', '2.4.0', 'aar'),
    (G, 'androidx.startup', 'startup-runtime', '1.1.1', 'aar'),
    (G, 'androidx.tracing', 'tracing', '1.2.0', 'aar'),
    (G, 'androidx.concurrent', 'concurrent-futures', '1.2.0', 'jar'),
    (G, 'androidx.profileinstaller', 'profileinstaller', '1.3.1', 'aar'),
    (G, 'androidx.interpolator', 'interpolator', '1.0.0', 'aar'),
    (G, 'androidx.versionedparcelable', 'versionedparcelable', '1.1.1', 'aar'),
    (G, 'androidx.arch.core', 'core-common', '2.2.0', 'jar'),
    (G, 'androidx.arch.core', 'core-runtime', '2.2.0', 'aar'),
    (G, 'com.google.android.material', 'material', '1.12.0', 'aar'),
    (G, 'androidx.cardview', 'cardview', '1.0.0', 'aar'),
    (G, 'androidx.swiperefreshlayout', 'swiperefreshlayout', '1.1.0', 'aar'),
    (G, 'androidx.viewpager2', 'viewpager2', '1.1.0', 'aar'),
    (G, 'androidx.constraintlayout', 'constraintlayout', '2.1.4', 'aar'),
    (G, 'androidx.coordinatorlayout', 'coordinatorlayout', '1.2.0', 'aar'),
]

def main():
    for repo, group, artifact, version, ext in ITEMS:
        filename = f"{artifact}-{version}.{ext}"
        dest = os.path.join(DEPS, filename)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"Have {filename}")
            continue
        url = f"{repo}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.{ext}"
        print(f"Fetching {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'KyronDepFetcher/1.0'})
            with urllib.request.urlopen(req) as resp, open(dest, 'wb') as out:
                out.write(resp.read())
            print(f"OK {filename} ({os.path.getsize(dest)} bytes)")
        except Exception as e:
            print(f"FAIL {filename}: {e}")

if __name__ == '__main__':
    main()
