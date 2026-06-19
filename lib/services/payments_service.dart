import 'dart:async';

/// Método de pago elegido por el usuario.
enum MetodoPago { yape, tarjeta }

/// Resultado de un cobro.
class PagoResult {
  final bool exito;
  final String referencia;
  final String? error;
  const PagoResult({required this.exito, required this.referencia, this.error});
}

/// Contrato de la pasarela de pagos. Hoy hay una implementación SIMULADA
/// ([PasarelaSimulada]); para producción se crea una que use Culqi / Niubiz /
/// Yape contra un backend que tokeniza la tarjeta y confirma por webhook.
/// Ver docs/PAYMENTS.md.
abstract class PaymentsGateway {
  /// Cobra [montoSoles] al jugador (ej. seña de una reserva).
  Future<PagoResult> cobrar({
    required int montoSoles,
    required MetodoPago metodo,
    required String concepto,
  });

  /// Recarga el saldo prepago del club.
  Future<PagoResult> recargarSaldo({
    required int montoSoles,
    required MetodoPago metodo,
  });
}

/// Implementación de demostración: no cobra de verdad, solo simula el flujo
/// (latencia + referencia). Sirve para probar la experiencia de pago completa.
class PasarelaSimulada implements PaymentsGateway {
  const PasarelaSimulada();

  Future<PagoResult> _simular(String prefijo) async {
    await Future.delayed(const Duration(milliseconds: 1400));
    final ref = '$prefijo-${DateTime.now().millisecondsSinceEpoch % 1000000}';
    return PagoResult(exito: true, referencia: ref);
  }

  @override
  Future<PagoResult> cobrar({
    required int montoSoles,
    required MetodoPago metodo,
    required String concepto,
  }) =>
      _simular('PAGO');

  @override
  Future<PagoResult> recargarSaldo({
    required int montoSoles,
    required MetodoPago metodo,
  }) =>
      _simular('RECARGA');
}

/// Pasarela activa de la app. Cambiar aquí por la real en la fase de pagos.
const PaymentsGateway pasarela = PasarelaSimulada();
