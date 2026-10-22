import '../models/academia.dart';
import '../models/plan_trabajo.dart';
import '../services/supabase_service.dart';

/// OPERACIÓN DE LA ACADEMIA en la nube: asistencia, rúbrica de evaluación,
/// bitácora de clases y planes de trabajo del profe. Son las MISMAS tablas que
/// usa la web (`backend/growth/web/anfitrion_academia_ops.py`), con las mismas
/// columnas y formatos, así lo que el profe marca en el app se ve en la web y
/// al revés:
///
/// - `pichangol_academia_asistencias` (academia_id, alumno_id, dia, presente,
///   avisado, actualizado) — clave (alumno_id, dia).
/// - `pichangol_academia_evaluaciones` (academia_id, alumno_id, plan_id,
///   habilidad, nivel, ts) — clave (alumno_id, plan_id, habilidad).
/// - `pichangol_academia_notas` (id, academia_id, alumno_id, plan_id,
///   sesion_numero, fecha, desempeno, nota, creado) — clave id.
/// - `pichangol_academia_planes` (id, academia_id, data = PlanTrabajo.toJson,
///   eliminado, actualizado) — clave id, borrado lógico.
///
/// SQL: `docs/piloto/supabase_academia_operacion.sql` +
/// `supabase_academia_operacion_rls.sql` (políticas para la llave del APK).
///
/// Fail-safe: las LECTURAS devuelven null si algo falla (tabla inexistente,
/// sin red, RLS), para que quien sincroniza NO confunda "no pude leer" con
/// "la nube está vacía". Las escrituras devuelven false y no lanzan.
class AcademiaOpsRepo {
  static const _tAsis = 'pichangol_academia_asistencias';
  static const _tEval = 'pichangol_academia_evaluaciones';
  static const _tNotas = 'pichangol_academia_notas';
  static const _tPlanes = 'pichangol_academia_planes';

  /// Tope de filas por página (PostgREST corta en 1000 por defecto).
  static const _pagina = 1000;

  static bool get disponible => SupabaseService.disponible;

  /// Lee TODAS las filas de [tabla] de esas academias, paginando.
  static Future<List<Map<String, dynamic>>?> _leerTodo(
      String tabla, List<String> academiaIds, String orden) async {
    if (!disponible || academiaIds.isEmpty) return null;
    try {
      final out = <Map<String, dynamic>>[];
      var desde = 0;
      while (true) {
        final rows = await SupabaseService.client
            .from(tabla)
            .select()
            .inFilter('academia_id', academiaIds)
            .order(orden, ascending: true)
            .range(desde, desde + _pagina - 1);
        final lista = (rows as List)
            .map((r) => Map<String, dynamic>.from(r as Map))
            .toList();
        out.addAll(lista);
        if (lista.length < _pagina) break;
        desde += _pagina;
        if (desde > 200000) break; // cinturón de seguridad
      }
      return out;
    } catch (_) {
      return null;
    }
  }

  // ── Asistencia ──────────────────────────────────────────────────────────

  static Future<List<Map<String, dynamic>>?> asistencias(
          List<String> academiaIds) =>
      _leerTodo(_tAsis, academiaIds, 'dia');

  /// Upsert de presente/falta (NO toca `avisado`: así no se pisa un aviso que
  /// marcó la web). Una fila nueva nace con avisado = false (default).
  static Future<bool> guardarAsistencias(List<Asistencia> regs) async {
    if (!disponible || regs.isEmpty) return false;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      await SupabaseService.client.from(_tAsis).upsert([
        for (final a in regs)
          {
            'academia_id': a.academiaId,
            'alumno_id': a.alumnoId,
            'dia': a.dia,
            'presente': a.presente,
            'actualizado': now,
          }
      ], onConflict: 'alumno_id,dia');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// "Ya se avisó a los padres" de ese día. Si no había fila, nace con el
  /// presente que tenga el teléfono (sin registro = falta, como la web).
  static Future<bool> marcarAvisado(
          {required String academiaId,
          required String alumnoId,
          required String dia,
          required bool presente}) =>
      marcarAvisados([
        (
          academiaId: academiaId,
          alumnoId: alumnoId,
          dia: dia,
          presente: presente
        )
      ]);

  /// Igual que [marcarAvisado] para varios en un solo viaje.
  static Future<bool> marcarAvisados(
      List<({String academiaId, String alumnoId, String dia, bool presente})>
          regs) async {
    if (!disponible || regs.isEmpty) return false;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      await SupabaseService.client.from(_tAsis).upsert([
        for (final r in regs)
          {
            'academia_id': r.academiaId,
            'alumno_id': r.alumnoId,
            'dia': r.dia,
            'presente': r.presente,
            'avisado': true,
            'actualizado': now,
          }
      ], onConflict: 'alumno_id,dia');
      return true;
    } catch (_) {
      return false;
    }
  }

  // ── Evaluaciones (rúbrica) ───────────────────────────────────────────────

  static Future<List<Map<String, dynamic>>?> evaluaciones(
          List<String> academiaIds) =>
      _leerTodo(_tEval, academiaIds, 'ts');

