# Diseño · Cargo por servicio y modelo de comisiones (reservas y academias)

**Estado:** diseño para aprobación del director (27-sep-2026). Nada de esto está
implementado todavía. Decisiones de negocio ya tomadas en la sesión del
27-sep-2026 con los Excel `comisiones_culqi_pichangol.xlsx`,
`escenarios_modelo_negocio_pichangol.xlsx` y `modelo_academias_cargo_tramos.xlsx`.

## 1. Por qué

Con la tarifa real de Culqi para tarjeta (6.05 % + S/ 0.30 + IGV ≈ 7.2 %
efectivo) el 5 % que Pichangol retiene no cubre la pasarela: en una reserva de
S/ 15 quedan S/ 0.58 gracias al mínimo de S/ 2, y en una matrícula de S/ 300
Pichangol pierde S/ 6.77. El dueño de la cancha o la academia no ven ese costo:
lo absorbe EBIM.

## 2. Modelo aprobado

Dos lados, como Airbnb (anfitrión 3 % · huésped ~14 %):

| Lado | Reservas de cancha | Academias |
|---|---|---|
| **Comisión a quien recibe** (ya existe) | 5 % del monto, mínimo S/ 2 · \$ 0.50 · Bs 3 | 5 % del monto, mínimo S/ 2 · \$ 0.50 · Bs 3 (hoy es 5 % SIN mínimo: se agrega el mínimo) |
| **Cargo por servicio al cliente** (nuevo) | 5 % sobre los primeros S/ 500 del pago + 2 % sobre el excedente, mínimo S/ 2 | Igual |
| **Pasarela (Culqi/PayPhone/Libélula)** | La absorbe Pichangol | La absorbe Pichangol |
| Recibe el dueño / la academia | monto − comisión (igual que hoy) | monto − comisión (igual que hoy) |

**Una sola regla para las dos líneas.** En reservas casi nunca se pasa de
S/ 500, así que el tramo del 2 % no cambia nada en la práctica y evita tener
dos motores. La regla es continua (sin saltos en los bordes) y equivale a un
tope de S/ 25 que crece 2 céntimos por cada sol adicional. Se descartaron el
5 % plano (encarece los pagos familiares), el tope fijo de S/ 25 (con 4
personas y tarjeta Pichangol pierde) y la regla "familiar" (obliga a definir
familia en cada pago).

**Por país** (mismo criterio que `config.comision_min` y `PaisConfig`):

| Moneda | % base | Mínimo | Tramo al % base | % excedente |
|---|---|---|---|---|
| PEN | 5 % | S/ 2 | S/ 500 | 2 % |
| USD | 5 % | \$ 0.50 | \$ 140 | 2 % |
| BOB | 5 % | Bs 3 | Bs 1000 | 2 % |

**Números de referencia (tarjeta, tarifa observada):** reserva S/ 15 → cargo 2,
margen PCG 2.43 (antes 0.58). Matrícula S/ 300 → cargo 15, margen 7.16 (antes
−6.77). Familia 300+300+300+250 en un pago → cargo 38, margen 10.33; por
separado el cargo sería 57.50 (ahorro de 19.50 por pagar junto). Con Yape el
margen es entre 2 y 4 veces mayor en todos los casos.

**Red de seguridad (no visible, en el backend):** antes de cobrar, si
`comisión + cargo < costo_estimado_pasarela(medio, moneda) + margen_mínimo`
(S/ 2), el cargo sube al múltiplo de S/ 0.50 necesario y se registra en el
log `[cargo]`. Usa `pagos/tarifas_pasarela.costo_centimos` (la tarifa
configurada u observada). Así una subida de Culqi o un medio caro nunca deja
una operación en pérdida sin que nadie lo vea. Con PayPhone/Libélula en 0
("sin configurar") la red no actúa.

## 3. Reglas de cálculo (fuente de verdad: el backend)

- **Base del cargo** = lo que el cliente efectivamente paga por el servicio
  ANTES del cargo: precio de los turnos + servicios extra (reservas) o total
  de la(s) matrícula(s) con descuentos familiar/prepago ya aplicados
  (academias). El canje de puntos (100 pts = S/ 3) se descuenta de la base
  antes de calcular el cargo.
