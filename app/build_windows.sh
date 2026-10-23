#!/bin/bash
# Kyron Windows-local build (Git-for-Windows bash + local toolchain).
#
# This is a faithful mirror of app/build_manual.sh (the canonical manual
# pipeline) with ONLY path/location overrides for this machine; run it from
# the repo root. The canonical script targets the Linux-style sandbox layout
# ($HOME/kyron-build/manual/...). On this Windows machine the repository tree
# is built in place instead:
#
#   - sources/resources/assets/gates: the live repo tree (app/, tools/)
#   - deps + AAR work dir: $HOME/kyron-build/manual/work/aars + manual/deps
#     (pre-fetched, same dependency set as the last sandbox build)
#   - JDK 17 + kotlinc: $HOME/kyron-build/{jdk17,kotlinc}
#   - r8.jar: $HOME/kyron-build/android-sdk/cmdline-tools/latest/lib/r8.jar
#   - aapt2/zipalign/apksigner: local Android SDK build-tools 36.0.0
#   - android.jar: local Android SDK platforms/android-37.0 (compile-time
#     classpath for -jvm-target 17; min/target SDK semantics in aapt2 link
#     are pinned below, like the canonical script)
#
# Every step, gate, and guarantee of the canonical pipeline is preserved in
# the same order with the same flags. Nothing here publishes, signs with a
# release identity, or alters the canonical script.
set -e
set -o pipefail
KB=$HOME/kyron-build
M="$(pwd)"                       # repo root, unlike the canonical $KB/manual copy
W=$KB/work  # work dir distinct from the canonical $M/work (repo is source of truth)
SDK_LOCAL=$LOCALAPPDATA/Android/Sdk
BT=$SDK_LOCAL/build-tools/36.0.0
AJAR=$SDK_LOCAL/platforms/android-37.0/android.jar
JAVA=$KB/jdk17/bin/java
JAVAC=$KB/jdk17/bin/javac
R8JAR=$KB/android-sdk/cmdline-tools/latest/lib/r8.jar
export TMPDIR=$KB/tmp
export PATH=$KB/jdk17/bin:$PATH
export KB
mkdir -p $W $KB/tmp

step() { echo; echo "=== $1 ==="; }

step "1/8 merge manifests"
python app/merge_manifest.py app/src/main/AndroidManifest.xml $KB/manual/work/aars $W/merged/AndroidManifest.xml