  /// Upsert por (alumno, plan, habilidad). [academiaDe] da la academia de cada
  /// evaluación (el modelo del app no la guarda); las que no tienen academia
  /// conocida se omiten.
  static Future<bool> guardarEvaluaciones(List<EvaluacionAlumno> evs,
      String? Function(EvaluacionAlumno) academiaDe) async {
    if (!disponible || evs.isEmpty) return false;
    final filas = <Map<String, dynamic>>[];
    for (final e in evs) {
      final aid = academiaDe(e);
      if (aid == null || aid.isEmpty) continue;
      filas.add({
        'academia_id': aid,
        'alumno_id': e.alumnoId,
        'plan_id': e.planId,
        'habilidad': e.habilidad,
        'nivel': e.nivel.name,
        'ts': e.cuando.millisecondsSinceEpoch,
      });
    }
    if (filas.isEmpty) return false;
    try {
      await SupabaseService.client
          .from(_tEval)
          .upsert(filas, onConflict: 'alumno_id,plan_id,habilidad');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra la rúbrica de un plan (al eliminar el plan).
  static Future<bool> borrarEvaluacionesDePlan(String planId) async {
    if (!disponible || planId.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tEval).delete().eq('plan_id', planId);
      return true;
    } catch (_) {
      return false;
    }
  }

  static EvaluacionAlumno? evaluacionDeFila(Map<String, dynamic> r) {
    final nivel = NivelLogro.porNombre(r['nivel'] as String?);
    final al = (r['alumno_id'] ?? '').toString();
    final plan = (r['plan_id'] ?? '').toString();
    final hab = (r['habilidad'] ?? '').toString();
    if (nivel == null || al.isEmpty || plan.isEmpty || hab.isEmpty) return null;
    return EvaluacionAlumno(
      alumnoId: al,
      planId: plan,
      habilidad: hab,
      nivel: nivel,
      cuando:
          DateTime.fromMillisecondsSinceEpoch((r['ts'] as num?)?.toInt() ?? 0),
    );
  }

  // ── Bitácora de clases ───────────────────────────────────────────────────

  static Future<List<Map<String, dynamic>>?> notas(List<String> academiaIds) =>
      _leerTodo(_tNotas, academiaIds, 'creado');

  static Future<bool> guardarNotas(List<NotaClase> notas) async {
    if (!disponible || notas.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tNotas).upsert([
        for (final n in notas)
          {
            'id': n.id,
            'academia_id': n.academiaId,
            'alumno_id': n.alumnoId,
            'plan_id': n.planId,
            'sesion_numero': n.sesionNumero,
            'fecha': n.fecha,
            'desempeno': n.desempeno.name,
            'nota': n.nota,
            'creado': n.creado.toUtc().toIso8601String(),
          }
      ], onConflict: 'id');
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> borrarNotas(List<String> ids) async {
    if (!disponible || ids.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tNotas).delete().inFilter('id', ids);
      return true;
    } catch (_) {
      return false;
    }
  }

  static NotaClase? notaDeFila(Map<String, dynamic> r) {
    final id = (r['id'] ?? '').toString();
    final des = DesempenoClase.porNombre(r['desempeno'] as String?);
    if (id.isEmpty || des == null) return null;
    return NotaClase(
      id: id,
      academiaId: (r['academia_id'] ?? '').toString(),
      alumnoId: (r['alumno_id'] ?? '').toString(),
      planId: (r['plan_id'] ?? '').toString(),
      sesionNumero: (r['sesion_numero'] as num?)?.toInt() ?? 0,
      fecha: (r['fecha'] ?? '').toString(),
      desempeno: des,
      nota: (r['nota'] ?? '').toString(),
      creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
          DateTime.now(),
    );
  }

  // ── Planes de trabajo ────────────────────────────────────────────────────

  /// Filas de planes (incluye los eliminados, para propagar el borrado).
  static Future<List<Map<String, dynamic>>?> planes(List<String> academiaIds) =>
      _leerTodo(_tPlanes, academiaIds, 'id');

  static Future<bool> guardarPlanes(List<PlanTrabajo> planes) async {
    if (!disponible || planes.isEmpty) return false;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      await SupabaseService.client.from(_tPlanes).upsert([
        for (final p in planes)
          {
            'id': p.id,
            'academia_id': p.academiaId,
            'data': p.toJson(),
            'eliminado': false,
            'actualizado': now,
          }
      ], onConflict: 'id');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borrado lógico (así el otro equipo y la web también lo quitan).
  static Future<bool> eliminarPlanes(List<String> ids) async {
    if (!disponible || ids.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tPlanes).update({
        'eliminado': true,
        'actualizado': DateTime.now().toUtc().toIso8601String(),
      }).inFilter('id', ids);
      return true;
    } catch (_) {
      return false;
    }
  }

  static PlanTrabajo? planDeFila(Map<String, dynamic> r) {
    final d = r['data'];
    if (d is! Map) return null;
    try {
      final p = PlanTrabajo.fromJson(Map<String, dynamic>.from(d));
      if (p.id.isEmpty) return null;
      final aid = (r['academia_id'] ?? '').toString();
      return p.academiaId.isEmpty && aid.isNotEmpty
          ? p.copyWith(academiaId: aid)
          : p;
    } catch (_) {
      return null;
    }
  }
}
