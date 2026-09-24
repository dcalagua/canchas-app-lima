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
- **PRODUCCIÓN SOLO CON AUTORIZACIÓN EXPLÍCITA (regla del director, ago-2026):**
  nada toca PRD hasta que el director diga "pasa a PRD" / "sube a producción".
  Eso incluye: push a la rama `prd`, migraciones o SQL sobre **PCG-PRD**
  (`xjoqotzfgniinxyxvhxj`), variables de `pg-backend-prd` en Railway y builds
  de PRD. Sin esa orden, se trabaja SIEMPRE contra dev/QAS: rama
  `claude/apk-google-maps-setup-fvpl9w`, Supabase **"Pichangol"**
  (`iuwnpjbxsltgmsybooeg`, otra cuenta — el conector MCP de Claude NO la ve) y
  torre `https://pg-backend-production-c176.up.railway.app/admin`. Ojo: el
  conector Supabase de Claude sí ve PCG-PRD, así que es fácil tocar producción
  por accidente; ante la duda, preguntar. Cada torre muestra a qué proyecto
  habla en Mantenimiento → Limpiar almacenamiento (línea "Base de datos / Storage").
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
- **MULTI-PAÍS SIEMPRE (regla del director, ago-2026):** TODO lo que se
  construya debe estar pensado para los 3 países del despliegue — **Perú,
  Bolivia y Ecuador** — desde el día uno:
  - **Moneda por país**: usar `paisActual.moneda` (S/, Bs, $) o
    `monedaDeCoordenadas(...)` para lo anclado a una sede; NUNCA "S/" fijo en
    UI, backend ni páginas públicas. Lo que viaja a la nube guarda su moneda
    (p. ej. `Campeonato.moneda`, `pichangol_bodega_productos.moneda`) para que
    las páginas públicas la muestren bien.
  - **Sin jerga local fija**: "Yape/Plin" solo si `paisActual.iso == 'PE'`
    (fuera: "QR / transferencia"); documento = DNI/CI/cédula según
    `docIdActual`/`PaisConfig`.
  - **Catálogos y sugerencias por país**: marcas/productos (bodega:
    `_sugerenciasPE/BO/EC`), prefijo telefónico (`codigoTelActual`),
    validación de documento por país.
  - **Pasarela por país** (`PaisConfig.pasarela`, la decide `paisActual`):
    PE → **Culqi** (tokeniza en la app; `pago_tarjeta_sheet.dart`), BO →
    **Libélula** (página hospedada en WebView; `pago_libelula.dart`), EC →
    **PayPhone** (botón de pagos hospedado en USD; `pago_payphone.dart`,
    backend `pagos/payphone.py` + `/pagos/ec/*`, hecho sep-2026). **La
    página de PayPhone se abre en NAVEGADOR REAL (Chrome Custom Tab vía
    `launchUrl(inAppBrowserView)`), NUNCA en WebView:** PayPhone rechaza el
    WebView de Android ("No autorizado… intenta desde la página de origen")
    aunque dominio y puente estén bien; la misma URL en Chrome carga. La app
    se queda en un diálogo que sondea `/pagos/ec/pago/{id}` (y al volver al
    frente) hasta que el retorno confirme; el WebView queda solo de respaldo. Todo cobro
    entra por `PagoTarjeta.cobrar`, que enruta por país. **Sin pasarela
    configurada, en PRODUCCIÓN nunca se simula** (`kEsProduccion`): se avisa y
    se devuelve false; en dev/QAS cae a la pasarela simulada para probar.
  - **Comisión con MÍNIMO POR MONEDA (decisión del director, sep-2026):**
    5 % con mínimo **S/ 2 · \$ 0.50 · Bs 3** (`config.comision_min` en el
    backend, `PaisConfig.comisionMin` en el APK). Los endpoints
    `/pagos/comision-reserva`, `/pagos/liquidacion-online` y `/pagos/venta`
    reciben `moneda` (ISO o símbolo; vacío = PEN para APKs viejos) y la
    GUARDAN en el pago, así el desglose de liquidaciones recalcula con la
    moneda real. El APK la manda desde el país de las coordenadas de la
    cancha (`_accionContable`) o la moneda del producto. Test
    `test_comision_moneda.py`. Pendiente: la cuota de torneo sigue en PEN.
  - **Montos de recarga por país:** `PaisConfig.recargas` (chips) +
    `recargaMin`/`recargaMax` ("Otro monto"): S/ 20-200 (10-1000), \$ 5-50
    (1-300), Bs 50-500 (20-3000). Para PRD subir el mínimo de EC a \$ 5.
  - Referencia central: `lib/config/pais.dart` (`PaisConfig`, `paisActual`).
  - **TRES países, no uno (decisión del director, sep-2026, opción C):**
    (1) **país que EXPLORA** = `paisActual` (GPS, pero el usuario lo elige a
    mano en la bienvenida, en la bandera de la barra de Explorar o en el
    banner "Parece que estás en Ecuador"; con elección explícita
    `paisElegido=true` el GPS ya no lo pisa, solo propone vía
    `sugerenciaPais`, una vez por viaje); (2) **país de CASA / billetera** =
    `appState.paisBilletera` (moneda congelada del saldo → país de su 1.ª
    cancha → `paisCasa` persistido → GPS); decide la moneda del saldo y la
    pasarela de RECARGA; se cambia en Perfil → "Mi país" SOLO con saldo 0;
    (3) **país del COBRO** = `paisDeCoordenadas(cancha.ubicacion)`: decide
    moneda y pasarela del checkout ("Pagas en $ · PayPhone"). NUNCA preguntar
    el país con un modal en cada arranque. Selector único:
    `widgets/selector_pais.dart`.

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
- **Home de marca en la raíz (`GET /`, hecho sep-2026):** el backend sirve
  `backend/growth/legal/home.html` (antes `landing/index.html`, que no se
  servía en ningún lado y `www.pichangol.app/` daba 404). Es la **URL del
  comercio** que se declara en Culqi/PayPhone al afiliar: razón social, RUC,
  contacto, términos, cancelaciones, Libro de Reclamaciones y enlaces a
  `/legal/*`. Test `test_home_de_marca_en_la_raiz`. **Requisitos de Culqi
  para la URL del comercio (infografía, sep-2026), ya cubiertos:** ≥5
  servicios con foto (SVG inline), descripción y precio visible + botón de
  compra (sección `#servicios`, enlaza a Play); **Libro de Reclamaciones
  INTEGRADO** (INDECOPI: no correo ni formularios externos): la home hace
  `POST /reclamaciones` (`legal/router.py`, número `PICH-AAAAMMDD-NNNN`,
  `stores.reclamaciones` en el snapshot) y el operador lo atiende en la
  torre `/admin` → Cobros → Libro de Reclamaciones (responder en ≤15 días
  hábiles); SSL en todo el dominio; contacto con número, correo y dirección.
  Culqi además exige que la app esté PUBLICADA en Play (o darles acceso de
  tester). La URL registrada en Culqi debe ser `www.pichangol.app`, NO
  `grupoebim.com` (observación de Culqi, sep-2026).
- **RESERVA WEB (fase 1, hecho sep-2026, autorizado por el director):**
  `backend/growth/web/` — `GET /canchas` (catálogo de canchas verificadas,
  agrupado por país, filtro `?deporte=`), `GET /reservar/{id}` (fecha,
  horarios libres con precio, datos del cliente, extras, **Culqi Checkout
  v4** con Yape + tarjeta), `GET /web/disponibilidad/{id}?fecha=` (JSON),
  `POST /web/asegurar` (INSERT `pichangol_reservas` estado `nueva` con
  hold de 10 min, id `web_<epoch_ms>_n`, firma HMAC), `POST /web/pagar`
  (cargo Culqi → `confirmada`+`pagado`+`medio_pago` → `/pagos/
  liquidacion-online` billetera-first → push "Nueva reserva 📅" al dueño),
  `POST /web/liberar`, `GET /reserva/{id|grupo}` (comprobante). Lee y
  escribe las MISMAS tablas del APK por Postgres directo (`web/datos.py`,
  `DATABASE_URL`, sin RLS) — el dueño ve la reserva web en su agenda como
  una online más; el UNIQUE `(cancha_id, fecha, hora_inicio)` evita la
  doble reserva. `web/horarios.py` es ESPEJO de `Cancha` (slots, cierre
  que cruza medianoche, fecha real de madrugada, hora feliz, descuentos por
  slot, bloqueos). **Multi-país:** cobro web sólo en soles (Culqi); canchas
  en \$ o Bs muestran el detalle y mandan a la app. El checkout se muestra
  con cualquier `CULQI_PUBLIC_KEY` (también `pk_test`, para que Culqi lo
  revise en PRD antes de dar las llaves live); el APK sigue apagado hasta
  `sk_live`. Tests `test_web_reservas.py` (base simulada). **Look & feel =
  el del APK** (decisión del director, sep-2026): `web/ui.py` es el sistema
  de diseño web (tokens de `lib/theme.dart`: Montserrat, azul noche
  `#0F1B2D`, esmeralda `#0E8F67`, papel `#F4F7FA`; wordmark Pichang[o]l con
  la pelota SVG; chips/tarjetas/botones Airbnb; marcas Yape/Visa/MC; sello
  "✓ Verificada"); `ui.shell()` envuelve TODAS las páginas públicas y la home
  usa los mismos tokens. Assets de marca en `backend/growth/static/brand/`
  (`/static/...`, montado en `main.py`; favicon/OG). Reserva: tira de 14
  días (Hoy/Mañana/…), selector de deporte si la loza es multiuso, resumen
  fijo "Resumen de tu reserva" (barra inferior en móvil), skeleton al
  cargar, comprobante con check animado + `.ics` + Cómo llegar + WhatsApp,
  JSON-LD `SportsActivityLocation`, 404 propio. **`/canchas` es la pantalla
  inicial "Explorar" de la web (sep-2026):** pide ubicación al cargar (y con
  el botón "Usar mi ubicación"), ordena por cercanía con la distancia en cada
  tarjeta, pone primero el país del usuario (cajas de `paises._CAJAS`
  pasadas al JS) y muestra un mapa **Leaflet + OpenStreetMap** (sin API key)
  con pines de precio y popup "Ver horarios"; la ubicación se recuerda en
  `localStorage`. Banderas como SVG (`ui.bandera`): los emoji de bandera no
  se ven en Windows. Regla anti scroll horizontal: `html,body{overflow-x:
  hidden}` + `minmax(0,1fr)`/`min-width:0` en las columnas de la grilla.
  **Canchas NO verificadas NO salen en la web hasta ser aprobadas (regla
  del director, 23-sep-2026, "sigue el flujo como en el app"; REVIERTE la
  decisión anterior de mostrarlas con "Aún sin verificar"):** el explorador
  lista solo `datos.reservable(c)` (verificada + con dueño, espejo de
  `Cancha.reservable`); `datos.canchas_publicas()` sigue trayendo todas las
  registradas para otros usos. La ficha `/reservar/{id}` de una cancha en
  verificación CON dueño responde 404 ("Esta cancha aún está en
  verificación") salvo al propio dueño (vista previa con "Reserva desde la
  app"); el LEGADO sin dueño sí se abre por enlace para reclamarlo.
  `/web/asegurar` responde `no_verificada`. El modal de filtros ya no tiene
  "Tipo de local". Dedup de descubiertas: contra las registradas CON dueño;
  el legado sin dueño no se descuenta (su pin de Google sigue) y "Reclámala"
  → `/anfitrion/nueva?place&lat&lng` ADOPTA la fila legado a ≤120 m
  (`anfitrion._legado_cerca`) en vez de duplicarla. **FICHA = LOCAL (queja
  del director: "sale el nombre de la cancha en vez del local"):** `_ficha`
  pone de título `_titulo_local(c)` (= `club`, como `club_detalle` del app),
  la cancha debajo y, si el local tiene varias (`_hermanas`: mismo `club`,
  aprobadas + las del dueño que mira), chips para cambiar de cancha;
  `<title>`, descripción, JSON-LD y "Cómo llegar" usan el local. Test
  `test_no_verificadas_no_salen_hasta_ser_aprobadas`.
  **TARJETA DEL EXPLORADOR = UN LOCAL (queja del director, 23-sep-2026:
  "sigue saliendo el nombre de la cancha como nombre del local"):**
  `_agrupar_locales` junta las canchas aprobadas por `club` (como
  `Club.agrupar`/`ClubCard` del app) y `_tarjeta(grupo, ratings, fecha)`
  pinta título = local, zona, "N canchas · deportes · horario (el más
  temprano–el último cierre) · duración", precio "desde" el más barato y ★
  ponderado de todas. `data-ids` lleva todas las canchas: el filtro de
  fecha+hora oculta el local solo si NINGUNA tiene turno libre y el enlace
  apunta a la cancha que SÍ lo tiene (`idsDe` en el JS); `data-pasos` y
  `data-sup` con varios valores para Duración/Superficie del modal.
  **Canchas DESCUBIERTAS en Google también (sep-2026):** `web/descubrir.py`
  llama a la MISMA Edge Function `places-cerca` que el APK (key de Places
  como secret de Supabase; el backend usa `SUPABASE_URL` + `SUPABASE_ANON_KEY`)
  y aplica la misma heurística de `places_service.dart` (`deporte_de`), con
  caché en memoria por celda de ~2 km + país (6 h) y dedup contra las
  registradas (nombre + <120 m). `GET /web/descubrir?lat&lng[&fotos=1][&deporte=]`
  (la pestaña activa viaja al servidor y filtra: en Tenis no salen canchas de
  fútbol descubiertas, queja del director sep-2026; `buscarEnGoogle` también
  filtra por `C.dep`); el
  explorador las pinta en "Más canchas cerca de ti" con "Aún sin registrar",
  "Reservar en la app", "Cómo llegar" y "¿Es tuya? Reclámala"; pines grises
  en el mapa. Sin Supabase/key → lista vacía, la web sigue.
