import '../models/mensaje.dart';
import '../services/supabase_service.dart';

/// Chat de academia en Supabase (tabla `pichangol_mensajes`) con **Realtime**.
/// El hilo es 1:1 por (academia, cuenta del alumno). Fail-safe: si Supabase no
/// está configurado, los streams quedan vacíos y la UI muestra un aviso.
class MensajesRepo {
  static const _tabla = 'pichangol_mensajes';

  static bool get disponible => SupabaseService.disponible;

  /// Mensajes de UNA conversación, en vivo (orden cronológico).
  static Stream<List<Mensaje>> streamHilo(String hilo) {
    if (!SupabaseService.disponible) return Stream<List<Mensaje>>.empty();
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['id'])
        .eq('hilo', hilo)
        .order('creado')
        .map((rows) => rows.map((r) => Mensaje.fromRow(r)).toList());
  }

  /// Todos los mensajes de una academia, en vivo (para la bandeja del profe:
  /// se agrupan por hilo en la pantalla).
  static Stream<List<Mensaje>> streamAcademia(String academiaId) {
    if (!SupabaseService.disponible) return Stream<List<Mensaje>>.empty();
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['id'])
        .eq('academia_id', academiaId)
        .order('creado')
        .map((rows) => rows.map((r) => Mensaje.fromRow(r)).toList());
  }

  /// Envía un mensaje (INSERT). Devuelve true si se guardó. Fail-safe.
  static Future<bool> enviar(Mensaje m) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).insert(m.toInsert());
      return true;
    } catch (_) {
      return false;
    }
  }
}
