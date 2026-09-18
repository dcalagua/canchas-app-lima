import '../services/supabase_service.dart';

/// DESCUENTOS por slot puntual (hora feliz de una hora concreta): el dueño rebaja
/// el precio de un (cancha, fecha, hora) para llenar la cancha. Se guarda en
/// Supabase (`pichangol_descuentos_slot`) para que el precio rebajado valga en
/// todos los dispositivos (también cuando el jugador reserva online). Fail-safe:
/// sin backend, no hay descuentos en la nube (el dueño igual los ve local).
///
/// Clave lógica: "canchaId|fecha|hora" (fecha ISO 'YYYY-MM-DD'). `pct` = % 1..90.
///
/// Tabla (crear una vez en Supabase):
///   create table pichangol_descuentos_slot (
///     cancha_id text not null, fecha text not null, hora text not null,
///     pct int not null,
///     primary key (cancha_id, fecha, hora)
///   );
class DescuentosRepo {
  static const _tabla = 'pichangol_descuentos_slot';

  static bool get disponible => SupabaseService.disponible;

  static String clave(String canchaId, String fecha, String hora) =>
      '$canchaId|$fecha|$hora';

  /// Trae todos los descuentos vigentes como mapa "canchaId|fecha|hora" → pct.
  static Future<Map<String, int>> fetch() async {
    if (!disponible) return <String, int>{};
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('cancha_id, fecha, hora, pct');
      final out = <String, int>{};
      for (final r in rows as List) {
        final m = r as Map;
        final pct = (m['pct'] as num?)?.toInt() ?? 0;
        if (pct <= 0) continue;
        out[clave((m['cancha_id'] ?? '').toString(),
            (m['fecha'] ?? '').toString(), (m['hora'] ?? '').toString())] = pct;
      }
      return out;
    } catch (_) {
      return <String, int>{};
    }
  }

  static Future<void> aplicar(
      String canchaId, String fecha, String hora, int pct) async {
    if (!disponible) return;
    try {
      await SupabaseService.client.from(_tabla).upsert({
        'cancha_id': canchaId,
        'fecha': fecha,
        'hora': hora,
        'pct': pct,
      }, onConflict: 'cancha_id,fecha,hora');
    } catch (_) {}
  }

  static Future<void> quitar(
      String canchaId, String fecha, String hora) async {
    if (!disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .eq('cancha_id', canchaId)
          .eq('fecha', fecha)
          .eq('hora', hora);
    } catch (_) {}
  }
}
