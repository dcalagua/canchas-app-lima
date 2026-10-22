# Estrategia comercial — justificar la comisión al dueño de cancha

> Notas de estrategia (no es código). Guardado para cuando armemos formalmente
> el modelo comercial. La comisión de Pichangol se cobra vía **Arquitectura A**
> (el pago del jugador pasa por Pichangol, que retiene su comisión y liquida el
> resto al dueño). Pasarelas: **Culqi** (Perú) y **Libélula** (Bolivia).

## El problema
El dueño preguntará: *"¿por qué tengo que pagar una comisión?"*. La respuesta
NO es "por aparecer en la app". Es una **comisión por éxito** a cambio de
**demanda + una plataforma digital completa** para operar su negocio.

## La reframe central
- ❌ NO decir: *"te cobramos por estar en la app / por estar destacado."*
- ✅ SÍ decir: *"No pagas por aparecer. Pagas solo cuando **nosotros te traemos
  un cliente y ganas**. Si nadie te reserva, no pagas nada. Y gratis te damos
  todo el sistema para manejar tu negocio."*

Convierte el **costo** en **comisión por éxito** (modelo Uber/Rappi/Airbnb): el
dueño solo paga sobre plata que antes no tenía.

## Stack de valor (lo que recibe por la comisión)
No es "estar destacado". Es un **sistema operativo para su cancha**:

| Le damos | Dolor que le quitamos |
|---|---|
| Clientes nuevos (lo encuentran en el mapa) | Antes solo lo conocían sus habituales |
| Reservas online 24/7 | Ya no contesta el teléfono/WhatsApp a cada rato |
| Cobro digital garantizado | Menos efectivo, menos "te quedé debiendo" |
| Menos plantones (se paga al reservar) | Antes le dejaban la hora botada |
| Panel + reportes de su negocio | No sabía cuánto facturaba |
| Academia: alumnos, cuotas, cobros, morosos | Lo llevaba en un cuaderno |
| Chat + notificaciones con clientes | — |
| Estar destacado (más visibilidad) | — |

**Pitch de una línea:** *"Pichangol es tu socio digital: te traemos clientes y
te damos el sistema para manejar todo. Cobramos comisión solo cuando tú cobras."*

## Recomendaciones comerciales
1. **Comisión por éxito, no suscripción.** Nada de cuota fija mensual (frena la
   adopción). Solo % por reserva concretada. Cero riesgo para el dueño.
2. **El saldo como beneficio, no castigo.** *"Con saldo recibes el 100% de cada
   reserva; sin saldo, te descontamos nuestra comisión de tu liquidación."* Es
   fidelidad + te asegura visibilidad (destacado). Nunca "obligatorio".
3. **Comisión baja/transparente al inicio.** Piloto: arrancar con **0% o muy
   baja los primeros 1–2 meses** ("lanzamiento") y luego una comisión modesta
   (ej. 8–10% que ya incluye el ~2.5–3.5% de la pasarela). Al dueño SÍ se le
   muestra el desglose (cobrado − comisión − pasarela = recibe); al jugador NO.
4. **Hazle visible lo que le generas.** Panel *"Cuánto te generó Pichangol"*
   (reservas y ventas del mes que le llegaron por la app). Cuando ve el número,
   la comisión se siente **ganada**, no cobrada → retención. (Implementado en
   `mis_canchas_screen`.)

## Regla de percepción del JUGADOR (ya implementada)
El jugador **siempre paga el precio de siempre de la cancha** (ej. S/120), tenga
o no saldo el dueño. Nunca se le suma la comisión de Pichangol ni la del banco.
La comisión es 100% del lado del dueño.

## Pendiente de esta estrategia
- **B) Mensaje de bienvenida al dueño** (onboarding con el "stack de valor").
- Definir % de comisión final y política de lanzamiento.
- Desglose honesto en los cobros del dueño (cobrado − comisión − pasarela).
