# Plan de mejora nocturna — CanchaLibre

> Base: rama `claude/apk-google-maps-setup-fvpl9w` (= `prd` + CLAUDE.md), commit `ccff09b`.
> Evaluación previa: 890 tests backend en verde, 1 test Flutter; hallazgos críticos
> de seguridad/dinero documentados en la evaluación del 26-oct-2026.
> **Estado: PROPUESTA. No se ejecuta nada hasta el "go" del usuario.**

## 0. Principios de la noche

1. **Orden pedido:** (A) funcional → (B) UI/UX → (C) corregir lo erróneo.
   Excepción única: **C0 = hotfix de la fuga del 2FA** (30 min, al inicio), porque
   probablemente está vivo en PRD y el resto del trabajo no lo toca.
2. **Lo nuevo nace correcto** (regla del director: "producción, no demo"): todo módulo
   nuevo calcula montos en el servidor, exige identidad del usuario, es idempotente y
   transaccional. Así la fase C no tiene que rehacer lo construido en A.
3. **Nada toca producción ni QAS:** sin push a `prd` ni a `claude/apk-…` (redespliega
   `pg-backend`), sin SQL en Supabase, sin variables en Railway, sin cambiar
   `applicationId`. Los SQL quedan como scripts para que el usuario los corra.
4. **Rama de trabajo:** `feat/noche-canchalibre` (desde `ccff09b`). Commits pequeños,
   uno por tarea, cada uno con sus tests. Push de **esa** rama solo si el usuario lo
   autoriza (CI compila el APK con Flutter 3.24.5 sin publicar Release ni redesplegar).
5. **Puertas de calidad por tarea:** `pytest` completo en verde · `flutter analyze`
   **con Flutter 3.24.5** (igual que CI) sin errores nuevos · `flutter test` en verde ·
   golden tests de las pantallas tocadas (capturas revisadas).
6. **Multi-país siempre** (PE/BO/EC): moneda por país, sin "Yape/Plin" fuera de PE.
7. **Bitácora:** `docs/plan/BITACORA_NOCHE.md` con lo hecho, decisiones, pendientes y
   cómo probar cada cosa. Si una tarea se traba >45 min, se documenta y se pasa a la
   siguiente.

## Preparación (lo hago yo antes de empezar, ~30 min)

- Flutter **3.24.5** local (copia aparte, sin tocar la 3.47.1) para analizar/compilar
  como CI.
- `docker-compose.dev.yml` con **Postgres 16 local** + `backend/growth/.env.local`
  apuntando a él. Requiere **Docker Desktop abierto**.
- Sistema de **migraciones versionadas**: `backend/growth/migraciones/NNNN_*.sql` +
  runner (`python -m db.migrar`) con tabla `schema_migraciones`. Los scripts
  sirven igual para correrlos a mano en Supabase (convención del repo).
- Llaves Culqi de **prueba** leídas desde `backend/growth/.env` (gitignored).

---

## FASE A — Funcional: motor de reservas configurable + cobro directo al club (~5 h)

### A1. Catálogo de deportes ampliable (45 min)
- Ampliar `enum Deporte`: **básquet, vóley, futsal, fútbol 7/11, pádel (re-activable),
  tenis, pickleball, frontón, multiuso**, con ícono y color por deporte.
- `deportesActivos` pasa a venir del backend (`/config/canal` → `deportes_activos`
  por país), con fallback local; la torre los activa/desactiva sin publicar un APK.
- Campos de la cancha: **superficie** (grass sintético, natural, losa, arcilla, parquet,
  cemento), **techada**, **iluminación**, **formato** (5v5, 6v6, 7v7, 11v11; singles/dobles),
  **capacidad**. Se usan como filtros en Explorar.

### A2. Reglas de reserva por cancha — `motor_reservas.py` (2 h)
Fuente ÚNICA de verdad (backend, funciones puras con tests exhaustivos), usada por la
app y por la web:
- **Horario por día de la semana** (lun–dom, varios tramos por día, cruce de
  medianoche) + **cierres especiales/feriados** por fecha.
- **Tarifas por franja y día** (varias franjas: valle/normal/punta/fin de semana),
  precio por duración, **recargo nocturno de iluminación** opcional.
- **Duraciones permitidas** (p. ej. 60/90/120) en vez de una sola; **buffer** entre
  turnos (limpieza/rotación).
- **Ventana de reserva:** anticipación mínima (p. ej. 2 h) y máxima (p. ej. 30 días).
- **Política de cancelación POR CLUB** (hoy es global por env): horas límite, % de
  devolución por tramo, reprogramación permitida sí/no y cuántas veces.
- **Seña** (% o monto fijo) y **confirmación**: automática o con aprobación del dueño.
- **Límites:** máximo de reservas activas por jugador y por día.
- **Extras** con precio (pelotas, raquetas, chalecos, árbitro, ducha).
- `cotizar(cancha, fecha, hora, duración, extras)` → precio, seña, comisión, moneda,
  desglose. `disponibilidad(cancha, fecha)` → turnos libres considerando reglas,
  bloqueos, reservas fijas y **solapamiento por RANGO de tiempo** (no solo
  `hora_inicio`).
