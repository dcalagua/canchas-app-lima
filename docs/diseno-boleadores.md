# Diseño · Boleadores (sparring por turno como servicio extra)

**Estado:** aprobado por el director el 28-sep-2026 (decisiones en § 7). Fase 1
en construcción. Pensado para tenis (y pádel), pero el modelo es genérico:
"prestadores por turno" con `deporte`, así después entran árbitros de fútbol o
sparring de pádel sin otro módulo.

## 1. Qué es

Un jugador que quiere **bolear** (pelotear con alguien de nivel) contrata a un
**boleador** al reservar la cancha, como un servicio extra más. El boleador se
registra solo desde su Perfil (app) o desde Modo anfitrión (web), pone su
**categoría de la Liga Pichangol**, su **tarifa por turno** y **en qué locales
atiende**. Cuando lo contratan recibe un push y **acepta o rechaza** (puede
estar ocupado). Cobra por Pichangol: su neto entra a "por recibir" en su
billetera y se le liquida con la misma cola que a los dueños de cancha.

Nombre por país: **Boleador** en Perú; **Sparring** en Ecuador y Bolivia
(`PaisConfig.nombreBoleador` / `paises.nombre_boleador`).

## 2. La plata (decidido)

| Regla | Valor |
|---|---|
| Precio que ve el cliente | El que puso el boleador, por turno (× turnos reservados) |
| Comisión de Pichangol al boleador | **Fija por turno: S/ 2 · \$ 0.50 · Bs 3** (`config` `boleador_comision_<PEN\|USD\|BOB>`; default = `comision_min` de la moneda) |
| Cargo por servicio al cliente | **Sí, sobre todo lo pagado en línea incluido el boleador** (misma regla que hoy) |
| Pasarela | La absorbe Pichangol, como en el resto |
| Forma de pago | **Solo en línea** (total o seña). Si la cancha se paga en efectivo, el boleador no se ofrece. En reserva con seña, la parte del boleador se cobra completa. |

Ejemplo: cancha S/ 60 + boleador S/ 20 → cargo 5 % S/ 4 → el cliente paga
S/ 84; el dueño recibe S/ 57 (60 − 5 % mín 2); el boleador recibe **S/ 18**
(20 − 2); Pichangol S/ 9 antes de Culqi. El boleador ve en su billetera
"Boleo · sáb 10:00 · Club X · S/ 18 (S/ 20 − S/ 2 comisión Pichangol)".

## 3. Flujo

1. **Registro del boleador** (`POST /boleadores/perfil`, app y web): exige
   identidad verificada (`pichangol_verificaciones`, la misma del marketplace).
   Todo por selección: deporte (tenis · pádel), **categoría** (5P · 5A · 5B ·
   4ta · 3ra · 2da · 1ra, las de la liga), tarifa por turno (chips en la moneda
   de su país + "otro monto"), locales donde atiende (elige locales VERIFICADOS
   de Pichangol; guarda los ids de sus canchas), disponibilidad (días de la
   semana + franja desde/hasta), celular, etiquetas (chips: "Peloteo",
   "Partido de práctica", "Clases a niños", "Zurdo", "Saque fuerte"). Activo al
   instante; la torre puede suspenderlo.
2. **Selección al reservar** (`GET /boleadores/disponibles?cancha_id&fecha&hora
   &turnos`): en la ficha (app y web), debajo de los servicios extra y SOLO si
   el pago es en línea, la sección "🎾 ¿Quieres un boleador?" lista los que
   atienden en ese local, están disponibles en esa franja y no tienen otra
   solicitud aceptada o pendiente que se cruce. Tarjeta: foto real, nombre,
   categoría, ★ (reseñas), "S/ 20 por turno". Al elegirlo entra como línea
   `{clave: 'boleador', boleador: email, nombre, precio total, unitario,
   cantidad = turnos, tipo: 'turno', pendiente: true}` en `servicios_extra` de
   la reserva (mismo formato que los demás extras → comprobantes y agenda del
   dueño ya lo pintan).
3. **Pago:** el total en línea incluye al boleador. Al confirmar el cargo:
   - la liquidación del DUEÑO se calcula SIN la parte del boleador;
   - se crea la **solicitud** (`pichangol_boleador_solicitudes`, estado
     `pendiente`, `vence_en` = mín(ahora + `BOLEADOR_ACEPTAR_HORAS` (2),
     inicio del turno − 1 h)), con `charge_id`, monto, moneda y turnos;
   - push al boleador "Te contrataron 🎾 · sáb 10:00 · Club X · Ana" (tipo
     `boleador`, abre Solicitudes) y push al cliente "Esperando que Juan
     confirme".
4. **Aceptar / rechazar** (`POST /boleadores/solicitudes/{id}/aceptar|rechazar`,
   app y web; solo el boleador de la solicitud):
   - **Acepta** → estado `aceptada`; se crea el `PagoRegistro`
     `liquidacion_boleador` (neto = monto − comisión × turnos, `liquidado=False`,
     `disponible_desde` = fin del último turno: la torre lo ve pero el lote solo
     lo incluye cuando el turno ya pasó); comisión como `PagoRegistro`
     `<id>_com`; push al cliente "Juan confirmó ✅" y chat abierto entre ambos.
   - **Rechaza** o **vence** (cron cada 5 min) → estado `rechazada`/`vencida`;
     **devolución automática al medio original** de la parte del boleador + su
     cargo proporcional (`culqi.reembolsar` parcial; en app con `_cargo_app`);
     si no se puede, `manual` para la torre; push al cliente "Juan no puede ese
     día; te devolvimos S/ 21.00" y la reserva sigue sin boleador (la línea
     queda `estado: 'rechazada'`). Al cliente se le ofrece elegir otro desde
     la ficha de su reserva (fase 2).
