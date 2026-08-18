import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// PERFILES públicos de usuario en Supabase (`pichangol_perfiles`): el nombre y
/// la foto que la persona quiere mostrar (a veces su Gmail muestra cualquier
/// cosa). Los usa el chat (y donde se muestre a otra persona) para pintar
/// nombre + foto en vez del correo. Clave = email. Fail-safe.
class PerfilesRepo {
  static const _tabla = 'pichangol_perfiles';

  static bool get disponible => SupabaseService.disponible;

  /// Crea/actualiza el perfil del correo (upsert). Devuelve true si guardó.
  static Future<bool> guardar({
    required String email,
    required String nombre,
    String? fotoUrl,
    String? celular,
    String? recado,
    Map<String, String>? bio,
  }) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return false;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'email': e,
        'nombre': nombre.trim(),
        if (fotoUrl != null && fotoUrl.isNotEmpty) 'foto_url': fotoUrl,
        // celular: se envía siempre que no sea null (permite BORRARLO con '').
        if (celular != null) 'celular': celular.trim(),
        // recado/estado (tipo WhatsApp): se envía si no es null. Requiere la
        // columna `recado` en la tabla (ver docs/piloto/supabase_recado.sql).
        if (recado != null) 'recado': recado.trim(),
        // BIO estilo Airbnb (jsonb): requiere docs/piloto/supabase_perfil_bio.sql.
        if (bio != null) 'bio': bio,
        'actualizado': DateTime.now().toUtc().toIso8601String(),
      }, onConflict: 'email');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Lee la BIO (campos estilo Airbnb) del perfil. {} si no hay o falla.
  static Future<Map<String, String>> leerBio(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return {};
    try {
      final r = await SupabaseService.client
          .from(_tabla)
          .select('bio')
          .eq('email', e)
          .maybeSingle();
      final b = r?['bio'];
      if (b is Map) {
        return {
          for (final en in b.entries)
            if (en.value != null && en.value.toString().trim().isNotEmpty)
              en.key.toString(): en.value.toString()
        };
      }
      return {};
    } catch (_) {
      return {};
    }
  }

  /// Sube la foto de perfil del usuario al bucket `chat` (carpeta `perfiles/`) y
  /// devuelve su URL pública, o null si falla. Reusa el bucket público del chat.
  static Future<String?> subirFoto(String email, Uint8List bytes) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return null;
    try {
      final carpeta =
          'perfiles/${e.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_')}';
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

  /// Perfil de un correo, o null si no existe.
  static Future<Map<String, dynamic>?> obtener(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('email', e)
          .limit(1);
      final l = rows as List;
      return l.isEmpty ? null : Map<String, dynamic>.from(l.first as Map);
    } catch (_) {
      return null;
    }
  }

  /// Busca usuarios por NOMBRE o CORREO (para el buscador tipo WhatsApp).
  /// Devuelve hasta [limite] perfiles. Fail-safe.
  static Future<List<Map<String, dynamic>>> buscar(String query,
      {int limite = 25}) async {
    final q = query.trim();
    if (!disponible || q.length < 2) return const [];
    try {
      final patron = '%${q.toLowerCase()}%';
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .or('nombre.ilike.$patron,email.ilike.$patron')
          .limit(limite);
      return (rows as List)
          .map((r) => Map<String, dynamic>.from(r as Map))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Perfiles de varios correos → mapa email→{nombre, foto_url}. Para listas
  /// (bandeja de chats). Best-effort.
  static Future<Map<String, Map<String, dynamic>>> obtenerVarios(
      List<String> emails) async {
    final es = emails
        .map((e) => e.trim().toLowerCase())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();
    if (!disponible || es.isEmpty) return const {};
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('email', es);
      final out = <String, Map<String, dynamic>>{};
      for (final r in rows as List) {
        final m = Map<String, dynamic>.from(r as Map);
        final e = (m['email'] ?? '').toString().toLowerCase();
        if (e.isNotEmpty) out[e] = m;
      }
      return out;
    } catch (_) {
      return const {};
    }
  }
}
