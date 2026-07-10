import '../models/academia.dart';
import '../services/supabase_service.dart';

/// Acceso a academias en Supabase (tabla `pichangol_academias`). Guarda la
/// academia completa como JSON (columna `data` jsonb) para no depender de
/// migraciones por campo. Todo fail-safe: si Supabase no está o falla, no rompe;
/// la app sigue con los datos locales.
///
/// Con esto las academias **sobreviven a reinstalar el APK** (antes vivían solo
/// en SharedPreferences y se perdían al desinstalar).
class AcademiasRepo {
  static const _tabla = 'pichangol_academias';

  static Future<List<Academia>> fetchRemotas() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .neq('eliminada', true);
      return (rows as List)
          .map((r) => Academia.fromJson(
              Map<String, dynamic>.from((r as Map)['data'] as Map)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Inserta o actualiza (upsert por id). Fail-safe.
  static Future<void> guardar(Academia a) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': a.id,
        'dueno': a.dueno,
        'data': a.toJson(),
        'eliminada': false,
      });
    } catch (_) {}
  }

  /// Borrado lógico durable (sobrevive reinstalar). Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update({'eliminada': true}).eq('id', id);
    } catch (_) {}
  }
}
