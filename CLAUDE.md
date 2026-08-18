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

- **ESTO ES DESARROLLO REAL PARA PRODUCCIÓN. NO es demo ni piloto.** (Regla del
  director, repetida.) No tomar atajos justificados con "para el piloto está bien"
  ni "es solo demo": construir cada feature **de forma correcta y completa, lista
  para prod** (casos borde, datos reales, robustez). Si una solución tiene una
  versión "simple" y una "correcta", implementar la **correcta**; si de verdad hay
  que diferir algo, avisarlo explícito con su costo, no asumir que "por ser piloto
  da igual". Las referencias históricas a "piloto/QAS" en este doc son de
  ambientes/infra, NO permiso para bajar la calidad del código.
- **Idioma:** todas las respuestas al usuario en **español**.
- **Rama de desarrollo:** `claude/apk-google-maps-setup-fvpl9w`. Commitear y
  pushear ahí (`git push -u origin <rama>`). No crear PRs salvo que se pida.
- **No exponer secretos** en commits/PRs/código. El usuario ha pegado en el chat
  contraseñas/tokens (DB, Factiliza) — recordar rotarlos; nunca guardarlos en el
  repo. No incluir el identificador de modelo en artefactos del repo.
- **Builds solo por CI** (no hay Android SDK local). Ver "Build" abajo.
- **Scripts SQL → SIEMPRE dar el LINK de GitHub** (no solo la ruta): cada vez que
  creas o mencionas un `.sql` que el usuario debe correr, entrégale el enlace
  clickable `https://github.com/dcalagua/canchas-app-lima/blob/<rama>/<ruta>`
  (rama actual `claude/apk-google-maps-setup-fvpl9w`). El usuario corre los SQL a
  mano en Supabase.
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
también existe `pg.ebim.pe`. **`https://www.pichangol.app` es el dominio de
marca/PRODUCCIÓN** de las landings. En el **piloto** (dev/QAS, provisional) las
landings usan **`https://pg.ebim.pe`** y se RESERVA `pichangol.app` para PROD
(ver «Estrategia de ambientes» más abajo). El host `*.up.railway.app` queda solo
para la API del APK.

- **Landing pública:** `https://www.pichangol.app/l/{academiaId}` (motor FastAPI
  en `backend/growth/marketing/`, ruta `GET /l/{id}`).
- **Cómo se arma la URL:** el APK usa el dart-define `LANDING_BASE_URL`
  (`lib/services/pagos_service.dart`, `landingUrl`); si está vacío cae al host del
  API. El backend emite `canonical`/`og:url` con la env `LANDING_BASE_URL`
  (`config.py` → `marketing/router.py` → `marketing/landing.py`), fallback a
  `PUBLIC_BASE_URL` o al host de la request.
- **Para activarlo hay que setear el valor en dos lados** (por entorno):
  secret `LANDING_BASE_URL` en GitHub Actions (para el APK) **y** variable
  `LANDING_BASE_URL` en Railway `pg-backend` (para el HTML) = `https://pg.ebim.pe`
  en el **piloto**, `https://www.pichangol.app` en **PROD**.
- El apex `pichangol.app` (sin `www`) queda libre para la home de marketing
  (`landing/index.html`).

## Estrategia de ambientes (piloto → prod)

**Decisión vigente (jul-2026):** para el **piloto / primeras pruebas con
academias amigas** se usa **UN SOLO ambiente** (el actual: Railway `pg-backend` +
Supabase dev). **DEV y QAS colapsados**; NO se monta un QAS separado todavía
(acelera salir a pruebas). Cuando el piloto esté sólido se monta el PROD real.

- **Piloto (dev/QAS, ahora):** dominio de landings **`https://pg.ebim.pe`** — se
  reserva la marca. Culqi en `sk_test`. Supabase dev.
- **PROD real (fase posterior):** ambiente dedicado — Supabase prod **con
  backups** + Culqi `sk_live` + AAB a Play Store (`pe.ebim.pichangol`). Al
  montarlo se **mueve** el custom domain `www.pichangol.app` de `pg-backend` al
  backend PROD, y el piloto queda con `pg.ebim.pe` / el host `*.up.railway.app`.
  Ahí `LANDING_BASE_URL = https://www.pichangol.app`.
