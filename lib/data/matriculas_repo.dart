import '../models/academia.dart';
import '../services/supabase_service.dart';

/// Acceso a MATRÍCULAS (alumnos) en Supabase (tabla `pichangol_matriculas`).
/// Guarda el alumno completo como JSON (columna `data` jsonb) + columnas sueltas
/// `academia_id` y `email` para poder filtrar rápido.
///
/// Sirve para que el flujo "Unirme con código" funcione ENTRE dispositivos: el
/// alumno se une en su celular → su matrícula sube a la nube → el profe la ve en
/// el suyo. Todo fail-safe: si Supabase no está o falla, la app sigue con lo
/// local.
class MatriculasRepo {
  static const _tabla = 'pichangol_matriculas';

  /// Matrículas de un conjunto de academias (las del profe). Fail-safe.
  static Future<List<Alumno>> deAcademias(List<String> academiaIds) async {
    if (!SupabaseService.disponible || academiaIds.isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('academia_id', academiaIds)
          .neq('eliminada', true);
      return _mapear(rows);
    } catch (_) {
      return [];
    }
  }

  /// Matrículas de un alumno-app por su correo (para que vea sus academias).
  static Future<List<Alumno>> deAlumno(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', email)
          .neq('eliminada', true);
      return _mapear(rows);
    } catch (_) {
      return [];
    }
  }

  static List<Alumno> _mapear(dynamic rows) => (rows as List)
      .map((r) =>
          Alumno.fromJson(Map<String, dynamic>.from((r as Map)['data'] as Map)))
      .toList();

  /// Inserta o actualiza (upsert por id). Fail-safe.
  static Future<void> guardar(Alumno a) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': a.id,
        'academia_id': a.academiaId,
        'email': a.email,
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