- Compatibilidad: la cancha sin reglas nuevas se comporta exactamente como hoy
  (apertura/cierre/precio/franja valle actuales se mapean a la regla por defecto).
- Endpoints: `GET/PUT /reservas/reglas/{cancha_id}` (dueño autenticado),
  `GET /reservas/disponibilidad`, `POST /reservas/cotizar`.

### A3. Reserva con estados en el servidor (1 h)
- Estados: `apartada → pendiente_pago | pago_en_revision → confirmada →
  completada | cancelada | expirada | no_show | reembolsada`.
- `POST /reservas/intent`: valida reglas, **aparta con vencimiento** (configurable,
  10 min tarjeta/Yape; 30–60 min voucher), monto calculado por el servidor.
  Transacción en Postgres con **restricción EXCLUDE por rango** (cancha, tstzrange)
  → imposible el doble booking o el solapamiento.
- Cron de vencimiento para TODOS los apartados (hoy los del APK no vencen).
- Historial de transiciones (quién, cuándo, por qué) para auditoría y soporte.

### A4. Culqi PROPIO de cada club (1 h 15)
- `cuentas_pasarela`: el club registra **pk/sk de Culqi**; la `sk` se guarda
  **cifrada (Fernet, `PAGOS_ENC_KEY` obligatorio, fail-closed)**, nunca vuelve al
  cliente (solo `sk_…••••1234`). Validación de las llaves al guardarlas.
- `culqi.py` parametrizado por llave (hoy usa la global).
- Flujo: intent → el APK tokeniza con la **pk del club** → `POST
  /reservas/intent/{id}/pagar` → cargo con la **sk del club**, metadata `reserva_id`,
  idempotente → confirma atómicamente; si el turno se perdió → **reembolso
  automático en el servidor** (no en el teléfono).
- **Webhook por club** (`/pagos/culqi/webhook/{club_ref}`) que vuelve a consultar el
  cargo con la llave del club antes de cambiar nada.
- **3DS** y medios por órdenes (PagoEfectivo/Cuotéalo): se implementan según la
  documentación oficial de Culqi vigente (verificada esa noche); si algo depende de
  habilitación comercial de Culqi, queda detrás de un flag y se documenta.
- Sin llaves del club → ese club ofrece solo pago manual o en cancha (nunca simulado
  en PRD, como hoy).

### A5. Pagos manuales del club con voucher (1 h)
- El club configura **sus** medios: Yape/Plin (número, titular, QR), transferencia
  (banco, cuenta, CCI, titular), otras billeteras; en BO/EC "QR / transferencia".
- Checkout muestra los datos del club, el jugador **sube el voucher** (foto) + n.º de
  operación / código de seguridad de Yape → `pago_en_revision` con temporizador.
- **Bandeja del dueño** "Pagos por confirmar": confirmar / rechazar con motivo; push al
  jugador; vence sola si nadie confirma.
- Anti-fraude: **n.º de operación único por club**, hash de la imagen (voucher
  reciclado), monto y fecha visibles para comparar; en PE se reutiliza la
  conciliación automática `yape_auto` de academias.

### A6. Comisión por reserva con dinero directo al club (45 min)
- Libro `comisiones_reserva`: se devenga al **confirmar** (online, voucher o
  efectivo), con la regla de comisión vigente congelada (5 %, mínimo por moneda).
- Se descuenta del **saldo prepago** del dueño; si no alcanza, queda **deuda** (hoy se
  pierde en silencio). Con deuda > tope configurable en la torre, se suspende el
  cobro online/las reservas nuevas de ese club hasta regularizar.
- Torre: comisiones por club, deuda, estado; reporte para el dueño "Lo que debes / lo
  que pagaste".

---

## FASE B — UI/UX premium, sistema de diseño CanchaLibre (~4 h)

### B1. Design system (1 h 15)
- **Tokens semánticos** en `lib/ui/tokens.dart` (roles, no colores sueltos):
  `primary/onPrimary`, `surface/surfaceAlt`, `outline`, `success/warning/danger/info`,
  acentos por deporte. Paleta con **contraste AA verificado** (el verde actual con
  blanco da 4.1:1; se oscurece a ≥4.5:1).
- **Una sola tipografía** app = web (propuesta: **DM Sans**, la que ya usa la web);
  escala tipográfica de 8 pasos (reemplaza ~20 tamaños sueltos).
- Escalas de **espaciado** (4/8), **radios** (8/12/16/24/full), sombras, duraciones de
  animación.
- `ThemeData` completo desde los tokens (botones, inputs, chips, sheets, snackbars).
- Mismos tokens volcados a la web (`backend/growth/web/ui.py`) para tener UNA marca.

