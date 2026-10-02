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

  /// Matrículas de un alumno-app por su correo (para que vea sus academias):
  /// las que PAGA (columna `email` = titular) y las que un familiar registró
  /// con SU correo (`data->>emailAlumno`, "Para otra persona"), así la esposa
  /// ve sus clases en su propia app aunque las pague el titular.
  static Future<({List<Alumno> alumnos, List<Cuota> cuotas})> deAlumno(
      String email) async {
    if (!SupabaseService.disponible || email.isEmpty) {
      return (alumnos: <Alumno>[], cuotas: <Cuota>[]);
    }
    try {
      final e = email.trim().toLowerCase().replaceAll(',', '');
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .or('email.eq.$e,data->>emailAlumno.eq.$e')
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

  // Cola por alumno: dos guardados del mismo alumno (p. ej. agregarAlumno +
  // inscribir) se hacen EN ORDEN, para que el segundo lea lo que dejó el
  // primero y no lo pise.
  static final Map<String, Future<List<Cuota>?>> _cola = {};

  /// Inserta o actualiza (upsert por id) FUSIONANDO con la fila de la nube:
  /// - conserva las claves que el app no conoce (`pagoWeb`, `canal`… de la web);
  /// - las cuotas se fusionan POR ID: las de la nube que el teléfono no trae
  ///   (p. ej. una cuota que el profe agregó en la web) se conservan, las de
  ///   [cuotas] se agregan o actualizan, y el pago es "pegajoso" (una cuota
  ///   pagada en la nube no vuelve a pendiente).
  /// Nunca revive una matrícula eliminada. Devuelve la lista FUSIONADA de
  /// cuotas (para que el teléfono incorpore las de la nube) o null si no se
  /// pudo guardar. Fail-safe.
  static Future<List<Cuota>?> guardar(Alumno a,
      {List<Cuota> cuotas = const []}) {
    final previo = _cola[a.id] ?? Future<List<Cuota>?>.value(null);
    final f = previo
        .catchError((_) => null)
        .then((_) => _guardarFusionando(a, cuotas));
    _cola[a.id] = f;
    f.whenComplete(() {
      if (identical(_cola[a.id], f)) _cola.remove(a.id);
    });
    return f;
  }

  static Future<List<Cuota>?> _guardarFusionando(
      Alumno a, List<Cuota> cuotas) async {
    if (!SupabaseService.disponible) return null;
    try {
      final row = await SupabaseService.client
          .from(_tabla)
          .select('data, eliminada')
          .eq('id', a.id)
          .maybeSingle();
      if (row != null && row['eliminada'] == true) return null;
      final nube = (row != null && row['data'] is Map)
          ? Map<String, dynamic>.from(row['data'] as Map)
          : <String, dynamic>{};
      // Fusión de cuotas por id, respetando el orden de la nube.
      final orden = <String>[];
      final porId = <String, Map<String, dynamic>>{};
      final cs = nube['cuotas'];
      if (cs is List) {
        for (final c in cs) {
          if (c is! Map) continue;
          final m = Map<String, dynamic>.from(c);
          final id = (m['id'] ?? '').toString();
          if (id.isEmpty) continue;
          if (!porId.containsKey(id)) orden.add(id);
          porId[id] = m;
        }
      }
      for (final c in cuotas) {
        final local = c.toJson();
        final previa = porId[c.id];
        if (previa == null) {
          orden.add(c.id);
          porId[c.id] = local;
        } else if (previa['pagada'] == true && !c.pagada) {
          // La nube ya la tiene pagada (web / otro equipo): se queda pagada.
        } else {
          porId[c.id] = {...previa, ...local};
        }
      }
      final fusion = [for (final id in orden) porId[id]!];
      final data = <String, dynamic>{
        ...nube,
        ...a.toJson(),
        if (fusion.isNotEmpty) 'cuotas': fusion,
      };
      await SupabaseService.client.from(_tabla).upsert({
        'id': a.id,
        'academia_id': a.academiaId,
        'email': a.email,
        'data': data,
        'eliminada': false,
      });
      final out = <Cuota>[];
      for (final m in fusion) {
        try {
          out.add(Cuota.fromJson(m));
        } catch (_) {}
      }
      return out;
    } catch (_) {
      return null;
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
