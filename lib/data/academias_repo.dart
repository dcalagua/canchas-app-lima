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

  /// Último error al guardar en la nube (para diagnóstico). null = todo OK.
  static String? ultimoError;

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

  /// Inserta o actualiza (upsert por id). Devuelve true si quedó guardada en la
  /// nube (o si no hay nube configurada: nada que sincronizar). Devuelve FALSE si
  /// Supabase está disponible pero el guardado FALLÓ (p. ej. RLS sin política de
  /// UPDATE): así la app sabe que la edición local aún no está en la nube y no la
  /// pisa con la versión vieja al recargar. Guarda el motivo en [ultimoError].
  static Future<bool> guardar(Academia a) async {
    if (!SupabaseService.disponible) {
      ultimoError = null;
      return true; // sin nube: la fuente de verdad es lo local
    }
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': a.id,
        'dueno': a.dueno,
        'data': a.toJson(),
        'eliminada': false,
      }, onConflict: 'id'); // fuerza UPDATE sobre la misma fila (no duplica)
      ultimoError = null;
      return true;
    } catch (e) {
      ultimoError = e.toString();
      return false;
    }
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
