import '../services/supabase_service.dart';

/// PREFERENCIAS DE BANDEJA por usuario en la nube (`pichangol_chat_prefs`):
/// qué chats ELIMINÓ de su bandeja (y cuándo), cuáles fijó, archivó o
/// silenció. Antes vivían SOLO en `SharedPreferences` → al reinstalar, cambiar
/// de equipo o volver a iniciar sesión, los chats "eliminados" reaparecían.
/// Ahora se espejan aquí por (email, hilo): el teléfono sigue mandando al
/// instante (device-first) y la nube es la memoria que sobrevive.
///
/// Fail-safe: sin Supabase (o si la tabla no existe todavía) no hace nada y la
/// app sigue con lo local. Requiere `docs/piloto/supabase_chat_prefs.sql`.
class ChatPrefsRepo {
  static const _tabla = 'pichangol_chat_prefs';

  static bool get disponible => SupabaseService.disponible;

  /// Todas las preferencias del usuario. Cada fila: `hilo`, `oculto_en`
  /// (ISO o null), `fijado`, `archivado`, `silenciado`.
  static Future<List<Map<String, dynamic>>> leer(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('hilo, oculto_en, fijado, archivado, silenciado')
          .eq('email', e);
      return (rows as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return const [];
    }
  }

  /// Guarda (upsert) el estado completo de UN hilo para el usuario.
  /// `ocultoEn` null = visible; ISO = eliminado de la bandeja en ese momento.
  static Future<bool> guardar({
    required String email,
    required String hilo,
    required String? ocultoEn,
    required bool fijado,
    required bool archivado,
    required bool silenciado,
  }) =>
      guardarVarios(email, [
        {
          'hilo': hilo,
          'oculto_en': ocultoEn,
          'fijado': fijado,
          'archivado': archivado,
          'silenciado': silenciado,
        }
      ]);

  /// Upsert de varias filas de una vez (para subir lo local que la nube aún no
  /// tenía). Cada mapa lleva `hilo`, `oculto_en`, `fijado`, `archivado`,
  /// `silenciado`.
  static Future<bool> guardarVarios(
      String email, List<Map<String, dynamic>> filas) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty || filas.isEmpty) return false;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      final rows = [
        for (final f in filas)
          if ((f['hilo'] ?? '').toString().isNotEmpty)
            {
              'email': e,
              'hilo': f['hilo'].toString(),
              'oculto_en': f['oculto_en'],
              'fijado': f['fijado'] == true,
              'archivado': f['archivado'] == true,
              'silenciado': f['silenciado'] == true,
              'actualizado': now,
            }
      ];
      if (rows.isEmpty) return false;
      await SupabaseService.client
          .from(_tabla)
          .upsert(rows, onConflict: 'email,hilo');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra TODAS las preferencias del usuario (Eliminar mi cuenta / virgen).
  static Future<void> eliminarTodo(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('email', e);
    } catch (_) {}
  }
}
