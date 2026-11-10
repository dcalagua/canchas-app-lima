import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// Estado de ENTREGA/LECTURA de los mensajes (checks tipo WhatsApp). Por cada
/// (hilo, correo) guardamos hasta cuándo ese usuario tiene ENTREGADO y LEÍDO el
/// hilo. El remitente compara la marca del OTRO con la fecha de su mensaje:
///   - sin llegar a "entregado"      → 1 check gris (enviado)
///   - entregado ≥ msg               → 2 checks grises (recibido)
///   - leído ≥ msg                   → 2 checks azules (leído)
/// Fail-safe: sin Supabase, no hace nada y los checks quedan en "enviado".
/// Requiere docs/piloto/supabase_lecturas.sql.
class LecturasRepo {
  static const _tabla = 'pichangol_lecturas';

  static bool get disponible => SupabaseService.disponible;

  /// Marca que [email] tiene LEÍDO (y por ende entregado) el [hilo] hasta ahora.
  static Future<void> marcarLeido(String hilo, String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || hilo.isEmpty || e.isEmpty) return;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      await SupabaseService.client.from(_tabla).upsert({
        'hilo': hilo,
        'email': e,
        'entregado_hasta': now,
        'leido_hasta': now,
      }, onConflict: 'hilo,email');
    } catch (_) {}
  }

  /// Marca ENTREGADO (no leído) varios hilos para [email] hasta ahora. Se llama
  /// cuando el dispositivo del destinatario baja los mensajes (abre Mensajes),
  /// aunque no haya abierto el chat → el remitente ve 2 checks grises.
  static Future<void> marcarEntregados(
      List<String> hilos, String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || hilos.isEmpty || e.isEmpty) return;
    try {
      final now = DateTime.now().toUtc().toIso8601String();
      // Solo la columna entregado_hasta → NO pisa leido_hasta existente.
      final filas = hilos
          .toSet()
          .where((h) => h.isNotEmpty)
          .map((h) => {'hilo': h, 'email': e, 'entregado_hasta': now})
          .toList();
      if (filas.isEmpty) return;
      await SupabaseService.client
          .from(_tabla)
          .upsert(filas, onConflict: 'hilo,email');
    } catch (_) {}
  }

  /// Stream en vivo de las marcas de un hilo (ambos participantes). El chat filtra
  /// la fila del OTRO para pintar los checks.
  static Stream<List<Map<String, dynamic>>> stream(String hilo) {
    if (!disponible || hilo.isEmpty) {
      return const Stream<List<Map<String, dynamic>>>.empty();
    }
    return SupabaseService.client
        .from(_tabla)
        .stream(primaryKey: ['hilo', 'email'])
        .eq('hilo', hilo)
        .map((rows) => rows.map((r) => Map<String, dynamic>.from(r)).toList());
  }
}
