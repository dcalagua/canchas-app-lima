import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart';

import '../models/mensaje.dart';
import '../services/supabase_service.dart';

/// Chat de academia en Supabase (tabla `pichangol_mensajes`) con **Realtime**.
/// El hilo es 1:1 por (academia, cuenta del alumno). Fail-safe: si Supabase no
/// está configurado, los streams quedan vacíos y la UI muestra un aviso.
class MensajesRepo {
  static const _tabla = 'pichangol_mensajes';

  static bool get disponible => SupabaseService.disponible;

  /// Mensajes de UNA conversación, en vivo, PAGINADO: solo trae los últimos
  /// [limite] mensajes (los más recientes), sin importar cuán largo sea el hilo.
  /// Así abrir un chat es instantáneo aunque tenga miles de mensajes. Se pide a
  /// Supabase en DESC + limit (los N más nuevos) y se REVIERTE a orden
  /// cronológico (el más nuevo abajo, estilo WhatsApp) para pintar. Para ver más
  /// historia, se sube [limite] (botón "Cargar mensajes anteriores").
  static Stream<List<Mensaje>> streamHilo(String hilo, {int limite = 50}) {
    if (!SupabaseService.disponible) return Stream<List<Mensaje>>.empty();
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['id'])
        .eq('hilo', hilo)
        .order('creado', ascending: false) // los más NUEVOS primero…
        .limit(limite) // …y solo N (ventana reciente)
        .map((rows) =>
            rows.map((r) => Mensaje.fromRow(r)).toList().reversed.toList());
  }

  /// Todos los mensajes de una academia, en vivo (para la bandeja del profe:
  /// se agrupan por hilo en la pantalla).
  static Stream<List<Mensaje>> streamAcademia(String academiaId) {
    if (!SupabaseService.disponible) return Stream<List<Mensaje>>.empty();
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['id'])
        .eq('academia_id', academiaId)
        .order('creado', ascending: true) // cronológico: el inbox se apoya en esto
        .map((rows) => rows.map((r) => Mensaje.fromRow(r)).toList());
  }

  /// Trae (one-shot) todos los mensajes de un conjunto de academias, en orden
  /// cronológico. Se usa para el inbox unificado "Mensajes" (agrupa por hilo).
  /// Fail-safe: si no hay backend o falla, devuelve lista vacía.
  static Future<List<Mensaje>> mensajesDeAcademias(List<String> ids) async {
    if (!SupabaseService.disponible || ids.isEmpty) return const <Mensaje>[];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('academia_id', ids)
          .order('creado', ascending: true);
      return (rows as List)
          .map((r) => Mensaje.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <Mensaje>[];
    }
  }

  /// Conversaciones de CANCHA del usuario (one-shot): mensajes donde es el dueño
  /// (ref_id = su email) o el jugador (cuenta_email = su email). Para el inbox.
  static Future<List<Mensaje>> mensajesCanchaDe(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return const <Mensaje>[];
    try {
      final e = email.trim().toLowerCase();
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('tipo', 'cancha')
          .or('ref_id.eq.$e,cuenta_email.eq.$e')
          .order('creado', ascending: true);
      return (rows as List)
          .map((r) => Mensaje.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <Mensaje>[];
    }
  }

  /// Mensajes DIRECTOS 1:1 del usuario (los que envió o recibió), para el inbox.
  static Future<List<Mensaje>> mensajesDirectosDe(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return const <Mensaje>[];
    try {
      final e = email.trim().toLowerCase();
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('tipo', 'directo')
          .or('autor_email.eq.$e,cuenta_email.eq.$e')
          .order('creado', ascending: true);
      return (rows as List)
          .map((r) => Mensaje.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <Mensaje>[];
    }
  }

  /// Mensajes de un conjunto de GRUPOS (one-shot), para el inbox.
  static Future<List<Mensaje>> mensajesDeGrupos(List<String> grupoIds) async {
    if (!SupabaseService.disponible || grupoIds.isEmpty) {
      return const <Mensaje>[];
    }
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('tipo', 'grupo')
          .inFilter('ref_id', grupoIds)
          .order('creado', ascending: true);
      return (rows as List)
          .map((r) => Mensaje.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <Mensaje>[];
    }
  }

  /// Sube una foto del chat al bucket `chat` de Storage y devuelve su URL
  /// pública (o null si falla). El path agrupa por hilo.
  static Future<String?> subirFoto(String hilo, Uint8List bytes) async {
    if (!SupabaseService.disponible) return null;
    try {
      final carpeta = hilo.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      final path = '$carpeta/${DateTime.now().microsecondsSinceEpoch}.jpg';
      await SupabaseService.client.storage.from('chat').uploadBinary(
            path,
            bytes,
            fileOptions:
                const FileOptions(contentType: 'image/jpeg', upsert: true),
          );
      return SupabaseService.client.storage.from('chat').getPublicUrl(path);
    } catch (_) {
      return null;
    }
  }

  /// Sube una nota de voz (.m4a) al bucket `chat` y devuelve su URL pública.
  static Future<String?> subirAudio(String hilo, Uint8List bytes) async {
    if (!SupabaseService.disponible) return null;
    try {
      final carpeta = hilo.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      final path = '$carpeta/${DateTime.now().microsecondsSinceEpoch}.m4a';
      await SupabaseService.client.storage.from('chat').uploadBinary(
            path,
            bytes,
            fileOptions:
                const FileOptions(contentType: 'audio/mp4', upsert: true),
          );
      return SupabaseService.client.storage.from('chat').getPublicUrl(path);
    } catch (_) {
      return null;
    }
  }

  /// Envía un mensaje (INSERT). Devuelve true si se guardó. Fail-safe.
  static Future<bool> enviar(Mensaje m) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).insert(m.toInsert());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra los mensajes de un conjunto de academias (para "Dejar en virgen").
  /// Best-effort: no lanza.
  static Future<void> eliminarDeAcademias(List<String> ids) async {
    if (!SupabaseService.disponible || ids.isEmpty) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .inFilter('academia_id', ids);
    } catch (_) {}
  }

  /// Borra las conversaciones de CANCHA donde el usuario participa (dueño =
  /// ref_id, o jugador = cuenta_email). Best-effort.
  static Future<void> eliminarCanchaDe(String email) async {
    if (!SupabaseService.disponible || email.isEmpty) return;
    try {
      final e = email.trim().toLowerCase();
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .eq('tipo', 'cancha')
          .or('ref_id.eq.$e,cuenta_email.eq.$e');
    } catch (_) {}
  }
}
