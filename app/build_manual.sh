#!/bin/bash
# Kyron manual build pipeline (no Gradle — its daemon needs inter-process TCP
# that this sandbox intercepts). Every step below is a single process.
set -e
set -o pipefail
KB=$HOME/kyron-build
M=$KB/manual
W=$M/work
# Single source of build metadata (plain KEY=VALUE lines), shared with
# build_windows.sh and tools/build_release_app.py.
source $M/app/version.properties
SDK=$KB/android-sdk
BT=$SDK/build-tools/34.0.0
AJAR=$SDK/platforms/android-34/android.jar
JAVA=$KB/jdk17/bin/java
JAVAC=$KB/jdk17/bin/javac
export TMPDIR=$KB/tmp
export PATH=$KB/jdk17/bin:$PATH
mkdir -p $W $KB/tmp

step() { echo; echo "=== $1 ==="; }

step "1/8 merge manifests"
python3 $M/merge_manifest.py $M/src/main/AndroidManifest.xml $W/aars $W/merged/AndroidManifest.xml

step "2/8 collect resource packages"
PKGS=$(python3 - <<'PY'
import os, xml.etree.ElementTree as ET
pkgs = []
base = os.path.expanduser('~/kyron-build/manual/work/aars')
for name in sorted(os.listdir(base)):
    mp = os.path.join(base, name, 'AndroidManifest.xml')
    if os.path.exists(mp):
        try:
            pkg = ET.parse(mp).getroot().get('package')
            resdir = os.path.join(base, name, 'res')
            if pkg and os.path.isdir(resdir) and os.listdir(resdir):
                pkgs.append(pkg)
        except Exception:
            pass
print(':'.join(pkgs))
PY
)
echo "extra packages: $PKGS"

step "gate: validate vector pathData"
# aapt2 never validates pathData arity, but android.util.PathParser parses
# it at runtime during inflation -- a malformed path (e.g. an S command with
# 10 floats) compiles clean and crashes the app on device at first frame
# (FIX2 device crash, Oct 14 2026). This gate fails the build instead.
if ! python3 $M/tools/validate_pathdata.py $M/src/main/res; then
  echo "BUILD FAILED: malformed vector pathData above (file + segment named)."
  echo "Fix the path to its canonical source; do not bypass this gate."
  exit 1
fi

step "gate: validate seed dataset"
# Workstream B gate (Oct 2026): a score must never ship unattached to a
# named place at an address. The pre-gate seed failed with 88 violations
# (2 scored places with no street address at all, 58 JCDH fused name/street
# splits, 28 placeholder/truncated names) -- it took a user report ("2
# scores that are not to any restaurant") to surface them. This gate fails
# the build, naming every violating place id, if the dataset regresses.
if ! python3 $M/tools/validate_seed.py $M/src/main/assets/places_seed_geocoded.json; then
  echo "BUILD FAILED: seed dataset violations above (place ids named)."
  echo "Fix the dataset at the harvest/normalizer level; do not bypass this gate."
  exit 1
fi

step "gate: canary completeness (Workstream D)"
# validate_seed proves the dataset is CLEAN; this gate proves it is COMPLETE.
# 134 curated canaries (2+ well-known establishments per county, incl. the
# Chelsea McDonald's adph_750e13236c) must be present with un-drifted
# name/city/county; expected=pinned canaries must still carry coordinates
# (pin regression); expected=accounted canaries must carry their signed-off
# reason in tools/canaries.json; and 6 data-level search canaries must
# resolve under the FIX5 search semantics. A seed rebuild that silently
# drops an establishment (e.g. jcdh_22521, whose fused JCDH blob the current
# splitter rejects) fails HERE, not on a user's phone. Never edit
# canaries.json to make a build pass; fix the dataset/normalizer.
if ! python3 $M/tools/canary_gate.py $M/src/main/assets/places_seed_geocoded.json $M/tools/canaries.json; then
  echo "BUILD FAILED: canary completeness failures above (place ids named)."
  echo "Fix the dataset at the harvest/normalizer level; do not bypass this gate."
  exit 1
fi

step "3/8 aapt2 compile resources"
rm -rf $W/res_compiled $W/gen
mkdir -p $W/res_compiled
$BT/aapt2 compile --dir $M/src/main/res -o $W/res_compiled/app.zip
i=0
for d in $W/aars/*/; do
  if [ -d "$d/res" ] && [ -n "$(ls -A $d/res 2>/dev/null)" ]; then
    i=$((i+1))
    $BT/aapt2 compile --dir "$d/res" -o "$W/res_compiled/lib$i.zip" || { echo "aapt2 compile FAILED for $d"; exit 1; }
  fi
done
echo "compiled $i library res dirs"

step "4/8 aapt2 link"
# merge asset dirs (app + any AAR assets)
rm -rf $W/assets_merged && mkdir -p $W/assets_merged
cp -r $M/src/main/assets/* $W/assets_merged/ 2>/dev/null || true
for d in $W/aars/*/; do
  if [ -d "$d/assets" ] && [ -n "$(ls -A $d/assets 2>/dev/null)" ]; then
    cp -r "$d/assets/"* $W/assets_merged/ 2>/dev/null || true
  fi
done
$BT/aapt2 link \
  -o $W/resources.apk \
  -I $AJAR \
  --manifest $W/merged/AndroidManifest.xml \
  --java $W/gen \
  --extra-packages "$PKGS" \
  -A $W/assets_merged \
  --min-sdk-version "$MIN_SDK" --target-sdk-version "$TARGET_SDK" \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" \
  --auto-add-overlay \
  $W/res_compiled/*.zip