- **ACADEMIAS EN EL EXPLORADOR (pedido del director, sep-2026: "he creado
  una academia, ¿cómo la busco por acá?"):** `datos.academias_publicas()`
  (`pichangol_academias` no eliminadas, `data` = `Academia.toJson`) →
  sección `#academias` (`.grupo-aca`, título "🎓 Academias [de tenis]") entre
  las canchas registradas y las descubiertas, filtrada por la pestaña de
  deporte (`academia.deporte == dep`; natación solo en "Todas") y ORDENADA
  POR CERCANÍA con las canchas (`ordenar()` también recorre `.grupo-aca`).
  `router._tarjeta_academia`: `<a class='lst aca'>` a su página `/l/{id}`,
  logo/fotos o emoji del deporte, badge "🎓 Academia", sede · zona, "N
  programas · a X km", "S/ 250 al mes desde" (mínimo `precioMes` de sus
  planes, moneda congelada o la del país de la sede) o "Consulta precios",
  botones Ver academia / 💬 WhatsApp (`span.wa[data-wa]` + handler;
  prefijo del país de la sede si el número es local) / 📍 Cómo llegar
  (`.ir`). **OJO: la tarjeta es un `<a>`; un `<a>` anidado (el WhatsApp
  fue así en la 1.ª versión) hace que el navegador parta la tarjeta en
  tres.** En el JS las academias pasan solo por texto/cercanía (`pasaBase`
  devuelve true para `.aca`, se saltan `pasaFil`), la sección se oculta si
  ninguna pasa, y en el mapa llevan pin `🎓 Deporte` con popup "Ver
  academia". **Botones (pedido del director, sep-2026):** "Ver academia"
  abre la FICHA WEB `/academia/{id}` (ver abajo; existe siempre). ~~SOLO si el dueño generó su página~~ (versión anterior: (`/l/{id}` existe en `stores.landings`;
  si no, esa ruta responde 404 "Landing no disponible"); en su lugar salen
  las REDES registradas (`Academia.redes`: instagram/facebook/tiktok/youtube/
  web, `_botones_redes` + `_url_red` acepta @usuario o URL completa) con
  logo SVG inline y color de marca (`.red-<red>`), enlace directo en pestaña
  nueva (`span.wa[data-wa]`). Sin redes → ningún botón. Una tarjeta sin
  página (`data-sinpagina='1'`, `href='#'`) no navega: el clic abre su
  primera red/WhatsApp; el popup del mapa hace lo mismo. **PESTAÑA "🎓
  Academias" en la cabecera (pedido del director, sep-2026: "¿dónde busco
  academias?"):** última de `CATEGORIAS` (`?deporte=academias`,
  `solo_aca` en `_explorar`): solo academias de TODOS los deportes,
  ordenadas por cercanía; sin canchas registradas, sin descubiertas
  (`descubrir()`/`buscarEnGoogle()` se saltan con `C.dep==='academias'`),
  sin barra/modal de Filtros (amenidades y precio por hora no aplican), el
  "Dónde" dice "Busca academias por nombre o zona" y filtra por texto;
  vacío propio y, sin academias, CTA "Publicar mi academia". Test
  `test_academias_en_el_explorador_por_deporte_y_cercania`.
- **FICHA DE ACADEMIA + MATRÍCULA WEB (`web/academia.py`, pedido del
  director, sep-2026: "si hago clic en la academia debería ir a la academia,
  ver los planes y poder matricularme"):** `GET /academia/{id}` = ficha
  tipo anuncio (galería logo+fotos, deporte, sede · zona, descripción,
  `ul.datos` con Cómo llegar → mapa Leaflet inline y WhatsApp, botones de
  redes con logo, enlace a `/l/{id}` si la landing existe), "Programas y
  tarifario" (`_tarifario`: tarjeta `.prog` por programa con etapa ·
  duración · horario, filas `.tarifa-fila` por frecuencia/modalidad con
  precio socio e invitado si hay `recargoInvitado`, "Otros planes" para los
  sin programa, descuentos hermanos/prepago) y el panel de matrícula = el
  MISMO flujo que `academia_detalle_screen._matricular` del app: sesión
  Google obligatoria (login-box como la reserva), Para mí / Para mi hijo(a)
  (+ edad 2-17; el titular queda como `apoderadoNombre`), nombre + celular,
  Mes a mes (solo mensuales) o Adelantado con cantidad 1/2/3/6/12 y
  descuento prepago si `cantidad ≥ mesesMinPrepago`, Culqi Checkout v4 (solo
  PEN; en $/Bs el tarifario se ve y "Matricúlate desde la app"). `POST
  /web/matricular` recalcula el total en el servidor (`_total` =
  `_HojaDatosAlumno._total`), cobra (`culqi.crear_cargo`) y escribe en
  `pichangol_matriculas` (`datos.insertar_matricula`) EXACTAMENTE la fila de
  `AppState.matricular`: `Alumno.toJson` (`al_<µs>`, `email` = cuenta
  Google, `esSocioSede` true, `sedeId` '') + `cuotas` (`cu_<µs>_i`,
  concepto "Plan · Mes", `vencimiento` = mismo día i meses después, mes a
  mes = 1 pagada + resto pendientes con `autoDebito`, `operacionId` =
  charge) + extras que el app ignora (`canal: web`, `pagoWeb {monto,
  ahorro, operacion, medio}` = lo cobrado con descuento, que el comprobante
  muestra). Luego: `pagos.router.post_matricula` (comisión del país, neto
  "por recibir"), `stores.registrar_pago(cobro_web, concepto
  matricula:<id>)`, mes a mes → `post_suscripcion_alumno` best-effort
  (débito automático de los meses restantes) y push al dueño "Nuevo alumno
  🎓" (`_aviso_push_usuario`). `GET /academia/{id}/matricula/{alumno_id}` =
  comprobante solo para el titular (cuotas ✅/⏳, N.º de operación, WhatsApp
  a la academia). `datos.academia(id)`, `insertar_matricula`, `matricula`.
  Test `test_ficha_de_academia_y_matricula_web_como_el_app`.
- **PORTADA TIPO AIRBNB (`GET /`, hecho sep-2026, pedido del director):** la
  raíz del dominio YA NO es la home de marketing sino el EXPLORADOR
  (`web/router.py::_explorar`; `/canchas` es alias): cabecera con buscador en
  pastilla (Dónde · Deporte · Cuándo · lupa), "Pon tu cancha" + "Descarga la
  app", barra de categorías con ícono y subrayado (`CATEGORIAS`), grilla de
  tarjetas Airbnb (`_tarjeta`: foto cuadrada con carrusel scroll-snap y
  puntos, corazón = favorito en `localStorage`, badge Verificada / Aún sin
  verificar, ★ promedio real de `pichangol_resenas` vía `datos.ratings()` o
  "Nuevo", zona, deportes + turnos + distancia, precio por hora), botón
  flotante "Mostrar mapa" (split view lista+mapa sticky en escritorio, mapa a
  pantalla completa en móvil; Leaflet se dibuja al abrirlo; preferencia en
  `localStorage`), "Filtros" (solo verificadas, precio máx.). El DEPORTE lo
  filtra el servidor (`?deporte=`, categorías = enlaces, SEO); zona/texto,
  verificadas y precio se filtran en el navegador; la FECHA del buscador
  viaja a la ficha (`/reservar/{id}?fecha=` preselecciona el día de la tira).
  Debajo de las canchas van las secciones de comercio que revisan Culqi e
  INDECOPI (`web/marca.py` extrae de `legal/home.html` las secciones desde
  "Qué ofrecemos" hasta el Libro de Reclamaciones y re-escribe su CSS bajo el
  prefijo `.marca` para no pisar `ui.py`); el pie (`ui.footer()`, columnas
  estilo Airbnb) lleva razón social, RUC, contacto y enlaces legales en TODAS
  las páginas. `home.html` sigue siendo el texto legal/comercial editable, ya
  no se sirve entero. Test `test_raiz_es_el_explorador_tipo_airbnb`.
  **PRIMERA FOTO SIEMPRE (regla del director, sep-2026):** la web muestra la
  primera foto como el app. Las canchas SEMBRADAS desde el app no guardan las
  fotos de Google en la base; `GET /web/foto?id|nombre&club&lat&lng`
  (`descubrir.fotos_de_lugar` → misma Edge Function `places-cerca` con radio
  250 m y `fotos=true`; `_elegir_lugar` = mejor coincidencia de palabras con
  nombre/club sin el sufijo de sede, a igual puntaje el más cercano; caché
  12 h por lugar, 10 min si vino vacío) las resuelve en vivo. Las tarjetas y
  la galería de la ficha nacen con placeholder `data-buscar` y el JS las
  rellena (cola de 3 en paralelo); también las descubiertas más allá de las
  16 con foto que devuelve la Edge. **Respaldo directo:** si la Edge no trae
  fotos (en QAS pasó: las descubiertas salían sin foto aun con `fotos=1`) y
  hay `PLACES_API_KEY` en Railway (llave SIN restricción Android, la misma
  del secret de Supabase), el backend habla con Google Places (New)
  (`_fotos_directo`: Place Details por `place_id` o Text Search por
  nombre/club a 300 m; URLs públicas vía `skipHttpRedirect`). Cada
  resolución imprime una línea `[foto] …` en los logs de Railway (lugares
  que devolvió la Edge, cuántos con foto, `diag` de Google, origen) para
  diagnosticar sin adivinar. Dedup de descubiertas también por CLUB
  (`registradas` lleva `club`; "Fútbol 1" del club "Sabor Golazo" = el
  lugar de Google). **CUOTA (trampa real, sep-2026):** la 1.ª versión pedía
  la foto de cada tarjeta vía la Edge (12 Text Search por tarjeta) →
  Google 429 "SearchTextRequest per minute" y NADA tenía foto. Regla:
  con `PLACES_API_KEY` es UNA llamada a Google por lugar (Place Details por
  id / un Text Search por club) y la Edge solo sin llave; semáforo de 3 en
  el servidor; un 429 pausa 60 s sin cachear vacíos; el navegador pide
  fotos solo de las tarjetas visibles (IntersectionObserver, 2 a la vez).
  **COSECHA de fotos** (`pichangol_lugares_fotos`, SQL
  `docs/piloto/supabase_lugares_fotos.sql`; `datos.leer/guardar_fotos_lugar`):
  la primera foto resuelta se guarda por `place_id` (o `cancha:<id>`) y se
  paga UNA vez; se refresca sola a los 30 días (tope de caché de los
  términos de Google; nunca se descarga el archivo) y, si Google falla, vale
  la guardada. Lugares que Google confirma SIN foto se reintentan cada 6 h.
  Test `test_primera_foto_siempre_como_el_app`.
- **LOGIN CON GOOGLE EN LA WEB (decisión del director, sep-2026: mismo
  flujo que el app):** `web/sesion.py`. Botón oficial de Google Identity
  Services (`GOOGLE_WEB_CLIENT_ID` = client id OAuth de tipo "Aplicación
  web" del proyecto de Google de Pichangol, con orígenes autorizados
  `https://pg.ebim.pe` y `https://www.pichangol.app`); `POST /web/sesion`
  verifica el ID token contra Google (tokeninfo, audiencia = ese client id
  o `GOOGLE_OAUTH_CLIENT_IDS`) y deja la cookie httpOnly FIRMADA
  `pcg_sesion` (HMAC con el secreto del backend, 30 días); `POST /web/salir`,
  `GET /web/sesion`, página `GET /entrar?volver=`. Con el client id
  configurado, la ficha muestra en "Tus datos" la caja "Inicia sesión con
  Google para reservar" (sin recargar: `alIniciarSesion`), luego "Reservando
  como" + Cambiar cuenta; `/web/asegurar` y `/web/pagar` responden
  `sesion_requerida` sin cookie y la reserva queda a nombre del CORREO de
  Google (`usuario`), así aparece en "Mis reservas" del app con la misma
  cuenta. La barra muestra avatar/nombre o "Iniciar sesión"
  (`ui.chip_sesion`). **Sin `GOOGLE_WEB_CLIENT_ID` la web sigue en modo
  invitado** (nombre + correo) para no romper antes de crear el client id.
  Test `test_reservar_exige_login_con_google_como_el_app`.
- **Paleta = la del LOGO oficial (sep-2026):** `ui.py` TOKENS: verde
  `#0B8A3E` (CTA), verde oscuro `#067A38`, lima `#7CB518`, naranja `#F28C28`
  (corazón de favorito), azul noche `#0A1B3D` (texto), fondo blanco `#FFFFFF`. El
  wordmark web es el logo real: `/static/brand/logo_pin.png` + "Pichangol"
  peso 800 SIN cursiva (`ui.wordmark`, pedido del director). Buscador con foco tipo Airbnb (pastilla gris,
  segmento activo blanco con sombra, cursor visible, chevron en el select);
  categorías centradas en escritorio.
