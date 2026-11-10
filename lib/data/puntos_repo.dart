import '../services/supabase_service.dart';

/// CANJES de puntos Pichangol (tabla `pichangol_puntos_canjes`). Los puntos
/// GANADOS se derivan de las reservas (AppState.misPuntos); aquí vive solo lo
/// CANJEADO: disponibles = ganados − canjeados. Fail-safe: sin Supabase no
/// rompe nada (el canje simplemente no se ofrece).
class PuntosRepo {
  static const _tabla = 'pichangol_puntos_canjes';

  /// Total de puntos ya canjeados por [email]. null = no se pudo leer.
  static Future<int?> totalCanjeado(String email) async {
    if (!SupabaseService.disponible || email.trim().isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('puntos')
          .eq('email', email.trim().toLowerCase());
      if (rows is List) {
        var total = 0;
        for (final r in rows) {
          total += ((r as Map)['puntos'] as num?)?.toInt() ?? 0;
        }
        return total;
      }
    } catch (_) {}
    return null;
  }

  /// Registra un canje (100 pts → S/3 en una reserva). Best-effort.
  static Future<bool> registrarCanje({
    required String email,
    required int puntos,
    required double soles,
    required String referencia,
  }) async {
    if (!SupabaseService.disponible || email.trim().isEmpty) return false;
    try {
      await SupabaseService.client.from(_tabla).insert({
        'email': email.trim().toLowerCase(),
        'puntos': puntos,
        'soles': soles,
        'referencia': referencia,
      });
      return true;
    } catch (_) {
      return false;
    }
  }
}
