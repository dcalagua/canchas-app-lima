# Plan nocturno 2 — la WEB de CanchaLibre (28→29-oct-2026)

Rama: `feat/noche-canchalibre` (se sigue sobre la misma; push a `dcalagua` al final).
Solo QAS/dev: nada toca PRD. La web es HTML server-side de FastAPI (`backend/growth/web/`),
no Flutter.

## De dónde sale este plan

Evaluación del 28-oct con tres revisiones de código (lado jugador, modo anfitrión,
diseño/rendimiento/seguridad) + capturas reales de QAS (`pg.ebim.pe`, 9 páginas, 1440 px y
390 px). Resumen del diagnóstico:

- **La noche anterior fue casi toda backend + APK.** La web tiene los endpoints de cobro
  directo y reglas, pero **ninguna pantalla** que los use, y dos caminos de pago web
  quedaron **rotos** para clubes con cobro directo.
- **Seguridad:** XSS persistente posible vía JSON-LD de la ficha; sin cabeceras anti-iframe
  en páginas de pago; clave de sesión con valor por defecto; endpoints que gastan Google
  Places sin límite.
- **Diseño:** el CTA web (`#0B8A3E`) no pasa AA, la variable `--verde` se usa y no existe,
  1.250 `style=` en línea y 539 colores sueltos; la web no comparte tokens con el APK nuevo.
- **Rendimiento:** portada de 366 KB de HTML, ~70 KB de CSS + 18 KB de JS repetidos en cada
  página, sin gzip y con `no-store` en todo.
- **En QAS se ve:** fotos rotas (URLs de Google caducadas sin respaldo), título ilegible en
  `/tenis`, "Pickleball" cortado, direcciones tipo plus-code ("373R+J63, …").

## Orden de ejecución

Igual que la noche anterior: **arreglar lo roto → funcional → UI/UX → robustez**. Cada fase
cierra con tests verdes y un commit. Criterio de "hecho" por fase: pytest completo verde
(Python 3.11 en Docker al final), Playwright 390 px y 1440 px sin desbordes ni diálogos del
navegador, y el escenario de la fase recorrido en local contra Postgres de Docker.

---

### Fase W0 — Lo roto y lo peligroso (primero, ~1,5 h)

| # | Qué | Dónde | Prueba |
|---|---|---|---|
| W0.1 | **Pago con el Culqi del club**: la ficha abre Culqi con la `pk` de la plataforma y `/web/pagar` cobra con la `sk` del club → todo pago sale rechazado. La ficha debe usar `directo.culqi_public_key` que ya devuelve `/web/asegurar`. | `web/router.py:1978, 2282, 2783` | test: club con Culqi propio → el token se crea con su pk y el cargo con su sk (mock) |
| W0.2 | **Club solo con voucher**: hoy el jugador cae en Culqi y luego "sube tu comprobante" sin dónde subirlo, y el horario queda retenido. Mientras W1.1 no exista, no abrir Culqi. | `router.py` JS de la ficha | test + Playwright |
| W0.3 | **BO/EC con cobro directo** pasa por la pasarela de la plataforma (cobra a la cuenta equivocada). Rama directa o rechazo explícito. | `router.py:2466`, `web/pago_hospedado.py:683` | test |
| W0.4 | **Cargo por servicio y puntos** que se ofrecen a un club directo y luego desaparecen o fallan. Pasar `directo` al JS y no mostrarlos. | `router.py:1732, 2611, 2654` | test |
| W0.5 | **XSS en JSON-LD**: `json.dumps` sin escapar `<` dentro de `<script>`. Helper `json_en_script()` y usarlo en todo JSON incrustado. | `router.py:2134`, `ui.py:1281` y demás `json.dumps` en `<script>` | test con `</script><script>` en el nombre del club |
| W0.6 | **Clave de sesión por defecto** `"pichangol-web"` → falsificable. Nuevo `WEB_SESION_SECRETO` preferido; mientras no exista se sigue usando la clave actual (no se cierran sesiones) y, si no hay NINGÚN secreto, las sesiones web se rechazan en vez de firmarse con la constante. | `web/sesion.py:42` | test |
| W0.7 | **Reglas ignoradas en la web del dueño**: calendario, bloqueo, reserva manual y Disponibilidad usan el horario base, no `reglas.cancha_del_dia` → turnos en días cerrados y precio sin franja ni luz. | `anfitrion.py:372-603`, `anfitrion_negocio.py:600, 1539` | test: día cerrado no ofrece turnos; precio de franja |
| W0.8 | **Tope diario cuenta canceladas** (quien cancela no puede volver a reservar). | `router.py:2537` | test |