- **Redondeo:** el cargo se redondea a S/ 0.10 hacia arriba (Culqi cobra
  céntimos enteros; 0.10 evita totales feos). El mínimo y el tope de la red
  de seguridad ya son múltiplos de 0.50.
- **Un pago = un cargo.** El carrito familiar y el multi-turno se cobran en UN
  cargo de Culqi → un solo cargo por servicio sobre el total. Es lo que hace
  que pagar junto sea más barato: el checkout muestra "Ahorras S/ X pagando
  en familia" (X = suma de cargos por separado − cargo del total).
- **Mes a mes (débito automático):** hoy cada alumno tiene su suscripción y
  Culqi hace un débito por alumno. Para que la regla del tramo (y el fijo de
  Culqi) se apliquen una sola vez, los débitos de la MISMA cuenta pagadora
  (mismo `email` + misma tarjeta `crd_`) que vencen el mismo día se agrupan
  en UN cobro ("cobro familiar mensual"): un `crear_cargo`, un cargo por
  servicio, y luego se reparte por alumno en `pichangol_matriculas` y en la
  contabilidad. Sin agrupación, la familia pagaría 15 + 15 + 15 + 12.50 al
  mes en vez de 38.
- **Comisión + cargo = ingreso de Pichangol.** La pasarela se resta de ese
  ingreso, no del dueño. `margen = comisión + cargo − pasarela_real`.
- **Puntos Pichangol:** se ganan sobre la base (precio), no sobre el cargo.
- **Reembolsos:** si el reembolso es del 100 % (la cancha cancela, o el
  jugador cancela con ≥ `WEB_CANCELACION_HORAS`), se devuelve TODO incluido el
  cargo (política Airbnb). En reembolsos parciales o `sin_reembolso` el cargo
  no se devuelve. La reversa contable anula también el registro del cargo.
- **APKs viejos:** el APK decide el monto que tokeniza y cobra; un APK sin
  esta versión cobrará solo el precio. El backend acepta `cargo_servicio`
  ausente (= 0) en `LiquidacionOnlineReq`/`MatriculaReq`, registra la
  operación sin cargo y la marca `sin_cargo` para medir cuánto se pierde;
  la torre muestra el conteo. Tras un periodo de gracia se puede exigir
  versión mínima en `/config/canal` ("Actualiza la app para reservar").

## 4. Desglose del cargo (transparencia INDECOPI / Culqi)

Una sola línea visible **"Cargo por servicio Pichangol"** con un ícono ⓘ que
abre el desglose. El desglose describe SOLO lo que Pichangol entrega; nunca
"mantenimiento de cancha" ni nada que sea del dueño (eso ya existe como
**servicios extra** del catálogo, los cobra el dueño). Los porcentajes son
referenciales del 5 %; el cliente paga el total.

**Cliente · reservas**

| Componente | Peso | Qué cubre |
|---|---|---|
| Pago protegido | 2 % | Cobro seguro con Yape o tarjeta, antifraude, comprobante, reembolso si la cancha cancela |
| Reserva garantizada | 1.5 % | Turno bloqueado al instante, sin doble reserva, aviso al dueño, cancelación según política, soporte |
| Promociones y beneficios | 1.5 % | Puntos Pichangol, bonos de recarga, cupones, recordatorios, historial. **Texto por deporte:** fútbol/futsal/básquet/vóley → "Tu equipo y tu partido" (vaquita, invitación por enlace, campeonatos, petos/árbitro reservables); tenis/pádel/pickleball → "Comunidad y ranking" (jugadores disponibles, retos, ranking, campeonatos); loza multiuso → texto genérico |

**Cliente · academias**

| Componente | Peso | Qué cubre |
|---|---|---|
| Pago protegido | 2 % | Cobro seguro, comprobante, reembolso según política de la academia |
| Gestión de tu matrícula | 2 % | Cuotas, débito automático sin volver a poner tarjeta, recordatorios antes del vencimiento, carrito y descuento familiar aplicado solo |
| Portal del alumno y promociones | 1 % | Clases y pagos en la app para el alumno o el apoderado, chat con la academia, un solo pago para toda la familia, puntos. **Por deporte:** tenis/pádel → "+ competencia" (ranking, retos, campeonatos); natación → "+ marcas" (pruebas, tiempos, ranking por prueba); fútbol → "+ equipos" (plantel, fixture, campeonatos) |