echo "linked resources.apk"

step "5/8 compile Kotlin + generated R"
CP=$(find $M/deps -name '*.jar' | tr '\n' ':')$(find $W/aars -name 'classes.jar' | tr '\n' ':')$(find $W/aars -path '*/libs/*.jar' | tr '\n' ':')$AJAR
find $M/src/main/java -name '*.kt' > $W/sources.txt
find $W/gen -name '*.java' >> $W/sources.txt
wc -l < $W/sources.txt
if ! $JAVA -Xmx640m -XX:+UseSerialGC -cp $KB/kotlinc/lib/kotlin-compiler.jar org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -classpath "$CP" \
  -d $W/classes.jar \
  -jvm-target 17 -no-stdlib -no-reflect \
  $(cat $W/sources.txt) > $W/kotlin.log 2>&1; then
  echo "KOTLINC FAILED:"; grep -vE "^warning:" $W/kotlin.log | head -n 80; exit 1
fi
grep -c "^warning:" $W/kotlin.log || true
echo "compiled classes.jar"
# CRITICAL: compile the generated R classes too. kotlinc reads R.java only for
# symbol resolution and emits NO R bytecode, but library bytecode (AppCompat!)
# references R fields at runtime via getstatic — without real R classes in the
# dex the app dies with NoClassDefFoundError on the very first screen.
echo "compile generated R classes with javac"
find $W/gen -name 'R.java' > $W/r_sources.txt
rm -rf $W/rclasses && mkdir -p $W/rclasses
$JAVAC -encoding UTF-8 -nowarn -cp "$AJAR" -d $W/rclasses @$W/r_sources.txt
$KB/jdk17/bin/jar uf $W/classes.jar -C $W/rclasses .
echo "R classes compiled: $(find $W/rclasses -name 'R$*.class' | wc -l)"

step "6/8 dex with d8"
rm -rf $W/dex && mkdir -p $W/dex
DEX_INPUTS="$W/classes.jar $(find $M/deps -name '*.jar' | tr ' ' '\n') $(find $W/aars -name 'classes.jar') $(find $W/aars -path '*/libs/*.jar')"
if ! $JAVA -Xmx640m -cp $KB/dl/r8.jar com.android.tools.r8.D8 --lib $AJAR --min-api 29 --output $W/dex $DEX_INPUTS > $W/d8.log 2>&1; then
  echo "D8 FAILED:"; head -n 40 $W/d8.log; exit 1
fi
head -n 5 $W/d8.log
ls -la $W/dex/

step "7/8 assemble + align"
cp $W/resources.apk $W/kyron-unsigned.apk
# Merge META-INF/services from every dexed jar into the APK (Gradle does this
# automatically; without it ServiceLoader finds nothing — e.g. coroutines'
# MainDispatcherFactory, whose absence crashes Dispatchers.Main at launch).
rm -rf $W/services_stage && mkdir -p $W/services_stage
for j in $(find $M/deps -name '*.jar' | grep -v stubs) $(find $W/aars -name 'classes.jar') $(find $W/aars -path '*/libs/*.jar'); do
  for svc in $(unzip -Z1 "$j" 2>/dev/null | grep '^META-INF/services/.' || true); do
    mkdir -p "$W/services_stage/$(dirname "$svc")"
    unzip -p "$j" "$svc" >> "$W/services_stage/$svc" || true
    echo >> "$W/services_stage/$svc"
  done
done
if [ -d $W/services_stage/META-INF ]; then
  (cd $W/services_stage && zip -q -r $W/kyron-unsigned.apk META-INF)
  echo "merged services: $(find $W/services_stage -type f | wc -l) files"
fi
cd $W/dex && zip -q $W/kyron-unsigned.apk classes*.dex && cd $KB

step "gate: APK dex audit (referenced classes must be packaged)"
python3 $M/app/audit_apk.py $W/kyron-unsigned.apk || {
  echo "BUILD FAILED: dex audit found packaged-but-referenced classes missing."
  echo "The APK would crash with NoClassDefFoundError at runtime."
  echo "Fix the dependency set (app/stage_aars.py re-stages the AAR work dir)."
  exit 1
}
# native libs from AARs (none expected, but include if present)
for d in $W/aars/*/; do
  if [ -d "$d/jni" ] && [ -n "$(find $d/jni -name '*.so' 2>/dev/null)" ]; then
    (cd "$d" && zip -q -r $W/kyron-unsigned.apk jni -i '*.so' && mv $W/kyron-unsigned.apk $W/tmp.apk && unzip -q -o $W/tmp.apk -d $W/restage >/dev/null && true)
  fi
done
$BT/zipalign -f -p 4 $W/kyron-unsigned.apk $W/kyron-aligned.apk

step "8/8 sign"
if [ ! -f $KB/debug.keystore ]; then
  $KB/jdk17/bin/keytool -genkeypair -keystore $KB/debug.keystore -storepass android -keypass android \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10950 \
    -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
fi
$BT/apksigner sign --ks $KB/debug.keystore --ks-pass pass:android --key-pass pass:android \
  --out $M/Kyron-2.0.apk $W/kyron-aligned.apk
$BT/apksigner verify --print-certs $M/Kyron-2.0.apk | head -n 3
ls -la $M/Kyron-2.0.apk
echo "BUILD OK"
