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
  backend growth), `growth_service.dart`, `places_service.dart` (Google Places;
  heurística de detección en `docs/heuristica-deteccion-canchas.md`),
  `supabase_service.dart`, `auth_service.dart` (Google Sign-In).
- **Pantallas clave:** `explorar_home_screen.dart` (mapa + menú jugador/dueño),
  `club_detalle_screen.dart` (ficha pública + panel pendiente con diagnóstico),
  `mis_canchas_screen.dart` (panel del dueño, agrupado por local),
  `agregar_cancha_screen.dart`, `registrar_cancha_screen.dart`,
  `editar_cancha_screen.dart`, `reservas_dueno_screen.dart` (cobros del dueño),
  `verificar_propiedad_screen.dart` (OTP), `validar_reclamo_screen.dart` (motorizado).
  > La administración del SaaS (reclamos, modo de aprobación) NO está en el APK:
  > vive en la **torre de control web** `/admin` (ver backend growth).
- **Tema:** `lib/theme.dart` (tokens del handoff EBIM: lima `#AEEA94`, bosque
  `#14463A`, etc., DM Sans). `lib/brand.dart` (nombre, eslogan, respaldo EBIM).
- **dart-defines (secrets de GitHub Actions):** `GROWTH_API_URL`
  (= `https://pg-backend-production-c176.up.railway.app`), `VERIF_API_URL`
  (= `https://eexpense-production.up.railway.app`, módulo de existencia),
  `MAPS_API_KEY`, `PLACES_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `APP_API_KEY` (secreto app↔backend; el APK lo manda en `X-App-Key`),
  `LANDING_BASE_URL` (dominio de marca para el enlace público de la landing).
  **OJO:** `GROWTH_API_URL` ≠ `VERIF_API_URL` (servicios distintos).

## Dominio oficial: `pichangol.app`

El dominio de marca **YA ESTÁ REGISTRADO Y VIVO**. En Railway (`pg-backend`) el
custom domain **`www.pichangol.app`** apunta al servicio (SSL activo, verde);
también existe `pg.ebim.pe`. De aquí en adelante **el dominio público de las
landings de canchas/academias es `https://www.pichangol.app`**, NO el host
`*.up.railway.app` (ese sigue solo para la API del APK).

- **Landing pública:** `https://www.pichangol.app/l/{academiaId}` (motor FastAPI
  en `backend/growth/marketing/`, ruta `GET /l/{id}`).
- **Cómo se arma la URL:** el APK usa el dart-define `LANDING_BASE_URL`
  (`lib/services/pagos_service.dart`, `landingUrl`); si está vacío cae al host del
  API. El backend emite `canonical`/`og:url` con la env `LANDING_BASE_URL`
  (`config.py` → `marketing/router.py` → `marketing/landing.py`), fallback a
  `PUBLIC_BASE_URL` o al host de la request.
- **Para activarlo hay que setear el valor en dos lados** (por entorno):
  secret `LANDING_BASE_URL` en GitHub Actions (para el APK) **y** variable
  `LANDING_BASE_URL` en Railway `pg-backend` (para el HTML) =
  `https://www.pichangol.app`.
- El apex `pichangol.app` (sin `www`) queda libre para la home de marketing
  (`landing/index.html`).

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
- **Panel web `/admin` = TORRE DE CONTROL del operador (SaaS).** Página HTML
  self-contained, co-marca **Pichangol + EBIM** (solo aquí), protegida por
  **`ADMIN_PANEL_TOKEN`** (header `X-Admin-Token`, no viaja en URL). Endpoints
  `/admin/api/*`. Aquí el operador aprueba/rechaza reclamos y configura el **modo
  de aprobación**: `marcha_blanca` (aprobar activa al instante) | `nuevo_flujo`
  (exige validación en sitio). Global + override por cancha (`/admin/api/modo`,
  `/admin/api/modo/cancha`; lógica en `reclamos` + `stores.modo_aprobacion`).
  Cada tarjeta muestra **fecha/hora** y un **mapa de desde dónde se envió la
  solicitud** (GPS del dispositivo). El operador puede **exigir ubicación al
  reclamar** (`/admin/api/ubicacion`, `config.exigir_ubicacion_reclamo`): si se
  activa, sólo se puede **Aprobar** cuando ese GPS está a ≤
  `RECLAMO_UBICACION_MAX_M` (150 m) de la cancha (anti-fraude "estás en el lugar").
  Ver `docs/flujo-reclamo-propiedad.md`.
  > **Separación de responsabilidades:** el **APK** es para **jugadores y dueños
  > de cancha** (+ rol de campo "Verificador"); **toda la administración del SaaS**
  > (aprobaciones, configuración) vive en la **torre de control web**, no en el APK.
  > **Auth:** los endpoints ADMIN de `propiedad/router.py` (`/reclamo/{id}/triage`,
  > `/aprobar`, `/activar`, `GET /reclamos`, `/config/modo*`, `/aprobar-manual`) y
  > `PUT /config/incentivos/{clave}` exigen **`X-Admin-Token`** (`_require_admin`,
  > fail-closed 503 sin token). Público (app del dueño): `POST /reclamo`,
  > `GET /reclamo/{cancha_id}` (estado), `/lugar-reclamado`, `/otp/*`,
  > `/reclamo/validar` (validador, protegido por código+GPS). Aprobación por
  > WhatsApp usa `aprobar_por_codigo` (firma Twilio), no el endpoint HTTP.
