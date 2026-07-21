#!/usr/bin/env python3
"""
Configura las carpetas android/ e ios/ (generadas por `flutter create`) para
google_maps_flutter:

- Android: permiso INTERNET + meta-data com.google.android.geo.API_KEY.
- iOS: import GoogleMaps + GMSServices.provideAPIKey en AppDelegate.swift,
  y deployment target 14.0 en el Podfile (lo exige el SDK de Google Maps iOS).

La API key se toma de la variable de entorno MAPS_API_KEY (en CI viene del
secret). Si no existe, usa un placeholder: el build funciona, pero el mapa no
cargará hasta poner una key real.
"""
import base64
import os
import re
import sys

KEY = os.environ.get("MAPS_API_KEY", "").strip() or "YOUR_MAPS_API_KEY_HERE"


def patch(path, fn):
    if not os.path.exists(path):
        print(f"  (omitido, no existe) {path}")
        return
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()
    updated = fn(original)
    if updated != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"  parchado {path}")
    else:
        print(f"  sin cambios {path}")


# Entorno de build: dev | qas | prod (viene de la env ENTORNO en el CI).
# QAS usa un applicationId/label DISTINTO (sufijo .qas) para convivir con
# prod/dev en el mismo teléfono y apuntar a la base de datos de pruebas.
ENTORNO = os.environ.get("ENTORNO", "dev").strip().lower()
_ES_QAS = ENTORNO == "qas"

APP_LABEL = "Pichangol QAS" if _ES_QAS else "Pichangol"
# Identidad PERMANENTE de la app en Google Play / App Store. NO cambiar una vez
# publicada la primera versión (el applicationId es inmutable en la tienda).
# El paquete de código Dart sigue siendo `canchas_lima`; esto sólo fija el
# applicationId (Android) y el bundle id (iOS) que ve la tienda.
APPLICATION_ID = "pe.ebim.pichangol.qas" if _ES_QAS else "pe.ebim.pichangol"


def android_manifest(text):
    text = text.replace('android:label="canchas_lima"', f'android:label="{APP_LABEL}"')
    if "android.permission.INTERNET" not in text:
        text = re.sub(
            r"(<manifest[^>]*>)",
            r'\1\n    <uses-permission android:name="android.permission.INTERNET"/>',
            text,
            count=1,
        )
    if "ACCESS_FINE_LOCATION" not in text:
        text = re.sub(
            r"(<manifest[^>]*>)",
            r'\1\n    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>'
            r'\n    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>',
            text,
            count=1,
        )
    # Cámara: para adjuntar/tomar fotos en el chat (image_picker source camera).
    if "android.permission.CAMERA" not in text:
        text = re.sub(
            r"(<manifest[^>]*>)",
            r'\1\n    <uses-permission android:name="android.permission.CAMERA"/>'
            r'\n    <uses-feature android:name="android.hardware.camera" android:required="false"/>',
            text,
            count=1,
        )
    # Micrófono: notas de voz en el chat (plugin record).
    if "android.permission.RECORD_AUDIO" not in text:
        text = re.sub(
            r"(<manifest[^>]*>)",
            r'\1\n    <uses-permission android:name="android.permission.RECORD_AUDIO"/>',
            text,
            count=1,
        )
    if "com.google.android.geo.API_KEY" not in text:
        meta = (
            '        <meta-data android:name="com.google.android.geo.API_KEY" '
            f'android:value="{KEY}"/>\n    </application>'
        )
        text = text.replace("</application>", meta, 1)
    else:
        text = re.sub(
            r'(android:name="com\.google\.android\.geo\.API_KEY"\s+android:value=")[^"]*(")',
            rf"\g<1>{KEY}\g<2>",
            text,
        )
    return text


def ios_appdelegate(text):
    if "import GoogleMaps" not in text:
        text = text.replace("import UIKit", "import UIKit\nimport GoogleMaps", 1)
    if "GMSServices.provideAPIKey" not in text:
        text = text.replace(
            "GeneratedPluginRegistrant.register(with: self)",
            f'GMSServices.provideAPIKey("{KEY}")\n    '
            "GeneratedPluginRegistrant.register(with: self)",
            1,
        )
    else:
        text = re.sub(
            r'GMSServices\.provideAPIKey\("[^"]*"\)',
            f'GMSServices.provideAPIKey("{KEY}")',
            text,
        )
    return text


