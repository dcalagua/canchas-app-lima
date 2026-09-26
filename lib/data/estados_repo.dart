import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/estado.dart';
import '../services/supabase_service.dart';
import 'storage_limpieza.dart';

/// Acceso a los ESTADOS / HISTORIAS (tipo WhatsApp) en Supabase. Tabla
/// `pichangol_estados` (dura 24 h) + tabla `pichangol_estados_vistas` (quién vio
/// cada estado) + bucket público `estados` para las fotos. Todo fail-safe: sin
/// Supabase o ante error devuelve vacío / no hace nada y la app sigue.
/// Requiere docs/piloto/supabase_estados.sql.
class EstadosRepo {
  static const _tabla = 'pichangol_estados';
  static const _tablaVistas = 'pichangol_estados_vistas';
  static const _bucket = 'estados';

  static bool get disponible => SupabaseService.disponible;

  /// Todos los estados de las últimas 24 h (los vigentes), más antiguos primero
  /// (así se ven en orden de publicación dentro de cada autor).
  static Future<List<Estado>> fetchVigentes() async {
    if (!disponible) return [];
    try {
      final desde = DateTime.now()
          .toUtc()
          .subtract(const Duration(hours: 24))
          .toIso8601String();
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .gte('creado_en', desde)
          .order('creado_en', ascending: true);
      return (rows as List)
          .map((r) => Estado.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Publica (inserta) un estado. Fail-safe.
  static Future<bool> publicar(Estado e) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).upsert(e.toRow());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra un estado propio (fila + su media del bucket). Fail-safe.
  static Future<bool> eliminar(String id) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
      await StorageLimpieza.borrar(_bucket, ['$id.jpg', '$id.mp4']);
      return true;
    } catch (_) {}
    return false;
  }

  /// Barre los estados VENCIDOS (más viejos que [antiguedad], default 24 h)
  /// del autor [email]: borra su media del bucket, sus vistas y sus filas.
  /// Cada usuario limpia lo SUYO al cargar estados ("cada uno barre su
  /// vereda") — así el bucket no acumula historias muertas sin necesitar un
  /// cron en el servidor. Con `antiguedad: Duration.zero` borra TODOS los
  /// estados del autor (lo usa "Dejar en virgen"). Fail-safe.
  static Future<void> limpiarVencidosDe(String email,
      {Duration antiguedad = const Duration(hours: 24)}) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return;
    try {
      final limite =
          DateTime.now().toUtc().subtract(antiguedad).toIso8601String();
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('id')
          .eq('autor_email', e)
          .lt('creado_en', limite);
      final ids = [
        for (final r in (rows as List))
          ((r as Map)['id'] ?? '').toString()
      ]..removeWhere((id) => id.isEmpty);
      if (ids.isEmpty) return;
      await StorageLimpieza.borrar(_bucket, [
        for (final id in ids) ...['$id.jpg', '$id.mp4'],
      ]);
      await SupabaseService.client
          .from(_tablaVistas)
          .delete()
          .inFilter('estado_id', ids);
      await SupabaseService.client.from(_tabla).delete().inFilter('id', ids);
    } catch (_) {}
  }

  /// Marca que [email] vio el estado [estadoId] (upsert idempotente).
  static Future<void> marcarVisto(String estadoId, String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tablaVistas).upsert({
        'estado_id': estadoId,
        'email': e,
        'visto_en': DateTime.now().toUtc().toIso8601String(),
      }, onConflict: 'estado_id,email');
    } catch (_) {}
  }

  /// Devuelve, por cada estado de [estadoIds], la lista de correos que lo vieron.
  /// Sirve para que el autor vea "quién vio" su estado.
  static Future<Map<String, List<String>>> vistas(
      List<String> estadoIds) async {
    if (!disponible || estadoIds.isEmpty) return {};
    try {
      final rows = await SupabaseService.client
          .from(_tablaVistas)
          .select('estado_id, email')
          .inFilter('estado_id', estadoIds);
      final m = <String, List<String>>{};
      for (final r in (rows as List)) {
        final id = ((r as Map)['estado_id'] ?? '').toString();
        final em = (r['email'] ?? '').toString().toLowerCase();
        if (id.isEmpty || em.isEmpty) continue;
        (m[id] ??= <String>[]).add(em);
      }
      return m;
    } catch (_) {
      return {};
    }
  }

  static String? ultimoErrorFoto;

  /// Sube la foto de un estado al bucket público `estados` y devuelve su URL.
  /// Null si falla (motivo en [ultimoErrorFoto]).
  static Future<String?> subirFoto(String estadoId, Uint8List bytes) async {
    if (!disponible) {
      ultimoErrorFoto = 'Supabase no está configurado en esta app.';
      return null;
    }
    try {
      final ruta = '$estadoId.jpg';
      final storage = SupabaseService.client.storage.from(_bucket);
      await storage.uploadBinary(ruta, bytes,
          fileOptions:
              const FileOptions(upsert: true, contentType: 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      ultimoErrorFoto = null;
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (e) {
      final s = e.toString().toLowerCase();
      if (s.contains('bucket') || s.contains('not found')) {
        ultimoErrorFoto =
            'Falta el bucket "estados" en Supabase Storage (créalo público).';
      } else if (s.contains('policy') ||
          s.contains('row-level') ||
          s.contains('403') ||
          s.contains('unauthorized')) {
        ultimoErrorFoto =
            'El bucket "estados" no permite subir fotos (falta la política).';
      } else {
        ultimoErrorFoto = 'No se pudo subir la foto. Detalle: $e';
      }
      return null;
    }
  }

  /// Sube el VIDEO de un estado al bucket público `estados` (.mp4) y devuelve su
  /// URL. Null si falla (motivo en [ultimoErrorFoto]). Mismo bucket que las fotos.
  static Future<String?> subirVideo(String estadoId, Uint8List bytes) async {
    if (!disponible) {
      ultimoErrorFoto = 'Supabase no está configurado en esta app.';
      return null;
    }
    try {
      final ruta = '$estadoId.mp4';
      final storage = SupabaseService.client.storage.from(_bucket);
      await storage.uploadBinary(ruta, bytes,
          fileOptions:
              const FileOptions(upsert: true, contentType: 'video/mp4'));
      final base = storage.getPublicUrl(ruta);
      ultimoErrorFoto = null;
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (e) {
      final s = e.toString().toLowerCase();
      if (s.contains('bucket') || s.contains('not found')) {
        ultimoErrorFoto =
            'Falta el bucket "estados" en Supabase Storage (créalo público).';
      } else if (s.contains('policy') ||
          s.contains('row-level') ||
          s.contains('403') ||
          s.contains('unauthorized')) {
        ultimoErrorFoto =
            'El bucket "estados" no permite subir videos (falta la política).';
      } else if (s.contains('maximum') || s.contains('size') || s.contains('413')) {
        ultimoErrorFoto =
            'El video es muy pesado para el bucket. Graba uno más corto.';
      } else {
        ultimoErrorFoto = 'No se pudo subir el video. Detalle: $e';
      }
      return null;
    }
  }
}