- Por qué reservar `pichangol.app` para PROD: no exponer la marca ni el SEO a
  páginas de prueba, y evitar que enlaces de piloto compartidos bajo el dominio
  de marca se rompan en el corte a PROD (los datos del piloto son desechables).
- Referencia técnica del salto a QAS/PROD dedicado: `docs/entornos-qas-prod.md`
  y `docs/checklist-qas.md`.

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
  dart-define `APP_API_KEY` del APK. `CM_REQUIERE_PRO` (candado del community
  manager con IA: si `1`, sólo un correo con **Pichangol Pro** vigente
  —`stores.pro_activo(email)`— puede generar post/reel o activar el CM;
  `marketing/router.py:_require_pro` responde **402 `requiere_pro`**. Fail-open:
  apagado por defecto y no bloquea a APKs que no mandan `email` — sólo a quien SÍ
  se identifica y no es Pro. El APK manda `email` y ante 402 ofrece activar Pro).
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

## Mensajería: arquitectura DEVICE-FIRST (cache, tal cual WhatsApp)

**REGLA de arquitectura (transversal a TODA la mensajería):** chats, inbox,
estados/historias, canales, avatares y media deben comportarse **exactamente
como WhatsApp** — **pre-cargados y cacheados**, nunca "cargando" al reabrir. Toda
pantalla/feature nueva de mensajería se diseña **device-first**: pinta al
instante desde el teléfono y solo sincroniza/actualiza en segundo plano.

Piezas ya implementadas (reusar, no reinventar):
- **Inbox (`mensajes_screen.dart`):** caché local **SQLite** (`data/db_local.dart`,
  `DbLocal.leerConvs/guardarConvs`) → pinta al instante; refresco en silencio
  (`_cargar(silencioso:true)`), sin spinner de pantalla completa. **Anti-shrink:**
  la bandeja NUNCA se encoge en un refresco (conserva de la caché los chats que
  una pasada no reconstruyó porque su fuente aún no cargó); auto-refresca cuando
  cargan academias/alumnos. El borrado explícito se respeta con `chatOculto`.
- **Chat (`chat_screen.dart`):** mensajes device-first desde SQLite; solo baja lo
  nuevo. Fotos/avatares con **`CachedNetworkImage`/`CachedNetworkImageProvider`**
  (caché en disco vía `flutter_cache_manager`), nunca `NetworkImage` crudo.
- **Estados/Novedades:** pre-cache de la media de las historias vigentes
  (`AppState._precacharEstados`), avatares/íconos de Novedades pre-calentados
  (`novedades_screen._precachar` + `CachedNetworkImageProvider`); video
  device-first (archivo local → caché → red y baja a caché).
- **Canales:** lista cacheada (`AppState.leerCanalesCache/guardarCanalesCache`) y
  detalle device-first (`_seedDesdeCache`), video con la misma estrategia.
- **Perfiles** (nombre/foto) persistidos en `SharedPreferences`
  (`AppState._perfiles`) para no re-bajarlos cada vez.

**Al agregar cualquier cosa nueva a mensajería:** primero pregúntate "¿esto cómo
lo cachea WhatsApp?" y hazlo cache-first (disco + pre-warm) antes de mostrar
spinners. Un spinner de pantalla completa al reabrir un chat/inbox/estado se
considera un bug.

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
- **NADA de campos de texto libre para el usuario (REGLA de todo el app).**
  Toda entrada de datos del usuario se hace por SELECCIÓN (chips, listas,
  pickers, toggles) con opciones curadas — nunca un TextField libre para datos
  descriptivos. Motivo: data limpia y filtrable, cero moderación de contenido,
  menos fricción de tipeo. Texto libre SOLO donde es inevitable por naturaleza:
  nombre propio, celular, búsquedas, mensajes de chat y montos. Si un feature
  "necesita" un campo libre, proponer primero la versión con opciones.
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

