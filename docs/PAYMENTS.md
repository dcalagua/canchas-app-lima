# Pagos y monetización — diseño preparado (tarea para después)

> Estado: **NO implementado**. Este documento deja el modelo y los puntos de
> integración listos para cuando lo abordemos. Hoy las reservas son demo, sin cobro.

## Modelo propuesto (estilo inDrive, en dos lados)

### Lado oferta — el dueño de la cancha recarga saldo (prepago)
Igual que inDrive con el chofer: el **dueño carga un saldo prepago** (ej. S/ 20,
S/ 50) y eso lo **activa/posiciona en las búsquedas** y le habilita recibir
reservas. Ideas de cómo se consume el saldo:

- **Visibilidad**: con saldo, el club aparece y puede destacarse en el mapa
  (pin resaltado / arriba en la lista). Sin saldo, deja de aparecer destacado.
- **Créditos por reserva entrante**: cada reserva nueva que le trae la app
  descuenta un pequeño crédito del saldo (equivalente a la comisión, cobrada por
  adelantado vía recarga en lugar de por transacción).
- **Boost temporal**: paquetes para aparecer primero en su distrito por X días.

Esto encaja con la estrategia (Fase 2): comisión solo sobre **reservas nuevas**,
nunca sobre la clientela de siempre.

### Lado demanda — el jugador paga la reserva
- **Seña/garantía con tarjeta** al reservar (anti no-show). Se descuenta del total.
- Opción de pagar el total por la app o solo la seña y el resto en cancha.
- La app puede tomar una **comisión de servicio** sobre la reserva del jugador.

## Pasarelas candidatas (Perú)
- **Culqi**, **Niubiz (VisaNet)**, **Izipay**, **Mercado Pago** (tarjeta).
- **Yape / Plin** (billeteras, altísima penetración local) para seña/recarga.

> Seguridad: la tarjeta **nunca** se maneja en el cliente. Se tokeniza con el SDK
> de la pasarela y el cobro real lo confirma un **backend** (webhooks). Por eso
> esto requiere primero el backend (ver más abajo).

## Puntos de integración en el código (dónde se va a enchufar)
- `AppState.agregarReservaJugador(...)` → aquí va el **cobro de la seña** antes de
  confirmar la reserva.
- Nuevo módulo **"Saldo del club"** en el Panel del Club (Reportes/Cuenta) →
  recarga, historial de créditos, estado de visibilidad.
- Interfaz sugerida (a crear cuando lo hagamos):
  ```dart
  abstract class PaymentsGateway {
    Future<PagoResult> cobrarSena({required int montoSoles, required String reservaId});
    Future<RecargaResult> recargarSaldoClub({required int montoSoles, required String clubId});
  }
  ```

## Requisitos para arrancar pagos
1. **Backend** (API + base de datos) para órdenes, webhooks y antifraude.
2. Cuenta de comercio en la pasarela elegida (Culqi/Niubiz/Mercado Pago/Yape).
3. Definir la **unidad económica**: % de comisión, costo del crédito, paquetes de boost.

## Fases sugeridas
| Fase | Pago |
|---|---|
| 1 (actual) | Sin cobro. Reservas demo. |
| 2 | Seña con tarjeta/Yape al reservar + recarga prepago del dueño. |
| 3 | Comisión sobre reservas nuevas + boost/destacados + suscripción opcional. |
