#!/bin/bash
# Kyron Robolectric rig, Windows-local (Git-for-Windows bash).
#
# Windows adaptation of run_national.sh — the sandbox-canonical script's
# paths don't exist here. Differences, explicitly:
#   - APK/classes come from THIS repo's build outputs produced by
#     app/build_windows.sh (repo tree, not $HOME/kyron-build/manual copy).
#   - android.jar: the machine's local Android SDK (platform android-37.0)
#     instead of the sandbox android-34 — tests compile against it but run
#     under Robolectric's own android-all (API level still pinned by
#     @Config(sdk=34) in the tests).
#   - The tests hard-code @Config(manifest=.../home/hatch/kyron-build/test/
#     robo-apk/AndroidManifest.xml): on Windows the JVM resolves that
#     against the current drive, so the script mirrors the unzipped APK
#     into C:\home\hatch\kyron-build\test\robo-apk and the constant works
#     unmodified — no per-file @Config rewrites.
#   - Classpath strings are converted with cygpath -wp (Windows java needs
#     C:\... ';' lists; MSYS argument conversion is unreliable for lists).
#
# Usage: bash tools/robolectric-test/run_national_windows.sh [TestNames...]
#        default: NationalCoverageTest  (plus always SortingModelTest/
#        AlertLogicTest when present in the rig src dir)
set -e
set -o pipefail
B=$HOME/kyron-build
T=$B/test
MREPO=$(pwd)
APK=$MREPO/app/Kyron-2.0-windows-build.apk
CLASSES=$B/work/classes.jar
# $LOCALAPPDATA arrives in Windows form (C:\...) — the ':' would corrupt a
# POSIX ':'-joined classpath (the bare-'C' entry bug), so convert it FIRST.
LA_POSIX=$(cygpath -u "$LOCALAPPDATA")
AJAR=$LA_POSIX/Android/Sdk/platforms/android-37.0/android.jar
export PATH=$B/jdk17/bin:$B/kotlinc/bin:$PATH
export JAVA_HOME=$B/jdk17
KOTLINC=$B/kotlinc/bin/kotlinc

[ -f "$APK" ] || { echo "FAIL: $APK missing — run ./app/build_windows.sh first"; exit 1; }
[ -f "$LA_POSIX/Android/Sdk/platforms/android-37.0/android.jar" ] || {
  echo "FAIL: android-37 jar missing at $LA_POSIX"; exit 1; }

echo "== stage robo-apk =="
rm -rf $T/robo-apk && mkdir -p $T/robo-apk
# NOTE: git-bash's unzip mangles wildcard args in this environment, so the
# APK is extracted in FULL (includes classes*.dex, ~10 MB extra — harmless).
( cd $T/robo-apk && unzip -o -q "$APK" )
ls $T/robo-apk | head -3
# Robolectric parses the manifest with a TEXT XML parser; the APK's copy is
# binary AXML ("Content is not allowed in prolog"). Stage the repo's text
# manifest instead — Robolectric only reads metadata (package/sdk/apps) from it.
cp "$MREPO/app/src/main/AndroidManifest.xml" $T/robo-apk/AndroidManifest.xml

# Mirror for the hard-coded @Config manifest path (see header).
MIRROR=/c/home/hatch/kyron-build/test/robo-apk
if ! mkdir -p ${MIRROR%/*} 2>/dev/null; then
  echo "FAIL: cannot create C:\\home\\hatch mirror (need write access to C:\\)"
  exit 1
fi
rm -rf "$MIRROR" && cp -r $T/robo-apk "$MIRROR"

echo "== stage test sources =="
mkdir -p $T/src $T/classes
rm -rf $T/classes/*
for f in TestKyronApplication.kt "${TEST_SRC:-NationalCoverageTest.kt}"; do
  cp tools/robolectric-test/$f $T/src/ 2>/dev/null || { echo "FAIL: no $f in repo"; exit 1; }
done
if ls tools/robolectric-test/SortingModelTest.kt tools/robolectric-test/AlertLogicTest.kt >/dev/null 2>&1; then
  cp tools/robolectric-test/SortingModelTest.kt tools/robolectric-test/AlertLogicTest.kt $T/src/
fi

APP_DEPS=$(find $B/manual/work/aars -name 'classes.jar' | tr '\n' ':')$(find $B/manual/work/aars -path '*/libs/*.jar' | tr '\n' ':')$(find $B/manual/deps -name '*.jar' | grep -v stubs | tr '\n' ':')
TEST_DEPS=$(find $T/deps -name '*.jar' | tr '\n' ':')
# POSIX join everywhere, ONE cygpath conversion to a Windows ';' list.
WCP="$T/classes:$CLASSES:$T/robo-apk:$APP_DEPS$TEST_DEPS$AJAR"

echo "== compile tests =="
TCP=$(cygpath -wp "$WCP")
"$KOTLINC" -cp "$TCP" -d "$(cygpath -w $T/classes)" $T/src/*.kt 2>&1 \
  | grep -vE "^warning:" | head -n 40 || true
[ -n "$(ls $T/classes 2>/dev/null)" ] || { echo "KOTLINC FAILED (no classes produced)"; exit 1; }

echo "== run =="
ANDROID_DIR=$(cygpath -w $T/android-all)
REG_FILE=$(cygpath -w $T/robo-apk/assets/coverage/us_national_registry.json)
RC=0
for CLS in "$@"; do
  echo "---- $CLS ----"
  java -Xmx1200m \
    -Drobolectric.offline=true \
    -Drobolectric.dependency.dir="$ANDROID_DIR" \
    -Dkyron.registry.file="$REG_FILE" \
    -cp "$TCP" \
    org.junit.runner.JUnitCore "com.kyronapp.kyron.$CLS" || RC=1
done
exit $RC
