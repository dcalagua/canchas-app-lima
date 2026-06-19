# Firma release, login Google real y TestFlight — preparación

> Estado: **pendiente de credenciales tuyas**. El código ya está listo; esto
> documenta qué hace falta para activar (1) login Gmail real, (2) APK firmado
> estable, (3) iOS instalable por TestFlight.

## 1) Login con Google (Gmail) REAL
Hoy el botón "Continuar con Google" usa un **fallback de demo** porque falta el
OAuth y una firma estable. Para activarlo de verdad:

1. Crear proyecto en **Google Cloud Console** (o Firebase) y configurar la
   pantalla de consentimiento OAuth.
2. Crear **OAuth Client IDs**:
   - **Android**: package `pe.ebim.canchas_lima` + **SHA-1** de la firma (ver §2).
   - **iOS**: bundle id `pe.ebim.canchasLima`.
   - **Web** (serverClientId) si luego validamos en backend.
3. **Android**: agregar `google-services.json` (si usamos Firebase) o registrar el
   cliente; no se requiere código extra, `google_sign_in` ya está integrado.
4. **iOS**: agregar el **reversed client id** como URL scheme en `Info.plist` y el
   `GIDClientID`. Se puede inyectar en CI igual que la `MAPS_API_KEY`
   (ver `tool/configure_platforms.py`).

> Importante: en Android, Google Sign-In valida la **SHA-1 de la firma**. Con la
> firma de debug efímera del CI no funciona; necesita la firma estable de §2.

## 2) Firma release de Android (keystore estable)
1. Generar un **keystore** (una vez):
   ```bash
   keytool -genkey -v -keystore pichangol.keystore -alias pichangol \
     -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Obtener su **SHA-1** (para registrarlo en el OAuth de Google):
   ```bash
   keytool -list -v -keystore pichangol.keystore -alias pichangol
   ```
3. Cargar como **secrets** de GitHub Actions (base64 del keystore + passwords):
   `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
   `ANDROID_KEY_PASSWORD`.
4. El workflow decodifica el keystore y firma el `app-release.apk`/`.aab`.

Con esto el SHA-1 es **constante** → Google Sign-In funciona y se puede subir a
Play Store.

## 3) iOS instalable (TestFlight)
Requiere **cuenta Apple Developer (USD 99/año)**. Necesito:
1. **Apple Developer Program** activo (Team ID).
2. Certificado de distribución + perfil de aprovisionamiento (o usar **App Store
   Connect API key** para firma automática con `fastlane match`/`xcode`).
3. App registrada en **App Store Connect** (bundle id `pe.ebim.canchasLima`).

Con esos secretos, el job iOS pasa de `--no-codesign` a `flutter build ipa` firmado
y sube a **TestFlight** (vía `fastlane` o la App Store Connect API). Ahí tu equipo
lo instala desde TestFlight.

## Qué necesito de ti para activar cada uno
- **Login Gmail real**: que crees el proyecto en Google Cloud y me pases los Client
  IDs (Android/iOS) — o me das acceso para configurarlos.
- **APK firmado**: que generes el keystore (te paso el comando) y cargues los 4
  secrets; o lo genero yo y te entrego el keystore para que lo guardes a buen recaudo.
- **TestFlight**: tu cuenta Apple Developer (Team ID + API key de App Store Connect).
