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


def main():
    print(f"Configurando plataformas (MAPS_API_KEY {'definida' if KEY != 'YOUR_MAPS_API_KEY_HERE' else 'placeholder'})")
    patch("android/app/src/main/AndroidManifest.xml", android_manifest)
    patch("ios/Runner/AppDelegate.swift", ios_appdelegate)
    patch("ios/Runner/Info.plist", ios_infoplist)
    patch("ios/Podfile", ios_podfile)


if __name__ == "__main__":
    sys.exit(main())