step "2/8 collect resource packages"
PKGS=$(python - <<'PY'
import os, xml.etree.ElementTree as ET
pkgs = []
base = os.path.join(os.environ['KB'], 'manual', 'work', 'aars')
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
if ! python tools/validate_pathdata.py app/src/main/res; then
  echo "BUILD FAILED: malformed vector pathData above (file + segment named)."
  echo "Fix the path to its canonical source; do not bypass this gate."
  exit 1
fi

step "gate: validate seed dataset"
if ! python tools/validate_seed.py app/src/main/assets/places_seed_geocoded.json; then
  echo "BUILD FAILED: seed dataset violations above (place ids named)."
  echo "Fix the dataset at the harvest/normalizer level; do not bypass this gate."
  exit 1
fi

step "gate: canary completeness (Workstream D)"
if ! python tools/canary_gate.py app/src/main/assets/places_seed_geocoded.json tools/canaries.json; then
  echo "BUILD FAILED: canary completeness failures above (place ids named)."
  echo "Fix the dataset at the harvest/normalizer level; do not bypass this gate."
  exit 1
fi

step "3/8 aapt2 compile resources"
rm -rf $W/res_compiled $W/gen
mkdir -p $W/res_compiled
"$BT/aapt2.exe" compile --dir app/src/main/res -o $W/res_compiled/app.zip
i=0
for d in $KB/manual/work/aars/*/; do
  if [ -d "$d/res" ] && [ -n "$(ls -A $d/res 2>/dev/null)" ]; then
    i=$((i+1))
    "$BT/aapt2.exe" compile --dir "$d/res" -o "$W/res_compiled/lib$i.zip" || { echo "aapt2 compile FAILED for $d"; exit 1; }
  fi
done
echo "compiled $i library res dirs"

step "4/8 aapt2 link"
rm -rf $W/assets_merged && mkdir -p $W/assets_merged
cp -r app/src/main/assets/* $W/assets_merged/ 2>/dev/null || true
for d in $KB/manual/work/aars/*/; do
  if [ -d "$d/assets" ] && [ -n "$(ls -A $d/assets 2>/dev/null)" ]; then
    cp -r "$d/assets/"* $W/assets_merged/ 2>/dev/null || true
  fi
done
"$BT/aapt2.exe" link \
  -o $W/resources.apk \
  -I $AJAR \
  --manifest $W/merged/AndroidManifest.xml \
  --java $W/gen \
  --extra-packages "$PKGS" \
  -A $W/assets_merged \
  --min-sdk-version 29 --target-sdk-version 34 \
  --version-code 11 --version-name "2.0.1" \
  --auto-add-overlay \
  $W/res_compiled/*.zip
echo "linked resources.apk"

step "5/8 compile Kotlin + generated R"
CP=$(find $KB/manual/deps -name '*.jar' | tr '\n' ':')$(find $KB/manual/work/aars -name 'classes.jar' | tr '\n' ':')$(find $KB/manual/work/aars -path '*libs/*.jar' | tr '\n' ':')$AJAR
find app/src/main/java -name '*.kt' > $W/sources.txt
find $W/gen -name '*.java' >> $W/sources.txt
wc -l < $W/sources.txt
if ! $JAVA -Xmx1600m -XX:+UseSerialGC -cp $KB/kotlinc/lib/kotlin-compiler.jar org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -classpath "$CP" \
  -d $W/classes.jar \
  -jvm-target 17 -no-stdlib -no-reflect \
  $(cat $W/sources.txt) > $W/kotlin.log 2>&1; then
  echo "KOTLINC FAILED:"; grep -vE "^warning:" $W/kotlin.log | head -n 80; exit 1
fi
grep -c "^warning:" $W/kotlin.log || true
echo "compiled classes.jar"
echo "compile generated R classes with javac"
find $W/gen -name 'R.java' > $W/r_sources.txt
rm -rf $W/rclasses && mkdir -p $W/rclasses
# javac.exe is a native Windows binary: convert each path in the sources
# list to a Windows path (MSYS converts command-line args but not file
# contents).
while read -r p; do cygpath -w "$p"; done < <(find $W/gen -name 'R.java') > $W/r_sources_w.txt
$JAVAC -encoding UTF-8 -nowarn -cp "$(cygpath -w $AJAR)" -d "$(cygpath -w $W/rclasses)" @$W/r_sources_w.txt
$KB/jdk17/bin/jar uf $W/classes.jar -C $W/rclasses .
echo "R classes compiled: $(find $W/rclasses -name 'R$*.class' | wc -l)"

step "6/8 dex with d8"
rm -rf $W/dex && mkdir -p $W/dex
DEX_INPUTS="$W/classes.jar $(find $KB/manual/deps -name '*.jar' | tr ' ' '\n') $(find $KB/manual/work/aars -name 'classes.jar') $(find $KB/manual/work/aars -path '*/libs/*.jar')"
if ! $JAVA -Xmx1600m -cp $R8JAR com.android.tools.r8.D8 --lib $AJAR --min-api 29 --output $W/dex $DEX_INPUTS > $W/d8.log 2>&1; then
  echo "D8 FAILED:"; head -n 40 $W/d8.log; exit 1
fi
head -n 5 $W/d8.log
ls -la $W/dex/

step "7/8 assemble + align"
cp $W/resources.apk $W/kyron-unsigned.apk
# Git-for-Windows bash has no `zip`; use Python's zipfile for the same
# "append files into the APK" job (store or deflate both fine for APK).
zipadd() { python "$M/tools/zipadd.py" "$@"; }
rm -rf $W/services_stage && mkdir -p $W/services_stage
for j in $(find $KB/manual/deps -name '*.jar' | grep -v stubs) $(find $KB/manual/work/aars -name 'classes.jar') $(find $KB/manual/work/aars -path '*/libs/*.jar'); do
  for svc in $(unzip -Z1 "$j" 2>/dev/null | grep '^META-INF/services/.' || true); do
    mkdir -p "$W/services_stage/$(dirname "$svc")"
    unzip -p "$j" "$svc" >> "$W/services_stage/$svc" || true
    echo >> "$W/services_stage/$svc"
  done
done
if [ -d $W/services_stage/META-INF ]; then
  (cd $W/services_stage && zipadd $W/kyron-unsigned.apk META-INF)
  echo "merged services: $(find $W/services_stage -type f | wc -l) files"
fi
cd $W/dex && zipadd $W/kyron-unsigned.apk classes*.dex && cd $KB

step "gate: APK dex audit (referenced classes must be packaged)"
python $M/app/audit_apk.py $W/kyron-unsigned.apk || {
  echo "BUILD FAILED: dex audit found packaged-but-referenced classes missing."
  echo "The APK would crash with NoClassDefFoundError at runtime."
  echo "Fix the dependency set (app/stage_aars.py re-stages the AAR work dir)."
  exit 1
}

for d in $KB/manual/work/aars/*/; do
  if [ -d "$d/jni" ] && [ -n "$(find $d/jni -name '*.so' 2>/dev/null)" ]; then
    (cd "$d" && zipadd $W/kyron-unsigned.apk jni -i '*.so' && true)
  fi
done
"$BT/zipalign.exe" -f -p 4 $W/kyron-unsigned.apk $W/kyron-aligned.apk

step "8/8 sign (release keystore when KYRON_RELEASE_KS is set; debug otherwise)"
if [ -n "${KYRON_RELEASE_KS:-}" ] && [ -f "$KYRON_RELEASE_KS" ]; then
  # OPT-IN release signing: caller supplies KYRON_RELEASE_KS (path to the
  # keystore) and KYRON_RELEASE_PASS. The keystore and password are NEVER
  # stored in the repo and never echoed here.
  KYOUT=$M/app/Kyron-2.0-release.apk
  "$BT/apksigner.bat" sign --ks "$(cygpath -w $KYRON_RELEASE_KS)" \
    --ks-pass "pass:$KYRON_RELEASE_PASS" --key-pass "pass:$KYRON_RELEASE_PASS" \
    --out "$(cygpath -w $KYOUT)" "$(cygpath -w $W/kyron-aligned.apk)"
  "$BT/apksigner.bat" verify --print-certs "$(cygpath -w $KYOUT)" | head -n 3
  ls -la $KYOUT
  echo "BUILD OK (release-signed local build; distribution is a separate, explicit step)"
else
  if [ ! -f $KB/debug.keystore ]; then
    $KB/jdk17/bin/keytool -genkeypair -keystore $KB/debug.keystore -storepass android -keypass android \
      -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10950 \
      -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
  fi
  "$BT/apksigner.bat" sign --ks "$KB/debug.keystore" --ks-pass pass:android --key-pass pass:android \
    --out "$(cygpath -w $M/app/Kyron-2.0-windows-build.apk)" "$(cygpath -w $W/kyron-aligned.apk)"
  "$BT/apksigner.bat" verify --print-certs "$(cygpath -w $M/app/Kyron-2.0-windows-build.apk)" | head -n 3
  ls -la $M/app/Kyron-2.0-windows-build.apk
  echo "BUILD OK (windows-local debug build for test rig; not for distribution)"
fi