def ios_infoplist(text):
    # Nombre visible de la app en iOS.
    text = re.sub(
        r"(<key>CFBundleDisplayName</key>\s*<string>)[^<]*(</string>)",
        rf"\g<1>{APP_LABEL}\g<2>",
        text,
    )
    # Permiso de ubicación (para canchas cercanas).
    if "NSLocationWhenInUseUsageDescription" not in text:
        block = (
            "\t<key>NSLocationWhenInUseUsageDescription</key>\n"
            "\t<string>Pichangol usa tu ubicación para mostrarte canchas cercanas.</string>\n"
            "</dict>\n</plist>"
        )
        text = text.replace("</dict>\n</plist>", block, 1)
    # Permiso de fotos (registrar cancha + detección de deporte con IA).
    if "NSPhotoLibraryUsageDescription" not in text:
        block = (
            "\t<key>NSPhotoLibraryUsageDescription</key>\n"
            "\t<string>Pichangol usa tus fotos para registrar canchas y detectar el deporte.</string>\n"
            "</dict>\n</plist>"
        )
        text = text.replace("</dict>\n</plist>", block, 1)
    # Permiso de micrófono (notas de voz en el chat).
    if "NSMicrophoneUsageDescription" not in text:
        block = (
            "\t<key>NSMicrophoneUsageDescription</key>\n"
            "\t<string>Pichangol usa el micrófono para enviar notas de voz en el chat.</string>\n"
            "</dict>\n</plist>"
        )
        text = text.replace("</dict>\n</plist>", block, 1)
    return text