- **CABECERA TAL CUAL AIRBNB.COM (pedido del director, sep-2026):**
  `ui.cabecera()` es la cabecera de TODAS las páginas web: fila 1 = logo a
  la izquierda · pestañas por deporte con ícono al centro (`CATEGORIAS`,
  subrayado negro en la activa) · a la derecha "Modo anfitrión" (→ Play), el
  avatar (foto de Google si hay sesión, silueta si no) y el botón ☰ con menú
  desplegable (`ui.menu_cuenta`: Iniciar sesión o registrarse / nombre +
  correo + Mis reservas + Cerrar sesión, Cómo funciona, Centro de ayuda, Pon
  tu cancha, Descarga la app, Libro de Reclamaciones; se cierra al hacer
  clic fuera o con Esc, `ui.JS_NAV`); fila 2 = buscador GRANDE centrado en
  pastilla (Dónde · Cuándo · Hora · botón verde "Buscar"; el deporte va en
  las pestañas). Bajo "Dónde" se desglosa un panel (`#sugDonde`) con
  **Búsquedas recientes** (`localStorage` `pcg_busq`, se guardan al
  Buscar/Enter/elegir) y **Zonas sugeridas** ("Cerca de ti" →
  `ubicar(true)` + las zonas con más canchas, `router._zonas_sugeridas`).
  **"Cuándo" abre un CALENDARIO tipo Airbnb** (`#panCuando`, dos meses en
  escritorio / uno en móvil, flechas, días pasados y más allá de
  `DIAS_ADELANTE` tachados, toggle "Fecha | Cualquier día", atajos Hoy /
  Mañana / Sábado / Domingo; al elegir un día se abre solo el panel de
  hora). **"Hora" abre un panel de chips** (`#panHora`: Cualquier hora +
  Mañana/Tarde/Noche, 06:00-23:00). **Con "Hoy", las horas que ya pasaron
  quedan DESHABILITADAS** (`horaPasada`: solo turnos que empiezan después
  de este momento, reloj del navegador; grupos enteros en gris y aviso si
  ya no queda ninguna); una hora elegida que pasa a ser inválida se
  descarta. **También se deshabilitan las horas en las que NINGUNA cancha
  de la lista tiene turno** (tooltip "Ninguna cancha tiene turno a esta
  hora"; con la regla "el último turno EMPIEZA a la hora de cierre", una
  que cierra 23:00 sí ofrece las 23:00) y el vacío explica el motivo ("Ninguna cancha tiene
  turno libre hoy a las 23:00…"). La tarjeta muestra el horario
  (`07:00–23:00 · 60 min`) para que se entienda por qué sale o no. **NADA se filtra hasta pulsar "Buscar"** (regla del director,
  sep-2026, como Airbnb): lo elegido vive en `pend` (zona, fecha, hora) y
  `buscar()` lo copia a `filtro`, aplica, guarda la búsqueda reciente y
  pinta el resumen "Buscando: … · Limpiar" (`#resBusq`) en la línea de
  ubicación. Elegir una zona sugerida solo rellena "Dónde" y pasa a
  "Cuándo"; **"Cerca de ti"** pone ese texto en "Dónde" y, al Buscar, pide
  la ubicación, ordena por cercanía y deja solo las canchas a ≤30 km
  (`filtro.cerca`). **FILTROS TAL CUAL AIRBNB (sep-2026):** bajo la línea
  de ubicación va la barra `_barra_filtros` (botón "⚙️ Filtros" con badge
  de filtros activos + chips rápidos con las amenidades más comunes, que
  aplican al instante) y el MODAL `_modal_filtros` (`#modalFiltros`, 568
  px, cuerpo con scroll, pie fijo): "Recomendado para ti" (tarjetas con
  ícono: estacionamiento, iluminación, vestuarios, techada — las que
  existan en los datos), "Tipo de local" (segmentado Cualquier tipo /
  Verificadas / Aún sin verificar), "Rango de precios" (histograma de los
  precios reales + doble slider + cajas Mínimo/Máximo; SOLO en la moneda
  del país del usuario o del primer grupo, `data-mon`; las canchas en
  otra moneda no se filtran por precio), "Servicios del local" (todas las
  amenidades con conteo), "Superficie" y "Duración del turno" (si hay más
  de una). Todo se cuenta en vivo ("Mostrar N canchas"), "Limpiar
  filtros" y se aplica al pulsar Mostrar (`fil` vs `filTmp`; `pasaBase` =
  buscador, `pasaFil` = modal). Datos por tarjeta: `data-am`, `data-sup`,
  `data-paso`, `data-mon`, `data-pnum`. Los viejos chips "Solo verificadas
  / precio máx." desaparecieron. **PANTALLA COMPLETA como Airbnb:**
  `.wrap-xl` ya no tiene tope de 1440 px: márgenes 80 px (≥1128), 40 px,
  24 px, 16 px; la grilla es `auto-fill minmax(250px)` (5-6 columnas en
  1900 px). El filtro de hora es REAL, no cosmético: en el navegador se ocultan las canchas cerradas a esa hora
  (`data-ap`/`data-ci`/`data-paso` de cada tarjeta, `abiertaA`) y, con
  fecha + hora, `GET /web/libres?fecha&hora` responde qué canchas
  reservables tienen un turno LIBRE que cubra esa hora (`_hora_libre`:
  inicio ≤ hora < fin, misma lógica de slots/madrugada/turnos pasados que
  la ficha; `datos.ocupados_varias` = UNA consulta para todas). La fecha y
  la hora viajan a la ficha (`/reservar/{id}?fecha=&hora=` → `cfg.hora`
  preselecciona el turno libre que la cubre) y también se aceptan en la
  URL de la portada (`/?fecha=&hora=`). Un solo desplegable abierto a la
  vez (`abrirPanel`); OJO: al repintar el calendario el día clicado sale
  del DOM, por eso el "clic fuera" ignora nodos `!isConnected`. Test
  `test_buscador_por_fecha_y_hora_como_airbnb`. Al hacer scroll la cabecera se COMPACTA
  (`.cab.chica`): pestañas y buscador se esconden y al centro queda la
  pastilla chica "Cualquier zona · Cualquier deporte · Cuándo quieras"
  (`ui.busq_mini`); tocarla vuelve arriba y enfoca "Dónde". Las páginas
  interiores (`nav_simple`) llevan la misma cabecera en modo `simple` con la
  pastilla chica enlazando a `/canchas`. Responsive: <1400 px las 8
  pestañas pasan a su propia fila centrada bajo el buscador (no caben junto
  al logo); <1060 px sin compactar, tira desplazable; <900 px se esconden
  "Modo anfitrión", "Cuándo" y el texto de Buscar. Los filtros (Solo
  verificadas, precio máx.) viven en el cuerpo, botón "⚙️ Filtros" a la
  derecha de la línea de ubicación. **Fuente = DM Sans** (Airbnb Cereal es
  propietaria y no se puede descargar; DM Sans es su equivalente libre) y
  fondo BLANCO (`--papel:#FFFFFF`) como airbnb.com. **Trampa CSS:**
  `overflow-x:hidden` en `body` convierte al body en scroll container y
  mata el `position:sticky` de la cabecera → `html{overflow-x:hidden}` +
  `body{overflow-x:clip}`.
  **MÓVIL (≤900 px, arreglado sep-2026 tras captura del director):** la
  cabecera `simple` de las páginas interiores ponía logo · pastilla · avatar
  en UNA fila y "Pichangol" se montaba sobre la pastilla. Ahora en móvil
  va en dos filas como airbnb.com en el celular: logo + avatar + ☰ arriba y
  la pastilla a TODO el ancho debajo, con lupa a la izquierda y dos líneas
  ("¿Dónde juegas?" / "Cualquier zona · Cualquier deporte · Cuándo quieras",
  `busq_mini` lleva el bloque `.mov` solo visible en móvil); la compacta
  `.chica` en móvil deja solo la pastilla. Toda pantalla web nueva se prueba
  también a 390 px (Playwright `isMobile`).
