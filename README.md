# Canchas Lima — Panel del Club (Fase 1)

App **multiplataforma (Android + iOS)** del marketplace de reserva de **canchas de
fútbol, tenis y pádel en Lima**, hecha en **Flutter**. Esta primera versión está
alineada a la **Fase 1 de la estrategia comercial: captar la oferta (dueños de
canchas)**. Por eso el corazón de la app es el **Panel del Club**, no todavía la app
del jugador.

> El fútbol (canchas sintéticas 5/7) es el mercado de mayor rotación de Lima y entra
> de lleno en el alcance: la app ya descubre, mapea y filtra canchas de fútbol. Nota
> estratégica: es también el terreno fuerte del competidor regional (ATC), así que
> en fútbol ganamos por **soporte humano local** y por el **gancho social**
> ("te falta 1 para tu pichanga"), no por reserva pura. Ver `docs/PLAN_FUTBOL.md`.

> Tesis: *no vendemos software, le llenamos al dueño sus horas vacías.* El software
> es el medio; las reservas nuevas son la venta.

## Qué incluye la v1

Pantallas (acceso de demostración, datos en memoria, sin backend aún):

| Pestaña | Para qué sirve |
|---|---|
| **Agenda** | La agenda de hoy por cancha. Botón **“Simular reserva”** para el pitch de demo: el dueño ve entrar una reserva en vivo. |
| **Horarios** | El dueño abre/cierra su disponibilidad. Resalta las **horas valle** (mañanas) que conviene llenar. |
| **Reservas** | Reservas con estado, seña (anti no-show) y distinción **reserva nueva vs. cliente de siempre** (solo las nuevas generan comisión en Fase 2). |
| **Reportes** | KPIs de la fase: canchas activas, reservas por la app, ingreso vía app, % horas valle, anti no-show, sello Club Fundador. |
| **Explorar** | Mapa de **Google Maps** con las canchas de la zona piloto (San Borja · Surco · La Molina). |

Stack: **Flutter (Material 3) + google_maps_flutter**. Código en `lib/`.

## Arquitectura del repo

Para evitar versionar miles de archivos de plataforma, **solo se versiona el código
Dart** (`lib/`, `pubspec.yaml`, `test/`). Las carpetas `android/` e `ios/` se
**generan en cada build de CI** con `flutter create` y se configuran con
`tool/configure_platforms.py` (inyecta la API key de Google Maps y los permisos).

## Cómo se genera el instalable (GitHub Actions)

Este entorno no compila apps móviles localmente (el SDK de Google está fuera del
allowlist de red), así que el build corre en **GitHub Actions** (`.github/workflows/build.yml`):

- **`android`** (Ubuntu): genera el APK **release** instalable → artifact `canchas-lima-apk`.
- **`ios`** (macOS): compila la app iOS **sin firma** para validar que el código es
  iOS-ready (ver nota de firma abajo).

### 1) Configura la API key de Google Maps (una sola vez)
`Settings → Secrets and variables → Actions → New repository secret`
- Nombre: `MAPS_API_KEY`
- Valor: tu clave de Google Maps Platform con **Maps SDK for Android** (y **Maps SDK for iOS**) habilitados.

### 2) Descarga el APK
Cada **push** dispara el build. El APK queda en **Actions → (último run) → Artifacts → `canchas-lima-apk`**.

### 3) (Opcional) Publicar APK en un Release
```bash
git tag v0.1.0 && git push origin v0.1.0
```
El workflow adjunta el APK al Release `v0.1.0`.

## iOS: nota sobre instalación

La app **compila para iOS** (job `ios`), pero un **instalable de iOS (.ipa) requiere
firma con una cuenta de Apple Developer** (USD 99/año). Apple no permite sideload
libre como Android. Para sacar un iOS instalable:

1. Cuenta de **Apple Developer** + certificado de distribución + perfil de
   aprovisionamiento (ad-hoc o App Store/TestFlight).
2. Cargar esos secretos en GitHub Actions y reemplazar `--no-codesign` por un build
   firmado (`flutter build ipa --export-options-plist ...`).
3. Distribuir por **TestFlight** (lo más cómodo para que el equipo lo pruebe).

Cuando tengas la cuenta, te configuro el pipeline de firma + TestFlight.

## Desarrollo local (opcional)

Necesitas Flutter instalado. Desde la raíz:

```bash
flutter create --org pe.ebim --project-name canchas_lima --platforms=android,ios .
MAPS_API_KEY=tu_clave python3 tool/configure_platforms.py
flutter pub get
flutter run            # en un emulador/dispositivo
flutter build apk --release
```

## Roadmap

- **Fase 1 (esta v1):** panel del club + captación de oferta. Datos de demo.
- **Fase 2:** backend real, app del jugador, reservas y comisión introductoria, seña/anti no-show.
- **Fase 3:** SaaS, destacados, torneos/ligas por nivel.
