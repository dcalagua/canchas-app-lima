import '../models/partido.dart';
import '../services/supabase_service.dart';

/// Partidos abiertos ("busca con quién jugar") en Supabase. La metadata vive en
/// `pichangol_partidos`; el ROSTER y el chat de coordinación reutilizan los
/// GRUPOS (`pichangol_grupos` + `pichangol_grupo_miembros`) con el mismo id que
/// el partido. Fail-safe: sin backend devuelve vacío / false.
class PartidosRepo {
  static const _tPartidos = 'pichangol_partidos';
  static const _tGrupos = 'pichangol_grupos';
  static const _tMiembros = 'pichangol_grupo_miembros';

  static bool get disponible => SupabaseService.disponible;

  /// Publica un partido: crea la fila, el grupo de coordinación (mismo id) y
  /// apunta al creador como primer jugador. Devuelve true si se guardó.
  static Future<bool> crear(PartidoAbierto p) async {
    if (!disponible) return false;
    try {
      final c = SupabaseService.client;
      await c.from(_tPartidos).insert(p.toInsert());
      // Grupo de chat homónimo (para coordinar el partido) — best-effort.
      try {
        await c.from(_tGrupos).insert({
          'id': p.id,
          'nombre': p.titulo,
          'creador_email': p.creadorEmail.trim().toLowerCase(),
        });
      } catch (_) {}
      await c.from(_tMiembros).upsert({
        'grupo_id': p.id,
        'email': p.creadorEmail.trim().toLowerCase(),
        'nombre': p.creadorNombre,
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Partidos con fecha de hoy en adelante, con su roster cargado. El filtro por
  /// país/cercanía lo hace la pantalla (por lat/lng), igual que las academias.
  static Future<List<PartidoAbierto>> abiertos({String? hoyIso}) async {
    if (!disponible) return const <PartidoAbierto>[];
    try {
      final c = SupabaseService.client;
      final desde = hoyIso ?? _hoy();
      final rows = await c
          .from(_tPartidos)
          .select()
          .gte('fecha', desde)
          .order('fecha', ascending: true)
          .order('hora', ascending: true);
      final partidos = (rows as List)
          .map((r) => PartidoAbierto.fromRow(r as Map<String, dynamic>))
          .toList();
      if (partidos.isEmpty) return partidos;

      // Roster de todos de una sola consulta (grupo_id ∈ ids).
      final ids = partidos.map((p) => p.id).toList();
      final mRows = await c
          .from(_tMiembros)
          .select('grupo_id, email, nombre')
          .inFilter('grupo_id', ids);
      final emailsPorId = <String, List<String>>{};
      final nombresPorId = <String, List<String>>{};
      for (final r in (mRows as List)) {
        final m = r as Map;
        final gid = (m['grupo_id'] ?? '').toString();
        final em = (m['email'] ?? '').toString().toLowerCase();
        if (gid.isEmpty || em.isEmpty) continue;
        emailsPorId.putIfAbsent(gid, () => []).add(em);
        nombresPorId
            .putIfAbsent(gid, () => [])
            .add((m['nombre'] ?? '').toString());
      }
      return partidos
          .map((p) => p.copyWith(
                jugadoresEmails: emailsPorId[p.id] ?? const [],
                jugadoresNombres: nombresPorId[p.id] ?? const [],
              ))
          .toList();
    } catch (_) {
      return const <PartidoAbierto>[];
    }
  }

  /// Un jugador se apunta al partido (entra al roster/grupo). Devuelve true si
  /// quedó apuntado.
  static Future<bool> apuntarse(
      String partidoId, String email, String nombre) async {
    if (!disponible || partidoId.isEmpty || email.trim().isEmpty) return false;
    try {
      await SupabaseService.client.from(_tMiembros).upsert({
        'grupo_id': partidoId,
        'email': email.trim().toLowerCase(),
        'nombre': nombre,
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Un jugador se baja del partido (sale del roster/grupo).
  static Future<bool> bajarse(String partidoId, String email) async {
    if (!disponible || partidoId.isEmpty || email.trim().isEmpty) return false;
    try {
      await SupabaseService.client
          .from(_tMiembros)
          .delete()
          .eq('grupo_id', partidoId)
          .eq('email', email.trim().toLowerCase());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// El creador elimina su partido (y su grupo de coordinación).
  static Future<bool> eliminar(String partidoId) async {
    if (!disponible || partidoId.isEmpty) return false;
    try {
      final c = SupabaseService.client;
      await c.from(_tPartidos).delete().eq('id', partidoId);
      try {
        await c.from(_tMiembros).delete().eq('grupo_id', partidoId);
        await c.from(_tGrupos).delete().eq('id', partidoId);
      } catch (_) {}
      return true;
    } catch (_) {
      return false;
    }
  }

  static String _hoy() {
    final n = DateTime.now();
    return '${n.year.toString().padLeft(4, '0')}-'
        '${n.month.toString().padLeft(2, '0')}-'
        '${n.day.toString().padLeft(2, '0')}';
  }
}
