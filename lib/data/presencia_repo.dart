import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// Presencia "EN LÍNEA" por hilo de chat, sobre Realtime **broadcast** (sin tabla
/// ni columnas nuevas). Mientras el chat está abierto, cada quien "late" (ping)
/// cada pocos segundos; el otro lo ve "en línea" si su último ping es reciente.
/// Fail-safe: si no hay backend, `abrir` devuelve null y todo sigue igual.
class Presencia {
  Presencia(this._canal);
  final RealtimeChannel _canal;

  /// Envía un latido con mi correo (el otro me verá "en línea").
  void ping(String miEmail) {
    try {
      _canal.sendBroadcastMessage(
          event: 'ping', payload: {'email': miEmail.toLowerCase()});
    } catch (_) {}
  }

  Future<void> cerrar() async {
    try {
      await _canal.unsubscribe();
    } catch (_) {}
  }
}

class PresenciaRepo {
  static const _tablaVisto = 'pichangol_presencia';

  /// Marca que YO estoy activo AHORA (upsert de mi fila en pichangol_presencia).
  /// Se llama en un latido global mientras la app está en primer plano y al
  /// minimizar. Fail-safe: si no hay tabla/backend, no hace nada.
  static Future<void> latir(String miEmail) async {
    final e = miEmail.trim().toLowerCase();
    if (!SupabaseService.disponible || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tablaVisto).upsert({
        'email': e,
        'visto_en': DateTime.now().toUtc().toIso8601String(),
      }, onConflict: 'email');
    } catch (_) {}
  }

  /// Borra mi fila de presencia (al apagar "última vez": nadie la ve más).
  static Future<void> ocultar(String email) async {
    final e = email.trim().toLowerCase();
    if (!SupabaseService.disponible || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tablaVisto).delete().eq('email', e);
    } catch (_) {}
  }

  /// Última vez que [email] estuvo activo (UTC→local), o null si no hay dato.
  static Future<DateTime?> ultimoVisto(String email) async {
    final e = email.trim().toLowerCase();
    if (!SupabaseService.disponible || e.isEmpty) return null;
    try {
      final row = await SupabaseService.client
          .from(_tablaVisto)
          .select('visto_en')
          .eq('email', e)
          .maybeSingle();
      final v = (row?['visto_en'] ?? '').toString();
      if (v.isEmpty) return null;
      return DateTime.tryParse(v)?.toLocal();
    } catch (_) {
      return null;
    }
  }

  /// Abre el canal de presencia de [hilo]. Llama [onPing] con el correo del OTRO
  /// cada vez que late. Devuelve un [Presencia] para latir/cerrar, o null si no
  /// hay backend.
  static Presencia? abrir({
    required String hilo,
    required String miEmail,
    required void Function(String email) onPing,
  }) {
    if (!SupabaseService.disponible || hilo.isEmpty || miEmail.isEmpty) {
      return null;
    }
    try {
      final me = miEmail.toLowerCase();
      final canal = SupabaseService.client.channel('presencia_$hilo');
      canal.onBroadcast(
        event: 'ping',
        callback: (payload) {
          final e = (payload['email'] ?? '').toString().toLowerCase();
          if (e.isNotEmpty && e != me) onPing(e);
        },
      );
      final p = Presencia(canal);
      canal.subscribe((status, [error]) {
        if (status == RealtimeSubscribeStatus.subscribed) {
          p.ping(me); // avisa que YO entré (el otro me ve al instante)
        }
      });
      return p;
    } catch (_) {
      return null;
    }
  }
}
