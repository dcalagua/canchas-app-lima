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

  /// Matrículas de un conjunto de academias (las del profe). Devuelve alumnos +
  /// las cuotas EMBEBIDAS en cada matrícula (lo que pagó al inscribirse por la
  /// app), para que el profe vea el programa y el pago. Fail-safe.
  static Future<({List<Alumno> alumnos, List<Cuota> cuotas})> deAcademias(
      List<String> academiaIds) async {
    if (!SupabaseService.disponible || academiaIds.isEmpty) {
      return (alumnos: <Alumno>[], cuotas: <Cuota>[]);
    }
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('academia_id', academiaIds)
          .neq('eliminada', true);
      return _mapear(rows);
    } catch (_) {
      return (alumnos: <Alumno>[], cuotas: <Cuota>[]);
    }
  }

  /// Matrículas de un alumno-app por su correo (para que vea sus academias).
  static Future<({List<Alumno> alumnos, List<Cuota> cuotas})> deAlumno(
      String email) async {
    if (!SupabaseService.disponible || email.isEmpty) {
      return (alumnos: <Alumno>[], cuotas: <Cuota>[]);
    }
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', email)
          .neq('eliminada', true);
      return _mapear(rows);
    } catch (_) {
      return (alumnos: <Alumno>[], cuotas: <Cuota>[]);
    }
  }

  static ({List<Alumno> alumnos, List<Cuota> cuotas}) _mapear(dynamic rows) {
    final alumnos = <Alumno>[];
    final cuotas = <Cuota>[];
    for (final r in (rows as List)) {
      final data = Map<String, dynamic>.from((r as Map)['data'] as Map);
      alumnos.add(Alumno.fromJson(data));
      final cs = data['cuotas'];
      if (cs is List) {
        for (final c in cs) {
          try {
            cuotas.add(Cuota.fromJson(Map<String, dynamic>.from(c as Map)));
          } catch (_) {}
        }
      }
    }
    return (alumnos: alumnos, cuotas: cuotas);
  }

  /// Inserta o actualiza (upsert por id). Si se pasan [cuotas], se EMBEBEN en el
  /// dato para que el profe las vea desde otro dispositivo. Fail-safe.
  static Future<void> guardar(Alumno a, {List<Cuota> cuotas = const []}) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': a.id,
        'academia_id': a.academiaId,
        'email': a.email,
        'data': {
          ...a.toJson(),
          if (cuotas.isNotEmpty)
            'cuotas': cuotas.map((c) => c.toJson()).toList(),
        },
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
