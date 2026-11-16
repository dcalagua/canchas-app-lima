# Política de pagos, comisión y cancelación

> Regla oficial del producto. La comisión de Pichangol (PCG) se cobra vía
> **Arquitectura A**: el pago del jugador pasa por PCG, que retiene su comisión y
> liquida el resto al dueño. Pasarelas: Culqi (Perú), Libélula (Bolivia).

## Formas de pago y cómo PCG cobra su comisión

| Forma de pago | ¿Cuándo se ofrece al jugador? | ¿Cómo cobra PCG su comisión? |
|---|---|---|
| **Yape / Tarjeta** (online, por PCG) | **Siempre** | Se neta del pago (Arquitectura A) |
| **Efectivo / pago en cancha** | **Solo si el dueño tiene saldo** (≥ comisión de esa reserva) | Se descuenta del **saldo** del dueño al reservar |
| Dueño **sin saldo** | Efectivo **oculto** → solo online | Se neta del pago |

**Resultado:** PCG cobra SIEMPRE. El saldo del dueño funciona como **billetera de
comisión prepagada** para las reservas en efectivo (modelo inDrive). Sin saldo,
el jugador solo puede pagar online, así que la comisión se garantiza en el pago.

### Por qué el gate del efectivo
Si "pago en cancha" estuviera siempre disponible, todos lo elegirían, pagarían
en efectivo directo al dueño y **PCG nunca cobraría** (fuga #1 del marketplace).
Gatearlo detrás del saldo amarra el cobro de comisión a ese método.

## Reglas finas (a prueba de "dueños vivos")

1. **La comisión se cobra al RESERVAR, no al asistir.**
   - Online → se neta del pago al confirmar.
   - Efectivo → se descuenta del saldo del dueño al confirmar.
   - ⇒ Marcar **no-show NO evita la comisión** (ya se cobró). Neutraliza al
     dueño que pone no-show a todo para dodgear a PCG.
2. **El efectivo solo aparece si `saldo del dueño ≥ comisión` de esa reserva.**
   Si no alcanza, se oculta y solo queda online.
3. **La métrica sigue el DINERO, no la asistencia.** Un no-show **pagado**
   (online) SÍ es ingreso y PCG mantiene comisión; un no-show **sin pagar**
   (efectivo, no vino) es 0.

## Política de cancelación (reembolso por ventana)

| Cuándo cancela el jugador | Reembolso al jugador | Dueño recibe | Comisión PCG |
|---|---|---|---|
| **≥ 24 h antes** (ventana libre) | 100% | 0 | se devuelve (no hubo servicio) |
| **< 24 h y ≥ 3 h** | 50% (o crédito) | 50% (slot perdido) | **PCG la mantiene** |
| **< 3 h o no-show** | 0% | 100% − comisión | **PCG la mantiene** |

**Regla de comisión:** se gana al reservar. Solo se devuelve si PCG reembolsa
**todo** (ventana libre). En cualquier no-reembolso, PCG conserva su comisión.

## Anti-colusión (jugador + dueño "vivos")

Riesgos:
- **Sacar la transacción de la app** (reservan, "cancelan", pagan en efectivo
  directo → PCG pierde comisión).
- **No-show/cancelación falsa** para recuperar plata y seguir jugando.

Defensas:
1. **Comisión cobrada al pagar/reservar, antes de cualquier cancelación.**
   Mientras la plata pase por PCG (o salga del saldo), la comisión ya está.
2. **Reembolsos SOLO por la app, iniciados por PCG.** El dueño no puede
   devolverle plata al jugador; marcar no-show no le devuelve nada al jugador.
3. **El dueño nunca toca la comisión.** Una cancelación devuelve la plata del
   jugador; la comisión de un slot consumido/tardío se queda.
4. **Detección de abuso:** monitorear tasa de cancelaciones/no-shows por jugador
   y por dueño. Anomalías = bandera roja → auditar / exigir prepago no
   reembolsable.
5. **Reputación:** jugador con muchos no-shows → prepago obligatorio.
6. **La mejor defensa: valor al jugador por reservar en la app** (protección,
   confirmación instantánea, disputas, puntos) para que no quiera irse por fuera.

**Insight estructural:** la comisión la protege **por dónde fluye el dinero**
(por PCG o del saldo), no la asistencia. La colusión solo paga si la transacción
ocurre **fuera** de la app.

## Estado de implementación
- [x] Gate del efectivo por saldo del dueño (mostrar "pago en cancha" solo si el
      dueño está destacado / con saldo) — en el flujo de reserva.
- [ ] Neteo real de comisión online (va con Libélula/Culqi, Arquitectura A).
- [ ] Deducción de comisión del saldo al reservar en efectivo (backend).
- [ ] Ventanas de cancelación + reembolsos (con el pago real).
- [ ] Métrica "sigue el dinero" (no-show pagado = ingreso) al activar pago online.
- [ ] Monitoreo de tasas de no-show/cancelación (anti-abuso).
