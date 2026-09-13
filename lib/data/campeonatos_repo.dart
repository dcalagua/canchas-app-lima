import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/campeonato.dart';
import '../services/supabase_service.dart';
import 'storage_limpieza.dart';

/// Acceso a CAMPEONATOS en Supabase (tabla `pichangol_campeonatos`). Guarda el
/// campeonato completo (participantes + fixture + resultados) como JSON en la
/// columna `data` jsonb: un solo upsert actualiza todo. Fail-safe.
///
/// El directorio es público (cualquiera ve llaves/tabla y se inscribe), como
/// `pichangol_academias`.
class CampeonatosRepo {
  static const _tabla = 'pichangol_campeonatos';

  static Future<List<Campeonato>> fetchRemotos() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .neq('eliminado', true);
      return (rows as List)
          .map((r) => Campeonato.fromJson(
              Map<String, dynamic>.from((r as Map)['data'] as Map)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Trae UN campeonato por su id (para abrirlo desde un enlace/código
  /// compartido, aunque no sea de una academia del usuario). null si no existe,
  /// fue eliminado, o no hay backend.
  static Future<Campeonato?> porId(String id) async {
    if (!SupabaseService.disponible || id.trim().isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('id', id.trim())
          .neq('eliminado', true)
          .limit(1);
      final lista = rows as List;
      if (lista.isEmpty) return null;
      return Campeonato.fromJson(
          Map<String, dynamic>.from((lista.first as Map)['data'] as Map));
    } catch (_) {
      return null;
    }
  }

  /// Trae UN campeonato por su CÓDIGO corto (para "Unirme a un campeonato").
  /// Busca en el jsonb `data->>codigo` (mayúsculas). null si no existe.
  static Future<Campeonato?> porCodigo(String codigo) async {
    final cod = codigo.trim().toUpperCase();
    if (!SupabaseService.disponible || cod.isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('data->>codigo', cod)
          .neq('eliminado', true)
          .limit(1);
      final lista = rows as List;
      if (lista.isEmpty) return null;
      return Campeonato.fromJson(
          Map<String, dynamic>.from((lista.first as Map)['data'] as Map));
    } catch (_) {
      return null;
    }
  }

  /// Sube el LOGO del campeonato a Storage y devuelve su URL pública (con
  /// cache-buster). Reusa el bucket público `canchas` con carpeta `campeonatos/`
  /// (no requiere crear un bucket nuevo). null si falla / sin backend.
  /// Busca campeonatos por NOMBRE (contiene, sin distinguir mayúsculas) en la
  /// nube. Hasta 15 coincidencias, los más recientes primero. Fail-safe.
  static Future<List<Campeonato>> buscarPorNombre(String q) async {
    final texto = q.trim();
    if (!SupabaseService.disponible || texto.length < 3) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('eliminado', false)
          .ilike('data->>nombre', '%$texto%')
          .order('updated_at', ascending: false)
          .limit(15);
      return [
        for (final r in (rows as List))
          if (r['data'] != null)
            Campeonato.fromJson(Map<String, dynamic>.from(r['data'] as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }

  static Future<String?> subirLogo(String campId, List<int> bytes) async {
    if (!SupabaseService.disponible || campId.isEmpty) return null;
    try {
      final ruta = 'campeonatos/$campId.jpg';
      final storage = SupabaseService.client.storage.from('canchas');
      await storage.uploadBinary(ruta, Uint8List.fromList(bytes),
          fileOptions: const FileOptions(upsert: true, contentType: 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }

  /// Inserta o actualiza (upsert por id). Fail-safe.
  static Future<void> guardar(Campeonato c) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'id': c.id,
        'academia_id': c.academiaId,
        'dueno': c.dueno,
        'data': c.toJson(),
        'eliminado': false,
      });
    } catch (_) {}
  }

  /// Borrado lógico durable (sobrevive reinstalar). Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update({'eliminado': true}).eq('id', id);
    } catch (_) {}
    // Su afiche/foto no debe quedar huérfano en el bucket.
    await StorageLimpieza.borrar('canchas', ['campeonatos/$id.jpg']);
  }
}
