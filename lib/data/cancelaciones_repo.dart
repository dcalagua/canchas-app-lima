import '../models/models.dart';
import '../services/supabase_service.dart';

/// Registro HISTÓRICO de reservas canceladas (tabla
/// `pichangol_reservas_canceladas`). La cancelación BORRA la fila de
/// `pichangol_reservas` (así el UNIQUE libera el slot), por eso el reporte de
/// cancelados vive en su propia tabla: se inserta una copia al cancelar.
/// Todo fail-safe: si la tabla no existe aún o no hay red, no rompe nada.
class CancelacionesRepo {
  CancelacionesRepo._();

  static const _tabla = 'pichangol_reservas_canceladas';

  /// Inserta el registro de cancelación de cada reserva del bloque.
  /// [canceladoPor] = correo de quien canceló (el jugador).
  static Future<void> registrar(
      List<Reserva> grupo, Cancha? cancha, String canceladoPor) async {
    if (grupo.isEmpty || !SupabaseService.disponible) return;
    final ahora = DateTime.now().toUtc().toIso8601String();
    List<Map<String, dynamic>> filas({required bool conSena}) => [
          for (final r in grupo)
            {
              'reserva_id': r.id,
              'cancha_id': r.canchaId,
              'cancha_nombre': cancha?.nombre ?? '',
              'local': cancha?.club ?? '',
              'dueno': (cancha?.dueno ?? '').toLowerCase(),
              'jugador': r.jugador,
              'usuario': r.usuario.toLowerCase(),
              'fecha': r.fecha,
              'hora_inicio': r.horaInicio,
              'hora_fin': r.horaFin,
              'precio': r.precio,
              'moneda': r.monedaSimbolo,
              'pagado': r.pagado,
              // Seña adelantada (no reembolsable): con la cancelación queda a
              // favor del dueño y el RESTO ya no se debe.
              if (conSena) 'sena': r.sena,
              'medio_pago': r.medioPago,
              'cancelado_por': canceladoPor.toLowerCase(),
              'cancelada_en': ahora,
            }
        ];
    try {
      await SupabaseService.client.from(_tabla).insert(filas(conSena: true));
    } catch (_) {
      // Reintento sin la columna `sena` (schema drift: BD sin actualizar).
      try {
        await SupabaseService.client.from(_tabla).insert(filas(conSena: false));
      } catch (_) {
        // best-effort: el reporte es histórico, no bloquea la cancelación
      }
    }
  }

  /// Cancelaciones de las canchas de [duenoEmail], más recientes primero.
  static Future<List<Map<String, dynamic>>> deDueno(String duenoEmail) async {
    if (!SupabaseService.disponible || duenoEmail.trim().isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('dueno', duenoEmail.trim().toLowerCase())
          .order('cancelada_en', ascending: false)
          .limit(200);
      return (rows as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }
}