- **Config (env, `config.py`):** `ADMIN_PANEL_TOKEN`, `FACTILIZA_API_TOKEN`,
  `PICHANGOL_ADMIN_WHATSAPP`, `TWILIO_*`, `WHATSAPP_*`, `OTP_CANAL_PREFERIDO`
  (`whatsapp|twilio_whatsapp|sms`), `VALIDADOR_ACTIVA_AUTOMATICO`,
  `RECLAMO_VALIDACION_GPS_MAX_M=150`, `RECLAMO_UBICACION_MAX_M=150`, `DATABASE_URL`,
  `APP_API_KEY` (clave app↔backend: si está seteada, los endpoints PÚBLICOS de
  `propiedad/router.py` exigen la cabecera `X-App-Key` — solo el APK oficial la
  trae; vacía = no se exige, para rollout gradual). Debe coincidir con el
  dart-define `APP_API_KEY` del APK.
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

## Marketplace Pichangol

Feed **global único** de productos (raquetas, pelotas, indumentaria…) que
publican **dueños/academias y cualquier usuario VERIFICADO**. El comprador paga
en la app (Culqi) y **coordina la entrega por chat** con el vendedor; Pichangol
cobra su comisión (5% mín S/2) y deja el **neto "por recibir"** del vendedor
(misma contabilidad que una reserva online).
- **Modelo/datos:** `lib/models/producto.dart`, `lib/data/productos_repo.dart`
  (Supabase tabla `pichangol_productos` + bucket público `productos`, fail-safe).
- **Comprador:** `marketplace_screen.dart` (feed + buscador + categorías) →
  `producto_detalle_screen.dart` (Comprar con `PagoTarjeta.cobrar` →
  `PagosService.venta` → coordinar por chat). Acceso: Perfil → "Marketplace".
- **Vendedor:** `mis_productos_screen.dart` + `editar_producto_screen.dart`.
  Acceso: **botón flotante "Vender" DENTRO del Marketplace** (no en el Perfil) y
  Modo anfitrión → "Mi tienda".
  **Candado:** publicar exige `appState.puedeVender` (verificado **o** dueño);
  si no, manda a "Verificar identidad". Badge "Vendedor verificado ✓" (icono
  `Icons.verified` lima) en el feed y la ficha vía `appState.estaVerificado`.
- **Backend:** `POST /pagos/venta` (`backend/growth/pagos/router.py`), tipo de
  pago `venta_producto`, idempotente por `venta_id`; entra en
  `liquidaciones()`/"por recibir". El catálogo NO vive en el backend growth (es
  Supabase).

## Diseño (handoff)

`docs/handoff_v2/` (referencia). Paleta oficial EBIM, **DM Sans**, premium
minimalista. Logo: wordmark "pichang(o)l" con la "o" = pelota (anillo + punto
lima). Splash en verde claro `#AEEA94` con el pin + amarillo `#F2C94C` donde
aporta. Eslogan: "Reserva, juega, repite." La co-marca con EBIM solo en el panel
web admin; la app del jugador es 100% Pichangol.

**Estándar de UI/UX: estilo Airbnb (siempre).** Toda pantalla/componente nuevo
sigue el lenguaje Airbnb sobre la paleta EBIM:
- **Pastillas/chips:** blancas, borde gris muy suave (`#E4E4E4`), relieve leve
  (sombra `0x0F000000`), esquinas muy redondeadas. Seleccionado = relleno gris
  plomo (`#EBEBEB`) o tinte lima, **nunca borde negro**.
- **Tarjetas:** fondo blanco, radio 16–18, sombra sutil, sin bordes duros.
- **Tipografía:** DM Sans (equivalente a Cereal), jerarquía clara, tamaños
  generosos (títulos 15–19+, texto charcoal `#222`).
- **Fondos** claros; acentos con lima/bosque, no saturar.
- **Pagos/estados:** caja centrada animada (procesando → check), logos de marca
  reales (Yape morado, Visa/Mastercard). Ver `widgets/marcas_pago.dart`,
  `widgets/pago_procesando.dart`.
- **Popups: UN SOLO formato (REGLA de todo el app).** Todo diálogo de
  confirmación/aviso usa `widgets/dialogo_pichangol.dart`: `confirmarPichangol(
  context, titulo:, mensaje:, textoConfirmar:, destructivo:, icono:)` (devuelve
  `bool`) para Sí/No, o `avisarPichangol(...)` para un solo botón. Formato: tarjeta
  blanca radio 24, ícono opcional en burbuja, título charcoal, mensaje tenue,
  primario relleno lima (rojo `clayOscuro` si `destructivo`), secundario de texto.
  **No** usar `AlertDialog`/`showDialog` suelto con estilos propios en pantallas
  nuevas; migrar los viejos a este componente cuando se toquen.