**Dueño y academia (explica la comisión del 5 %, hoy no se explica en ningún
lado):** se muestra en Mis canchas / Mi academia, en Ingresos de la web y en
cada liquidación, con datos reales de vistas de su ficha y reservas llegadas
por la app (`stores.vistas` ya existe).

| Componente | Reservas | Academias |
|---|---|---|
| Visibilidad y marketing (2 %) | Explorador app + web, ficha pública con fotos y reseñas, Google, redes de Pichangol, campañas por deporte y zona | Pestaña Academias, ficha web con tarifario y matrícula en línea, landing pública, redes de Pichangol |
| Operación (1.5 % / 2 %) | Agenda, reserva manual y bloqueos, sin doble reserva, recordatorios de cobro, WhatsApp del jugador | Matrículas, cuotas, débito automático, recordatorios, familia y descuentos, morosos |
| Cobros y liquidación (1.5 % / 1 %) | Cobro en línea, billetera, liquidación a su cuenta, reportes | Cobro en línea, comprobante al alumno, liquidación a su cuenta |

**Regla:** la publicidad pagada de un local específico (destacado en redes o
en el explorador) queda FUERA de esta comisión base: es producto Pro aparte
(decisión previa del director: la publicidad en redes es de la marca; solo
locales Pro entran).

**Multi-país:** "Yape" solo en PE (fuera: "tarjeta" / "QR"); no se nombra nada
que no exista en ese país/entorno (el entrenador virtual no entra hasta salir
de QAS). Los textos viven en la torre y se CONGELAN en cada pago (como los
servicios extra) para que el comprobante de hace seis meses muestre lo que se
prometió entonces.

## 5. Arquitectura

### 5.1 Backend (`backend/growth`)

**Nuevo módulo `pagos/cargo_servicio.py`** (fuente de verdad del cálculo):

- `PARAMS_DEFAULT` por moneda (tabla del § 2) + `margen_min`; se guardan en
  `stores.config` con claves `cargo_<PEN|USD|BOB>_pct|min|tramo|pct_exc`,
  `cargo_margen_min_<moneda>`, `cargo_activo_reservas|academias|marketplace|
  torneos` (0/1, arranca en 0 = apagado en los dos ambientes), y el catálogo
  de textos `stores.cargo_servicio_textos` (por línea y deporte, versión).
