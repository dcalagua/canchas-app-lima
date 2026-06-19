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


APP_LABEL = "Pichangol"


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


def main():
    print(f"Configurando plataformas (MAPS_API_KEY {'definida' if KEY != 'YOUR_MAPS_API_KEY_HERE' else 'placeholder'})")
    patch("android/app/src/main/AndroidManifest.xml", android_manifest)
    patch("ios/Runner/AppDelegate.swift", ios_appdelegate)
    patch("ios/Runner/Info.plist", ios_infoplist)
    patch("ios/Podfile", ios_podfile)
    configurar_firma_android()
    configurar_google_signin_ios()


if __name__ == "__main__":
    sys.exit(main())