- **MIS RESERVAS EN LA WEB (sep-2026, pedido del director):** `GET
  /mis-reservas` (router `pagina_mis_reservas`) lista las reservas del CORREO
  de Google con sesión — las mismas que "Mis reservas" del app —
  (`datos.reservas_de_usuario`: `lower(usuario)=email`, sin retenciones
  web sin pagar), separadas en Próximas y Pasadas, con estado (Pagada /
  Pagas en la cancha / Cancelada / No asististe), precio, Comprobante
  (`/reserva/{grupo|id}`), Ver cancha / Reservar de nuevo y Cómo llegar; los
  turnos de una misma reserva se agrupan en UNA tarjeta
  (`_agrupar_reservas`: 19:00–21:00 · 2 turnos, precio sumado). Sin cookie →
  302 a `/entrar?volver=/mis-reservas`; sin `GOOGLE_WEB_CLIENT_ID` explica
  que están en la app. Enlace "📅 Mis reservas" en el menú ☰ (solo con
  sesión). **Layout = "Viajes" de Airbnb (sep-2026):** columna izquierda
  (≤520 px) con tarjetas `.viaje` (foto cuadrada — propia o resuelta con
  `/web/foto` —, cancha, club, fecha · hora · turnos, avatar del jugador,
  pill de estado, precio y "Cancelar reserva"); clic = comprobante. Derecha:
  mapa Leaflet sticky con un pin por reserva próxima (popup "Ver reserva").
  Debajo: `<details>` "Dónde has jugado" (pasadas) y "🗓️ Reservaciones
  canceladas" (historial de `stores.cancelaciones_web` con el estado de la
  devolución). Aviso verde tras cancelar (`sessionStorage` `pcg_aviso`).
  **CANCELACIÓN CON REEMBOLSO DESDE LA WEB (hecho sep-2026, autorizado por
  el director):** `POST /web/cancelar {ref}` (grupo o turno; solo con sesión
  y solo reservas del propio correo; `estado_cancelacion()` decide: no se
  cancela lo que ya empezó; con ≥ `WEB_CANCELACION_HORAS` (6, env) y pagada
  → devolución del 100 %). Flujo: (1) si el cargo fue WEB (`stores` tipo
  `cobro_web`, registrado en `/web/pagar` con el `charge_id` de Culqi y
  `concepto=web:<ref>`) → `culqi.reembolsar` (`POST /v2/refunds`, funciona
  en test y live) → `reembolsado` (o `fallo` si Culqi rechazó); si pagó en el
  APP no tenemos su cargo → `manual` (el operador devuelve); < 6 h →
  `sin_reembolso`; pago en la cancha → `no_aplica`. (2) Reversa contable del
  dueño SOLO si el cliente recupera su plata: liquidación
  (`liquidacion_full|online` por `reserva_id`) → `anulado` si aún no se le
  pagó, y la comisión `<id>_com` → `anulado` devolviendo al dueño la parte
  real a su saldo y la parte regalo (`PagoRegistro.promo_centimos`, nuevo
  campo que guarda `post_liquidacion_online`) a su bolsillo promo; si YA se
  le liquidó → pago `ajuste_cancelacion` (estado `pendiente`) +
  `deuda_dueno_centimos` en el registro para descontar en la siguiente
  liquidación. (3) Se BORRAN las filas de `pichangol_reservas` (igual que el
  app al cancelar: libera el horario y el app deja de mostrarla; los puntos
  derivados desaparecen solos). (4) Registro en `stores.cancelaciones_web`
  (snapshot) + push al dueño ("Reserva cancelada 📅 … quedó libre") y al
  jugador (qué pasa con su plata) + línea `[cancelar]` en logs. Torre: `GET
  /pagos/cancelaciones-web[?pendientes=1]` (X-Admin-Token) lista todo; las
  `fallo`/`manual`/con deuda las atiende el operador en la torre `/admin` →
  Cobros → **"↩️ Cancelaciones web"** (`cargarCancelacionesWeb` en
  `propiedad/panel.py`; pendientes primero con borde ámbar): "✅ Marcar
  devuelto" (`POST /pagos/cancelaciones-web/{id}/resolver {accion:
  devuelto, referencia}` → `reembolsado_manual`) y "➖ Marcar deuda
  descontada" (`accion: descontado` → `deuda_resuelta` y el pago
  `ajuste_cancelacion` pasa a `aplicado`). El comprobante `/reserva/{ref}` muestra "Cancelar reserva" al
  dueño de la reserva (modal `_MODAL_CANCELAR` + `JS_CANCELAR`, compartidos
  con Mis reservas) y la política con las horas configuradas.
- **MODO ANFITRIÓN EN LA WEB (sep-2026, pedido del director: mismo flujo
  que airbnb.com/hosting):** `web/anfitrion.py` (router incluido en
  `main.py`). El enlace "Modo anfitrión" de la cabecera abre `/anfitrion`
  (sin sesión → `/entrar?volver=`) = **el MISMO MENÚ del app** (pedido del
  director, sep-2026): cabecera verde "‹ Modo anfitrión · Publica tu cancha
  o academia…" + tarjetas con ícono de color (`MENU`): 🏬 Mis canchas →
  `/anfitrion/mis-canchas` (panel web completo), 📣 Mi academia y 🏪 Mi
  tienda (web, ver abajo), 🏆 Mis campeonatos y 🛡️ Verificador →
  `/anfitrion/{modulo}` (páginas "está en la app" con pill "En la app" y
  botón Abrir en la app). Dentro de Mis canchas la
  cabecera cambia a modo anfitrión (`ui.cabecera(modo="anfitrion")`: logo →
  `/anfitrion`, pestañas 📅 Hoy · 🗓️ Calendario · 📋 Reservas · 💰 Ingresos ·
  🏟️ Canchas, y a la derecha "Cambiar a modo jugador" → `/`, también en el
  menú ☰; enlace "‹ Modo anfitrión" vuelve al menú). Datos:
  `datos.canchas_de_dueno(email)` (`lower(dueno)=correo`, no eliminadas),
  `datos.reservas_de_canchas(ids, desde, hasta)` (sin holds ni canceladas),
  `datos.bloqueos_de`. Sin canchas a su nombre → onboarding "Hola 👋 …
  Registrar mi cancha en la app" (el reclamo/verificación siguen en el
  app). **Hoy** = chips Hoy / Mañana / Próximos 7 días / Por cobrar en
  efectivo con tarjetas (hora, cancha, jugador + correo + celular + botón
  WhatsApp, monto, pill Pagada en línea · yape|tarjeta / Cobrada / Cobrar en
  la cancha) + atajos. **Calendario** = agenda SEMANAL de una cancha (chips
  para cambiar, ‹ › Hoy): filas = turnos (regla "último turno empieza al
  cierre"), celdas verde = pagada, ámbar = cobrar en cancha, gris =
  bloqueado; solo lectura (bloquear/manual → app). **Reservas** = próximas y
  pasadas 30 d agrupadas por día. **Ingresos** = billetera del backend
  (`stores.saldo_centimos`, `saldo_promo_centimos`, `liquidaciones` +
  `_liquidacion_dict`): KPIs Por recibir / Saldo / Regalo, liquidaciones
  pendientes y pagadas, últimos movimientos. **Canchas** = sus locales con
  foto, verificada, deportes, horario, precio y botones Ver ficha pública /
  Calendario / Mapa / Editar. **Agrupado por LOCAL como el app (sep-2026,
  queja del director: "el nombre del local me sale el de la cancha"):**
  `pagina_canchas` arma UNA tarjeta `.anf-local` por `club` (título = local,
  dirección · zona, N canchas, pill "✓ Verificado" si todas lo están) y
  dentro una fila `.anf-fila` por cancha (emoji del deporte, nombre, pill
  ✓ Verificada / Aún sin verificar, deporte · horario · duración · precio,
  Ficha / Calendario / Editar) + "＋ Agregar cancha a este local" (abre
  `/anfitrion/nueva` prellenado con nombre, dirección y punto del local) y
  Mapa; el botón de abajo dice "Registrar otro local". Test
  `test_modo_anfitrion_en_la_web_como_airbnb`.
- **PON TU CANCHA / RECLÁMALA DESDE LA WEB (sep-2026, autorizado por el
  director: "web = vender y atender"):** `GET/POST /anfitrion/nueva`
  (`web/anfitrion.py::pagina_nueva_cancha`, `_validar_registro`,
  `registrar_cancha_web`; fotos previas al alta `POST /anfitrion/nueva/foto?id=
  u<ms>&tipo=foto|evidencia` → `canchas/<id>/` y `canchas/ev<id>/`). MISMO
  flujo que `registrar_cancha_screen.dart`: local + dirección + punto en mapa
  Leaflet (obligatorio, dentro de las cajas PE/EC/BO: de ahí salen país,
  moneda, prefijo de WhatsApp y documento) + zona en cascada (`barrio`),
  deportes (chips) con "loza multiuso (una agenda)" vs "canchas separadas
  (una por deporte)" y piso por deporte, precio + horario + duración, fotos,
  y VERIFICACIÓN (WhatsApp local con largo por país, relación
  dueño/administrador/encargado, documento opcional con largo por país, nota,
  foto de evidencia, GPS del navegador en silencio). Al enviar: INSERT en
  `pichangol_canchas` (`datos.insertar_canchas`, ids `u<ms>` o
  `u<ms>_<deporte>`, `verificada=false`, `dueno`=correo de Google, moneda por
  coordenadas, `distrito=''`) + `reclamos.crear_reclamo` EN PROCESO (nota con
  sufijo `[web · place gp_…]`); si el lugar ya tiene reclamo activo ajeno →
  409 y `datos.borrar_canchas` revierte. Entradas: onboarding de Modo
  anfitrión ("Registrar mi cancha"), "＋ Registrar otra cancha" en Canchas,
  "Pon tu cancha en Pichangol" (pie y menú ☰) y el botón **"🏷️ ¿Es tuya?
  Reclámala"** de cada cancha DESCUBIERTA del explorador (prellena nombre,
  dirección, punto, deporte y `place`). **Al tocar una cancha descubierta se
  abre su FICHA WEB `GET /lugar/{gp_id}?nombre&direccion&lat&lng&deporte`**
  (`router.pagina_lugar`: foto vía `/web/foto`, Cómo llegar, "Aún sin
  registrar", panel "¿Es tuya? Reclámala y recibe reservas" y "Abrir en la
  app"); antes la tarjeta entera mandaba a Play (queja del director). **Canchas
  REGISTRADAS sin dueño (legado reclamable):** su ficha `/reservar/{id}`
  muestra "¿Es tuya esta cancha? → Reclamar" → `/anfitrion/nueva?cancha=<id>`
  PRELLENA todo (`_legado_reclamable`: existe, no verificada, `dueno` vacío)
  y el envío ADOPTA la misma fila (`datos.adoptar_cancha`: UPDATE con
  `dueno`=correo + campos `COLS_ADOPCION`, solo si sigue sin dueño; si el
  reclamo falla, `desadoptar_cancha`). `marcar_verificada` también cubre las
  hermanas del mismo dueño a ≈150 m del reclamo (legado sin prefijo `u<ts>`).
  **BUSCAR MI LOCAL POR NOMBRE (caso "Campo deportivo Edu Jr.", sep-2026):** el
  descubrimiento por celda solo trae los ~20 lugares MÁS CERCANOS por consulta
  (Text Search `rankPreference: DISTANCE`, `maxResultCount` 20) → en zonas
  densas un local a 2-4 km no entra en ninguna lista aunque la heurística lo
  acepte. Tres arreglos: (1) `GET /web/lugares?q&lat&lng`
  (`descubrir.buscar_lugares`: Text Search con la consulta LIBRE del dueño,
  sesgo 30 km, sin filtro de deporte, caché 10 min; exige `PLACES_API_KEY`,
  sin ella `disponible:false`) y en "Pon tu cancha" la caja "🔎 Busca tu
  local en Google Maps" (`#busca`, debounce 400 ms) cuyo resultado rellena
  nombre, dirección, punto, `place` y sugiere el deporte; (2) el explorador
  web RE-DESCUBRE al mover el mapa (`moveend`, zoom ≥ 12, 1 llamada por celda
  de ~1 km) y ACUMULA las descubiertas por id (`descAcum`) recalculando la
  distancia desde el usuario o el centro del mapa; (3) la Edge `places-cerca`
  sigue `nextPageToken` (hasta 3 páginas en "canchas de fútbol" y "campo
  deportivo", 2 en "complejo deportivo" y "grass sintético") → **hay que
  redesplegarla** (`supabase functions deploy places-cerca`, laptop) en QAS y
  PRD; también beneficia al APK, que usa la misma Edge. **(4) El EXPLORADOR
  también busca por nombre:** lo escrito en "Dónde" + Buscar llama a
  `/web/lugares` (`buscarEnGoogle`, una vez por consulta) y los lugares que
  la heurística reconoce entran a "Más canchas cerca de ti" como descubiertas
  (`data-q` = consulta que los trajo, así pasan el filtro de texto aunque el
  nombre no contenga lo escrito); el vacío dice "Buscando … también en
  Google Maps…" / "No encontramos … ni en Google Maps". Flag `C.lugares`
  (= hay `PLACES_API_KEY`). Test `test_buscar_mi_local_en_google_por_nombre`.
  El panel muestra el estado real del reclamo
  (`_aviso_verificacion` en Hoy y Canchas: En verificación / falta validar /
  No aprobada…). **ESPEJO EN LA NUBE (bug que esto destapó):** la torre
  marcaba `verificada` solo en `stores.canchas` y era el APK quien escribía
  `pichangol_canchas.verificada=true` al sincronizar → un dueño solo-web
  nunca quedaba reservable. Ahora `reclamos._nube_verificada` (llamado en
  `aprobar_directo`, `activar_admin`, `validar_en_sitio` y
  `_revocar_cancha_al_rechazar`) hace `datos.marcar_verificada(cancha_id,
  dueno, bool)` sobre la reclamada y sus hermanas `u<ts>_*` (fail-safe). OTP
  por WhatsApp y verificación de existencia (IA) siguen solo en el app. Test
  `test_registrar_y_reclamar_cancha_desde_la_web_como_el_app`.
  **AGREGAR CANCHA A UN LOCAL EXISTENTE (pedido del director, 23-sep-2026:
  "¿cómo registro otra cancha, y de otro deporte?"):** `GET/POST
  /anfitrion/cancha/{id}/agregar` (`web/anfitrion.py::pagina_agregar_cancha`,
  `_validar_agregada`, `agregar_cancha_web`) = `AgregarCanchaScreen` del app:
  la cancha nueva HEREDA club, dirección, punto, zona, fotos, servicios del
  local, moneda, dueño y ESTADO DE VERIFICACIÓN (local activo → activa al
  instante; en verificación → se activa con el local vía las hermanas de
  `marcar_verificada`); NO crea otro reclamo. Solo pide deporte (uno), piso,
  nombre opcional (auto "Fútbol 2" = siguiente número del deporte en el
  local, `_nombre_auto`), precio, horario y duración (defaults del local).
  Entradas: "＋ Agregar cancha a este local" en Mis canchas y "Pon tu
  cancha" prellenado con un local que ya es del dueño (mismo nombre o ≤120 m,
  `_local_propio`) → 303 al flujo corto (antes creaba otro local + otro
  reclamo y la 2.ª cancha quedaba "Aún sin verificar" para siempre). Aviso
  `?agregada=` en Mis canchas. Test
  `test_agregar_cancha_a_local_desde_la_web_como_el_app`.
  **SERVICIOS EXTRA = CATÁLOGO GLOBAL EN LA TORRE (decisión del director,
  23-sep-2026: "el admin debe poder registrar más servicios extra, p. ej.
  piscina y entrada general"):** `backend/growth/servicios_extra.py`.
  Antes eran 6 claves fijas duplicadas en el app (`ServicioExtra.catalogo`) y
  la web (`catalogos.SERVICIOS_EXTRA`, retirado). Ahora: (1) el OPERADOR
  administra el catálogo en `/admin` → Comunicación → **"🧩 Servicios
  extra"** (`GET/POST /admin/api/servicios-extra`, `/{clave}/activo`,
  sugerencias `/sugerencias/{id}`): clave (slug estable), nombre, emoji,
  **tipo de cobro** `reserva` (una vez) · `persona` (× cantidad que elige el
  jugador) · `turno` (× turnos reservados), **ámbito** `local` (piscina,
  sauna, entrada general: se copia a TODAS las canchas del local) · `cancha`
  (árbitro, petos: solo esa cancha), deportes ([] = todos), activo. Semilla
  `DEFAULTS` = los 6 de siempre (misma clave y cobro, no cambia data) +
  piscina, entrada_general, sauna, gimnasio, toallas, locker,
  estacionamiento_pago, clase, iluminacion, grabacion; vive en
  `stores.servicios_extra` (+ `servicios_extra_version`,
  `sugerencias_servicios`) en el snapshot. (2) **Público** `GET
  /config/servicios-extra` (APK + web). (3) El DUEÑO solo elige de la lista
  y pone precio: editor web agrupado "Del local / De esta cancha" con la
  etiqueta del cobro; al guardar, `_validar_edicion` CONGELA `{clave, precio,
  nombre, emoji, tipo, ambito}` (`_se.congelar`) y `_propagar_servicios_local`
  copia los de ámbito local a las hermanas (mismo `club`, mismo dueño)
  conservando los propios de cada cancha; "Agregar cancha a este local"
  hereda los del local. **Sin texto libre** para el dueño: caja "💡 Sugerir"
  (`POST /anfitrion/servicios/sugerir`, solo hacia el equipo) que la torre
  lista con "➕ Agregar al catálogo". (4) **Checkout web**: los "por persona"
  llevan `<select class='cant'>` (1-12); `/web/asegurar` acepta `extras` como
  claves o `{clave, cantidad}` y guarda la LÍNEA `{clave, precio=TOTAL,
  unitario, cantidad, nombre, emoji, tipo}` (`_se.linea_reserva`; `precio`
  total = compatible con APKs que solo suman `precio`); comprobante y
  resumen muestran "Piscina × 3". (5) **APK** (`lib/models/models.dart`):
  `ServicioCatalogo` + `ServicioExtra` con `nombre/emoji/tipo/ambito/
  cantidad/unitario`, `catalogoRemoto` (cache-first en SharedPreferences
  `servicios_extra_catalogo`, `AppState.cargarCatalogoServicios` al
  arrancar junto a `cargarCanalComunicacion`; sin red, `catalogo`
  empaquetado), `linea(personas:, turnos:)`; editor del app agrupado por
  ámbito con `_ctrlServicio` bajo demanda y `AppState.
  actualizarServiciosExtraLocal` (espejo de la propagación web); resumen de
  reserva con contador − n + de personas (`_FilaServicio`/`_BotonCantidad`);
  `AgregarCanchaScreen` hereda los del local; Reservas del dueño muestran
  "× n". Test `test_servicios_extra_catalogo_global_por_local_y_por_persona`.
  **EDITAR LOCAL vs EDITAR CANCHA (pedido del director, 24-sep-2026: "los
  atributos del local no deberían repetirse al editar cada cancha"; solo
  web):** `GET/POST /anfitrion/local/{cancha_id}/editar`
  (`pagina_editar_local`, `guardar_edicion_local`) edita UNA vez lo que
  comparten todas las canchas del local: nombre del local (renombra todas),
  dirección (`COLS_EDITABLES` suma `direccion`), servicios del local
  (`amenidades`) y servicios extra de ámbito local; se escribe en cada
  hermana conservando sus extras propios de cancha. El editor de CANCHA ya no
  muestra club, amenidades ni extras del local: solo nombre, deportes/piso,
  precio, horario, fotos y "Servicios extra de esta cancha" filtrados por su
  deporte (`servicios_extra.para_cancha`; DEFAULTS: pelotero solo
  tenis/pádel/pickleball, petos solo fútbol/futsal/básquet; migración
  `servicios_extra_semilla=2` completa `deportes` en snapshots ya sembrados)
  + tarjeta "Tu local" con enlace a Editar local. `_validar_edicion` conserva
  amenidades y extras del local si el cuerpo no los trae (compat con
  clientes que sí los mandan). **Mis canchas** agrupa las filas por DEPORTE
  dentro del local (`.anf-dep`: "🎾 Tenis · 2 canchas") y tiene "✏️ Editar
  local" en la cabecera; aviso `?local_guardado=`. Test actualizado
  `test_servicios_extra_catalogo_global_por_local_y_por_persona`.
- **EDITAR CANCHA DESDE LA WEB (sep-2026, decisión del director: "web =
  vender y atender; app = operar", punto 1):** `GET/POST /anfitrion/cancha/
  {id}/editar` (`web/anfitrion.py`, calcado del editor de anuncios de
  Airbnb: nav lateral de secciones + tarjetas + barra inferior fija "Guardar
  cambios"). MISMO formulario, catálogos y validaciones que
  `editar_cancha_screen.dart`: fotos (hasta 8, portada = la primera, ★ para
  hacer portada, ✕ quita), nombre y local (único texto libre), deportes
  (chips ≥1, principal = 1.º de `deportesActivos`), tipo de piso
  (obligatorio, por deporte principal), precio + hora feliz [0,10,15,20,30]
  con rango + seña [0,20,30,50] con vista previa, horario (selects en punto,
  regla "cierre = empieza el último turno") + duración 60/90/120,
  amenidades (claves del APP: vestuario, duchas, parking, luces, techado,
  cafeteria, wifi, alquiler) y servicios extra con precio. Catálogo espejo
  en `web/catalogos.py` (**al cambiar un catálogo en el app, cambiarlo
  ahí**). Fotos: el navegador comprime a 1600 px JPEG y hace `POST
  /anfitrion/cancha/{id}/foto` (cuerpo crudo) → `web/almacen.py` sube al
  MISMO bucket `canchas/<id>/web_<ms>.jpg` por la REST de Storage con la
  llave anon (`SUPABASE_URL` + `SUPABASE_ANON_KEY` en Railway; sin ellas
  la subida queda apagada y se avisa); al guardar solo se aceptan URLs que
  ya tenía la cancha o de SU carpeta, y las quitadas se borran del bucket.
  Guardado: `datos.actualizar_cancha(id, dueno, campos)` = UPDATE con
  `lower(dueno)=correo de la sesión` en el WHERE (cancha ajena → 404) solo
  sobre `COLS_EDITABLES`; el explorador (`AMENIDAD_NOMBRE/ICONO`) reconoce
  las claves del app. **APK:** `_sincronizarConfigLocalDesdeNube` ahora
  también trae deportes, fotos y servicios extra (si no, el siguiente upsert
  del app pisaba la edición web). Test
  `test_editar_cancha_desde_la_web_como_el_app`.
- **CALENDARIO WEB OPERATIVO (sep-2026, puntos 2 y 3 del plan aprobado):**
  en `/anfitrion/calendario` cada turno es clicable (como el calendario de
  Airbnb, modal `#modalCal`): LIBRE → "📝 Reserva manual" (cliente reciente
  de sus propias reservas de 180 d, nombre, teléfono, correo opcional para
  que la vea en su app, precio sugerido = `precio_slot` con hora feliz y
  descuento del slot, "Ya pagó") o "⛔ Bloquear turno"; BLOQUEADO →
  Desbloquear; RESERVA → detalle + WhatsApp + "✅ Marcar pagada" / "↩
  Marcar por cobrar" (no en pagadas en línea) + "🗑 Quitar reserva" (SOLO
  manuales). Endpoints JSON (sesión + cancha del dueño, si no 401/404):
  `POST /anfitrion/bloqueo {cancha_id, fecha, hora, bloquear}`
  (`datos.bloquear`, tabla `pichangol_bloqueos` = la del app, 409 si hay
  reserva), `POST /anfitrion/reserva-manual` (misma fila que
  `agregarReservaManual`: id `man_<ms>_w`, `confirmada`,
  `traida_por_app=false` → sin comisión ni billetera, `medio_pago='manual'`,
  fecha REAL del slot de madrugada, rechaza pasado/bloqueado/ocupado; push
  "Reserva confirmada 🎾" al correo del cliente), `POST
  /anfitrion/reserva/{id}/pagado {pagado}` (`datos.marcar_pagado`, = 
  `marcarPago` del app; en la transición a pagado de reservas traídas por
  la app manda el push "¡Te llegaron puntos! ⭐"; también botón en la
  tarjeta de "Hoy", `JS_PAGAR`) y `POST /anfitrion/reserva/{id}/quitar`
  (`datos.borrar_reserva_manual`, solo `medio_pago='manual'`; push
  "Reserva cancelada 📅"). **Candado Pro:** `WEB_MANUAL_REQUIERE_PRO=1`
  (env, fail-open como `CM_REQUIERE_PRO`) exige `stores.pro_activo` para
  reserva manual y bloqueos (402 `requiere_pro` + aviso en el calendario);
  marcar pagado nunca es Pro. Apagado hasta que el APK también lo exija
  (backlog "Candado PRO"). Test
  `test_calendario_web_reserva_manual_bloqueo_y_marcar_pagado`. OJO tests:
  `FakeDB` copia las fixtures (`dict(c)`) — antes un test mutaba `LIMA`
  para los siguientes.
