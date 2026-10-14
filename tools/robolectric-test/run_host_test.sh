#!/bin/bash
# Kyron 2.1 Robolectric UI tests: LaunchTest + UiTest against the built APK.
set -e
set -o pipefail
export PATH=$HOME/kyron-build/jdk17/bin:$PATH
export JAVA_HOME=$HOME/kyron-build/jdk17
B=$HOME/kyron-build
M=$B/manual
T=$B/test
export KOTLINC_OPTS="-Xmx512m -XX:+UseSerialGC"
KOTLINC=$B/kotlinc/bin/kotlinc
ANDROID_JAR=$B/android-sdk/platforms/android-34/android.jar

mkdir -p $T/robo-apk $T/classes
cd $T/robo-apk && unzip -o -q $M/Kyron-2.0.apk "AndroidManifest.xml" "resources.arsc" "res/*" "assets/*"

APP_DEPS=$(find $M/work/aars -name 'classes.jar' | tr '\n' ':')$(find $M/work/aars -path '*/libs/*.jar' | tr '\n' ':')$(find $M/deps -name '*.jar' | grep -v stubs | tr '\n' ':')
TEST_DEPS=$(find $T/deps -name '*.jar' | tr '\n' ':')

echo "== compile tests =="
$KOTLINC -cp "$M/work/classes.jar:$APP_DEPS$TEST_DEPS$ANDROID_JAR" -d $T/classes \
  $T/src/HostTest.kt $T/src/TestKyronApplication.kt 2>&1 | grep -vE "^warning:" | head -n 30 || true

echo "== run tests =="
java -Xmx900m -XX:+UseSerialGC \
  -Drobolectric.offline=true \
  -Drobolectric.dependency.dir=$T/android-all \
  -cp "$T/classes:$M/work/classes.jar:$T/robo-apk:$APP_DEPS$TEST_DEPS$ANDROID_JAR" \
  org.junit.runner.JUnitCore com.kyronapp.kyron.HostTest
