import '../models/campeonato.dart';
import '../services/supabase_service.dart';

/// Acceso a CAMPEONATOS en Supabase (tabla `pichangol_campeonatos`). Guarda el
/// campeonato completo (participantes + fixture + resultados) como JSON en la
/// columna `data` jsonb: un solo upsert actualiza todo. Fail-safe.
///
/// El directorio es público (cualquiera ve llaves/tabla y se inscribe), como
/// `pichangol_academias`.
class CampeonatosRepo {
  static const _tabla = 'pichangol_campeonatos';

  static Future<List<Campeonato>> fetchRemotos() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .neq('eliminado', true);
      return (rows as List)
          .map((r) => Campeonato.fromJson(
              Map<String, dynamic>.from((r as Map)['data'] as Map)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Inserta o actualiza (upsert por id). Fail-safe.
  static Future<void> guardar(Campeonato c) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': c.id,
        'academia_id': c.academiaId,
        'dueno': c.dueno,
        'data': c.toJson(),
        'eliminado': false,
      });
    } catch (_) {}
  }

  /// Borrado lógico durable (sobrevive reinstalar). Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update({'eliminado': true}).eq('id', id);
    } catch (_) {}
  }
}
