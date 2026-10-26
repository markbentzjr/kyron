plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing comes from the environment (CI secrets) — never committed:
//   KYRON_KEYSTORE (path), KYRON_KEYSTORE_PASSWORD, KYRON_KEY_ALIAS, KYRON_KEY_PASSWORD
val ks: String? = System.getenv("KYRON_KEYSTORE")

android {
    namespace = "com.kyronapp.kyron"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.kyronapp.kyron"
        minSdk = 29
        targetSdk = 34
        versionCode = 10
        versionName = "2.1"
    }
    signingConfigs {
        if (ks != null) create("release") {
            storeFile = file(ks)
            storePassword = System.getenv("KYRON_KEYSTORE_PASSWORD")
            keyAlias = System.getenv("KYRON_KEY_ALIAS")
            keyPassword = System.getenv("KYRON_KEY_PASSWORD")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            if (ks != null) signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
    lint { abortOnError = false }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jsoup:jsoup:1.18.1")
    implementation("org.osmdroid:osmdroid-android:6.1.18")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.fragment:fragment:1.8.3")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.lifecycle:lifecycle-process:2.8.4")
}
