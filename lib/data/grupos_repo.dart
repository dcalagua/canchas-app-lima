import '../models/grupo.dart';
import '../services/supabase_service.dart';

/// Grupos de chat en Supabase (`pichangol_grupos` + `pichangol_grupo_miembros`).
/// Fail-safe: si no hay backend, devuelve vacío / false.
class GruposRepo {
  static const _tGrupos = 'pichangol_grupos';
  static const _tMiembros = 'pichangol_grupo_miembros';

  static bool get disponible => SupabaseService.disponible;

  /// Crea un grupo con sus miembros (el creador ya debe venir en [miembros]).
  /// [miembros] = lista de {email, nombre}. Devuelve true si se guardó.
  static Future<bool> crear(Grupo g, List<Map<String, String>> miembros) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tGrupos).insert(g.toInsert());
      final filas = miembros
          .where((m) => (m['email'] ?? '').trim().isNotEmpty)
          .map((m) => {
                'grupo_id': g.id,
                'email': m['email']!.trim().toLowerCase(),
                'nombre': m['nombre'] ?? '',
              })
          .toList();
      if (filas.isNotEmpty) {
        await SupabaseService.client.from(_tMiembros).upsert(filas);
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Agrega un miembro a un grupo existente.
  static Future<bool> agregarMiembro(
      String grupoId, String email, String nombre) async {
    if (!disponible || grupoId.isEmpty || email.trim().isEmpty) return false;
    try {
      await SupabaseService.client.from(_tMiembros).upsert({
        'grupo_id': grupoId,
        'email': email.trim().toLowerCase(),
        'nombre': nombre,
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Grupos donde el usuario es miembro, con la lista de miembros cargada.
  static Future<List<Grupo>> gruposDe(String email) async {
    if (!disponible || email.trim().isEmpty) return const <Grupo>[];
    try {
      final e = email.trim().toLowerCase();
      final mios = await SupabaseService.client
          .from(_tMiembros)
          .select('grupo_id')
          .eq('email', e);
      final ids = (mios as List)
          .map((r) => (r as Map)['grupo_id']?.toString() ?? '')
          .where((s) => s.isNotEmpty)
          .toSet()
          .toList();
      if (ids.isEmpty) return const <Grupo>[];

      final gRows = await SupabaseService.client
          .from(_tGrupos)
          .select()
          .inFilter('id', ids);
      final mRows = await SupabaseService.client
          .from(_tMiembros)
          .select('grupo_id, email')
          .inFilter('grupo_id', ids);

      final porGrupo = <String, List<String>>{};
      for (final r in (mRows as List)) {
        final gid = (r as Map)['grupo_id']?.toString() ?? '';
        final em = r['email']?.toString() ?? '';
        if (gid.isEmpty || em.isEmpty) continue;
        porGrupo.putIfAbsent(gid, () => []).add(em);
      }
      return (gRows as List)
          .map((r) => Grupo.fromRow(r as Map<String, dynamic>))
          .map((g) => g.copyWith(miembros: porGrupo[g.id] ?? const []))
          .toList();
    } catch (_) {
      return const <Grupo>[];
    }
  }
}
