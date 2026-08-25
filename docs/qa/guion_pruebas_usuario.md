# QA · Guión de pruebas de usuario en TELÉFONO REAL

Lo que ninguna automatización sin dispositivo puede probar: GPS, push,
cámara, dos celulares a la vez. Se ejecuta en ~40 min con **2 teléfonos**
(uno con cuenta de JUGADOR, otro con cuenta de DUEÑO) y la torre `/admin`
abierta en una laptop. Marca cada ✅/❌ y anota el build (Ajustes → pie).

> Regla de oro del tester: ante cualquier ❌, anota QUÉ esperabas, QUÉ pasó
> y una captura. Un "no me llegó la notificación" sin hora exacta no sirve —
> con hora, el equipo la encuentra en los logs en un minuto.

## Persona 1 · Valeria, jugadora nueva (teléfono A)

1. [ ] Instalar el APK, entrar con Google. El nombre y la foto salen bien
       en Perfil.
2. [ ] Explorar detecta tu ubicación (<10 s) y pinta canchas cercanas.
       Apagar el GPS y reabrir: la lista NO se queda colgada en "Detectando…".
3. [ ] Abrir la ficha de la cancha del dueño de prueba: precio, duración del
       turno y horarios coinciden con lo que el dueño configuró.
4. [ ] Reservar en EFECTIVO una hora de hoy. La confirmación menciona los
       puntos que ganarás al pagar ("⭐ ganas +N puntos…").
5. [ ] **Push al dueño**: en el teléfono B (app ABIERTA) suena y aparece el
       banner "Nueva reserva 📅" en <10 s. Repetir con la app de B CERRADA:
       llega la notificación del sistema con el sonido nuevo.
6. [ ] Tocar la notificación en B → abre directo el panel de Reservas.
7. [ ] Chat: Valeria escribe al local desde la ficha; B responde; los checks
       (entregado/leído) y la foto de perfil se ven bien en ambos lados.
8. [ ] Pedido de bodega (estando EN el local o con el candado GPS en mente):
       pedir 2 productos → en B llega "🧃 Pedido a la…" → B confirma → en A
       el RECORRIDO avanza a "En camino" SOLO (sin refrescar) → B entrega →
       "Entregado" ✅. Cancelar un segundo pedido ANTES de que B confirme:
       a B le llega "Pedido cancelado".
9. [ ] Puntos: tras que B marque pagada la reserva en efectivo, a A le llega
       "¡Te llegaron puntos! ⭐" y Mis puntos muestra la reserva.

## Persona 2 · Don Ramón, dueño nuevo (teléfono B)

1. [ ] Registrar/reclamar su cancha (con la ubicación real). El registro
       avisa que la solicitud llegó.
2. [ ] Operador aprueba en la torre → a B le llega "¡Cancha aprobada! ✅"
       y, si la bienvenida automática está encendida, el push "🎁 Bienvenido"
       + el banner del saldo de regalo en su billetera.
3. [ ] Billetera: se ve el saldo de REGALO separado de la plata real, y el
       aviso de "saldo bajo" NO aparece mientras haya regalo.
4. [ ] Tras la reserva en efectivo de Valeria: en Movimientos, la comisión
       dice "cubierta por tu saldo de regalo 🎁" y el saldo real sigue igual.
5. [ ] Pro de cortesía: Mi bodega abre (sin pedir pago), reserva manual y
       bloqueo de horas disponibles.
6. [ ] Caja de la bodega: venta rápida en efectivo (3 taps), el stock baja,
       el reporte del día la muestra con su medio de pago.
7. [ ] Cuenta abierta: activar el toggle, anotar un consumo a Valeria (con
       el buscador), a ella le llega "Anotado en tu cuenta 📒" y ve "llevas
       S/X" en la pantalla del local; cerrar la cuenta → push "Cuenta
       cerrada ✅" y UNA sola venta en el reporte.

## Persona 3 · Operador (laptop, torre `/admin`)

1. [ ] Login con el token del ambiente correcto (el del otro ambiente debe
       fallar).
2. [ ] Reclamos: el mapa de "desde dónde se envió" pinta la ubicación real.
3. [ ] Liquidaciones: "Marcar pagado" abre el MODAL (chips Yape/Transfer./
       Efectivo), y al confirmar la fila desaparece SIN refrescar la página.
4. [ ] Pichangol Pro: dar una cortesía y verla en la tabla como "🎁
       cortesía"; revocarla; regalar saldo manual y verificar que al dueño
       le llega el push "🎁 Te regalamos saldo".

## Casos malvados (los que rompen apps en producción)

1. [ ] **Doble reserva simultánea**: A y otro teléfono intentan reservar el
       MISMO horario a la vez → uno gana, el otro ve "ese horario acaba de
       tomarse" y, si pagó, el aviso de reembolso.
2. [ ] **Carrera de cancelación**: Valeria cancela su pedido de bodega justo
       cuando B lo confirma → gana UNO solo (o "ya va en camino" en A, o
       "el cliente lo canceló" en B). Nunca los dos.
3. [ ] **Modo avión**: reservar sin señal → "Reserva pendiente ⏳"; al volver
       la señal se confirma sola y recién ahí avisa al dueño.
4. [ ] **Reinstalar el app** (jugador): al volver a entrar con Google, sus
       reservas, puntos y saldo regresan de la nube; las canchas eliminadas
       NO reaparecen.
5. [ ] **Mismo teléfono, dos cuentas**: cerrar sesión del dueño y entrar como
       jugador → NO se ven movimientos ni saldo del dueño.
6. [ ] **Sonido**: todas las notificaciones (chat, reserva, bodega, puntos)
       suenan con el audio nuevo, con app abierta Y cerrada.

## Al terminar

Pasar los ❌ (con hora y captura) al hilo de Claude: cada uno se convierte
en diagnóstico contra los logs (Supabase/Railway) y en fix con test de
regresión en `backend/growth/tests/test_qa_journeys.py`.
