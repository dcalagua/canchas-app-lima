import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/canal.dart';
import '../services/supabase_service.dart';
import 'storage_limpieza.dart';

/// Canales de difusión (tipo WhatsApp Channels) en Supabase. Tablas
/// `pichangol_canales`, `pichangol_canal_seguidores`, `pichangol_canal_posts` +
/// bucket público `canales`. Todo fail-safe. Requiere
/// docs/piloto/supabase_canales.sql.
class CanalesRepo {
  static const _tCanales = 'pichangol_canales';
  static const _tSeguidores = 'pichangol_canal_seguidores';
  static const _tPosts = 'pichangol_canal_posts';
  static const _bucket = 'canales';

  static bool get disponible => SupabaseService.disponible;

  // ── Canales ────────────────────────────────────────────────────────────────

  /// Todos los canales (para descubrir), con el conteo de seguidores.
  static Future<List<Canal>> todos() async {
    if (!disponible) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tCanales)
          .select()
          .order('creado', ascending: false);
      final canales = (rows as List)
          .map((r) => Canal.fromRow(r as Map<String, dynamic>))
          .toList();
      final conteos = await _contarSeguidores(canales.map((c) => c.id).toList());
      return canales
          .map((c) => c.copyWith(seguidores: conteos[c.id] ?? 0))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// IDs de canales que sigue [email].
  static Future<Set<String>> seguidosDe(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return {};
    try {
      final rows = await SupabaseService.client
          .from(_tSeguidores)
          .select('canal_id')
          .eq('email', e);
      return (rows as List)
          .map((r) => (r as Map)['canal_id']?.toString() ?? '')
          .where((s) => s.isNotEmpty)
          .toSet();
    } catch (_) {
      return {};
    }
  }

  static Future<Map<String, int>> _contarSeguidores(List<String> ids) async {
    if (!disponible || ids.isEmpty) return {};
    try {
      final rows = await SupabaseService.client
          .from(_tSeguidores)
          .select('canal_id')
          .inFilter('canal_id', ids);
      final m = <String, int>{};
      for (final r in (rows as List)) {
        final id = ((r as Map)['canal_id'] ?? '').toString();
        if (id.isEmpty) continue;
        m[id] = (m[id] ?? 0) + 1;
      }
      return m;
    } catch (_) {
      return {};
    }
  }