- **MI ACADEMIA Y MI TIENDA EN LA WEB (sep-2026, pedido del director):**
  `web/anfitrion_academia.py` y `web/anfitrion_tienda.py` (routers incluidos
  en `main.py` ANTES de `anfitrion_router`, porque `/anfitrion/{modulo}` es
  comodín; en `MENU` ambos van con `True` = web). **Mi tienda**
  (`/anfitrion/tienda`): candado = `puedeVender` del app
  (`datos.esta_verificado` en `pichangol_verificaciones` O dueño de canchas);
  lista con Publicado/Pausado, "＋ Publicar producto" (`/anfitrion/tienda/
  nuevo`, id `prod_<µs>_w`), editor tipo Airbnb (foto → bucket
  `productos/<id>.jpg` como el app, nombre, categoría chips
  `catalogos.CATEGORIAS_PRODUCTO`, descripción, moneda chips S/ $ Bs FIJA al
  crear —por defecto la del país de su 1.ª cancha—, precio, stock vacío =
  ilimitado, Publicado), `POST /anfitrion/tienda/guardar` (UPSERT
  `pichangol_productos` con `WHERE lower(vendedor_email)=yo`: id ajeno →
  404), `/{id}/activo`, `/{id}/eliminar` (borra fila + foto), y VENTAS
  desde `stores.ventas` por `vendedor_email`. **Mi academia**
  (`/anfitrion/academia`): lista de `pichangol_academias` del dueño
  (`data` jsonb = `Academia.toJson`), onboarding "Crear mi academia", editor
  (`/anfitrion/academia/nueva` id `ac_<µs>`, `/{id}/editar`): logo →
  `canchas/academia_<id>/logo_web.jpg`, deporte chips `DEPORTES_ACADEMIA`,
  nombre, descripción, sede (el campo "Club / local" AUTOCOMPLETA con
  Google Maps vía `/web/lugares` —pedido del director, sep-2026: escribir
  "esmon" y que el pin se ponga solo; `#resSede`, `CFG.buscar` = hay
  `PLACES_API_KEY`, sin llave es texto simple— + MAPA Leaflet clic / "Usar
  mi ubicación": del punto salen país → prefijo de WhatsApp, moneda —fija al
  crear— y zona; OJO: el div del mapa lleva la clase `.mapa-sede`, NO
  `.mapa-ficha`, que arranca en `display:none` y lo ocultaba), **zona en cascada** por país (`GET /web/geo/{iso}` sirve
  `web/geo/{pe,bo,ec}_geo.json` = COPIA de `assets/geo` del app; se guarda
  el nivel 3 como el app), WhatsApp (largo por país `TEL_LONGITUD`), fotos
  (hasta 8), redes chips + handle, **PROGRAMAS Y TARIFARIO = el MISMO
  editor del app `_EditorPrograma` (pedido del director, sep-2026: "en el
  app está perfecto, debería ser como en el app")**: tarjeta por PROGRAMA
  (Bola Roja y Naranja, Avanzados…) con etapa/edad, duración de clase, días y
  horario y el PRECIO SOCIO por frecuencia 2x…5x/sem (vacío = no se ofrece);
  al guardar se aplanan a los mismos `planes` mensuales que genera el app
  (id `prog | 2x`, nombre `prog · 2x/sem`, `programa` compartido). El editor
  web anterior ("Plan N" + programa escondido en un desplegable) hacía crear
  un plan por programa. Los planes viejos que no encajan (sin programa, sin
  frecuencia 2-5 o no mensuales) salen como "planes sueltos" solo para
  quitarlos; si no se tocan se conservan. `POST /guardar` deriva el nombre
  del plan si viene vacío con `programa`; reglas de cobro (recargo invitado, descuentos
  2.º/3.º hermano y prepago, meses mínimos, retribución al club). `POST
  /anfitrion/academia/guardar` valida como `crear_academia_screen._validar`
  y hace MERGE sobre la fila actual: `sedes`, `horarios`, `preciosSede`,
  `partidos`, `categorias`, `landingUrl` se CONSERVAN (se editan en la app).
  `/{id}/foto?tipo=logo|foto`, `/{id}/eliminar` (borrado lógico). **Alumnos**
  (`/anfitrion/academia/alumnos?academia=`): `pichangol_matriculas` con KPIs
  (alumnos, cobrado este mes, por cobrar, vencido) y tabla por alumno
  (apoderado, WhatsApp, cuotas pagadas, deuda, estado); los COBROS siguen en
  la app. Catálogos espejo en `web/catalogos.py`. Tests
  `test_mi_tienda_en_la_web_como_el_app`, `test_mi_academia_en_la_web_como_el_app`.
- **FICHA DE RESERVA (sep-2026, pedidos del director):** "Cómo llegar" abre
  el mapa DENTRO de la ficha (Leaflet + OpenStreetMap en `#mapaFicha`, con
  enlaces "Abrir en Google Maps" e "Indicaciones paso a paso" debajo), no en
  otra pestaña. Los turnos van ORDENADOS por franja (🌅 Mañana <12 · ☀️ Tarde
  12-18 · 🌙 Noche + madrugada del día siguiente) en tarjetas `.slot` con
  hora, fin, PRECIO del turno y etiqueta "⚡ hora feliz" / "−N % promo";
  ocupado = gris tachado; seleccionado = azul noche; nota "El precio varía
  según la hora: desde … hasta …" cuando hay diferencias.
- **Pool de conexiones Postgres (`db/pg.py::conexion()`, sep-2026):** cada
  `_conn()` abría una conexión nueva al pooler de Supabase (TLS ≈ 300-500 ms)
  y la ficha hacía 4-5 seguidas → 2 s de espera. `web/datos.py` usa
  `with pg.conexion() as conn` (hasta 4 conexiones reutilizadas, TTL 4 min,
  commit al salir / rollback+descarte si falló). Los caminos del snapshot
  siguen con `_conn()`.
- El apex `pichangol.app` (sin `www`) sigue libre (podría redirigir al `www`).

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
- **TORRES DE CONTROL (una por ambiente, IDÉNTICAS a la vista):**
  - **QAS / dev** → `https://pg-backend-production-c176.up.railway.app/admin`
    (mismo servicio: `https://pg.ebim.pe/admin`). Habla con Supabase
    **"Pichangol"** (`iuwnpjbxsltgmsybooeg`). Es la de trabajo diario.
  - **PRD** → `https://pg-backend-prd-production.up.railway.app/admin`. Habla
    con **PCG-PRD** (`xjoqotzfgniinxyxvhxj`). NO se toca sin autorización.
  - **`www.pichangol.app` → PRD** (movido ago-2026, autorizado por el director):
    el dominio de marca apunta al servicio `pg-backend-prd`, así que
    `https://www.pichangol.app/admin` **es la torre de PRODUCCIÓN**. Antes
    apuntaba a dev/QAS y esa trampa hizo revisar producción creyendo que era
    dev. QAS queda con `pg.ebim.pe` y su host `*.up.railway.app`.
    Las landings del piloto siguen emitiendo `pg.ebim.pe` (`LANDING_BASE_URL`
    de `pg-backend` sin cambios); la de PRD se ajusta en el corte.
  - Cada torre muestra su ambiente en la barra lateral (`PICHANGOL_ENTORNO` +
    ref del proyecto Supabase; PRD sale en rojo). Ante la duda, mirar ahí.
  - **PASE A PRD del 11-sep-2026 (autorizado por el director: "Pasar todo a
    producción. El app y la parte web"):** `prd` = merge `eadf629` de la rama
    de desarrollo (web anfitrión completa, reserva web, cabecera móvil, sync
    APK). Procedimiento que se siguió y se repite en cada pase: (1) `git
    checkout -B prd origin/prd && git merge --no-ff origin/<rama-dev> && git
    push origin prd` (Railway `pg-backend-prd` redespliega solo); (2) SQL
    pendientes en PCG-PRD vía el conector Supabase `apply_migration`
    (aplicados: `pichangol_chat_prefs`, `pichangol_lugares_fotos`); (3)
    variables nuevas en `pg-backend-prd` como REFERENCIAS al servicio QAS
    cuando el valor es el mismo (`GOOGLE_WEB_CLIENT_ID=${{pg-backend.
    GOOGLE_WEB_CLIENT_ID}}`, `PLACES_API_KEY` igual); (4) APK/AAB de PRD =
    `workflow_dispatch` de `build.yml` con `ref=prd` e `inputs.entorno=prod`
    (run 1277 → `pichangol-prod-1277.aab` como artifact + APK en el Release).
    Pendiente manual del checklist `docs/prd_railway_checklist.md`: llaves
    Culqi live y `DATABASE_URL` de PCG-PRD si aún no están. **Pase del
    18-sep-2026 (autorizado: "pasa todo a PRD"):** `prd` = merge `2b9b027`
    (reclamo/registro de canchas desde la web, ficha `/lugar`, búsqueda por
    nombre en Google, redescubrir al mover el mapa); Edge `places-cerca`
    v6 (paginación) desplegada en PCG-PRD vía el conector Supabase
    `deploy_edge_function` (`verify_jwt=false`, como estaba). Sin cambios
    en `lib/` → no hizo falta APK nuevo. **`search_path` de las funciones
    de push: aplicado en QAS (13-sep, push real verificado por el director)
    y en PRD el 18-sep-2026** vía `apply_migration`
    (`push_funciones_search_path`): las 3 funciones (`notificar_push_aviso`,
    `_matricula`, `_mensaje`) con `proconfig = {search_path=public, net}`,
    SECURITY DEFINER y su trigger activo. **Pase del 21-sep-2026
    (autorizado: "pasa todo a PRD"):** `prd` = merge `670f631` (mapa de la
    sede visible con `.mapa-sede` + buscador de club con Google Maps en Mi
    academia). Solo backend/web: sin SQL, sin Edge, sin APK. **Pase del
    22-sep-2026 (autorizado):** `prd` = merge de "Programas y tarifario en
    Mi academia igual que el app" (solo web). **Pase del 22-sep-2026 (2.º,
    autorizado):** `prd` = merge de "academias en el explorador web +
    descubiertas por pestaña" (solo web). **Pase del 22-sep-2026 (3.º,
    autorizado):** `prd` = merge `3688132` (ficha web de academia
    `/academia/{id}` con programas, tarifario y matrícula en línea + redes
    con logo en la tarjeta). Solo web: sin SQL, sin Edge, sin APK. **Pase
    del 22-sep-2026 (4.º, autorizado):** `prd` = merge `b498b24` (pestaña
    "🎓 Academias" en el explorador web). Solo web. **Pase del 23-sep-2026
    (autorizado):** `prd` = merge `6922720` (requisitos de Culqi: Libro de
    Reclamaciones en página propia, /legal/devoluciones, términos de
    compra web, redes oficiales configurables; Mis canchas del anfitrión
    agrupado por local). Solo web. Pendiente del director en PRD: cargar
    las redes oficiales en la torre y tener ≥1 cancha verificada. **Pase del
    23-sep-2026 (2.º, autorizado):** `prd` = merge del ícono SVG de local
    (`ui.LOCAL_SVG`) en Mis canchas. Solo web. **Pase del 23-sep-2026 (3.º,
    autorizado):** `prd` = merge de "ficha con el LOCAL de título + canchas
    en verificación ocultas hasta aprobarse" (solo web).
    **Pase del 23-sep-2026 (4.º, autorizado):** `prd` = merge `701ae4b`
    (explorador web con una tarjeta por LOCAL, como el app). Solo web.
    **Pase del 23-sep-2026 (5.º, autorizado):** `prd` = merge `6d9a97e`
    (agregar otra cancha a un local existente desde la web). Solo web.
    **Pase del 24-sep-2026 (autorizado: "Pasa a prd"):** `prd` = merge
    `940e636` (catálogo global de servicios extra en torre/web/APK, cobro por
    persona, Editar local separado del editor de cancha, Mis canchas por
    deporte). Sin SQL ni Edge (el catálogo se siembra solo en el snapshot).
    CAMBIÓ `lib/` → APK/AAB de PRD por `workflow_dispatch` de `build.yml`
    con `ref=prd` e `inputs.entorno=prod`.
    APK/AAB de PRD = run 1335 (`pichangol-1335.apk`, artifact
    `pichangol-aab-prod`; el 1.º intento falló por Gradle transitorio y se
    relanzó). **Pase del 24-sep-2026 (2.º, autorizado):** `prd` = merge
    `c2c3bd2` (texto blanco del botón del popup del mapa). Solo web.
    **Culqi en PRD (22-sep-2026, decisión del director):** mientras Culqi
    entrega las llaves live, `pg-backend-prd` lleva `CULQI_PUBLIC_KEY` y
    `CULQI_SECRET_KEY` como REFERENCIAS a QAS (`${{pg-backend.CULQI_*}}`,
    llaves `pk_test`/`sk_test`) para que la reserva y la matrícula web se
    vean en producción (Culqi lo revisa ahí). El director las sobrescribe A
    MANO con las live cuando lleguen; ojo: hasta entonces una tarjeta de
    prueba deja matrículas/reservas "pagadas" sin plata real en PRD. **RLS en
    `growth_*` de PCG-PRD: ACTIVADO el 12-sep-2026** (sin políticas ni
    FORCE: el backend entra como `postgres`, dueño de las tablas, y no lo
    afecta; la anon key ya no puede leerlas). **Funciones trigger de push
    `notificar_push_*` (SECURITY DEFINER): `EXECUTE` revocado a
    PUBLIC/anon/authenticated el 12-sep-2026 en PRD y el 13-sep en QAS
    (push real verificado por el director)** (script tolerante a funciones
    inexistentes: en QAS no hay `notificar_push_aviso()`, ahí el aviso va
    por Database Webhook; `docs/piloto/supabase_push_funciones_privilegios.sql`). Los
    triggers siguen disparando: Postgres pide EXECUTE al CREAR el trigger,
    no al dispararlo (probado con tabla desechable: INSERT como anon →
    dispara; llamada directa como anon → permission denied).
