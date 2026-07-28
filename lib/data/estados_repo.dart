import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/estado.dart';
import '../services/supabase_service.dart';

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

  /// Borra un estado propio. Fail-safe.
  static Future<bool> eliminar(String id) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
      return true;
    } catch (_) {}
    return false;
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
}
