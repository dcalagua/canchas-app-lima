# Entornos DEV · QAS · PROD y publicación en Play Store

Guía para pasar Pichangol de desarrollo a **QAS** (pruebas con base de datos
propia) y luego a **producción / Play Store**. Todo el CI ya está preparado; lo
que falta es infraestructura que se crea una sola vez.

## Cómo funcionan los entornos

Cada entorno es **independiente**: su propia base de datos (Supabase), su propio
backend (Railway) y su propio APK. El APK sabe a qué entorno apunta por los
`--dart-define` que inyecta el CI desde los secrets del *Environment* de GitHub.

| Entorno | applicationId | Backend (GROWTH_API_URL) | Base de datos | APK |
|---|---|---|---|---|
| **dev** | `pe.ebim.pichangol` | Railway `pg-backend` (dev) | Supabase dev | `pichangol-<n>.apk` (Release) |
| **qas** | `pe.ebim.pichangol.qas` | Railway QAS | Supabase QAS | `pichangol-qas-<n>.apk` (Artifact) + banner **QAS** |
| **prod** | `pe.ebim.pichangol` | Railway prod | Supabase prod | AAB para Play |

- **dev** y **prod** comparten `applicationId` (es la misma app publicada); no
  conviven en un teléfono. **qas** usa `.qas` → **sí convive** con dev/prod.
- Los `push` a la rama compilan siempre **dev** (sideload, sin cambios).
- QAS/PROD se compilan **a mano**: Actions → *Build app (Android)* → **Run
  workflow** → elegir `entorno`.

## A) Montar QAS

### 1. Supabase QAS
1. Crea un proyecto nuevo (ej. `pichangol-qas`).
2. SQL Editor → pega y ejecuta **`docs/piloto/supabase_QAS_completo.sql`**
   (crea todas las tablas del APK, idempotente).
3. Anota de *Project Settings → API*: `Project URL` (= `SUPABASE_URL`) y
   `anon public` (= `SUPABASE_ANON_KEY`).
4. De *Database → Connection string → Session pooler*: el `DATABASE_URL`
   (agrega `?sslmode=require`). Es para el backend, no para el APK.

### 2. Backend QAS (Railway)
1. Nuevo servicio (o *environment* "qas") con **Root Directory** `backend/growth`.
2. Variables de entorno QAS:
   - `DATABASE_URL` = el de Supabase QAS (crea la tabla `growth_state` sola).
   - `ADMIN_PANEL_TOKEN`, `APP_API_KEY`, `FACTILIZA_API_TOKEN`,
     `PICHANGOL_ADMIN_WHATSAPP`, `TWILIO_*`, `WHATSAPP_*` según haga falta.
   - **Importante:** `APP_API_KEY` debe coincidir con el secret `APP_API_KEY`
     del *Environment* `qas` de GitHub (abajo).
3. Anota la URL pública del servicio → es el `GROWTH_API_URL` de QAS.

### 3. GitHub → Settings → Environments → `qas`
Crea el environment **`qas`** y agrégale estos *secrets* (mismos nombres que en
el repo, valores de QAS). Los que no definas caen a los del repositorio (dev):

- `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- `GROWTH_API_URL` (el de Railway QAS)
- `APP_API_KEY` (igual al del backend QAS)
- `VERIF_API_URL`, `MAPS_API_KEY`, `PLACES_API_KEY`
- (firma) puede reusar los del repo: `ANDROID_KEYSTORE_B64`,
  `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.

### 4. Compilar el APK QAS
Actions → **Build app (Android)** → **Run workflow** → `entorno = qas`.
- Descarga `pichangol-qas-<n>.apk` desde los **Artifacts** del run.
- Trae **banner "QAS"** y package `.qas` → instálalo junto al dev sin conflicto.
- QAS **no** se publica en el Release público (queda solo en Artifacts).

## B) Publicar en Play Store (Prueba interna)

### 1. Generar el AAB (Play exige AAB, no APK)
Actions → Run workflow → `entorno = prod` (o `qas` para una prueba) → descarga
`pichangol-<entorno>-<n>.aab` desde los **Artifacts**.

### 2. Play Console
1. Crea la app con package **`pe.ebim.pichangol`** (⚠️ irreversible).
2. Track **Prueba interna** → sube el AAB → agrega correos de testers.
3. Completa: **política de privacidad** (URL), **Data safety**, **clasificación
   de contenido**, **público objetivo y contenido**.

### 3. ⚠️ SHA-1 (si se olvida, fallan login y mapa en la versión de Play)
Play re-firma tu app con **Play App Signing**. Copia el **SHA-1 de "App
signing"** (Play Console → *Test and release → Setup → App integrity*) y
agrégalo en:
- **Google Cloud → APIs y servicios → Credenciales → OAuth (Android)** → para
  que **Google Sign-In** funcione.
- **Restricción de la Maps API key** (huella SHA-1 + package) → para que **el
  mapa** cargue.
- **Firebase** (si activas push/FCM) → *Configuración del proyecto → tus apps*.

> El SHA-1 de **tu keystore** (el de los secrets `ANDROID_KEYSTORE_*`) ya debería
> estar registrado para dev; el de **Play App Signing** es ADICIONAL y distinto.

## Notas
- **Precios de servicios** (landing/redes/presencia) y **WhatsApp de contacto**
  se configuran por entorno desde la **torre de control** (`/admin` del backend
  de ese entorno) — cada backend tiene su propia config.
- **Versión / build number:** el CI usa `github.run_number` como `versionCode`;
  es monótono, sirve para Play.
- **iOS/TestFlight:** el job de iOS está retirado (ahorro de minutos macOS). Se
  re-agrega cuando haya cuenta Apple Developer.
