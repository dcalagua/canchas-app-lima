# CLAUDE.md — Pichangol

Guía para Claude Code al trabajar en este repo. **Responder siempre en español**
(el equipo es de Lima, Perú).

## Qué es

**Pichangol** — marketplace de reserva de canchas (fútbol, tenis, pádel) en Lima,
estilo "Airbnb de canchas". App **Flutter** (jugador + panel del dueño) con
backends **FastAPI/Python**. Producto de **EBIM** (marca endosante; en la app del
jugador es 100% Pichangol, EBIM solo aparece discreto como respaldo).

- Director / contacto: Dennis Calagua (dcalagua@ebim.pe).
- Repo GitHub: `dcalagua/canchas-app-lima`. Paquete Flutter: `canchas_lima`.

## Reglas de trabajo

- **Idioma:** todas las respuestas al usuario en **español**.
- **Rama de desarrollo:** `claude/apk-google-maps-setup-fvpl9w`. Commitear y
  pushear ahí (`git push -u origin <rama>`). No crear PRs salvo que se pida.
- **No exponer secretos** en commits/PRs/código. El usuario ha pegado en el chat
  contraseñas/tokens (DB, Factiliza) — recordar rotarlos; nunca guardarlos en el
  repo. No incluir el identificador de modelo en artefactos del repo.
- **Builds solo por CI** (no hay Android SDK local). Ver "Build" abajo.
- **Flutter 3.24.5**: NO existe `Color.withValues`/`.a`. Por eso
  `font_awesome_flutter` está **clavado en 10.8.0** (10.9.0 rompe el build).

## App Flutter (`lib/`)

- **Estado central:** `lib/state/app_state.dart` (`appState`, ChangeNotifier).
  Persiste en `SharedPreferences` (usuario, saldo, movimientos, reservas,
  `canchasExtra`, `canchasEliminadas`).
- **Modelos:** `lib/models/models.dart` (`Cancha`, `Reserva`, `Deporte`,
  `Distrito`), `lib/models/club.dart` (`Club` = agrupación runtime de canchas por
  `club`; no se persiste).
  - `Cancha.precioHora` es **double** (precios con 2 decimales, signo `S/`).
  - `Cancha.reservable = registrada && verificada`.
  - `Cancha.pendienteVerificacion = registrada && !verificada`.
- **Datos:** `lib/data/sample_data.dart` (demo en memoria; club demo =
  `"Club Raqueta San Borja"`), `canchas_repo.dart` (Supabase tabla
  `pichangol_canchas`, fail-safe), `reservas_repo.dart`.
- **Servicios:** `propiedad_service.dart` (reclamo/OTP/estado/aprobar contra el
  backend growth), `growth_service.dart`, `places_service.dart` (Google Places),
  `supabase_service.dart`, `auth_service.dart` (Google Sign-In).
- **Pantallas clave:** `explorar_home_screen.dart` (mapa, menú con accesos admin),
  `club_detalle_screen.dart` (ficha pública + panel pendiente con diagnóstico),
  `mis_canchas_screen.dart` (panel del dueño), `registrar_cancha_screen.dart`,
  `editar_cancha_screen.dart`, `admin_reclamos_screen.dart` (admin in-app),
  `verificar_propiedad_screen.dart` (OTP), `validar_reclamo_screen.dart` (motorizado).
- **Tema:** `lib/theme.dart` (tokens del handoff EBIM: lima `#AEEA94`, bosque
  `#14463A`, etc., DM Sans). `lib/brand.dart` (nombre, eslogan, respaldo EBIM).
- **dart-defines (secrets de GitHub Actions):** `GROWTH_API_URL`
  (= `https://pg-backend-production-c176.up.railway.app`), `VERIF_API_URL`
  (= `https://eexpense-production.up.railway.app`, módulo de existencia),
  `MAPS_API_KEY`, `PLACES_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
  **OJO:** `GROWTH_API_URL` ≠ `VERIF_API_URL` (servicios distintos).

## Flujo de PROPIEDAD (clave del producto)

Existir ≠ ser dueño. Un RUC válido **no** basta. Modelo "concierge":

1. **Reclamar/registrar** (`registrar_cancha_screen` / `editar_cancha_screen`):
   crea la cancha local (`verificada=false`, `dueno=email`) y un **reclamo** en el
   backend (`POST /propiedad/reclamo`). El registro **espera** la respuesta y avisa
   si no llegó.
2. **Aprobar (piloto = aprobación directa):** el admin aprueba en el **panel web**
   (`/admin`) o en **"Reclamos (admin)"** dentro de la app. Ambos llaman a
   `aprobar_directo` → la cancha queda **`verificada=True`** al instante (sin
   validación en sitio todavía). El triage clásico NO activa; por eso el botón de
   la app usa `/propiedad/reclamo/{id}/aprobar`.
3. **Sincronizar:** la app consulta `GET /propiedad/reclamo/{cancha_id}` (método
   `PropiedadService.estado` → `AppState.sincronizarPropiedades`) al arrancar, al
   abrir "Mis canchas"/ficha, y con pull-to-refresh. Si el backend la marca
   verificada → quita el cartel "pendiente" y habilita reservas.
4. **Recuperación:** si el reclamo se perdió (p. ej. el backend se reinició), la
   ficha pendiente tiene **"Verificar estado ahora"** (diagnóstico) y **"Reenviar
   solicitud de verificación"**.

**Reglas de visibilidad (`AppState.misCanchas`):** una cancha **verificada** solo
la ve/administra su **dueño** (`dueno==email`). El "legado reclamable" (visible
para que cualquiera reclame) se limita a canchas **sin dueño y NO verificadas**.
Otros usuarios solo ven la cancha en el mapa para **reservar**.

**Borrado durable:** `canchasEliminadas` (tombstones en `SharedPreferences`) — las
canchas eliminadas no reaparecen aunque Supabase las devuelva. Re-registrar/editar
"revive" el id.

**Validación en sitio (fase posterior, ya en el código):** motorizado ingresa
código + GPS; si coincide (≤ `RECLAMO_VALIDACION_GPS_MAX_M`) activa.

## Backend growth (`backend/growth/`, FastAPI)

Desplegado en **Railway** servicio **`pg-backend`** (root dir `backend/growth`,
**auto-deploy de la rama `claude/apk-google-maps-setup-fvpl9w`**, "Wait for CI"
off → redeploy inmediato en cada push). URL pública:
`https://pg-backend-production-c176.up.railway.app`.