5. **Después del turno:** el cliente califica al boleador (reseñas existentes,
   `pichangol_resenas` con `objetivo = boleador:<email>`, fase 2). La
   liquidación queda liberada y entra al lote BCP / Yape como las demás.

## 4. Cancelaciones y faltas

| Caso | Qué pasa |
|---|---|
| Cliente cancela la reserva (política vigente) | La solicitud pasa a `cancelada`; si había liquidación del boleador sin pagar → `anulado`; si ya se le pagó → `ajuste_cancelacion` con deuda, como el dueño. Push al boleador. |
| Boleador cancela después de aceptar (`POST …/cancelar`) | Devolución 100 % de su parte + cargo proporcional al medio original (regla "cancela el anfitrión"); falta en su perfil (`faltas`). 2 faltas en 90 días → `activo=false` + push "Tu perfil de boleador quedó pausado". |
| Boleador no aparece (el cliente lo reporta desde la reserva, fase 2) | Igual que cancelar + falta. Fase 1: el operador lo resuelve desde Cancelaciones web con "Marcar devuelto". |
| Cliente no aparece | El boleador cobra igual (el turno pasó). |
| Local que no quiere boleadores externos | `pichangol_canchas.permite_boleadores` (default true) editable en Editar local (web) y Editar cancha (app). |

## 5. Datos

SQL `docs/piloto/supabase_boleadores.sql` (el director lo corre a mano en QAS
y, con "pasa a PRD", se aplica en PCG-PRD):

- `pichangol_boleadores` (`email` PK en minúsculas, `deporte`, `categoria`,
  `tarifa numeric`, `moneda`, `activo`, `data jsonb` = nombre, foto, celular,
  canchas [ids], locales [{club, lat, lng}], disponibilidad {dias, desde,
  hasta}, etiquetas, stats {aceptadas, rechazadas, faltas, ultima_falta},
  `creado`, `actualizado`).
- `pichangol_boleador_solicitudes` (`id` `bs_<µs>`, `boleador_email`,
  `cliente_email`, `cliente_nombre`, `reserva_ref` (grupo o id), `cancha_id`,
  `club`, `fecha`, `hora_inicio`, `hora_fin`, `turnos`, `monto_centimos`,
  `comision_centimos`, `moneda`, `estado`, `canal` web|app, `charge_id`,
  `vence_en`, `respondido_en`, `creado`, `data jsonb`).
- `pichangol_canchas.permite_boleadores boolean default true`.
- Todo se lee y escribe **por el backend** (`web/datos.py`, Postgres directo):
  el APK y la web llaman a `/boleadores/*`; una sola validación y una sola
  contabilidad. Snapshot: `stores.config` (comisión por moneda, horas para
  aceptar); las liquidaciones son `PagoRegistro` normales.

## 6. Superficies

- **APK:** Perfil → "🎾 Ser boleador" (registro/edición + solicitudes con
  Aceptar/Rechazar + "Mis boleos"); ficha del club → sección en el resumen
  cuando el pago es en línea; Mis reservas muestra "Boleador: Juan ·
  Esperando confirmación / Confirmado / No disponible"; billetera con el neto
  por recibir. Push tipo `boleador` abre Solicitudes.
- **Web:** ficha `/reservar/{id}` (misma sección, JS `boleadorSel`), resumen y
  comprobante con la línea y su estado; Modo anfitrión → "🎾 Soy boleador"
  (`/anfitrion/boleador`: registro y solicitudes).
- **Torre:** Liquidaciones agrupa "🎾 Boleador · Juan" y muestra "se libera el
  <fecha>"; Cobros → Cancelaciones web recibe las devoluciones `manual`.
  Pane propio de boleadores (suspender, ver faltas) en fase 2.

## 7. Decisiones del director (28-sep-2026)

1. Comisión **fija por turno** S/ 2 · \$ 0.50 · Bs 3 (no porcentaje). ✔
2. Cargo por servicio **también** sobre la parte del boleador. ✔
3. Boleador **solo con pago en línea**. ✔
4. **El boleador debe recibir la notificación y ACEPTAR** (puede estar
   ocupado). No hay confirmación instantánea. Si no responde en el plazo, se
   devuelve al cliente. ✔
5. Identidad verificada **obligatoria** para registrarse. ✔
6. Categorías = **las de la Liga Pichangol**: 5P · 5A · 5B · 4ta · 3ra · 2da ·
   1ra. ✔

## 8. Estado

- Fase 1 HECHA (28-sep-2026, en QAS): backend (`boleadores.py`, tablas
  `pichangol_boleadores` / `pichangol_boleador_solicitudes`, columna
  `pichangol_canchas.permite_boleadores`; SQL
  `docs/piloto/supabase_boleadores.sql`), web (sección "¿Quieres un
  boleador?" en `/reservar/{id}`, resumen, comprobante y
  `/anfitrion/boleador` en Modo anfitrión) y APK (Perfil → "Ser boleador",
  tarjetas en el resumen de reserva de `club_detalle`, solicitud tras el pago
  con outbox, pase de Mis reservas con el estado, push `boleador`, billetera
  con `liquidacion_boleador`, toggle "Boleadores en esta cancha" en Editar
  cancha). Tests `tests/test_boleadores.py`.
- Fase 2: reseñas del boleador, elegir otro boleador tras un rechazo, reporte
  de "no vino", pane en la torre, radio por zona además de locales, staff del
  propio club como boleadores.
