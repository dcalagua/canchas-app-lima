import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// La API key de Google Maps se resuelve, en orden de prioridad:
// 1) propiedad de Gradle -PMAPS_API_KEY=...   (la usa el workflow de CI con el secret)
// 2) variable de entorno MAPS_API_KEY
// 3) local.properties -> MAPS_API_KEY=...      (para desarrollo local)
// 4) placeholder "YOUR_MAPS_API_KEY_HERE"      (el mapa no cargará hasta poner una key real)
val mapsApiKey: String = run {
    val fromProp = (project.findProperty("MAPS_API_KEY") as String?)?.takeIf { it.isNotBlank() }
    val fromEnv = System.getenv("MAPS_API_KEY")?.takeIf { it.isNotBlank() }
    val fromLocal = rootProject.file("local.properties").takeIf { it.exists() }?.let { f ->
        Properties().apply { f.inputStream().use { load(it) } }.getProperty("MAPS_API_KEY")
    }?.takeIf { it.isNotBlank() }
    fromProp ?: fromEnv ?: fromLocal ?: "YOUR_MAPS_API_KEY_HERE"
}

android {
    namespace = "pe.ebim.canchaslima"
    compileSdk = 35

    defaultConfig {
        applicationId = "pe.ebim.canchaslima"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        manifestPlaceholders["MAPS_API_KEY"] = mapsApiKey
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.maps.compose)
    implementation(libs.play.services.maps)
    implementation(libs.play.services.location)
    debugImplementation(libs.androidx.ui.tooling)
}
