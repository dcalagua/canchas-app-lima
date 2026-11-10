# Fase 2 — Pagos (modelo inDrive) — diseño cerrado

Cómo Pichangol cobra por las reservas de cancha. Decidido con el usuario.
Pendiente de codear; se retoma tras cerrar el piloto Perú.

## Modelo elegido: inDrive (efectivo + comisión de saldo prepago)

- El jugador le paga **directo a la cancha** (efectivo / Yape del dueño).
- Pichangol **no toca la plata del jugador**: solo cobra su **comisión**, que
  descuenta del **saldo prepago** del dueño.
- Con saldo → la cancha aparece **destacada** y recibe reservas. Sin saldo →
  entra el fallback (ver abajo).

**Ventaja:** no retienes plata ajena, sin payouts ni regulación de agregador,
funciona con efectivo (multi-país PE/EC/BO). La única integración de pago real
es la **recarga del dueño** (+ el fallback).

## Comisión

- **5% de la reserva, mínimo S/ 2** (ya implementado: `AppState.comisionDe`).
- Igual en ambos modos (efectivo y pasarela), por consistencia.

## Fallback en saldo CERO (idea del usuario)

Cuando el saldo del dueño llega a **0**, se **apaga el modo efectivo** y solo
queda **pasarela**. Así Pichangol **siempre** cobra su comisión.

**Implementación elegida: 🟢 Simple.** En saldo cero, el **jugador paga solo la
comisión** de Pichangol por pasarela (un "fee de reserva") para confirmar el
cupo; el **precio de la cancha lo sigue pagando en efectivo al dueño**. Así la
pasarela mueve **solo la comisión de Pichangol, a su propia cuenta** — nunca la
plata de la cancha (cero payouts, cero regulación de agregador).

- Matiz: en saldo cero el fee lo paga el **jugador** (no el dueño). Es un
  empujón para que el dueño recargue; es un estado de fallback, no el normal.
- **Meta futura (🔵 split):** el jugador paga el total por pasarela y ésta hace
  split (comisión a Pichangol, resto a la cuenta del dueño, vía Culqi/Izipay
  marketplace). Más consistente pero exige dar de alta a cada dueño en el PSP.
  Se evalúa cuando haya volumen.

## Bono de bienvenida: S/ 500 al reclamar

Incentivo de arranque (CAC). Con 3 candados:
1. **Crédito de COMISIÓN, no efectivo:** no retirable ni transferible; solo se
   consume como comisión → sin valor si no hay reservas reales (anti-fraude:
   nadie farmea canchas falsas porque no puede sacar la plata).
2. **Solo al dueño VERIFICADO** (no al que apenas reclama).
3. **Con vencimiento** (3-6 meses). Empujón de lanzamiento, no deuda eterna.
- Equivale a "tus primeras ~250 reservas sin comisión". Llevar la cuenta del
  total regalado para controlar la exposición.

## Aviso de saldo bajo

Alertar al dueño cuando queden ~**3 reservas de saldo (≈ S/ 6)** para que
recargue antes de caer al fallback. Sin sorpresas.

## Cancelaciones y no-shows (punto débil del modelo efectivo)

El jugador no prepaga nada → no tiene "piel en el juego". Se combate con 3 cosas
juntas (la ventana de horas sola no basta):

1. **Ventana: 6 horas.**
   - Cancela **> 6 h antes** → libre; se libera el cupo (y si hubo comisión, se
     reembolsa al saldo del dueño).
   - Cancela **< 6 h antes** → cuenta **strike**; la comisión NO se reembolsa.
2. **El dueño confirma la verdad:** botón **"Se presentó" / "No-show"** en cada
   reserva (como la asistencia de academias). Mata el "empiezo a jugar y
   cancelo": el dueño marca "se presentó" → la reserva se honra + strike al vivo.
3. **Strikes al jugador (como inDrive):** 1º aviso; 2-3 strikes en 30 días →
   el jugador ya NO reserva en efectivo, debe **prepagar por pasarela** (ahí sí
   pone piel en el juego). Reincidente → bloqueo temporal.

## Qué hay que construir (checklist)

- [ ] **Saldo server-side + libro (ledger)** por dueño (hoy es local en
      `SharedPreferences`; es plata → debe ser autoritativo en el backend).
- [ ] **Comisión por dueño** al confirmar reserva (extender el `_consumirComision`
      actual, que hoy solo aplica al club demo, a todos los dueños, server-side).
- [ ] **Pasarela real para recargas** (Yape checkout / Culqi) + **webhook** que
      acredita el saldo.
- [ ] **Fallback saldo cero:** cobro de la comisión al jugador por pasarela.
- [ ] **Modo visible** a ambos (dueño: "Saldo S/0 · cobras por pasarela";
      jugador: método disponible).
- [ ] **Bono S/500** al verificar dueño (crédito de comisión, con vencimiento).
- [ ] **Cancelaciones/strikes:** ventana 6 h, botón se-presentó/no-show del
      dueño, contador de strikes + regla de prepago para reincidentes.

## Ya existe (base para Fase 2)

- `AppState.saldoClub`, `comisionDe(precio)` (5% mín S/2), `recargar`,
  `_consumirComision`, `destacadoActivo`, `movimientos` (+ `MovimientoSaldo`).
- `services/payments_service.dart` (pasarela SIMULADA con `recargarSaldo`).
- `screens/pago_sheet.dart` (checkout Yape/Tarjeta), `screens/cuenta_screen.dart`.
- Falta migrar el saldo a server-side y enchufar la pasarela real por webhook.
