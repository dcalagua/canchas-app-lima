import '../services/supabase_service.dart';

/// Una posición "en vivo" leída de `pichangol_ubicacion_vivo`.
class UbicacionVivo {
  const UbicacionVivo({
    required this.lat,
    required this.lng,
    required this.actualizado,
    required this.expira,
  });

  final double lat;
  final double lng;
  final DateTime actualizado; // último fix (local)
  final DateTime expira; // hasta cuándo se comparte (local); parada = expira<=now

  /// ¿Sigue activa la compartición? (no venció y el fix es "reciente").
  bool get activa => DateTime.now().isBefore(expira);

  static UbicacionVivo? fromRow(Map<String, dynamic>? r) {
    if (r == null) return null;
    final la = (r['lat'] as num?)?.toDouble();
    final ln = (r['lng'] as num?)?.toDouble();
    if (la == null || ln == null) return null;
    final act = DateTime.tryParse((r['actualizado_en'] ?? '').toString())
            ?.toLocal() ??
        DateTime.now();
    final exp =
        DateTime.tryParse((r['expira_en'] ?? '').toString())?.toLocal() ??
            DateTime.now();
    return UbicacionVivo(lat: la, lng: ln, actualizado: act, expira: exp);
  }
}

/// Ubicación EN TIEMPO REAL por (hilo, correo). Una sola fila por persona/chat:
/// el que comparte hace upsert de su posición cada pocos segundos hasta
/// `expira_en`; el que mira la relee (poll) para ver el pin moverse. Fail-safe:
/// sin backend, todos los métodos no hacen nada / devuelven null.
class UbicacionVivoRepo {
  static const _tabla = 'pichangol_ubicacion_vivo';

  /// Sube/actualiza MI posición en este hilo (upsert por hilo+email).
  static Future<void> actualizar({
    required String hilo,
    required String email,
    required double lat,
    required double lng,
    required DateTime expira,
  }) async {
    final e = email.trim().toLowerCase();
    if (!SupabaseService.disponible || hilo.isEmpty || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'hilo': hilo,
        'email': e,
        'lat': lat,
        'lng': lng,
        'actualizado_en': DateTime.now().toUtc().toIso8601String(),
        'expira_en': expira.toUtc().toIso8601String(),
      }, onConflict: 'hilo,email');
    } catch (_) {}
  }

  /// Detiene MI compartición ahora (pone `expira_en` = ahora). El que mira lo ve
  /// "finalizado" en el siguiente refresco.
  static Future<void> detener({
    required String hilo,
    required String email,
  }) async {
    final e = email.trim().toLowerCase();
    if (!SupabaseService.disponible || hilo.isEmpty || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tabla).update({
        'expira_en': DateTime.now().toUtc().toIso8601String(),
      }).eq('hilo', hilo).eq('email', e);
    } catch (_) {}
  }

  /// Última posición de [email] en [hilo], o null si no hay / no hay backend.
  static Future<UbicacionVivo?> ultima({
    required String hilo,
    required String email,
  }) async {
    final e = email.trim().toLowerCase();
    if (!SupabaseService.disponible || hilo.isEmpty || e.isEmpty) return null;
    try {
      final row = await SupabaseService.client
          .from(_tabla)
          .select('lat,lng,actualizado_en,expira_en')
          .eq('hilo', hilo)
          .eq('email', e)
          .maybeSingle();
      return UbicacionVivo.fromRow(row);
    } catch (_) {
      return null;
    }
  }
}