### B2. Componentes (1 h)
`CLButton`, `CLCard`, `CLChip`, `CLBadgeEstado` (estados de reserva), `CLSlotGrid`
(selector de turnos con precio por franja), `CLPrecio` (moneda del país),
`CLSkeleton`, `CLVacio`, `CLError` (con reintentar), `CLSheet`, `CLTimeline` (estado de
la reserva), `CLIconoDeporte`, `CLTemporizador` (apartado). Cada uno con golden test y
`Semantics`.

### B3. Pantallas (1 h 45) — en este orden
1. **Ficha + reserva** (`club_detalle`, 4.541 líneas → se parte en widgets): galería,
   datos clave (superficie, techada, formato), selector de día/duración/turno con
   precio, extras, resumen sticky.
2. **Checkout nuevo:** resumen → medio (tarjeta / Yape / datos del club + voucher) →
   temporizador → estado con timeline. Sin copy de demo.
3. **Explorar:** buscador + chips de deporte + filtros (superficie, techada, precio,
   horario "disponible ahora"), skeletons, estados vacíos.
4. **Mis reservas:** próximas/pasadas, estado claro, cancelar/reprogramar según la
   política del club.
5. **Panel del dueño:** navegación de 7 → 5 pestañas (**Hoy · Agenda · Canchas ·
   Caja · Más**), pantalla **"Reglas de reserva"** (A2), **"Medios de pago"** (A4/A5),
   bandeja de vouchers.
6. Splash/carga: el loader y el splash dejan de mostrar el logo "Pichangol" y usan el
   wordmark CanchaLibre (`kBrandName`). **El ícono del launcher y un logo nuevo
   multideporte quedan como propuesta** para aprobación del director (no se publican).

### B4. Accesibilidad y QA visual (incluido en lo anterior)
Contraste AA, toque ≥48 dp, `Semantics` en lo interactivo, soporte de texto grande;
golden tests de cada pantalla rediseñada (capturas en la bitácora para revisión).

---

## FASE C — Corregir lo que está en estado erróneo (~3 h)

| # | Tarea | Tiempo |
|---|---|---|
| **C0** (al inicio) | `GET /config/incentivos` con **lista blanca**; secretos 2FA fuera de `stores.config`; `META_TOKEN_KEY` obligatorio (sin fallback base64); códigos de recuperación más largos con hash salado. **Tras el despliegue: re-enrolar el 2FA de los admins.** | 30 min |
| C1 | **Identidad en servidor:** el backend verifica el ID token de Google y emite sesión propia (JWT corto + refresh); dependencia `usuario_actual`; obligatoria en lo nuevo y aplicada a los endpoints legados de más riesgo (pagos, reservas, boleadores, `es_mio` de propiedad). | 1 h |
| C2 | **Pagos legados:** `/liquidacion-online` y `/comision-reserva` solo con montos derivados de un cargo/intent real; `/cobrar` exige intent; reembolsos pendientes al backend; carreras de `/web/pagar` (vigencia del apartado + filas afectadas). | 45 min |
| C3 | **Supabase:** scripts de migración (NO aplicados) que impiden a `anon` cambiar `verificada`, `dueno`, `pagado`, `estado`, y cierran `pichangol_avisos`; secreto obligatorio en `push-aprobacion`. Con **plan de despliegue** compatible con APKs viejos en la calle. | 30 min |
| C4 | **Operación:** job de `pytest` + `flutter test` en CI; `reset-total` deshabilitado en PRD; rate limit con IP de confianza; `/health` que revisa la BD; dependencias fijadas. | 30 min |
| C5 | Higiene: 7 pantallas muertas, imports sin uso, `invalid_null_aware_operator`, copy de demo visible. | 15 min |

**Fuera de esta noche (documentado con su costo):** migrar el snapshot JSON completo a
tablas (proyecto de varios días), RLS por usuario con Supabase Auth en todas las
tablas, partir `app_state.dart` (10k líneas), router con rutas nombradas, unificar el
rediseño a TODAS las pantallas (torneos, academias, chat, bodega).

---

## Entregable de la mañana

1. Rama `feat/noche-canchalibre` con commits por tarea y `BITACORA_NOCHE.md`.
2. Tests: suite backend completa + nuevos tests (motor de reservas, Culqi por club,
   vouchers, comisiones, 2FA); goldens Flutter.
3. Lista de **acciones del usuario/director**: SQL a correr (con link de GitHub),
   variables nuevas (`PAGOS_ENC_KEY`, …), re-enrolar 2FA, aprobar paleta/logo, pase a
   QAS/PRD.
4. Guía de prueba manual por rol (jugador, dueño, operador).

## Riesgos

- **Tiempo:** ~12 h de trabajo estimado; si no alcanza, se corta por el final de cada
  fase (lo menos crítico va al final de cada lista).
- **Culqi:** 3DS/órdenes pueden requerir habilitación de la cuenta del comercio.
- **APKs en la calle:** los cambios de C3 rompen APKs viejos si se aplican antes de
  distribuir el nuevo; por eso quedan como scripts con plan de despliegue.
- **Doble sistema** (snapshot + tablas nuevas) durante la transición: documentado.