- **Community Manager AUTÓNOMO (servicio estrella, ingreso recurrente):** la
  visión del director NO es "generar posts para que el dueño publique a mano"
  (eso ya existe, `community_manager_screen.dart` + `backend/growth/marketing/`).
  Es un **agente que mueve las redes de la academia/cancha SOLO, sin intervención
  manual** (suscripción ~S/100/mes): genera foto/video/copy/hashtags y **publica
  automático** en su Instagram/Facebook, en un calendario; el dueño solo entra a
  sus redes y ve que ya se posteó. Debe ser **configurable** (auto vs
  aprobar-antes; frecuencia; tono). **Estado (Fase 0 ya en código):**
  (1) **generación de media** — flyer de marca (`marketing/flyer.py`, Pillow,
  fuente empaquetada, plantillas por tipo) **y reels/video** (`marketing/reel.py`,
  Pillow+`imageio-ffmpeg` **empaquetado**, Ken Burns con variedad de movimiento,
  9:16, con **música ORIGINAL libre de regalías** —`marketing/musica.py`, síntesis
  numpy pad+kick por mood según el tipo, muxeada como AAC); (2) **scheduler** (`main.py` cron 30 min → `cm.procesar_cm_
  pendientes` en hilo) pre-arma flyer+reel por academia suscrita; (3) **auto-
  publish Meta** — `redes.publicar(texto, imagen_url, video_url)` sube foto **o
  reel** (IG Reels: contenedor `media_type=REELS` + poll de estado + publish; FB
  `/videos`), con **modo sandbox** que simula todo (test end-to-end sin Meta);
  el CM lo dispara solo si `auto_publicar` + redes conectadas (`cm._auto_publicar`
  usa `config.PUBLIC_BASE_URL` para la URL pública de la media). **APK:** en "Post
  del día" hay toggles "Publicar automático" + "Publicar solo en mis redes" y botón
  "Crear/Compartir reel". **Bloqueador real:** **App Review + Business Verification
  de Meta** (permisos `pages_manage_posts` / `instagram_content_publish`; la ruta
  `produccion` no corre hasta que Meta apruebe — ojo cuenta ya tuvo problemas).
  Pendiente: (4) guardrails/marca, música licenciada en el reel, push "tu post está
  listo" al dueño (vía FCM de Supabase, el backend growth no hace FCM), IA de imagen
  para negocios sin buenas fotos, y el candado "usuario pro" (#28).
- **Perfil/página de cada academia = HUB (NO clonar Facebook):** decisión de
  producto — NO construir una red social horizontal desde cero (efectos de red
  brutales, alto costo, bajo ROI). En su lugar, la **landing pública
  (`/l/{id}`, SEO en pichangol.app)** evoluciona a la "página" del negocio
  (galería, horario, reseñas, botón **Seguir**), y el engagement in-app se hace
  con lo que YA existe (**canales** = difusión tipo WhatsApp Channels, **estados/
  historias**, **rankings**, **retos**, **marketplace**). El CM autónomo empuja
  el contenido HACIA AFUERA (IG/FB, donde ya está la audiencia). Tesis: **capa
  social VERTICAL (deporte) sobre un core transaccional (reservas/pagos)**, no un
  FB genérico. Comparable de mercado que valida el modelo: **Playtomic** (reservas
  + comunidad + rankings + perfiles de jugador); otros: MindBody/ClassPass,
  Spond/Heja (gestión de equipos). Pendiente: barrido de mercado ligero.
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

### Memoria sesión pagos/reservas (ago-2026)

**Ya HECHO (en el APK):**
- **Reserva online = pagada automático** (`pagado=true` si `cobro=='online'`): el
  dueño NO marca como pagado lo que el jugador pagó por Culqi. Efectivo/seña sí
  los marca (hay efectivo por cobrar).
- **Trazabilidad `medioPago`** en `Reserva` (yape/tarjeta/efectivo/sena/manual):
  se captura al reservar (online lee `PagoTarjeta.ultimoMetodo`), viaja a Supabase
  (col `medio_pago`) y se muestra como chip en Reservas del dueño.
- **Reporte "Cuánto vas a recibir"**: `_ResumenComision` (reporte_canchas) ahora
  se calcula de `appState.movimientos` (los mismos que la billetera), desglosado
  por fuente (comisión del pago vs de tu saldo) → **cuadra EXACTO con "Por
  recibir"** de la billetera. Antes estimaba 5% local y no cuadraba.
- **Recordatorio LOCAL "cobra en efectivo"** (`recordatorio_service.dart`,
  `flutter_local_notifications` + `timezone`, modo INEXACTO): se programa en el
  teléfono del DUEÑO al sincronizar, 30 min antes, para reservas efectivo/futuras/
  no pagadas de sus canchas; se cancela al marcar pagado. **Requiere desugaring**
  (inyectado en `tool/configure_platforms.py::configurar_desugaring`).
- **Fix privacidad billetera**: `sincronizarSaldo` refleja SIEMPRE el backend
  (lista vacía → limpia); `_limpiarDatosDeSesion` vacía movimientos/saldo. Un
  jugador ya NO ve los movimientos del dueño.
- **Push "tu cancha fue aprobada"** (`supabase/functions/push-aprobacion`, el
  growth la dispara al aprobar) — código listo, falta DEPLOY (tarea laptop).
- **"Dejar en virgen"** ya vacía de verdad: local + nube + tombstones (canchas y
  academias) + reclamos + billetera del backend (`/pagos/reset-mi-billetera`) +
  colas de contabilidad. Sin data demo (no se auto-siembra academia/canchas, saldo 0).

**DECISIONES de producto:**
- **Seña**: la decide el DUEÑO por cancha (`senaPct`), NO el jugador (elegirla
  mataría la protección anti no-show + baja conversión). Default recomendado 30% ⭐.
  Seña por franja pico/valle = **post-piloto** (falta data de no-shows).

**PENDIENTES (ver tasks):** SQL `medio_pago` en Supabase; deploy Edge Function
`push-aprobacion` + envs Railway; SQL limpieza (academia demo + RLS academias);
filtro Online/Efectivo en Reservas + medio en reporte/estado de cuenta;
auth por usuario en `/pagos/movimientos` (PROD).

### Memoria sesión duración de turno + Servicios + Pro (ago-2026)

**Ya HECHO (en el APK):**
- **Bug "duración 1.5h": el cliente veía 1h.** Cadena de fixes:
  (1) `AppState.canchaVigente(c)` → versión más fresca por id (canchasExtra >
  canchasRemotas > descubiertas), con **fallback por sitio**: si lo mostrado es la
  cancha DESCUBIERTA de Google (`registrada=false`, id=place_id), cae a la MISMA
  cancha registrada cercana (Supabase) para usar su duración/precio reales.
  `club_detalle`/`cancha_detalle` leen `canchaVigente` y la ficha **baja canchas
  frescas de Supabase al abrir** (`_refrescarCanchasYFicha`).
  (2) `CanchasRepo.actualizar` ahora hace **UPSERT** (antes UPDATE): persiste aunque
  la fila no existiera. `_toRow` manda `duracion_slot_min` siempre.
  (3) **Causa raíz real:** la misma cancha tenía **VARIAS filas en Supabase** (ids
  distintos por re-registros de prueba); `_dedupPorLugar` conservaba en otro equipo
  un id que seguía en 60. Fix: `_propagarEdicionADuplicados` propaga
  duración/precio/horario/seña/valle a todos los duplicados del mismo lugar (local
  + nube) al editar. SQL: `docs/piloto/supabase_duracion_slot.sql` (columna),
  `docs/piloto/diag_canchas_duplicadas.sql` (ver duplicados),
  `docs/piloto/dedupe_canchas.sql` (dejar 1 fila: reapunta reservas + borrado lógico).
- **Verificación de guardado en la nube:** al editar (no reclamo) la app reescribe y
  RELEE `duracion_slot_min` de Supabase; si no persistió (columna/RLS) avisa al dueño
  en rojo en vez de "✅ actualizada" (`CanchasRepo.leerDuracion`).
- **Diagnóstico TEMPORAL en la ficha** (`club_detalle`): línea roja
  "🔧 dur Nmin · id … · reg … · fuente …" (`AppState.fuenteCancha`). **Quitar** una
  vez cerrado el tema de duración.
- **Servicios Pichangol OCULTO en el piloto** por feature flag
  `lib/config/features.dart` → `kServiciosPichangolActivo = false`. Se ocultaron
  TODOS los accesos (Mis canchas, academia shell/Mi academia, crear/editar academia,
  "Post del día", "Generar con IA" en canales). Código y backend intactos → reactivar
  = poner el flag en `true`.
- **Versión visible en Ajustes:** pie con "Pichangol · versión X (build N)" +
  `pichangol-N.apk`, toca para copiar (`package_info_plus`). El build = `run_number`
  del CI = nombre del APK.

**PENDIENTES nuevos (ver tasks) — pedido del director:**
- **Push al JUGADOR cuando el dueño le crea una RESERVA MANUAL** (hoy la reserva
  manual no notifica al usuario). Reusar arquitectura FCM/Edge Functions (device-first).
- **Notificaciones de ACADEMIA:** matrícula de alumno, pagos/cuotas (vencida, pagada),
  etc. → push al alumno/apoderado y/o al dueño.
- **Candado PRO:** **Reserva manual** y **Bloqueo de horas** pasan a ser features de la
  **suscripción Pichangol Pro** (gate `appState` tipo `esPro`/`pro_activo`, con CTA
  "Hazte Pro" — ver `hazte_pro_screen.dart` y `stores.pro_activo` del backend).
- **Historial del JUGADOR + PUNTOS acumulables (incentivo cruzado):** el jugador
  tiene su historial de reservas (online + efectivo, con estado pagado/por pagar).
  El efectivo se valida cuando el DUEÑO lo marca pagado (`AppState.marcarPago`). Se
  conecta con **puntos acumulables** (beneficios Pichangol/PCG): los puntos del
  efectivo recién se acreditan cuando el dueño marca pagado → el jugador **exige**
  al dueño que marque el efectivo (sube la confirmación de cobros). Pendiente:
  pantalla de historial del jugador + motor de puntos (regla, caducidad, canje) +
  gatillo (online auto, efectivo al marcar). Ojo: la reserva MANUAL (cliente propio
  del dueño) hoy queda fuera de comisión/billetera; evaluar si acumula puntos.

### Horarios de cancha (apertura/cierre) y cruce de medianoche
- `Cancha.horariosSlots()` genera los INICIOS reservables de apertura a cierre en
  pasos de `duracionSlotMin`; un slot solo entra si cabe COMPLETO antes del cierre
  (cierre 23:00 + 1h → último turno 22:00–23:00).
- **Cierre que CRUZA MEDIANOCHE:** si `cierre <= apertura`, el cierre cae al día
  siguiente (`fin += 24h`). Cubre "hasta medianoche" (07:00→00:00, último turno
  23:00–00:00), cancha nocturna (18:00→02:00) y **24 h** (00:00→00:00).
  `minutosEnHora` envuelve con `% 24` (1440 → `00:00`).
- **Fecha calendario REAL (producción):** los turnos de madrugada (hora < apertura)
  se ligan a su fecha real = día base + 1. Helpers en `Cancha`: `slotEsMadrugada`,
  `fechaRealSlot(baseIso, hora)`, `reservaEnSesion(baseIso, rFecha, rHora)`. Toda
  ocupación/bloqueo/precio/guardado de reserva usa la fecha real por slot
  (`agregarReservasJugadorMulti`, `agregarReservaManual`, `club_detalle._fechaSlot`,
  `cancha_detalle`). La **agenda** muestra la SESIÓN del día (incluye la madrugada
  del día siguiente vía `reservaEnSesion`); KPIs y match por slot usan la fecha real.
- `reserva_manual_screen._ocupada` también usa la fecha real por slot (marca
  ocupado un slot de madrugada ya tomado).

### Nota billetera/reservas (recordatorio de diseño)
- **Billetera (`cuenta_screen`)** = plata que pasa por la APP: pagos ONLINE del
  dueño ("por recibir"/liquidación), comisiones, recargas, Pro. Re-sincroniza al
  abrir (`flushContabilidad` + `sincronizarSaldo`) para reflejar un pago online
  recién hecho.
- **Reserva MANUAL del dueño** (`agregarReservaManual`, `traidaPorApp:false`) =
  cliente propio, **fuera de comisión**: NO genera movimiento en la billetera (a
  propósito); aparece en **reporte/caja del día**. Solo las reservas pagadas por
  la app (online) generan "por recibir".
- **Sync config de canchas entre equipos del mismo dueño:** la nube manda.
  `cargarCanchasRemotas` → `_sincronizarConfigLocalDesdeNube` actualiza
  `canchasExtra` (duración/precio/horario) desde Supabase. "Mis canchas" la llama
  al abrir y en pull-to-refresh.
- **`build` del footer de Ajustes = versionCode de Android** (arm64 → 2xxx), NO el
  número del APK (`pichangol-N.apk`). Para comparar equipos basta que coincida.

## Tips operativos

- La red del entorno de Claude **bloquea** llamadas salientes al backend de
  Railway (proxy 403). No intentar curl al backend; usar el **botón de
  diagnóstico in-app** o pedir captura al usuario.
- Cada push a la rama **redespliega `pg-backend`** (lo reinicia). Evitar pushes
  innecesarios mientras el usuario prueba el flujo de reclamo en vivo.
