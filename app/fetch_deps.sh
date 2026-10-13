#!/bin/bash
# Fetch Kyron's dependency artifacts directly (Maven layout) — no Gradle.
cd ~/kyron-build/manual/deps
G=https://maven.google.com
C=https://repo1.maven.org/maven2
fetch() { # repo group artifact version packaging
  local repo=$1 g=$2 a=$3 v=$4 p=${5:-aar}
  local path=$(echo $g | tr . /)/$a/$v/$a-$v.$p
  if [ -s "$a-$v.$p" ]; then echo "have $a-$v.$p"; return 0; fi
  if curl -sfL -o "$a-$v.$p" "$repo/$path"; then echo "ok   $a-$v.$p ($(stat -c%s $a-$v.$p))";
  else echo "FAIL $a-$v.$p  ($repo/$path)"; fi
}
# Kotlin / coroutines / network / parsing (Maven Central)
fetch $C org.jetbrains.kotlin kotlin-stdlib 2.0.20 jar
fetch $C org.jetbrains.kotlinx kotlinx-coroutines-android 1.8.1 jar
fetch $C org.jetbrains.kotlinx kotlinx-coroutines-core-jvm 1.8.1 jar
fetch $C com.squareup.okhttp3 okhttp 4.12.0 jar
fetch $C com.squareup.okio okio-jvm 3.6.0 jar
fetch $C org.jsoup jsoup 1.18.1 jar
fetch $C org.osmdroid osmdroid-android 6.1.18 aar
fetch $C com.google.guava listenablefuture 9999.0-empty-to-avoid-conflict-with-guava jar
# AndroidX (Google Maven)
fetch $G androidx.core core 1.13.1 aar
fetch $G androidx.core core-ktx 1.13.1 aar
fetch $G androidx.appcompat appcompat 1.7.0 aar
fetch $G androidx.appcompat appcompat-resources 1.7.0 aar
fetch $G androidx.fragment fragment 1.8.3 aar
fetch $G androidx.activity activity 1.9.2 aar
fetch $G androidx.activity activity-ktx 1.9.2 aar
fetch $G androidx.lifecycle lifecycle-runtime 2.8.4 aar
fetch $G androidx.lifecycle lifecycle-common 2.8.4 jar
fetch $G androidx.lifecycle lifecycle-livedata-core 2.8.4 aar
fetch $G androidx.lifecycle lifecycle-viewmodel 2.8.4 aar
fetch $G androidx.lifecycle lifecycle-viewmodel-savedstate 2.8.4 aar
fetch $G androidx.lifecycle lifecycle-process 2.8.4 aar
fetch $G androidx.savedstate savedstate 1.2.1 aar
fetch $G androidx.savedstate savedstate-ktx 1.2.1 aar
fetch $G androidx.annotation annotation 1.8.2 jar
fetch $G androidx.annotation annotation-experimental 1.4.1 aar
fetch $G androidx.collection collection 1.4.4 jar
fetch $G androidx.collection collection-ktx 1.4.4 jar
fetch $G androidx.recyclerview recyclerview 1.3.2 aar
fetch $G androidx.customview customview 1.1.0 aar
fetch $G androidx.cursoradapter cursoradapter 1.0.0 aar
fetch $G androidx.drawerlayout drawerlayout 1.2.0 aar
fetch $G androidx.vectordrawable vectordrawable 1.1.0 aar
fetch $G androidx.vectordrawable vectordrawable-animated 1.1.0 aar
fetch $G androidx.emoji2 emoji2 1.4.0 aar
fetch $G androidx.emoji2 emoji2-views-helper 1.4.0 aar
fetch $G androidx.resourceinspection resourceinspection-annotation 1.0.1 jar
fetch $G androidx.work work-runtime 2.9.0 aar
fetch $G androidx.work work-runtime-ktx 2.9.0 aar
fetch $G androidx.room room-runtime 2.6.1 aar
fetch $G androidx.room room-common 2.6.1 jar
fetch $G androidx.sqlite sqlite 2.4.0 aar
fetch $G androidx.sqlite sqlite-framework 2.4.0 aar
fetch $G androidx.startup startup-runtime 1.1.1 aar
fetch $G androidx.tracing tracing 1.2.0 aar
fetch $G androidx.concurrent concurrent-futures 1.2.0 jar
fetch $G androidx.profileinstaller profileinstaller 1.3.1 aar
fetch $G androidx.interpolator interpolator 1.0.0 aar
fetch $G androidx.versionedparcelable versionedparcelable 1.1.1 aar
fetch $G androidx.arch.core core-common 2.2.0 jar
fetch $G androidx.arch.core core-runtime 2.2.0 aar
