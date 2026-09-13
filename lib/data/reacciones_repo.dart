import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// Reacciones (emoji) a un mensaje, tipo WhatsApp: UNA por persona por mensaje.
/// Tabla `pichangol_reacciones` (mensaje_id, email, emoji, hilo). Se transmite en
/// vivo por hilo para pintar la reacción bajo la burbuja. Fail-safe.
/// Requiere docs/piloto/supabase_reacciones.sql (+ Realtime).
class ReaccionesRepo {
  static const _tabla = 'pichangol_reacciones';

  static bool get disponible => SupabaseService.disponible;

  /// Pone (o cambia) la reacción de [email] a [mensajeId]. Si ya tenía ese mismo
  /// emoji, la QUITA (toggle, como WhatsApp).
  static Future<void> alternar(
      String hilo, String mensajeId, String email, String emoji,
      {String? emojiActual}) async {
    final e = email.trim().toLowerCase();
    if (!disponible || mensajeId.isEmpty || e.isEmpty) return;
    try {
      if (emojiActual == emoji) {
        await SupabaseService.client
            .from(_tabla)
            .delete()
            .eq('mensaje_id', mensajeId)
            .eq('email', e);
        return;
      }
      await SupabaseService.client.from(_tabla).upsert({
        'mensaje_id': mensajeId,
        'email': e,
        'emoji': emoji,
        'hilo': hilo,
      }, onConflict: 'mensaje_id,email');
    } catch (_) {}
  }

  /// Stream en vivo de las reacciones de un hilo. El chat las agrupa por mensaje.
  static Stream<List<Map<String, dynamic>>> stream(String hilo) {
    if (!disponible || hilo.isEmpty) {
      return const Stream<List<Map<String, dynamic>>>.empty();
    }
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['mensaje_id', 'email'])
        .eq('hilo', hilo)
        .map((rows) => rows.map((r) => Map<String, dynamic>.from(r)).toList());
  }
}
