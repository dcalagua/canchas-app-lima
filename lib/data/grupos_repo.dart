import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/grupo.dart';
import '../services/supabase_service.dart';

/// Grupos de chat en Supabase (`pichangol_grupos` + `pichangol_grupo_miembros`).
/// Fail-safe: si no hay backend, devuelve vacío / false.
class GruposRepo {
  static const _tGrupos = 'pichangol_grupos';
  static const _tMiembros = 'pichangol_grupo_miembros';
  static const _bucket = 'grupos'; // fotos de grupo (bucket público)

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

  /// Un grupo por id, con sus miembros cargados (o null si no existe/falla).
  static Future<Grupo?> obtener(String grupoId) async {
    if (!disponible || grupoId.isEmpty) return null;
    try {
      final row = await SupabaseService.client
          .from(_tGrupos)
          .select()
          .eq('id', grupoId)
          .maybeSingle();
      if (row == null) return null;
      final mRows = await SupabaseService.client
          .from(_tMiembros)
          .select('email')
          .eq('grupo_id', grupoId);
      final miembros = (mRows as List)
          .map((r) => (r as Map)['email']?.toString() ?? '')
          .where((s) => s.isNotEmpty)
          .toList();
      return Grupo.fromRow(row as Map<String, dynamic>)
          .copyWith(miembros: miembros);
    } catch (_) {
      return null;
    }
  }

  /// Cambia el nombre y/o la foto del grupo. Devuelve true si se guardó.
  static Future<bool> actualizar(String grupoId,
      {String? nombre, String? fotoUrl}) async {
    if (!disponible || grupoId.isEmpty) return false;
    final cambios = <String, dynamic>{};
    if (nombre != null && nombre.trim().isNotEmpty) {
      cambios['nombre'] = nombre.trim();
    }
    if (fotoUrl != null) cambios['foto_url'] = fotoUrl;
    if (cambios.isEmpty) return true;
    try {
      await SupabaseService.client
          .from(_tGrupos)
          .update(cambios)
          .eq('id', grupoId);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Sube la foto del grupo al bucket público `grupos` y devuelve su URL.
  static Future<String?> subirFoto(String grupoId, Uint8List bytes) async {
    if (!disponible || grupoId.isEmpty) return null;
    try {
      final ruta = '$grupoId.jpg';
      final storage = SupabaseService.client.storage.from(_bucket);
      await storage.uploadBinary(ruta, bytes,
          fileOptions:
              const FileOptions(upsert: true, contentType: 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }

  /// Saca a un miembro del grupo (salir del grupo = quitarme yo). Devuelve true.
  static Future<bool> salir(String grupoId, String email) async {
    if (!disponible || grupoId.isEmpty || email.trim().isEmpty) return false;
    try {
      await SupabaseService.client
          .from(_tMiembros)
          .delete()
          .eq('grupo_id', grupoId)
          .eq('email', email.trim().toLowerCase());
      return true;
    } catch (_) {
      return false;
    }
  }
}
