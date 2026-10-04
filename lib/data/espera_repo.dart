import '../models/espera.dart';
import '../services/supabase_service.dart';

/// Lista de espera de horarios en Supabase (`pichangol_espera`). Fail-safe: si
/// no hay backend, devuelve vacío y las escrituras fallan en silencio (la UI lo
/// maneja).
class EsperaRepo {
  static const _tabla = 'pichangol_espera';

  static bool get disponible => SupabaseService.disponible;

  /// Entradas de espera de un conjunto de canchas (las de un local o las del
  /// dueño), más antiguas primero (orden de llegada = orden de la cola).
  static Future<List<EnEspera>> deCanchas(List<String> canchaIds) async {
    if (!disponible || canchaIds.isEmpty) return const <EnEspera>[];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('cancha_id', canchaIds)
          .order('creado', ascending: true);
      return (rows as List)
          .map((r) => EnEspera.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <EnEspera>[];
    }
  }

  /// El jugador se anota (o refresca su anotación) a un slot. Upsert por la
  /// clave única. Devuelve true si se guardó.
  static Future<bool> unirse(EnEspera e) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client
          .from(_tabla)
          .upsert(e.toInsert(), onConflict: 'cancha_id,fecha,hora,usuario');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// El jugador se baja de la lista de espera de ese slot. Best-effort.
  static Future<bool> salir(String id) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra la lista de espera de un conjunto de canchas (para "Dejar en virgen").
  static Future<void> eliminarDeCanchas(List<String> canchaIds) async {
    if (!disponible || canchaIds.isEmpty) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .inFilter('cancha_id', canchaIds);
    } catch (_) {}
  }
}