def ios_podfile(text):
    if re.search(r"^\s*#?\s*platform :ios", text, re.MULTILINE):
        text = re.sub(
            r"^\s*#?\s*platform :ios.*$",
            "platform :ios, '14.0'",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = "platform :ios, '14.0'\n" + text

    # Asegura que cada pod use iOS 14 (lo exige el SDK de Google Maps).
    if "IPHONEOS_DEPLOYMENT_TARGET'] = '14.0'" not in text:
        text = text.replace(
            "flutter_additional_ios_build_settings(target)",
            "flutter_additional_ios_build_settings(target)\n"
            "    target.build_configurations.each do |config|\n"
            "      config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '14.0'\n"
            "    end",
            1,
        )
    return text


def configurar_firma_android():
    """Si hay keystore en el entorno, configura la firma release de Android.
    Si no, no toca nada (sigue la firma debug por defecto)."""
    b64 = os.environ.get("ANDROID_KEYSTORE_B64", "").strip()
    gradle_path = "android/app/build.gradle"
    if not b64:
        print("  firma Android: debug (sin ANDROID_KEYSTORE_B64)")
        return
    if not os.path.exists(gradle_path):
        print("  firma Android: omitida (no hay android/app/build.gradle)")
        return

    store_pass = os.environ.get("ANDROID_KEYSTORE_PASSWORD", "")
    key_pass = os.environ.get("ANDROID_KEY_PASSWORD", "") or store_pass
    alias = os.environ.get("ANDROID_KEY_ALIAS", "pichangol")

    with open("android/app/pichangol.keystore", "wb") as f:
        f.write(base64.b64decode(b64))
    with open("android/key.properties", "w", encoding="utf-8") as f:
        f.write(
            f"storePassword={store_pass}\n"
            f"keyPassword={key_pass}\n"
            f"keyAlias={alias}\n"
            f"storeFile=pichangol.keystore\n"
        )

    with open(gradle_path, "r", encoding="utf-8") as f:
        g = f.read()

    if "keystoreProperties" not in g:
        loader = (
            "def keystoreProperties = new Properties()\n"
            "def keystorePropertiesFile = rootProject.file(\"key.properties\")\n"
            "if (keystorePropertiesFile.exists()) {\n"
            "    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))\n"
            "}\n\n"
        )
        g = re.sub(r"android\s*\{", loader + "android {", g, count=1)

        signing_block = (
            "android {\n"
            "    signingConfigs {\n"
            "        release {\n"
            "            keyAlias keystoreProperties[\"keyAlias\"]\n"
            "            keyPassword keystoreProperties[\"keyPassword\"]\n"
            "            storeFile keystoreProperties[\"storeFile\"] ? file(keystoreProperties[\"storeFile\"]) : null\n"
            "            storePassword keystoreProperties[\"storePassword\"]\n"
            "        }\n"
            "    }\n"
        )
        g = g.replace("android {", signing_block, 1)

    # Apunta el buildType release a la firma release (varias variantes de sintaxis).
    g = re.sub(
        r"signingConfig\s*=?\s*signingConfigs\.debug",
        "signingConfig signingConfigs.release",
        g,
    )

    with open(gradle_path, "w", encoding="utf-8") as f:
        f.write(g)
    print(f"  firma Android: RELEASE (alias {alias})")


def configurar_google_signin_ios():
    """Inyecta el reversed client id de Google como URL scheme en iOS (si hay)."""
    cid = os.environ.get("GOOGLE_IOS_CLIENT_ID", "").strip()
    plist = "ios/Runner/Info.plist"
    if not cid or not os.path.exists(plist):
        return
    reversed_id = ".".join(reversed(cid.split(".")))
    with open(plist, "r", encoding="utf-8") as f:
        text = f.read()
    if "CFBundleURLTypes" in text:
        return
    block = (
        "\t<key>CFBundleURLTypes</key>\n"
        "\t<array>\n\t\t<dict>\n\t\t\t<key>CFBundleURLSchemes</key>\n"
        f"\t\t\t<array>\n\t\t\t\t<string>{reversed_id}</string>\n\t\t\t</array>\n"
        "\t\t</dict>\n\t</array>\n"
        f"\t<key>GIDClientID</key>\n\t<string>{cid}</string>\n</dict>\n</plist>"
    )
    text = text.replace("</dict>\n</plist>", block, 1)
    with open(plist, "w", encoding="utf-8") as f:
        f.write(text)
    print("  Google Sign-In iOS: URL scheme configurado")


def configurar_compile_sdk_global():
    """Fuerza compileSdk en todos los subproyectos Android.
    Varios plugins (app_links, package_info_plus, geolocator…) esperan
    flutter.compileSdkVersion, que no está disponible para subproyectos en este
    entorno y rompe el build. Esto lo resuelve de raíz para todos a la vez."""
    path = "android/build.gradle"
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if "pichangol_compile_sdk_fix" in text:
        return
    # Se PREPONE para registrar el hook antes de que Flutter dispare la
    # evaluación de subproyectos (evita "afterEvaluate when already evaluated").
    bloque = (
        "// pichangol_compile_sdk_fix: forzar compileSdk en subproyectos de plugin\n"
        "subprojects { sub ->\n"
        "    if (!sub.state.executed) {\n"
        "        sub.afterEvaluate { p ->\n"
        "            if (p.hasProperty(\"android\")) {\n"
        "                p.android {\n"
        "                    if (namespace == null) {\n"
        "                        namespace p.group\n"
        "                    }\n"
        "                    compileSdkVersion 34\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(bloque + text)
    print("  compileSdk global aplicado a subproyectos Android")


def configurar_application_id():
    """Fija el applicationId de Android a APPLICATION_ID (identidad en Play Store).
    `flutter create --org pe.ebim` genera `pe.ebim.canchas_lima`; aquí lo
    sobreescribimos. El namespace del código se deja intacto (puede diferir del
    applicationId sin problema)."""
    path = "android/app/build.gradle"
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    nuevo = re.sub(
        r'(applicationId\s*=?\s*")[^"]*(")',
        rf"\g<1>{APPLICATION_ID}\g<2>",
        text,
        count=1,
    )
    if nuevo != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(nuevo)
        print(f"  applicationId Android → {APPLICATION_ID}")
    else:
        print("  applicationId Android: sin cambios (no se encontró el patrón)")


def configurar_bundle_id_ios():
    """Fija el PRODUCT_BUNDLE_IDENTIFIER de iOS a APPLICATION_ID (para App Store /
    Google Sign-In). El proyecto lo genera como pe.ebim.canchasLima."""
    path = "ios/Runner.xcodeproj/project.pbxproj"
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Sólo el bundle base (evita tocar el de RunnerTests, que lleva sufijo).
    nuevo = re.sub(
        r"(PRODUCT_BUNDLE_IDENTIFIER = )pe\.ebim\.canchasLima(;)",
        rf"\g<1>{APPLICATION_ID}\g<2>",
        text,
    )
    if nuevo != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(nuevo)
        print(f"  bundle id iOS → {APPLICATION_ID}")


def configurar_min_sdk():
    """Sube minSdk a 23 (lo exige passkeys_android de supabase_flutter)."""
    path = "android/app/build.gradle"
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    nuevo = re.sub(
        r"minSdk(?:Version)?\s*=?\s*flutter\.minSdkVersion",
        "minSdk = 23",
        text,
    )
    if nuevo != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(nuevo)
        print("  minSdk forzado a 23")


def configurar_firebase_android():
    """Habilita FCM (notificaciones push del chat) en Android SOLO si hay config.

    Requiere el `google-services.json` del proyecto Firebase (para el
    applicationId `pe.ebim.pichangol`), pasado como secret base64
    `GOOGLE_SERVICES_JSON_B64`. Si NO está, no se toca nada: el APK compila igual
    y el push queda desactivado en runtime (PushService es fail-safe). Así el CI
    sigue verde sin Firebase hasta que se configure."""
    if _ES_QAS:
        # El google-services.json es para pe.ebim.pichangol; con el sufijo .qas
        # el plugin fallaría ("no matching client"). En QAS el push va desactivado.
        print("  Firebase/FCM: omitido en QAS (applicationId .qas)")
        return
    b64 = os.environ.get("GOOGLE_SERVICES_JSON_B64", "").strip()
    if not b64:
        print("  Firebase/FCM: desactivado (sin GOOGLE_SERVICES_JSON_B64)")
        return
    app_gradle = "android/app/build.gradle"
    settings_gradle = "android/settings.gradle"
    if not os.path.exists(app_gradle):
        print("  Firebase/FCM: omitido (no hay android/app/build.gradle)")
        return

    # 1) Escribe el google-services.json donde el plugin lo busca.
    try:
        with open("android/app/google-services.json", "wb") as f:
            f.write(base64.b64decode(b64))
    except Exception as e:  # noqa: BLE001
        print(f"  Firebase/FCM: no se pudo escribir google-services.json ({e})")
        return

    # 2) Declara el plugin en settings.gradle (apply false) si usa el bloque plugins.
    if os.path.exists(settings_gradle):
        with open(settings_gradle, "r", encoding="utf-8") as f:
            s = f.read()
        if "com.google.gms.google-services" not in s and "plugins {" in s:
            s = s.replace(
                "plugins {",
                'plugins {\n    id "com.google.gms.google-services" version "4.4.2" apply false',
                1,
            )
            with open(settings_gradle, "w", encoding="utf-8") as f:
                f.write(s)

    # 3) Aplica el plugin en el módulo app.
    with open(app_gradle, "r", encoding="utf-8") as f:
        g = f.read()
    if "com.google.gms.google-services" not in g:
        if 'id "dev.flutter.flutter-gradle-plugin"' in g:
            g = g.replace(
                'id "dev.flutter.flutter-gradle-plugin"',
                'id "dev.flutter.flutter-gradle-plugin"\n'
                '    id "com.google.gms.google-services"',
                1,
            )
        else:  # fallback estilo apply plugin
            g = g + '\napply plugin: "com.google.gms.google-services"\n'
        with open(app_gradle, "w", encoding="utf-8") as f:
            f.write(g)
    print("  Firebase/FCM: ACTIVADO (google-services.json + plugin)")


def main():
    print(f"Configurando plataformas (MAPS_API_KEY {'definida' if KEY != 'YOUR_MAPS_API_KEY_HERE' else 'placeholder'})")
    configurar_min_sdk()
    configurar_application_id()
    configurar_bundle_id_ios()
    patch("android/app/src/main/AndroidManifest.xml", android_manifest)
    patch("ios/Runner/AppDelegate.swift", ios_appdelegate)
    patch("ios/Runner/Info.plist", ios_infoplist)
    patch("ios/Podfile", ios_podfile)
    configurar_firma_android()
    configurar_firebase_android()
    configurar_google_signin_ios()


if __name__ == "__main__":
    sys.exit(main())