- `calcular(base_centimos, moneda, linea, medio, *, deporte="") → Cotizacion`
  con `cargo_centimos`, `total_centimos`, `desglose` (lista congelable
  `{clave, nombre, pct, detalle}`), `regla` (texto legible "5 % hasta S/ 500 +
  2 %"), `ajuste_seguridad_centimos` (0 si la red no actuó) y `activo`.
- `red_de_seguridad(base, cargo, comision, medio, moneda)` usa
  `tarifas_pasarela.costo_centimos(total, moneda, medio, tipo)`.
- `ahorro_por_pagar_junto(bases: list[int], moneda)` para el mensaje del
  carrito.

**Endpoints:**

- `GET /config/cargo-servicio` (público, cache-first en el APK como
  `/config/servicios-extra`): params por moneda, activo por línea, textos.
- `POST /pagos/cotizar` (público con `X-App-Key`): `{linea, moneda, medio,
  base_centimos, deporte, partes:[…]}` → `Cotizacion`. El APK y la web la
  piden al armar el checkout y el backend RECALCULA al cobrar (nunca confía
  en el total que manda el cliente para la contabilidad).
- `LiquidacionOnlineReq` y `MatriculaReq` (+ `VentaProductoReq` cuando se
  active marketplace): nuevos campos `cargo_servicio_centimos: int = 0`,
  `cargo_desglose: list = []`. `post_liquidacion_online` / `post_matricula`
  registran, además del `liquidacion_online|matricula_online` de siempre, un
  `PagoRegistro` tipo **`cargo_servicio`** (estado `aprobado`, `email` del
  pagador, `dueno_id` del receptor solo como referencia, `cargo_id` =
  charge, `moneda`, `promo_centimos` no aplica) ligado por `reserva_id` /
  `matricula_id`. La billetera del jugador lo muestra como parte del pago
  ("Reserva S/ 15 + cargo por servicio S/ 2").
- Web: `/web/asegurar` devuelve `cargo_centimos`, `total_centimos` (=
  base + cargo) y `desglose`; `/web/pagar` cobra el total y manda
  `cargo_servicio_centimos` a `LiquidacionOnlineReq`. `/web/matricular(
  -varios)`: `_preparar_personas` calcula la base con descuentos, `cotizar`
  sobre el total, `_cobrar_y_matricular` cobra `total` y llama
  `post_matricula` con el cargo; `pagoWeb` guarda `cargo` y `desglose`.
- Cancelación (`/web/cancelar`, `estado_cancelacion`): reembolso 100 %
  incluye el cargo; reversa marca el `cargo_servicio` como `anulado`.
- **Mes a mes agrupado** (`procesar_renovaciones_alumnos`): agrupar las
  suscripciones vencidas por `(email, card_id, día)`; un `crear_cargo` por
  grupo por `suma(monto) + cargo(suma)`; repartir la parte proporcional del
  cargo a cada alumno en el concepto de su cuota; un solo `PagoRegistro`
  `cargo_servicio` con `matricula_id = "fam:<ids>"`. Si un débito del grupo
  falla, el grupo entero queda `pendiente_pago` (Culqi no cobra parcial).
- `_liquidacion_dict` / `/pagos/liquidaciones/pendientes`: sumar
  `cargo_servicio_soles` y recalcular `margen = comisión + cargo −
  pasarela`; totales `total_cargo_soles`. Torre: chip "Cargo por servicio
  S/ x" junto a "Pasarela" y "Margen".
- `tarifas_pasarela.costo_para(p)`: el cargo del tipo `cargo_servicio` NO
  paga pasarela aparte (ya la paga el cargo del pago principal, que se
  liga por `cargo_id`).
- Logs: `[cargo] <linea> base=… cargo=… ajuste=… medio=… moneda=…`.

**Torre `/admin` → Cobros → "🧾 Cargo por servicio"** (`GET/POST
/pagos/cargo-servicio/config`, admin): interruptor por línea; parámetros por
moneda (%, mínimo, tramo, % excedente, margen mínimo); editor de textos del
desglose por línea y deporte (cliente) y de la comisión (dueño/academia);
simulador (base → cargo → total → pasarela → margen, con Yape y tarjeta); KPI
"operaciones sin cargo (APK viejo)" de los últimos 30 días. Reusa
`simularTarifa` del pane de Tarifas de pasarela.

### 5.2 Web (`backend/growth/web`)

- Ficha de reserva `/reservar/{id}`: en "Resumen de tu reserva" nueva línea
  "Cargo por servicio Pichangol ⓘ" (modal `pcgAvisar` con el desglose y la
  regla), total = base + cargo; el botón dice "Pagar S/ total". JS pide
  `/pagos/cotizar` al cambiar turnos/extras (debounce) y NO calcula solo.
- Ficha de academia `/academia/{id}`: igual en el panel de matrícula y en el
  carrito; con 2+ personas, línea verde "Ahorras S/ X pagando en familia".
- Comprobantes `/reserva/{ref}` y `/academia/{id}/matricula[s]`: desglose
  congelado del pago.
- Mis reservas, Ingresos del anfitrión: el dueño ve la comisión desglosada
  (tarjeta "Tu 5 % incluye…") y NO ve el cargo del jugador (no es suyo).
- Legal: `/legal/terminos` (3-bis "Compras en la web": línea del cargo, regla
  y que se muestra antes de pagar), `/legal/devoluciones` (el cargo se
  devuelve en reembolsos del 100 %). Culqi e INDECOPI revisan estas páginas.

### 5.3 APK (`lib/`)

- `lib/models/cargo_servicio.dart`: `CargoServicioConfig` (params por
  moneda + activo por línea + textos) con `catalogoRemoto` cache-first en
  `SharedPreferences` (`cargo_servicio_config`), cargado en
  `AppState.cargarCatalogoServicios`; `Cotizacion` desde `/pagos/cotizar`.
- `club_detalle_screen` (checkout de reserva): fila "Cargo por servicio
  Pichangol ⓘ" en el resumen (`_ResumenReserva`), total con cargo, canje de
  puntos antes del cargo; `PagoTarjeta.cobrar(monto: total)`; `_accionContable`
  lleva `cargo_servicio_centimos` + `cargo_desglose` → `liquidacionOnline`.
  `cancha_detalle_screen` (una hora) igual. Seña: el cargo se calcula sobre la
  seña pagada online (lo que efectivamente paga ahora).
- `academia_detalle_screen` (`_HojaDatosAlumno`, `_CarritoCard`,
  `_pagarMatriculas`): cotización sobre el total del carrito, mensaje
  "Ahorras S/ X pagando en familia", `registrarMatricula(cargoServicio:)`.
  `mis_clases_screen._MiFamilia` (cuotas pendientes de varias personas):
  misma cotización sobre el total.
- Pantalla de detalle del cargo (`widgets/cargo_servicio_sheet.dart`): hoja
  Airbnb con los 3 componentes y sus textos por deporte; se abre desde ⓘ.
- Reservas del dueño / billetera / Mis pagos: el pago del jugador muestra
  "Precio + cargo por servicio"; el dueño ve solo su neto y su comisión
  desglosada (tarjeta en Mis canchas y en la billetera).
- Sin `cargo_activo_<linea>` en el config (o sin red y sin caché): el APK
  cobra sin cargo y el backend lo registra como `sin_cargo` (fail-safe, igual
  que `pagoOnlineDisponible`).

### 5.4 Datos

- Sin SQL nuevo: la configuración y los textos viven en el snapshot
  (`stores.config`, `stores.cargo_servicio_textos`); los registros
  `cargo_servicio` van en `stores.pagos` como los demás.
- `pichangol_reservas`: el precio guardado sigue siendo el de la cancha (no
  incluye el cargo); el `pagoWeb`/`extras` de matrícula guarda el cargo. Para
  auditoría por fila opcional: columna `cargo_servicio numeric` en
  `pichangol_reservas` y `pichangol_matriculas` (SQL en `docs/piloto/`), no
  bloqueante.

## 6. Fases y orden

| Fase | Alcance | Riesgo | Tamaño |
|---|---|---|---|
| 1 | Backend: `cargo_servicio.py`, config y textos en la torre, `/config/cargo-servicio`, `/pagos/cotizar`, campos en `LiquidacionOnlineReq`/`MatriculaReq`, registro `cargo_servicio`, liquidaciones con margen real, red de seguridad, tests | Bajo (todo apagado por flag) | 1 sesión |
| 2 | Web: reserva, academia + carrito, comprobantes, legal, Ingresos del anfitrión con la comisión desglosada; Playwright a 390 px | Medio (cambia precios visibles) | 1 sesión |
| 3 | APK: checkout de reserva (multi y una hora), academia + carrito + Mi familia, hoja ⓘ, billetera; CI verde | Medio | 1 a 2 sesiones |
| 4 | Mes a mes agrupado por familia + reembolsos con cargo + KPI de APKs sin cargo | Medio | 1 sesión |
| 5 | Encendido: primero QAS con flags en 1 para probar de punta a punta; pase a PRD solo con "pasa a PRD"; en PRD se enciende por línea desde la torre, reservas primero | — | — |

Marketplace y torneos quedan con la comisión actual; el módulo ya los
contempla (`cargo_activo_marketplace|torneos`) para encenderlos después.

## 7. Decisiones pendientes del director antes de la fase 1

1. Confirmar el mínimo de S/ 2 en la comisión de academias (hoy no lo tiene).
2. Confirmar que en reembolsos del 100 % se devuelve también el cargo.
3. Confirmar que Yape sea el medio por defecto en el checkout en Perú (baja
   el costo de pasarela a la mitad; el jugador puede cambiar a tarjeta).
4. Tarifa negociada con Culqi: cualquier baja mejora el margen sin tocar
   nada de lo anterior; los parámetros de la torre ya la recogen.
