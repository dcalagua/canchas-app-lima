import 'package:supabase_flutter/supabase_flutter.dart';

import '../models/resena.dart';
import '../services/supabase_service.dart';

/// Reseñas de canchas en Supabase (`pichangol_resenas`). Fail-safe: si no hay
/// backend, devuelve vacío y el envío falla en silencio (la UI lo maneja).
class ResenasRepo {
  static const _tabla = 'pichangol_resenas';

  static bool get disponible => SupabaseService.disponible;

  /// Reseñas de un conjunto de canchas (todas las de un local), más nuevas
  /// primero.
  static Future<List<Resena>> deCanchas(List<String> canchaIds) async {
    if (!disponible || canchaIds.isEmpty) return const <Resena>[];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .inFilter('cancha_id', canchaIds)
          .order('creado', ascending: false);
      return (rows as List)
          .map((r) => Resena.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <Resena>[];
    }
  }

  /// Crea o actualiza la reseña del autor para esa cancha (upsert por la clave
  /// única cancha_id + autor_email). Devuelve true si se guardó.
  static Future<bool> enviar(Resena r) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client
          .from(_tabla)
          .upsert(r.toInsert(), onConflict: 'cancha_id,autor_email');
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra las reseñas de un conjunto de canchas (para "Dejar en virgen").
  /// Best-effort: no lanza.
  static Future<void> eliminarDeCanchas(List<String> canchaIds) async {
    if (!disponible || canchaIds.isEmpty) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .inFilter('cancha_id', canchaIds);
    } catch (_) {}
  }
}