- **Íconos del menú lateral CON COLOR (Airbnb "con vida"):** los íconos de los
  rails/barras de navegación van coloreados por sección (no gris plano). Mensajes
  usa `widgets/icono_chat_pichan.dart` (burbuja verde WhatsApp con "P").
- **Avatares SIEMPRE con foto real:** cualquier avatar de jugador (ranking,
  jugadores disponibles, retos —incluido el reto de dobles—, chat, perfil, etc.)
  DEBE mostrar la foto del perfil (`appState.fotoDe(email)` o `usuario.fotoUrl`),
  cayendo a la inicial de color solo si no hay foto. Nunca dejar un ícono
  genérico donde va una persona. Si la lista trae correos, precargar perfiles
  con `appState.cargarPerfiles([...])` para que la foto esté disponible.
- **Contenido CENTRADO en pantallas anchas (REGLA de todo el app):** en tablet u
  horizontal el contenido NUNCA se estira de borde a borde; va **centrado con
  ancho máximo**. Envolver el `body:` (o el ListView/formulario) con
  `AnchoTablet` (`lib/widgets/responsive.dart`, canónico) — o el equivalente
  `AnchoLectura`. `maxWidth` según el contenido: ~560–640 para menús/formularios
  de una columna (p. ej. Perfil), ~760–900 para fichas/listas con tarjetas. En
  móvil vertical no cambia nada (devuelve el hijo tal cual). Toda pantalla nueva
  debe respetarlo; el spinner/loader también centrado.

## Pendientes / backlog

- Conexión con redes sociales (Fase 1): stub, **habilitado solo tras verificar
  dueño** (`docs/conexiones-sociales.md`).
- Política **RLS de DELETE** en `pichangol_canchas` (para que el borrado también
  sea en la nube / sobreviva reinstalación).
- Validación en sitio (motorizado) como fase de endurecimiento.
- Apelación a Meta (cuenta bloqueada) + Twilio Sandbox como respaldo OTP.
- Idea biométrica para validación de dueño (madurar).
- **Validación de documento en "Verificar identidad" (por país):** ya implementado
  Perú (DNI vs RENIEC/Factiliza; trae fecha de nacimiento → edad para categorías
  de campeonato; no guarda foto del doc). Pendientes:
  1. **Ecuador (cédula):** el usuario tiene un API propio → falta enchufarlo
     (endpoint + token) y activar el camino "por número" poniendo `consultaDoc:
     true` en `PaisConfig['EC']` + `consultar_cedula` en el backend (espejo de
     `identidad.consultar_dni`). Devolver también fecha de nacimiento.
  2. **Bolivia (CI):** no hay API oficial → **OCR on-device** (recomendado:
     `google_mlkit_text_recognition`, gratis/offline) para (a) confirmar que la
     imagen ES un documento (palabras "CÉDULA/IDENTIDAD/ESTADO PLURINACIONAL",
     patrón de número/fecha) y bloquear imágenes cualquiera, y (b) extraer nº +
     nacimiento. **Ojo build:** agregar plugin nativo puede romper Flutter 3.24.5
     → probar en CI aislado antes de mergear. Alternativa sin plugin: OCR en la
     nube (Google Vision), pero cuesta y viaja el dato personal.
- **Explorar carga rápida (idea del usuario, para más adelante):**
  1. **GPS colgado con mala señal:** Explorar se queda en "Detectando tu
     ubicación…" indefinidamente. Fix: timeout al GPS + caer a última ubicación
     conocida / default por país + botón reintentar; mostrar canchas ya con esa
     ubicación y reordenar por cercanía cuando el GPS resuelva.
  2. **Cosechar canchas a Supabase (no bajar todo en vivo cada vez):** llenar
     `pichangol_canchas` una vez con las descubiertas de Google (place_id +
     nombre + dirección + lat/lng + deporte) y que la app LEA de la tabla
     (instantáneo, offline-friendly, menos costo Google); la reserva sigue en
     vivo. Cuidados: **no** guardar fotos de Google (caducan + licencia) → foto
     diferida/placeholder en la lista y foto real sólo en canchas reclamadas;
     **refresco periódico** de la zona (frescura + ToS). Prioridad: que la lista
     NO se bloquee por GPS ni por fotos.

## Tips operativos

- La red del entorno de Claude **bloquea** llamadas salientes al backend de
  Railway (proxy 403). No intentar curl al backend; usar el **botón de
  diagnóstico in-app** o pedir captura al usuario.
- Cada push a la rama **redespliega `pg-backend`** (lo reinicia). Evitar pushes
  innecesarios mientras el usuario prueba el flujo de reclamo en vivo.
