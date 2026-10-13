#!/bin/bash
# Kyron manual build pipeline (no Gradle — its daemon needs inter-process TCP
# that this sandbox intercepts). Every step below is a single process.
set -e
set -o pipefail
KB=$HOME/kyron-build
M=$KB/manual
W=$M/work
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
  --min-sdk-version 29 --target-sdk-version 34 \
  --version-code 2 --version-name "2.0" \
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
