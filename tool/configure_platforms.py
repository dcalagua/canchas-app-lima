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
import shutil
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
    # Ícono + color por defecto de las notificaciones push (FCM). Sin esto,
    # Android pinta un ícono genérico (cuadrito) en vez del pin de Pichangol.
    if "default_notification_icon" not in text:
        notif = (
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_icon" '
            'android:resource="@drawable/ic_stat_pichangol"/>\n'
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_color" '
            'android:resource="@color/pichangol_notif"/>\n'
            # Canal por defecto de FCM: el "pichan_msgs" que crea MainActivity con
            # el sonido custom "Pichan" (Android 8+ toma el sonido del CANAL).
            '        <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" '
            'android:value="pichan_msgs"/>\n    </application>'
        )
        text = text.replace("</application>", notif, 1)
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
    # iOS 15.5: lo exige el pod de ML Kit (google_mlkit_text_recognition). Es
    # compatible hacia atrás con Google Maps/Supabase (sus mínimos son menores).
    if re.search(r"^\s*#?\s*platform :ios", text, re.MULTILINE):
        text = re.sub(
            r"^\s*#?\s*platform :ios.*$",
            "platform :ios, '15.5'",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = "platform :ios, '15.5'\n" + text

    # Fuerza el deployment target de cada pod a 15.5 (mínimo de ML Kit).
    if "IPHONEOS_DEPLOYMENT_TARGET'] = '15.5'" not in text:
        text = text.replace(
            "flutter_additional_ios_build_settings(target)",
            "flutter_additional_ios_build_settings(target)\n"
            "    target.build_configurations.each do |config|\n"
            "      config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.5'\n"
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


def configurar_r8_release():
    """Desactiva la minificación R8 en el buildType release.

    Un plugin nativo (google_mlkit_text_recognition) referencia reconocedores
    opcionales (chino/japonés/coreano/devanagari) que no incluimos; R8 los marca
    como "missing class" y rompe `minifyReleaseWithR8`. Para el piloto no
    necesitamos shrink/obfuscation, así que apagamos R8 en release (elimina toda
    esa clase de fallos). El APK pesa un poco más, nada crítico. El DSL del
    buildType es la fuente de verdad de `minifyEnabled`, así que esto gana."""
    path = "android/app/build.gradle"
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        g = f.read()
    # Inyecta minify/shrink OFF dentro del buildType release (no en signingConfigs).
    nuevo, n = re.subn(
        r"(buildTypes\s*\{\s*release\s*\{)",
        r"\1\n            minifyEnabled false\n            shrinkResources false",
        g,
        count=1,
    )
    # Si ya hubiera un minifyEnabled true explícito, lo forzamos a false también.
    nuevo = re.sub(r"minifyEnabled\s+true", "minifyEnabled false", nuevo)
    nuevo = re.sub(r"shrinkResources\s+true", "shrinkResources false", nuevo)
    if nuevo != g:
        with open(path, "w", encoding="utf-8") as f:
            f.write(nuevo)
        print(f"  R8/minify: desactivado en release ({n} bloque)")
    else:
        print("  R8/minify: no se encontró buildTypes release (sin cambios)")


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


def configurar_notificacion_android():
    """Ícono pequeño (monocromo) + color de las notificaciones push. El small
    icon de Android DEBE ser una silueta blanca sobre transparente (el sistema lo
    tiñe); si no se declara, sale un ícono genérico. Usamos el pin de Pichangol."""
    raiz = "android/app/src/main"
    if not os.path.isdir(raiz):
        print("  Notif icon: omitido (no hay android/app/src/main)")
        return
    draw = os.path.join(raiz, "res", "drawable")
    vals = os.path.join(raiz, "res", "values")
    os.makedirs(draw, exist_ok=True)
    os.makedirs(vals, exist_ok=True)

    # Pin de ubicación (estilo del logo Pichangol), silueta blanca.
    icono = (
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:width="24dp"\n'
        '    android:height="24dp"\n'
        '    android:viewportWidth="24"\n'
        '    android:viewportHeight="24">\n'
        '    <path\n'
        '        android:fillColor="#FFFFFFFF"\n'
        '        android:pathData="M12,2C8.13,2 5,5.13 5,9c0,5.25 7,13 7,13s7,-7.75 '
        '7,-13c0,-3.87 -3.13,-7 -7,-7zM12,11.5c-1.38,0 -2.5,-1.12 -2.5,-2.5s1.12,-2.5 '
        '2.5,-2.5 2.5,1.12 2.5,2.5 -1.12,2.5 -2.5,2.5z"/>\n'
        '</vector>\n'
    )
    with open(os.path.join(draw, "ic_stat_pichangol.xml"), "w", encoding="utf-8") as f:
        f.write(icono)

    # Color de acento del ícono en la notificación (verde bosque de la marca).
    colors_path = os.path.join(vals, "colors.xml")
    color_line = '    <color name="pichangol_notif">#14463A</color>'
    if os.path.exists(colors_path):
        with open(colors_path, "r", encoding="utf-8") as f:
            c = f.read()
        if "pichangol_notif" not in c:
            c = c.replace("</resources>", color_line + "\n</resources>", 1)
            with open(colors_path, "w", encoding="utf-8") as f:
                f.write(c)
    else:
        with open(colors_path, "w", encoding="utf-8") as f:
            f.write(
                '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                + color_line + "\n</resources>\n"
            )
    print("  Notif icon: ic_stat_pichangol + color pichangol_notif configurados")


def configurar_sonido_notificacion():
    """Sonido de notificación custom "Pichan" (estilo Yape). Copia el mp3 a
    res/raw/pichan.mp3 y reescribe MainActivity.kt para CREAR el canal de
    notificación `pichan_msgs` con ese sonido (Android 8+ toma el sonido del
    canal, no del payload). El manifest apunta a ese canal como el por defecto de
    FCM, así el push en segundo plano suena "Pichan" sin cambios en el backend."""
    raiz = "android/app/src/main"
    if not os.path.isdir(raiz):
        print("  Sonido notif: omitido (no hay android/app/src/main)")
        return
    # 1) Copiar el sonido a res/raw (nombre en minúsculas, sin extensión al usarlo).
    origen = "assets/sonidos/pichan.mp3"
    if not os.path.exists(origen):
        print("  Sonido notif: omitido (falta assets/sonidos/pichan.mp3)")
        return
    raw = os.path.join(raiz, "res", "raw")
    os.makedirs(raw, exist_ok=True)
    shutil.copyfile(origen, os.path.join(raw, "pichan.mp3"))

    # 2) Reescribir MainActivity.kt para crear el canal con el sonido.
    kt_dir = os.path.join(raiz, "kotlin", "pe", "ebim", "canchas_lima")
    kt = os.path.join(kt_dir, "MainActivity.kt")
    if not os.path.isdir(kt_dir):
        print("  Sonido notif: omitido (no está MainActivity.kt)")
        return
    contenido = (
        "package pe.ebim.canchas_lima\n\n"
        "import android.app.NotificationChannel\n"
        "import android.app.NotificationManager\n"
        "import android.content.Context\n"
        "import android.media.AudioAttributes\n"
        "import android.net.Uri\n"
        "import android.os.Build\n"
        "import android.os.Bundle\n"
        "import io.flutter.embedding.android.FlutterActivity\n\n"
        "class MainActivity : FlutterActivity() {\n"
        "    override fun onCreate(savedInstanceState: Bundle?) {\n"
        "        super.onCreate(savedInstanceState)\n"
        "        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {\n"
        "            val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager\n"
        "            if (mgr.getNotificationChannel(\"pichan_msgs\") == null) {\n"
        "                val sonido = Uri.parse(\"android.resource://\" + packageName + \"/raw/pichan\")\n"
        "                val attrs = AudioAttributes.Builder()\n"
        "                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)\n"
        "                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)\n"
        "                    .build()\n"
        "                val canal = NotificationChannel(\n"
        "                    \"pichan_msgs\", \"Mensajes Pichangol\", NotificationManager.IMPORTANCE_HIGH)\n"
        "                canal.description = \"Notificaciones de mensajes y retos\"\n"
        "                canal.setSound(sonido, attrs)\n"
        "                canal.enableVibration(true)\n"
        "                mgr.createNotificationChannel(canal)\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    with open(kt, "w", encoding="utf-8") as f:
        f.write(contenido)
    print("  Sonido notif: pichan.mp3 en res/raw + canal pichan_msgs en MainActivity")


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
    configurar_r8_release()
    configurar_firebase_android()
    configurar_notificacion_android()
    configurar_sonido_notificacion()
    configurar_google_signin_ios()


if __name__ == "__main__":
    sys.exit(main())