### Fase W1 — Funcional: lo de la noche anterior, ahora en la web (~4 h)

**Jugador**
- **W1.1 Checkout directo web** (pantalla del voucher): datos del medio del club (Yape/Plin/
  transferencia con botón copiar y QR si hay), monto exacto, subir foto (comprimida en el
  navegador) + N.º de operación → `POST /web/voucher`, cuenta regresiva del plazo, estado
  "En revisión del club". Mismo flujo que `checkout_directo_screen.dart`. Con Culqi del club,
  el selector Yape/Tarjeta normal (W0.1).
- **W1.2 Estado del pago visible**: "Pago en revisión del club · vence en X", "Voucher
  rechazado: motivo", "Venció" en **Mis reservas**, `/mis-pagos` y el **comprobante**
  (hoy la fila `nueva` sin pagar no aparece y el comprobante dice "no encontrada").
- **W1.3 Reglas visibles en la ficha**: día cerrado con motivo ("Cerrado: feriado"), franjas
  con su nombre y precio, recargo de luz, anticipación mín./máx., turnos mín./máx. del club
  (reemplaza el "Hasta 4 turnos" fijo), tope diario, y bloque **"Política del club"**
  (cancelación con las horas del club; se quita el "6 horas" fijo de la ficha y de Mis
  reservas).
- **W1.4 Errores de reglas con mensaje claro** (`min_turnos`, `max_turnos`,
  `tope_reservas_dia`, `pago_no_disponible`…), validados también en el navegador antes de
  ir al servidor.

**Anfitrión** (envoltorios web con sesión `pcg_sesion` sobre las mismas funciones de
`pagos/cobro_directo.py` y `reservas/reglas.py`; la lógica de aprobar/rechazar pasa a
funciones puras compartidas con los endpoints del APK; dueño re-verificado en cada id):
- **W1.5 "Cobros de tu club"** `/anfitrion/cobros-club`: conectar Culqi propio (pk + sk,
  verificación con `verificar_llave`, URL del webhook para copiar, desconectar), medios
  manuales (Yape/Plin/transferencia/billeteras por país, sin texto libre salvo número y
  titular), estado de la comisión.
- **W1.6 "Pagos por confirmar"** `/anfitrion/pagos-por-confirmar`: bandeja con imagen del
  voucher (zoom), monto, jugador, turno, tiempo restante; Aprobar / Rechazar con motivo por
  selección. Insignia con el número pendiente en Hoy y en el menú.
- **W1.7 Editor de "Reglas de reserva"** `/anfitrion/reglas/{cancha_id}`: horario por día,
  días cerrados (fechas), franjas con precio, luz, anticipación, turnos mín./máx., tope por
  jugador, cancelación; "aplicar a otras canchas del local". Vista previa del día con
  `cancha_del_dia`.
- **W1.8 Deuda de comisión en Ingresos + banner en Hoy**: saldo, deuda, tope y
  "Cobros directos suspendidos" con qué hacer; signo "−" en `comision_deuda`; moneda por
  movimiento (no la de la primera cancha).

### Fase W2 — UI/UX de nivel (~3 h)

- **W2.1 Tokens web = tokens del APK** (`ui.py` TOKENS): CTA `#0B7A57` (AA), noche, grises,
  definir `--verde`, escala de espaciado/radios/tipografía como `Esp/Rad/Tipo`. Reemplazar
  los hex sueltos de verdes (`#0B8A3E`, `#0E8F67`, `#0B7A55`, `#067A38`) y los grises más
  repetidos por variables. Componentes CSS reutilizables: `.cl-aviso`, `.cl-vacio`,
  `.cl-error`, `.cl-skeleton`, `.cl-insignia` (espejo de `ds.dart`) usados por las pantallas
  nuevas de W1.
