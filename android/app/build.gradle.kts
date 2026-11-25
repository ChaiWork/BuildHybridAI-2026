plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Automatically apply google-services if android/app/google-services.json is placed locally,
// while allowing clean CI / judge APK compilation without committed Google Cloud secrets (Rule Sec. 6).
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "space.tarscare.eva"
    compileSdk = 36

    defaultConfig {
        applicationId = "space.tarscare.eva"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "2.0.0-hybrid"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        optIn.add("com.google.firebase.ai.type.PublicPreviewAPI")
    }
}

dependencies {
    // Firebase BoM + Firebase AI Logic Hybrid Inference SDK (Gemini Nano 4 + Cloud Fallback)
    implementation(platform("com.google.firebase:firebase-bom:35.2.0"))
    implementation("com.google.firebase:firebase-ai:18.2.0")
    implementation("com.google.firebase:firebase-ai-ondevice:16.0.0-beta08")

    // Firebase App Check (Required for Firebase AI Logic; Debug tokens accepted per Contest Rules)
    implementation("com.google.firebase:firebase-appcheck")
    implementation("com.google.firebase:firebase-appcheck-debug:20.1.0")
    implementation("com.google.firebase:firebase-appcheck-playintegrity")

    // Supporting Firebase Suite: Auth, Offline-First Firestore Store-and-Forward, Remote Config
    implementation("com.google.firebase:firebase-auth")
    implementation("com.google.firebase:firebase-firestore")
    implementation("com.google.firebase:firebase-config")

    // Coroutines & Compose Material 3 Spacecraft UI
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.9.0")

    implementation(platform("androidx.compose:compose-bom:2026.06.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.10.1")
}
