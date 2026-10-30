import '../services/supabase_service.dart';

/// Horarios BLOQUEADOS por el dueño (mantenimiento, walk-in, etc.): esos slots
/// no se pueden reservar. Se guardan en Supabase (`pichangol_bloqueos`) para que
/// el bloqueo valga en todos los dispositivos. Fail-safe: sin backend, vacío.
///
/// Clave lógica de un bloqueo: "canchaId|fecha|hora" (fecha ISO 'YYYY-MM-DD').
class BloqueosRepo {
  static const _tabla = 'pichangol_bloqueos';

  static bool get disponible => SupabaseService.disponible;

  static String clave(String canchaId, String fecha, String hora) =>
      '$canchaId|$fecha|$hora';

  /// Trae todos los bloqueos como set de claves "canchaId|fecha|hora".
  static Future<Set<String>> fetch() async {
    if (!disponible) return <String>{};
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('cancha_id, fecha, hora');
      return (rows as List)
          .map((r) => clave(
                ((r as Map)['cancha_id'] ?? '').toString(),
                (r['fecha'] ?? '').toString(),
                (r['hora'] ?? '').toString(),
              ))
          .toSet();
    } catch (_) {
      return <String>{};
    }
  }

  static Future<void> bloquear(
      String canchaId, String fecha, String hora) async {
    if (!disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'cancha_id': canchaId,
        'fecha': fecha,
        'hora': hora,
      });
    } catch (_) {}
  }

  static Future<void> desbloquear(
      String canchaId, String fecha, String hora) async {
    if (!disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .eq('cancha_id', canchaId)
          .eq('fecha', fecha)
          .eq('hora', hora);
    } catch (_) {}
  }
}