  static Future<bool> crear(Canal c) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tCanales).insert(c.toInsert());
      // El creador queda como primer seguidor (ve su propio canal).
      await seguir(c.id, c.ownerEmail);
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> actualizar(String canalId,
      {String? nombre, String? descripcion, String? fotoUrl}) async {
    if (!disponible || canalId.isEmpty) return false;
    final cambios = <String, dynamic>{};
    if (nombre != null && nombre.trim().isNotEmpty) cambios['nombre'] = nombre.trim();
    if (descripcion != null) cambios['descripcion'] = descripcion.trim();
    if (fotoUrl != null) cambios['foto_url'] = fotoUrl;
    if (cambios.isEmpty) return true;
    try {
      await SupabaseService.client.from(_tCanales).update(cambios).eq('id', canalId);
      return true;
    } catch (_) {
      return false;
    }
  }

  // ── Seguir / dejar de seguir ────────────────────────────────────────────────

  static Future<bool> seguir(String canalId, String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || canalId.isEmpty || e.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tSeguidores).upsert(
        {'canal_id': canalId, 'email': e},
        onConflict: 'canal_id,email',
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> dejar(String canalId, String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || canalId.isEmpty || e.isEmpty) return false;
    try {
      await SupabaseService.client
          .from(_tSeguidores)
          .delete()
          .eq('canal_id', canalId)
          .eq('email', e);
      return true;
    } catch (_) {
      return false;
    }
  }

  // ── Publicaciones ───────────────────────────────────────────────────────────

  /// Feed de un canal (más nuevas primero).
  static Future<List<CanalPost>> posts(String canalId, {int limite = 50}) async {
    if (!disponible || canalId.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tPosts)
          .select()
          .eq('canal_id', canalId)
          .order('creado', ascending: false)
          .limit(limite);
      return (rows as List)
          .map((r) => CanalPost.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Últimas publicaciones de VARIOS canales (para el preview del inbox de
  /// canales): devuelve por canal la más reciente.
  static Future<Map<String, CanalPost>> ultimasDe(List<String> canalIds) async {
    if (!disponible || canalIds.isEmpty) return {};
    try {
      final rows = await SupabaseService.client
          .from(_tPosts)
          .select()
          .inFilter('canal_id', canalIds)
          .order('creado', ascending: false);
      final m = <String, CanalPost>{};
      for (final r in (rows as List)) {
        final p = CanalPost.fromRow(r as Map<String, dynamic>);
        m.putIfAbsent(p.canalId, () => p); // la primera = la más nueva
      }
      return m;
    } catch (_) {
      return {};
    }
  }

  /// Posts de VARIOS canales agrupados por canal (más nuevos primero). Sirve
  /// para el inbox de canales: última publicación + conteo de no leídos.
  static Future<Map<String, List<CanalPost>>> postsAgrupados(
      List<String> canalIds,
      {int limite = 400}) async {
    if (!disponible || canalIds.isEmpty) return {};
    try {
      final rows = await SupabaseService.client
          .from(_tPosts)
          .select()
          .inFilter('canal_id', canalIds)
          .order('creado', ascending: false)
          .limit(limite);
      final m = <String, List<CanalPost>>{};
      for (final r in (rows as List)) {
        final p = CanalPost.fromRow(r as Map<String, dynamic>);
        (m[p.canalId] ??= <CanalPost>[]).add(p);
      }
      return m;
    } catch (_) {
      return {};
    }
  }

  static Future<bool> publicar(CanalPost p) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tPosts).insert(p.toInsert());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra una publicación del canal y, con ella, su media del bucket (la
  /// ruta es `<canalId>/<postId>.<ext>`): si no, la foto o el video quedan
  /// ocupando espacio sin que nadie pueda verlos nunca más.
  static Future<bool> eliminarPost(String postId,
      {String canalId = '', String mediaUrl = ''}) async {
    if (!disponible || postId.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tPosts).delete().eq('id', postId);
      await _borrarMediaDePost(canalId, postId, mediaUrl);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// La extensión viaja en la URL guardada (jpg o mp4); si no la hay, se
  /// intentan las dos. Best-effort: nunca hace fallar el borrado del post.
  static Future<void> _borrarMediaDePost(
      String canalId, String postId, String mediaUrl) async {
    if (canalId.isEmpty || postId.isEmpty) return;
    final exts = <String>[];
    final limpia = mediaUrl.split('?').first;
    for (final e in const ['jpg', 'mp4']) {
      if (limpia.endsWith('.$e')) exts.add(e);
    }
    if (exts.isEmpty) exts.addAll(const ['jpg', 'mp4']);
    await StorageLimpieza.borrar(
        _bucket, [for (final e in exts) '$canalId/$postId.$e']);
  }

  /// Borra el canal entero: sus publicaciones, sus seguidores y TODA su media
  /// (portada + media de cada post viven en la carpeta `<canalId>/`).
  static Future<bool> eliminarCanal(String canalId) async {
    if (!disponible || canalId.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tPosts).delete().eq('canal_id', canalId);
      await SupabaseService.client
          .from(_tSeguidores)
          .delete()
          .eq('canal_id', canalId);
      await SupabaseService.client.from(_tCanales).delete().eq('id', canalId);
      await StorageLimpieza.borrarCarpeta(_bucket, canalId);
      return true;
    } catch (_) {
      return false;
    }
  }

  // ── Media (foto del canal / de una publicación) ──────────────────────────────

  static Future<String?> subirMedia(String ruta, Uint8List bytes,
      {bool video = false}) async {
    if (!disponible) return null;
    try {
      final storage = SupabaseService.client.storage.from(_bucket);
      await storage.uploadBinary(ruta, bytes,
          fileOptions: FileOptions(
              upsert: true, contentType: video ? 'video/mp4' : 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }
}