- `main.py` incluye routers: puntos, solicitudes, verificación física, propiedad,
  **panel** (`/admin`). Middleware persiste snapshot tras cada POST/PUT/DELETE.
- **Persistencia:** Stores en memoria + snapshot JSON a Postgres tabla
  `growth_state` vía `db/pg.py` (si `DATABASE_URL` está, fail-safe). Supabase
  session pooler, `?sslmode=require`, `conn.prepare_threshold=None` (pgbouncer).
- **Propiedad (`propiedad/`):** `reclamos.py` (crear/triage/`aprobar_directo`/
  validar en sitio), `service.py` (OTP), `identidad.py` (Factiliza DNI/RUC),
  `twilio_adapter.py` + `whatsapp_adapter.py` (OTP multicanal), `router.py`,
  `panel.py` (panel web admin).
- **Panel web `/admin`:** página HTML self-contained, co-marca **Pichangol +
  EBIM** (solo aquí), protegida por **`ADMIN_PANEL_TOKEN`** (header `X-Admin-Token`,
  no viaja en URL). Endpoints `/admin/api/*`. Aprobar = aprobación directa.
- **Config (env, `config.py`):** `ADMIN_PANEL_TOKEN`, `FACTILIZA_API_TOKEN`,
  `PICHANGOL_ADMIN_WHATSAPP`, `TWILIO_*`, `WHATSAPP_*`, `OTP_CANAL_PREFERIDO`
  (`whatsapp|twilio_whatsapp|sms`), `VALIDADOR_ACTIVA_AUTOMATICO`,
  `RECLAMO_VALIDACION_GPS_MAX_M=150`, `DATABASE_URL`.
- **Tests:** `cd backend/growth && python3 -m pytest -q` (deben pasar todos).
  Cumplimiento Ley 29733 (DNI = dato personal: solo validar dueño, no publicar).

> Existe además el servicio Railway `pg-places` y el backend
> `backend/onboarding_verificacion` (módulo de existencia / VERIF_API_URL).

## Build (GitHub Actions → APK)

- Workflow `.github/workflows/build.yml`: jobs Android + iOS.
  `--build-number=${{ github.run_number }}` (versionCode único).
- APK con nombre único `dist/pichangol-<run_number>.apk` (evita cache de APK
  viejo) y se publica en el **Release `v0.1.0`**.
- Para verificar un build: GitHub MCP `mcp__github__actions_list/get` (filtrar por
  rama). El `run_number` == número de build == nombre del APK
  (`pichangol-<n>.apk`). Link de descarga:
  `https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0`.
- Tras instalar, confirmar versión en Ajustes → Apps → Pichangol → build N.

## Diseño (handoff)

`docs/handoff_v2/` (referencia). Paleta oficial EBIM, **DM Sans**, premium
minimalista. Logo: wordmark "pichang(o)l" con la "o" = pelota (anillo + punto
lima). Splash en verde claro `#AEEA94` con el pin + amarillo `#F2C94C` donde
aporta. Eslogan: "Reserva, juega, repite." La co-marca con EBIM solo en el panel
web admin; la app del jugador es 100% Pichangol.

## Pendientes / backlog

- Conexión con redes sociales (Fase 1): stub, **habilitado solo tras verificar
  dueño** (`docs/conexiones-sociales.md`).
- Política **RLS de DELETE** en `pichangol_canchas` (para que el borrado también
  sea en la nube / sobreviva reinstalación).
- Validación en sitio (motorizado) como fase de endurecimiento.
- Apelación a Meta (cuenta bloqueada) + Twilio Sandbox como respaldo OTP.
- Idea biométrica para validación de dueño (madurar).

## Tips operativos

- La red del entorno de Claude **bloquea** llamadas salientes al backend de
  Railway (proxy 403). No intentar curl al backend; usar el **botón de
  diagnóstico in-app** o pedir captura al usuario.
- Cada push a la rama **redespliega `pg-backend`** (lo reinicia). Evitar pushes
  innecesarios mientras el usuario prueba el flujo de reclamo en vivo.
