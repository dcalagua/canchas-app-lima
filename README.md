# Canchas Lima — Panel del Club (Fase 1)

App Android del marketplace de reserva de **canchas de tenis y pádel en Lima**.
Esta primera versión está alineada a la **Fase 1 de la estrategia comercial: captar
la oferta (dueños de canchas)**. Por eso el corazón de la app es el **Panel del
Club**, no todavía la app del jugador.

> Tesis: *no vendemos software, le llenamos al dueño sus horas vacías.* El software
> es el medio; las reservas nuevas son la venta.

## Qué incluye la v1

Pantallas (acceso de demostración, datos en memoria, sin backend aún):

| Pestaña | Para qué sirve |
|---|---|
| **Agenda** | La agenda de hoy por cancha. Botón **“Simular reserva”** para el pitch de demo: el dueño ve entrar una reserva en vivo. |
| **Horarios** | El dueño abre/cierra su disponibilidad. Resalta las **horas valle** (mañanas) que conviene llenar. |
| **Reservas** | Lista de reservas con estado, seña (anti no-show) y distinción **reserva nueva vs. cliente de siempre** (solo las nuevas generan comisión en Fase 2). |
| **Reportes** | KPIs de la fase: canchas activas, reservas por la app, ingreso vía app, % de horas valle llenas, anti no-show, sello Club Fundador. |
| **Explorar** | Mapa de **Google Maps** con las canchas de la zona piloto (San Borja · Surco · La Molina), marcadas por deporte. |

Stack: **Kotlin + Jetpack Compose (Material 3) + Navigation Compose + Maps Compose**.
`minSdk 26`, `compileSdk 35`.

## Cómo se genera el APK (GitHub Actions)

Este entorno no puede compilar Android localmente (el SDK de Google está fuera del
allowlist de red), así que el APK se compila en **GitHub Actions**:

1. **Configura la API key de Google Maps como secret del repo** (una sola vez):
   `Settings → Secrets and variables → Actions → New repository secret`
   - Nombre: `MAPS_API_KEY`
   - Valor: tu clave de Google Maps Platform (con *Maps SDK for Android* habilitado).
2. Cada **push** dispara el workflow `Build APK` y deja el APK como **artifact**
   descargable: pestaña **Actions → (último run) → Artifacts → `canchas-lima-apk`**.
3. Para publicar el APK en un **Release** descargable, crea un tag:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
   El workflow adjuntará el APK al Release `v0.1.0`.

> El APK es **debug** (firmado con la clave de debug), instalable por sideload para
> demos en la cancha. Para publicar en Play Store luego configuramos firma release.

### Si el mapa sale en blanco
Significa que falta o es inválida la `MAPS_API_KEY`. Revisa el secret y que la key
tenga habilitado *Maps SDK for Android* y, si la restringes, el package
`pe.ebim.canchaslima` con la huella SHA-1 de la clave de debug.

## Desarrollo local (opcional)

Necesitas Android SDK instalado. Crea `local.properties` en la raíz con:

```properties
sdk.dir=/ruta/a/tu/Android/sdk
MAPS_API_KEY=tu_clave_de_google_maps
```

Luego:

```bash
./gradlew :app:assembleDebug
# APK en app/build/outputs/apk/debug/app-debug.apk
```

## Roadmap

- **Fase 1 (esta v1):** panel del club + captación de oferta. Datos de demo.
- **Fase 2:** backend real, app del jugador, reservas y comisión introductoria, seña/anti no-show.
- **Fase 3:** SaaS, destacados, torneos/ligas por nivel.