- **PUBLICAR EN FACEBOOK DESDE LA TORRE (pedido del director, 24-sep-2026:
  "una variante con fotos reales de canchas para mi primera publicación… y
  que en el admin haya un agente que mueva las redes"):** fase 1 en
  `backend/growth/marketing/post_redes.py` + pane `/admin` → Comunicación →
  **"📣 Publicar en Facebook"** (`GET /admin/api/redes/pichangol`, `POST
  …/plantilla|previsualizar|publicar`). El operador elige un LOCAL (fotos
  reales del bucket `canchas/` que subió el dueño, `_redes_canchas` agrupa
  por `club`) o sube fotos desde su computadora (data URL, comprimidas a
  1600 px en el navegador), hasta 4; plantilla (`PLANTILLAS`: lanzamiento,
  nuevo_local, promo, libre; `rellenar()` con {local} {zona} {deportes}
  {precio} {url}); `componer()` arma la pieza con Pillow (collage 1-4 fotos,
  degradado inferior, logo en disco, etiqueta naranja, título/subtítulo/pie;
  formatos `cuadrado` 1080², `horizontal` 1200×630, `historia` 1080×1920; DM
  Sans en `marketing/assets/`, sin emojis en la imagen). Vista previa en
  base64, "Descargar PNG" y **"Publicar en Facebook"** = Graph
  `/{FB_PAGE_ID}/photos` con el archivo en multipart (`_graph_multipart`, no
  necesita URL pública) + `message`. Credenciales `FB_PAGE_ID` +
  `FB_PAGE_TOKEN` (Page Access Token de larga duración, app propia en modo
  desarrollo: los administradores publican en sus páginas SIN App Review;
  guía en el propio pane); sin ellas el botón queda deshabilitado y la torre
  solo compone. Historial en `stores.publicaciones_redes` (snapshot, últimas
  50). **TOKEN DE PÁGINA vs DE USUARIO (trampa real, 24-sep-2026):** el
  director pegó en Railway el token de USUARIO extendido y Meta respondió
  `(#200) The permission(s) publish_actions are not available… deprecated`
  (ese mensaje NO habla de la página: sale cuando `/{page}/photos` recibe un
  token de usuario o uno sin `pages_manage_posts`). Ahora
  `post_redes._resolver_token()` pregunta `/me` con el token: si el id es la
  página → token de página (scopes vía `debug_token`); si es una persona →
  lee `/me/permissions`, pide `/{page}?fields=access_token` y publica con ESE
  token de página (caché 10 min); `estado_pagina()` devuelve `token_tipo`,
  `usuario`, `faltan`, `advertencia` y el pane lo pinta (rojo si falta
  `pages_manage_posts` o el usuario no administra la página, ámbar si es de
  usuario y se derivó solo). `_pista_error` traduce los #200/#190 a qué
  hacer. **TOKEN QUE VENCE (caso real, 24-sep-2026 22:00 PDT: "(#190)
  Session has expired"):** el token de usuario del Explorador sin extender
  dura 1-2 h. Ahora `_resolver_token()` prueba (1) el token de PÁGINA que la
  torre ya derivó y GUARDÓ cifrado en `stores.config[fb_page_token_cifrado]`
  (Fernet con `META_TOKEN_KEY` vía `redes.cifrar`; meta en
  `fb_page_token_meta`; se persiste al instante con `_persistir_ahora`) y
  (2) `FB_PAGE_TOKEN` de Railway: si es de usuario lo EXTIENDE a 60 días
  con `META_APP_ID/SECRET` (`oauth/access_token` `fb_exchange_token`) y
  pide `/{page}?fields=access_token` → token de página que NO vence
  (`debug_token` con `APP_ID|APP_SECRET` da `expires_at`, `vence`=0 =
  nunca), y lo guarda. Un guardado que Facebook rechaza se olvida solo y
  se cae al de Railway; publicar con (#190) también lo olvida. El pane tiene
  "🔑 Token de Facebook": el operador PEGA un token nuevo (`POST
  /admin/api/redes/pichangol/token`, `guardar_token_operador`: analiza,
  deriva, guarda; nunca se devuelve) sin tocar Railway, ve origen
  (torre/Railway) y vencimiento, y puede "Olvidar el guardado"
  (`/token/olvidar`). `configurado()` vale con `FB_PAGE_ID` + (Railway o
  guardado). Test `test_token_vencido_se_reemplaza_desde_la_torre_sin_
  tocar_railway`. **VIDEO (pedido
  del director, 24-sep-2026: "también debe permitir subir videos y que haga
  el post"):** bloque "🎬 O publica un VIDEO" en el pane: el archivo (MP4/MOV/
  M4V/WEBM/AVI/MKV/3GP, tope `FB_VIDEO_MAX_MB`=300) sube a la torre por XHR
  con barra de progreso (`POST /admin/api/redes/pichangol/video?nombre=`,
  cuerpo crudo por `request.stream()` a disco en `tempfile/pichangol_redes_
  videos`, 413 si pasa el tope; `video_id` temporal 2 h, `_limpiar_videos`;
  `/{id}/descartar`). La vista previa muestra el `<video>` local (el
  navegador; nada se compone en el servidor) y el título pasa a "Título del
  video (opcional)"; subtítulo/etiqueta/pie/formato se ocultan. Publicar con
  `video_id` → `publicar_video_facebook`: subida REANUDABLE de Graph
  `/{page}/videos` (`upload_phase=start` con `file_size` → `transfer` por
  trozos `video_file_chunk` con los offsets que devuelve Meta, timeout 600 s,
  corta si no avanza → `finish` con `description`=texto, `title`,
  `published=true`); URL `facebook.com/{video_id}`; Facebook lo procesa unos
  minutos. Historial con `tipo: video`, `video_nombre`, `video_bytes`; el
  temporal se borra al publicar y se conserva si Facebook falló (reintento).
  Preloader en todo (velo, barra, botón "Publicando…"). OJO Playwright: el
  Chromium del sandbox no decodifica H.264 (duración 0 con .mp4); probar con
  .webm. Test `test_video_se_sube_a_la_torre_y_se_publica_por_trozos`.
  **REDACTOR CON IA (queja del director, 24-sep-2026: "todos los posts son la
  misma temática, todos dicen llegó Pichangol; acá debe interactuar la IA
  para que sea más natural"):** `post_redes.redactar(cancha, tono, enfoque,
  tema, evitar)` + `POST /admin/api/redes/pichangol/redactar`. Chip
  "✨ Redactar con IA" es la plantilla POR DEFECTO del pane (las fijas
  siguen): controles de TONO (cercano/divertido/informativo/motivador),
  ENFOQUE (`ENFOQUES`: auto, beneficio, local, comunidad, tip, finde, promo,
  duenos, academia, humor, historia), "Algo que quieras que mencione" (texto
  del operador) y "🔁 Otra versión". Motor = Anthropic (`ANTHROPIC_API_KEY`
  + `MARKETING_MODEL`, el mismo del CM de academias) con `_SYSTEM_REDACTOR`
  (español natural, 0-3 emojis, un CTA, 3-6 hashtags con #pichangol, solo
  HECHOS del local vía `_contexto_local`: nombre, zona, deportes, precio con
  moneda del país, horario, país por `pais_de_coordenadas`; prohibido
  "¡Llegó Pichangol!" salvo pedido). ANTI-REPETICIÓN: se le pasan
  `recientes_no_repetir` (título + 1.ª línea de los últimos 10 del historial
  + lo generado en la sesión, `evitar`) y `enfoques_recientes`;
  `_elegir_enfoque` en "auto" evita los últimos 4 enfoques publicados (el
  historial guarda `enfoque` y `fuente`). Sin llave o si el modelo falla →
  `_banco` (variantes por enfoque con los datos reales, humor según el
  deporte) rotando a otro enfoque antes de repetir; un enfoque pedido a mano
  se respeta. Topes: título ≤36 (va sobre la foto), subtítulo ≤80, etiqueta
  ≤14. Test `test_redactor_ia_varia_el_enfoque_y_no_repite_lo_publicado`.
  **PULIDO DE VIDEO "ESTILO CAPCUT" EN CASA + SUBTÍTULOS WHISPER (plan
  aprobado por el director, 24-sep-2026, puntos 1 y 2; CapCut NO tiene API
  pública):** `marketing/video_pulido.py`. Con el video ya subido, el pane
  muestra "✨ Pulir con estilo Pichangol": formato (vertical 9:16 · cuadrado
  · original), Logo (marca de agua `_png_marca`), Intro 1,2 s (`_png_intro`),
  Rótulo con el título (`_png_rotulo`, 0,6-5,1 s), Cierre 3 s con título y
  www.pichangol.app (`_png_cierre`), Subtítulos automáticos y música original
  (`musica.generar_pista`) si el video no trae audio. Todo con el FFmpeg
  empaquetado de `imageio-ffmpeg` (johnvansickle static 7.0: tiene `ass`/
  `subtitles`, `gblur`, `concat`, `loudnorm`, `amix`; NO tiene `drawtext`,
  por eso los textos de marca son PNG de Pillow que se superponen). Encuadre
  que no calza → fondo desenfocado (`split` + `gblur=38` + overlay centrado);
  audio `loudnorm I=-16`; H.264 veryfast CRF 22 + AAC 128k + faststart, 30
  fps; intro/cierre = imagen en bucle + `aevalsrc` silencio → `concat`.
  **Subtítulos:** `transcribir()` extrae el audio (mono 16 kHz MP3 48k) y
  llama a Whisper (`OPENAI_API_KEY`, `WHISPER_MODEL`=whisper-1,
  `verbose_json` con `timestamp_granularities[] = word + segment`);
  `partir_segmentos` deja frases ≤6 palabras / ≤4 s; `escribir_ass` genera
  ASS con DM Sans (`fontsdir=marketing/assets`), caja oscura (BorderStyle 3)
  y la palabra en curso en LIMA con karaoke `\k` cuando hay tiempos por
  palabra (estilo Plano si no). El operador CORRIGE los textos en la torre
  ("✏️ Corregir subtítulos" → "🔁 Regenerar con mis correcciones"; una línea
  editada pierde el resaltado por palabra). Trabajo en hilo
  (`iniciar_trabajo`, progreso real de `-progress pipe:1`), endpoints
  `POST /admin/api/redes/pichangol/video/{id}/pulir` (409 si ya corre o si
  piden subtítulos sin llave), `GET …/estado` (sondeo cada 1,5 s),
  `GET …/archivo?cual=pulido|original` (la torre lo pide con fetch +
  cabecera y lo muestra como blob; un `<video src>` no puede mandar el
  token). El pulido queda junto al temporal (`<id>_pulido.mp4`,
  `anotar_video(pulido=, pulido_info=, transcripcion=)`); publicar usa la
  pulida salvo `usar_pulido=false` (radio "Publicar la pulida / el
  original"); historial con `pulido` y `subtitulos`. Un clip de 4 s se pule
  en ~6 s; el sondeo muestra fase y %. Test
  `test_pulido_estilo_pichangol_con_subtitulos_whisper` (renderiza de verdad
  con FFmpeg; Whisper simulado). Backlog del plan: (3) plantillas en la nube
  (Shotstack/Creatomate) si se quieren transiciones vistosas, (4) voz en off
  ElevenLabs, (5) IG Reels con el mismo video.
  **El entorno de Claude NO alcanza Storage de Supabase ni bancos de
  fotos (proxy 403): las piezas con fotos reales se componen en el backend.**
  Fase 2 (backlog): calendario + copy con IA reutilizando `marketing/cm.py`.
  Portada de la página: `tool/portada_facebook.py` →
  `static/brand/portada_facebook.png` (1640×720). Test `test_redes_pichangol.py`.
- **DATOS DE LA EMPRESA CONFIGURABLES DESDE LA TORRE (pedido del director,
  sep-2026):** razón social, tipo y número de documento fiscal (RUC/NIT),
  dirección, ciudad corta, **WhatsApp POR PAÍS** (Perú, Ecuador, Bolivia:
  claves `contacto_whatsapp_pe|ec|bo`, las MISMAS que ya usaba el APK vía
  `reclamos.contacto_whatsapp(pais)` → una sola fuente app+web; el pane viejo
  "Contacto WhatsApp" se fusionó aquí), correo de contacto, correo de
  privacidad (opcional; vacío = el de contacto) y horario viven en
  `stores.config` (claves `empresa_*`, defaults en `CONFIG_DEFAULT`) y se
  editan en la torre `/admin` → Comunicación → **"🏢 Datos de la empresa"**
  (`GET/POST /admin/api/empresa`, valida correo/WhatsApp local 7-10 dígitos/
  obligatorios). Un país sin número NO se muestra en la web; con varios, la
  tarjeta Contacto lista uno por línea con bandera SVG y hay un botón
  "WhatsApp Perú / Ecuador / Bolivia" por país. Migración única en
  `Stores.load_state` (`empresa_wa_migrado`): los snapshots viejos tenían
  Perú vacío y se siembra con el número que ya estaba publicado. Fuente
  única: `backend/growth/empresa.py` (`datos()` ya escapado + derivados
  `whatsapps`, `wa_url`, `whatsapp_bonito`, `anio`; `rellenar(html)`
  sustituye los marcadores `{{EMPRESA}} {{DOC_ETIQUETA}} {{RUC}} {{DIRECCION}}
  {{CIUDAD}} {{WA_URL}} {{WHATSAPP}} {{WHATSAPP_LISTA}} {{WA_BOTONES}}
  {{CORREO}} {{CORREO_PRIVACIDAD}} {{HORARIO}} {{ANIO}}`). Lo
  consumen: `legal/home.html` (secciones Contacto/Términos/Privacidad/Libro
  que la portada anida vía `web/marca.py`), el pie de TODAS las páginas web
  (`ui.footer`), `/legal/*` (`legal/router.py`, `CONTACTO` ahora es dinámico),
  la respuesta de `POST /reclamaciones` y los textos "Dudas:" del checkout,
  Mis reservas y el comprobante. **Nunca volver a escribir RUC/correo/
  teléfono a mano en HTML**: cada ambiente (QAS y PRD) tiene los suyos en su
  snapshot y el director los cambia sin publicar código. Test
  `test_datos_de_la_empresa_configurables_desde_la_torre`.
- **OBSERVACIONES DE CULQI AL AFILIAR www.pichangol.app (22-sep-2026) y cómo
  se cubrieron:** (1) **Libro de Reclamaciones "no implementado de forma
  correcta"** → antes solo era una sección anclada (`/#reclamaciones`) al
  fondo del explorador; ahora tiene PÁGINA PROPIA `GET /libro-de-reclamaciones`
  (alias `/legal/libro-de-reclamaciones`, `legal/router.py::
  libro_de_reclamaciones`, `ui.shell` con cabecera y pie) con el formato de
  hoja del D.S. 011-2011-PCM: distintivo rojo `ui.LIBRO_SVG`, datos del
  proveedor (razón social, RUC, domicilio, correo de la torre), consumidor
  (+ `c_apoderado` si es menor), bien contratado, detalle/pedido, texto legal
  (no impide denunciar ante INDECOPI; 15 días hábiles prorrogables), y tras
  registrar (`POST /reclamaciones`, mismo endpoint) muestra la HOJA completa
  con número y fecha, "Observaciones del proveedor: pendiente" y botón
  "Imprimir / guardar copia" (`window.print`, CSS `@media print` oculta
  cabecera/pie/formulario). La sección de la portada sigue y enlaza a la
  página. (2) **Política de cambios y devoluciones con razón social
  explícita** → `GET /legal/devoluciones` (reservas con `WEB_CANCELACION_
  HORAS`, matrículas, marketplace 7 días, saldo/Pro, cómo pedirla, mismo
  medio ≤7 días hábiles); la sección `#devoluciones` de `home.html` nombra a
  `{{EMPRESA}}` y enlaza. (3) **Términos visibles** → `/legal/terminos` suma
  "3-bis. Compras en la web" (precio visible, Culqi, comprobante, Libro) y
  el pie + menú ☰ enlazan Términos / Devoluciones / Libro (páginas propias,
  ya no anclas). (4) **Redes sociales** → la web NO tenía íconos; ahora
  `empresa.REDES` (instagram/facebook/tiktok/youtube) son campos de la
  torre → Comunicación → Datos de la empresa (`empresa_instagram|facebook|
  tiktok|youtube`, URL oficial o @usuario, `_url_red` valida el dominio) y
  el pie muestra "Síguenos" + ícono SOLO de las configuradas
  (`ui.redes_pie`, `empresa.redes()`); sin configurar, ningún ícono (Culqi
  rechaza íconos vacíos). Los SVG viven en `ui.RED_SVG` (router/academia los
  reusan). (5) **Botón de compra funcional** → la causa real era que PCG-PRD
  tenía 0 canchas públicas y `CULQI_PUBLIC_KEY` vacía (ver "Culqi en PRD"):
  sin canchas reservables ni llave, el revisor no ve ningún checkout. Hay que
  tener al menos una cancha VERIFICADA con dueño en PRD (y la academia con
  matrícula). Test `test_requisitos_culqi_libro_devoluciones_terminos_y_redes`.
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
- **`PUBLIC_BASE_URL` por ambiente (trampa resuelta sep-2026):** es la base
  de TODAS las URLs que el backend le entrega a terceros para volver (retorno
  y cancelación de PayPhone, callback de Libélula, página puente `/pagos/ec/ir`,
  media del CM). QAS (`pg-backend`) DEBE ser `https://pg.ebim.pe` y PRD
  (`pg-backend-prd`) `https://www.pichangol.app`. QAS quedó con el dominio de
  marca tras moverlo a PRD y todos los retornos de pasarela de pruebas caían en
  producción (que no conoce el pago) → PayPhone "No autorizado" + reversa a
  los 5 min. Al registrar dominios autorizados en una pasarela, registrar el
  host de `PUBLIC_BASE_URL` de ESE ambiente.
- **Config (env, `config.py`):** `ADMIN_PANEL_TOKEN`, `FACTILIZA_API_TOKEN`,
  `PICHANGOL_ADMIN_WHATSAPP`, `TWILIO_*`, `WHATSAPP_*`, `OTP_CANAL_PREFERIDO`
  (`whatsapp|twilio_whatsapp|sms`), `VALIDADOR_ACTIVA_AUTOMATICO`,
  `RECLAMO_VALIDACION_GPS_MAX_M=150`, `RECLAMO_UBICACION_MAX_M=150`, `DATABASE_URL`,
  `LIBELULA_APPKEY` (Bolivia), `PAYPHONE_TOKEN` + `PAYPHONE_STORE_ID`
  (Ecuador; se sacan en PayPhone Business → Developer → Aplicaciones; sin
  ambos el módulo queda inactivo y `/pagos/ec/config` responde
  `disponible:false`). PayPhone exige CONFIRMAR cada cobro antes de 5 min o
  lo revierte: lo hace `/pagos/ec/retorno` al instante y, de respaldo, el APK
  manda el `transaction_id` al consultar `/pagos/ec/pago/{id}`.
  **Persistencia en GET (trampa, sep-2026):** el middleware de `main.py`
  solo guarda el snapshot tras POST/PUT/DELETE; los RETORNOS de pasarela
  llegan por GET (el navegador del cliente vuelve) → todo handler GET que
  mute plata debe llamar `pagos/router.py::_persistir_ahora()` (lo hacen
  `/pagos/ec/retorno`, `/pagos/ec/pago/{id}` y `/pagos/ec/cancelado`). Se
  perdió la primera recarga real de PayPhone por esto.
  `APP_API_KEY` (clave app↔backend: si está seteada, los endpoints PÚBLICOS de
  `propiedad/router.py` exigen la cabecera `X-App-Key` — solo el APK oficial la
  trae; vacía = no se exige, para rollout gradual). Debe coincidir con el
  dart-define `APP_API_KEY` del APK. `CM_REQUIERE_PRO` (candado del community
  manager con IA: si `1`, sólo un correo con **Pichangol Pro** vigente
  —`stores.pro_activo(email)`— puede generar post/reel o activar el CM;
  `marketing/router.py:_require_pro` responde **402 `requiere_pro`**. Fail-open:
  apagado por defecto y no bloquea a APKs que no mandan `email` — sólo a quien SÍ
  se identifica y no es Pro. El APK manda `email` y ante 402 ofrece activar Pro).
- **Recargas por QR (Yape directo) — código HECHO, EN STANDBY (decisión del
  director ago-2026):** NO activar hasta tener un **QR de Yape EMPRESA a
  nombre de Pichangol/EBIM** (un QR personal mata la confianza). El flujo
  completo ya está: el usuario yapea al QR, sube su constancia
  (`RecargaQrScreen`, bucket `canchas/recargas/`) y el OPERADOR
  aprueba/rechaza en la torre (`/admin` → Cobros → Recargas QR): al aprobar
  se acredita el saldo (pago `recarga`, medio `yape_qr`) y llega push vía
  `pichangol_avisos`. Mientras las envs de Railway estén VACÍAS, la opción
  queda OCULTA en el APK (así se queda por ahora). Para activar cuando exista
  el Yape Empresa: `RECARGA_YAPE_QR_URL` (imagen del QR) +
  `RECARGA_YAPE_NUMERO` + `RECARGA_YAPE_NOMBRE`. Endpoints
  `/pagos/recarga-qr*` (app) y `/pagos/recargas-qr` (admin). Una pendiente
  por usuario; tope S/1000.
- **Auth por usuario billetera (endurecimiento PROD):** `PAGOS_AUTH_USUARIO=1`
  exige ID token de Google (header `X-User-Token`) en saldo/movimientos/reset;
  apagado default. Opcional `GOOGLE_OAUTH_CLIENT_IDS` (audiencia).
- **Promos de billetera (hecho ago-2026):** BONO DE RECARGA (config en torre
  `/admin` → Cobros → Promociones: % extra + recarga mínima + tope; 0% =
  apagado; se acredita solo en TODOS los caminos de recarga — Culqi síncrono,
  webhook, QR aprobado, Libélula — idempotente por cargo, pago
  `bono_recarga` + push 🎁) y CUPONES de saldo (crear/desactivar en torre;
  canje `/pagos/cupon/canjear`, un canje por usuario, pago `cupon`). APK:
  banner de la promo en billetera y en Recargar; "¿Tienes un cupón?" en la
  billetera. El costo lo asume Pichangol (marketing).
- **MARCHA BLANCA / onboarding de dueños (hecho ago-2026):** (1) **Pro de
  CORTESÍA**: torre `/admin` → Cobros → Pichangol Pro → "🎁 Pro de cortesía"
  (correo + 30/60/90/180 días; revocable; `POST /pagos/pro/cortesia`, admin).
  La cortesía NUNCA se auto-renueva del saldo (candado en
  `procesar_renovaciones_pro`) y queda FUERA del MRR. (2) **BIENVENIDA
  AUTOMÁTICA** (config torre, mismo pane: `bienvenida_pro_dias` +
  `bienvenida_saldo_soles`, 0/0 = off): al ACTIVARSE la primera cancha de un
  dueño (`_bienvenida_al_activar` en los 3 caminos de reclamos), recibe días
  de Pro cortesía + **SALDO DE REGALO POR PAÍS** (decisión del director,
  sep-2026: **S/ 20 · \$ 5 · Bs 35**; claves `bienvenida_saldo_soles|usd|bob`,
  el país sale de las coordenadas del reclamo vía `paises.py::
  pais_de_coordenadas`, espejo de las cajas del APK) (`stores.saldos_promo`, bolsillo
  SEPARADO que SOLO consumen comisiones vía `debitar_comision` — regalo
  primero, plata real después; NO liquidable/transferible/gastable en
  Pro/torneo/bodega, así no se vuelve plata real que salga de PCG). Un regalo
  por correo (`stores.bienvenidas`), pago auditable `bono_bienvenida` + push
  🎁. `/pagos/saldo` devuelve `saldo_promo_soles`; el APK lo pinta en la
  billetera (banner 🎁 en `cuenta_screen`, silencia el aviso "saldo bajo"
  mientras haya regalo).
- **Limpieza de Storage (hecho ago-2026):** el APK borra cada archivo cuando
  muere su dueño lógico (`lib/data/storage_limpieza.dart` + los `eliminar` de
  canchas/estados/productos/bodega/campeonatos, avatares viejos al cambiar foto,
  y estados+docs de identidad en "Dejar en virgen"). Para lo ACUMULADO antes,
  la torre `/admin` → Mantenimiento → **"Limpiar almacenamiento"** hace el
  barrido (`backend/growth/storage_limpieza.py`: detecta por SQL contra
  `storage.objects` y borra por Storage API). **Principio: nunca borrar lo que
  no se reconoce** — cada consulta parte de un JOIN contra la tabla dueña y
  sólo marca el archivo si esa fila dice que murió; lo que no corresponde a
  nada conocido se REPORTA (`desconocidos`), no se borra. Buckets cubiertos:
  `canchas`, `estados`, `productos`, `chat` (avatares viejos + media de chats
  borrados), `canales`, `grupos`, `verificacion`. **Jamás se borran**
  `canchas/recargas/*` (constancias), `ilustraciones/`, `afiches/` ni
  `bodega/packshot*` (arte compartido del backend). Cuidado al escribir SQL de
  detección: `NOT IN` con un solo NULL devuelve vacío en silencio (usar JOIN),
  y una denylist de carpetas se rompe apenas el backend crea una carpeta nueva.
  La torre muestra cuántos archivos ALCANZA A VER (radiografía): un "0
  huérfanos" sin ese dato no distingue "limpio" de "no veo nada". Opcional:
  cron `STORAGE_BARRIDO_AUTO=1` (apagado por defecto) cada
  `STORAGE_BARRIDO_HORAS`. Requiere las policies de
  `docs/piloto/supabase_storage_limpieza.sql`.
- **Tests:** `cd backend/growth && python3 -m pytest -q` (deben pasar todos).
  Cumplimiento Ley 29733 (DNI = dato personal: solo validar dueño, no publicar).

> Existe además el servicio Railway `pg-places` y el backend
> `backend/onboarding_verificacion` (módulo de existencia / VERIF_API_URL).

## Build (GitHub Actions → APK)

- **Nivel de API (Play Store):** `tool/configure_platforms.py::configurar_target_sdk`
  fuerza `compileSdk`/`targetSdk` a `SDK_OBJETIVO` (**36** desde ago-2026) y
  silencia el aviso del AGP viejo (`android.suppressUnsupportedCompileSdk`). Sin
  esto Play RECHAZA el App Bundle. **El mínimo SUBE con el tiempo** (34 → 35 →
  36): cuando Play lo vuelva a subir, se cambia esa constante y nada más. Los
  subproyectos de plugin van al mismo nivel. Ojo: apuntar a 35+ activa el modo
  borde a borde — revisar que ninguna pantalla quede tapada por las barras del
  sistema.
- **AAB para Play:** sólo lo generan los builds MANUALES (`workflow_dispatch`).
  `entorno=dev` → paquete `pe.ebim.pichangol`; `entorno=qas` → `.qas`, que
  **rompe el login con Google** (el cliente OAuth está registrado para el
  paquete de producción) — no usar `.qas` para pruebas con usuarios reales.

- **LOGIN CON GOOGLE EN LA VERSIÓN DE PLAY (trampa resuelta sep-2026):** Play
  App Signing re-firma el AAB, así que la app bajada de la tienda NO lleva la
  firma del keystore del CI. Google Sign-In exige un cliente OAuth Android por
  cada certificado (paquete + SHA-1); si falta uno, `ApiException: 10`. Hoy hay
  CUATRO huellas registradas en Firebase `fire-b9e79` (app `pe.ebim.pichangol`)
  y cada una con su cliente OAuth en Google Cloud (Firebase NO crea el cliente
  solo — hay que crearlo a mano en Credenciales):
  1. keystore del CI (sideload) `B9:37:…:81:07`;
  2. **llave de firma ANTERIOR de Play** `B1:37:61:D0:…:CC:FB:83:D1` — Play la
     generó el 29-ago-2026 y la rotó el mismo día; la consola la esconde al
     fondo de "Firma de apps → Claves de firma de la app anteriores" con 0 %
     de instalaciones, pero el APK entregado la lleva como PRIMER certificado
     del historial (`signingCertificateHistory[0]`) y ES la que Google Sign-In
     valida. Fue la causa de un día entero de "error 10" con todo lo demás
     bien configurado;
  3. clásica actual `A5:C1:…:51:73:18`; 4. poscuántica `4C:55:…:42:EC:BB`.
  Para diagnosticar sin adivinar: **Ajustes → Diagnóstico → "Firma de esta
  instalación"** muestra el SHA-256 del primer certificado del historial y el
  origen (Play vs sideload); se compara contra las huellas de Play Console.
  Ojo: la consola muestra SHA-1 y SHA-256 del MISMO certificado y no se parecen
  en nada — comparar siempre el mismo algoritmo.
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

## Mi bodega (POS ligero del dueño, función Pro)

Pestaña **Bodega** del panel del dueño (`bodega_screen.dart`): caja rápida
(venta en 3 s, descuenta stock, medio efectivo/yape/cortesía — la plata NO
pasa por Pichangol, cero comisión), catálogo con stock y alertas de
reposición, reportes (hoy/7 días/top/valorizado) y **carta digital pública**
`/b/{carta_id}` con QR imprimible (`/b/{id}/qr.png`, lib `qrcode` en el
backend growth). `carta_id` = hash FNV del correo (no expone el email).
Datos: `lib/models/bodega.dart`, `lib/data/bodega_repo.dart`, tablas
`pichangol_bodega_productos`/`pichangol_bodega_ventas`
(SQL `docs/piloto/supabase_bodega.sql` + `supabase_bodega_moneda.sql`).
Candado Pro dentro de la pantalla.
**Fase 2 — PEDIDOS A LA CANCHA (hecho):** el jugador pide desde la ficha del
club (`pedir_bodega_screen.dart`, botón "Bodega del local" en club_detalle,
solo locales verificados) → push al dueño (`avisarPedidoBodega`) → pestaña
"Pedidos" de la bodega: Confirmar/Rechazar y "Entregado · cobrar" (registra
venta + descuenta stock). Candados: toggle `acepta_pedidos` (off default) +
zonas configurables + GPS ≤250 m + expira a los 10 min. Tablas
`pichangol_bodega_pedidos`/`pichangol_bodega_config`
(SQL `docs/piloto/supabase_bodega_pedidos.sql`).
**CUENTA ABIERTA (hecho):** "apúntamelo, pago al salir" — el dueño la activa
(toggle `permite_cuenta`, off default) con TOPE por cuenta (`tope_cuenta`,
chips 50/100/200/300/sin tope, moneda del local). "A la cuenta 📒" aparece al
entregar un pedido (cliente identificado) y en la caja (solo cuentas ya
abiertas); el stock baja al entregar, la VENTA se registra UNA sola vez al
CERRAR la cuenta (cobro efectivo/yape/cortesía). Cliente ve "llevas X" en
vivo en `pedir_bodega_screen`. Candados de concurrencia en cerrar/anotar
(solo si sigue abierta) y en todo cambio de estado de pedidos
(`cambiarEstadoPedidoSi`: cancelar vs confirmar, cobro doble entre equipos).
Tabla `pichangol_bodega_cuentas` + columnas config
(SQL `docs/piloto/supabase_bodega_cuentas.sql`).
**Packshots IA (hecho):** imagen automática del producto = foto real del
dueño > packshot IA genérico por TIPO sin marcas (`marketing/packshot.py`,
`GET /bodega/packshot/{tipo}`, Storage `bodega/packshot_*.jpg`,
`packshotTipoDe`/`ImagenProductoBodega` en el APK) > emoji.
**Fase 3 — PAGO CON SALDO (hecho ago-2026):** el cliente puede PREPAGAR el
pedido con su saldo Pichangol en la confirmación (solo si alcanza y la
moneda coincide): debita al pedir, el pedido nace `pagado=true` (columna
SQL `supabase_bodega_pago.sql`; insert ESTRICTO si pagado — sin la columna
no se cobra) y el dueño recibe el monto COMPLETO "por recibir" (bodega =
CERO comisión, `venta_bodega` con comisión congelada 0; egreso del cliente
`bodega_pago`). El dueño VERIFICA el pago contra el backend antes de
entregar sin cobrar (`GET /pagos/bodega-pago/{id}`) y la venta se registra
con medio `saldo`. Cancelación/rechazo → `POST /pagos/bodega-reembolso`
(idempotente, bloqueado si ya se liquidó al dueño) + push 💸. La cuenta
abierta sigue cobrándose al cierre (efectivo/yape).

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

- **UNA PERSONA = UN CHAT (hecho sep-2026):** con la misma persona podían
  existir varios hilos (`cancha_<dueño>|<jugador>` desde la ficha,
  `directo_a|b` desde contactos, `<academiaId>|<alumno>`) y salían como filas
  DUPLICADAS. `mensajes_screen._fusionarPorPersona` agrupa por
  `_personaDe(conv)` (correo de la contraparte) y deja UNA fila: el hilo
  principal es el más reciente (ahí se envía lo nuevo), `_Conv.hilos` lleva
  todos, no leídos sumados, título = nombre del local/academia si soy el
  jugador/alumno, si no el nombre de perfil. `ChatScreen(hilosExtra:)` muestra
  el historial de todos los hilos (`MensajesRepo.streamHilos`, `inFilter`) y
  decide "mío" por correo en los mensajes de otros hilos. Fijar/archivar/
  silenciar/eliminar aplican a TODOS los hilos de la fila. `hiloCancha`
  ahora pasa el correo del dueño a minúsculas (evita hilos gemelos por
  mayúsculas).
- **BANDEJA EN LA NUBE (hecho sep-2026):** eliminar/fijar/archivar/silenciar
  vivían SOLO en `SharedPreferences` → al reinstalar o volver a entrar, los
  chats eliminados reaparecían. Ahora se espejan en Supabase
  `pichangol_chat_prefs` (email, hilo, oculto_en, fijado, archivado,
  silenciado; SQL `docs/piloto/supabase_chat_prefs.sql`) vía
  `ChatPrefsRepo`: cada acción sube su fila (`AppState._subirPrefChat`) y
  `sincronizarBandejaChats` (al login forzado + al abrir Mensajes, cada 10
  min) baja y fusiona (la nube manda sobre los hilos que conoce; lo solo-local
  se sube). Regla "reaparece si llega algo más nuevo" intacta (`chatOculto`
  también limpia la nube). "Eliminar mi cuenta" y "Dejar en virgen" borran
  las filas.

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
sigue el lenguaje Airbnb sobre la paleta EBIM. **REGLA del director (sep-2026):
TODO el diseño, app y web, debe ser similar al de Airbnb** — antes de dibujar
una pantalla nueva, buscar la pantalla equivalente en airbnb.com (Explorar =
portada, Mis reservas = "Viajes", ficha = anuncio, filtros = modal Filtros,
cabecera, menú ☰, calendario) y calcarla con la paleta y el logo de Pichangol;
no inventar layouts propios. Rasgos Airbnb:
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
  rails/barras de navegación van coloreados por sección (no gris plano). La
  pestaña **Mensajes lleva un ícono de chat NORMAL** (`Icons.chat_bubble` /
  `_outline`, vía `IconoMensajesLogo`/`IconoChatPichan`, que heredan el color
  del tema o reciben el de la sección) — decisión del director sep-2026:
  ni el logo de PCG ni la burbuja con la "P" (ambas se probaron y se
  revirtieron). El globo de chat de las fichas (ChatBurbuja) sí usa el pin de
  Pichangol como fallback sin logo del local.
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

## Entrenador virtual (visión IA, HECHO fase 0 ago-2026)

"Coach que ve tu video": el jugador graba su golpe (≤20 s) →
`entrenador_screen.dart` (Perfil → Entrenador virtual; deporte/golpe por
chips, multi-deporte) sube el clip al bucket `canchas/entrenador/` →
`POST /entrenador/analizar` (backend `entrenador/router.py`): extrae frames
(imageio-ffmpeg), visión IA (`ENTRENADOR_MODEL`, default haiku) con prompt de
coach → informe JSON (resumen, fortalezas, correcciones con `tip_reloj` ≤42
chars, drills, `encuadre_ok`). Historial en Supabase
`pichangol_entrenador_analisis` (SQL `docs/piloto/supabase_entrenador.sql`;
PRD ya aplicado). **TIPS AL RELOJ** (idea del director): toggle "⌚ Tips en mi
reloj" → las correcciones salen como avisos push cortos vía
`pichangol_avisos` y Android los ESPEJA al smartwatch emparejado (sin app de
reloj); sin reloj quedan en el informe. Candados: `ENTRENADOR_REQUIERE_PRO`
(fail-open, como CM), `ENTRENADOR_LIMITE_MES` (20), `ENTRENADOR_MAX_MB` (40),
solo videos del propio Supabase. El video NO se conserva en el backend.
Fase 2 (backlog): pose estimation on-device (ML Kit — ojo plugin nativo vs
Flutter 3.24.5, probar en CI aislado).

### Páginas legales (Play Store / Ley 29733)

`backend/growth/legal/router.py` sirve, públicas y sin login:
`/legal/privacidad`, `/legal/terminos`, `/legal/eliminar-cuenta` (la que exige
Play para apps con registro) y `/legal/eliminacion-datos` (+ callback POST de
Meta, no tocar). En PRD son `https://www.pichangol.app/legal/...`.
La privacidad se reescribió (ago-2026) para declarar lo que la app realmente
recoge: ubicación, contenido subido, mensajes, documento de identidad, pagos vía
Culqi, notificaciones, videos del entrenador analizados por IA y transferencia
internacional. **Al agregar un dato nuevo hay que actualizarla**: una política
que omite un dato que sí se recoge hace que Play rechace la ficha y no cubre
nada ante la ley. **"Eliminar mi cuenta"** vive en Perfil (último ítem, en rojo)
→ `AppState.eliminarMiCuenta`: reusa `resetVirgen` (todo lo que el usuario creó,
local y nube) y suma su identidad (perfil + avatar + verificación), con doble
confirmación. NO borra comprobantes de pagos (obligación contable) ni los
mensajes que ya entregó a otros — así está declarado en la página pública.

### Pago online: interruptor por ambiente (ago-2026)

`GET /config/canal` (público, el APK ya lo consultaba) devuelve además
`pago_online`. Lo decide `propiedad/panel.py::pago_online_disponible()`: sólo
una llave **`sk_live`** de Culqi lo habilita; `PAGO_ONLINE_ACTIVO=1|0` fuerza
el valor (probar en QAS con llaves de prueba, o corte de emergencia en PRD).

En el APK, `appState.pagoOnlineDisponible` (arranca en **false**, fail-safe) hace
que el checkout de `club_detalle` ofrezca SÓLO "Reservar y pagar en la cancha".
Motivo: sin cobro real, "Pagar ahora" lleva a un pago imposible — y simularlo
sería mentirle al jugador y llenar la billetera del dueño de plata inexistente.
Al cargar la llave live, el botón de pago aparece **sin publicar un APK nuevo**.
Ojo: con seña configurada el flujo exige pago online, así que durante esta fase
las canchas del piloto van con **seña 0**.

### Feature flags por ENTORNO (`lib/config/features.dart`)

El CI inyecta `--dart-define=ENTORNO=dev|qas|prod`, y de ahí salen `kEntorno` y
`kEsProduccion`. Lo que aún se prueba se ata al entorno, NO a un booleano suelto:
así el APK de PROD lo oculta solo, sin depender de que alguien recuerde apagarlo
antes del corte.
- `kEntrenadorVirtualActivo = !kEsProduccion` — **Entrenador virtual sigue en
  QAS y NO sale a producción** (decisión del director, ago-2026). Único acceso:
  Perfil → "Entrenador virtual". El backend `/entrenador/*` queda intacto.
- `kServiciosPichangolActivo = false` — Servicios Pichangol, oculto en el piloto.
- `kHerramientasPruebaActivas = !kEsProduccion` — la **Zona de pruebas** de
  Ajustes ("Dejar en virgen", "Empezar de cero", **"Depurar academias"**,
  simuladores de llamada) NO viaja en el APK de la tienda: "Depurar academias"
  lista todas las academias con el correo de su dueño y borra cualquiera en la
  nube. En producción el usuario tiene Perfil → "Eliminar mi cuenta"; el
  **diagnóstico de push** vive fuera de esa zona (sección "Diagnóstico") porque
  sólo lee y sirve para dar soporte. `OCULTAR_PRUEBAS=1` las apaga también en
  dev/QAS.

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
- ~~`search_path` fijo en las funciones trigger de push~~ HECHO en QAS y PRD
  (sep-2026, `docs/piloto/supabase_push_funciones_search_path.sql`). Si se
  crea una función `notificar_push_*` nueva, agregarla a la lista del script
  y correrlo en ambos ambientes.
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
- **PUNTOS PICHANGOL (fidelidad, HECHO ago-2026) — ARQUITECTURA DERIVADA:**
  los puntos GANADOS se DERIVAN de las reservas del jugador (`AppState.
  misPuntos/_puntosDe`: 1 pto por S/1 de `totalConExtras` de reservas
  `traidaPorApp` PAGADAS, últimos 12 meses — sin contador aparte = sin doble
  acreditación, retroactivo y consistente entre equipos). Online acredita al
  instante; EFECTIVO al `marcarPago` del dueño (el jugador exige que marquen);
  MANUAL no acumula. Lo CANJEADO vive en Supabase `pichangol_puntos_canjes`
  (`PuntosRepo`; disponibles = ganados − canjeados; `cargarPuntosCanjeados` en
  login + reset por cuenta en logout). CANJE EN CHECKOUT (hecho): toggle en el
  resumen de `club_detalle` (`usarPuntos`), 100 pts = S/3, solo pago online en
  S/, 1 canje por reserva; el descuento lo absorbe la comisión PCG (la
  liquidación al dueño va con el precio completo). UI: tarjeta en Mis reservas
  (`_PuntosCard`) + pantalla "Mis puntos" en Perfil (`mis_puntos_screen.dart`).
  SQL: `docs/piloto/supabase_puntos_canjes.sql`. OJO: el backend growth
  `/puntos/*` es el motor de INCENTIVOS growth (traer_cancha, etc.; ahora con
  caducidad FIFO 180d y valor 100 pts = 3 configurable) — el APK NO lo usa
  para la fidelidad de reservas. Push "te llegaron puntos": HECHO (reservas
  efectivo al `marcarPago`; bodega al entregar).
  **PUNTOS POR BODEGA (decisión del director, ago-2026):** SOLO los pedidos
  de bodega **pagados con SALDO Pichangol** suman puntos (incentivar la
  billetera; el efectivo del local NO acumula — cero comisión + fraude
  fácil). Derivado igual que reservas: `BodegaRepo.puntosBodegaCliente`
  (pedidos `pagado=true` + `entregado`, 12 meses) → `AppState._puntosBodega`
  (`cargarPuntosBodega` en login/splash/Mis puntos) se SUMA en `misPuntos`.
  Push ⭐ al entregarse (`avisarPuntosBodega`); nudge "⭐ ganas +N puntos"
  en la confirmación del pedido; historial unificado en `mis_puntos_screen`.

### Horarios de cancha (apertura/cierre) y cruce de medianoche
- `Cancha.horariosSlots()` genera los INICIOS reservables de apertura a cierre en
  pasos de `duracionSlotMin`. **REGLA (decisión del director, sep-2026): la hora
  de CIERRE es la hora en que EMPIEZA el último turno** — cierra 23:00 → último
  turno 23:00–00:00; cierra 00:00 → 00:00–01:00 (madrugada del día siguiente);
  con turnos de 90 min el último es el mayor inicio ≤ cierre (07:00→23:00:
  22:00–23:30). Excepción: 24 h (00:00→00:00) = 24 turnos sin repetir el de
  medianoche. Antes el turno debía caber COMPLETO antes del cierre (último
  22:00–23:00) y los dueños decían "sí atiendo a las 23:00". `web/horarios.py::
  slots` y `abiertaA` del explorador web son ESPEJO de esta regla; el texto de
  ayuda del selector de horario del APK lo explica al dueño.
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