- **W2.2 Fotos que nunca se ven rotas**: `onerror` → placeholder del deporte en tarjetas,
  galería y Mis reservas; las URLs de Google caducadas se marcan para no volver a pedirlas.
- **W2.3 Ficha de reserva**: dirección legible (ocultar plus-codes), turnos como `<button>`
  con `aria-pressed` y teclado, "Ocupado" con texto, resumen fijo móvil con contraste
  (`.mp-mini` hoy casi invisible), política del club en la ficha.
- **W2.4 Portada/explorador**: barra de deportes sin cortes ("Pickleball"), línea de
  ubicación sin el 📍 huérfano, desbordes a 390 px, estado vacío claro cuando solo hay
  descubiertas.
- **W2.5 `/tenis`**: título legible (contraste), coherente con la portada.
- **W2.6 Modo anfitrión**: menú agrupado (Mi club · Cobros · Academia · Comercio · Roles)
  con "Cobros y reglas" arriba, pestañas siempre con la activa marcada, calendario en móvil
  con vista por día y columna de horas fija.
- **W2.7 Accesibilidad mínima**: `:focus-visible` global, diálogo con `aria-labelledby` y
  foco atrapado/devuelto, Escape que resetea `aria-expanded`, `#err` con `role=alert`,
  objetivos táctiles ≥ 44 px, textos ≥ 12 px.

### Fase W3 — Rendimiento, seguridad y limpieza (~2 h)

- **W3.1 GZip** en `main.py` y **CSS/JS compartidos como estáticos versionados**
  (`/static/web.<hash>.css|js`, caché inmutable); `no-store` solo en páginas con sesión o
  pago. Meta: portada < 150 KB de HTML.
- **W3.2 Leaflet diferido** (solo al abrir el mapa, con SRI) y `loading=lazy` en todas las
  imágenes de tarjetas.
- **W3.3 Cabeceras**: `frame-ancestors 'self'` / `X-Frame-Options` en toda la web pública,
  CSP en modo **solo-reporte** con los dominios reales (Culqi, Google, unpkg, Supabase).
- **W3.4 CSRF**: middleware para POST con cookie (`Origin`/`Sec-Fetch-Site` same-origin +
  exigir `application/json`).
- **W3.5 Rate limit por IP real** (último valor de `X-Forwarded-For`) en `/web/lugares`,
  `/web/descubrir`, `/web/voucher`, `/web/asegurar` y el login de revisión.
- **W3.6 Comprobante sin datos personales** para quien no es el dueño de la reserva (el
  `ref` `web_<ms>` es adivinable).
- **W3.7 Marca y país**: "Pichangol" visible en WhatsApp, `.ics` y `.csv` → `MARCA`
  (y arreglar la regex del test que los dejó pasar); "S/" de respaldo → moneda del país;
  zona horaria por país en Mis reservas, `/web/libres`, clases, Pro y partidos; puntos
  solo en soles.
- **W3.8 Tests nuevos**: cabeceras, XSS de JSON-LD, tokens CSS indefinidos, contraste del
  CTA, tamaño de la portada, rate limit, clave de sesión.

## Fuera de esta noche (con su costo)

- Migrar los 1.250 `style=` restantes a clases (W2.1 hace los verdes, grises y las pantallas
  nuevas; el resto es trabajo de varios días sin cambio visible).
- Rediseño completo del explorador y de la ficha (nuevo layout): primero se ordena el
  sistema de diseño.
- CSP en modo bloqueo (después de ver los reportes en QAS).

## Necesito del usuario antes o al cerrar

1. **"Go"** para ejecutar.
2. Al cerrar: reiniciar `pg-backend` en Railway tras el despliegue y confirmar
   `PAGOS_ENC_KEY`. Si W0.6 exige una variable nueva (`WEB_SESION_SECRETO`), crearla en
   Railway QAS **antes** de desplegar; sin ella el backend arrancaría con la clave actual
   (no se cierran sesiones) y lo avisará en logs.
3. Probar en QAS con un club de prueba: conectar Culqi de pruebas → reservar → pagar; y con
   voucher → aprobar desde la web.
