import 'package:supabase_flutter/supabase_flutter.dart';

import '../services/supabase_service.dart';

/// Programa de referidos en Supabase (`pichangol_referidos`). Un invitado canjea
/// UN código (unique por invitado). El referidor cobra su bono cuando abre su
/// pantalla "Invita y gana" (self-credit por `referidor_dado`). Fail-safe.
class ReferidosRepo {
  static const _tabla = 'pichangol_referidos';

  static bool get disponible => SupabaseService.disponible;

  /// El invitado canjea un código. Devuelve true si se registró (false si ya
  /// había canjeado antes o si falló).
  static Future<bool> canjear({
    required String invitadoEmail,
    required String codigo,
  }) async {
    if (!disponible) return false;
    try {
      final e = invitadoEmail.trim().toLowerCase();
      await SupabaseService.client.from(_tabla).insert({
        'id': 'ref_${e.hashCode.toUnsigned(20).toRadixString(16)}',
        'invitado_email': e,
        'referido_codigo': codigo.trim().toUpperCase(),
        'referidor_dado': false,
      });
      return true;
    } catch (_) {
      // Violación de unique (ya canjeó) u otro error → no acredita.
      return false;
    }
  }

  /// Cuántas personas usaron mi código (para mostrarlo en "Invita y gana").
  static Future<int> contarInvitados(String miCodigo) async {
    if (!disponible || miCodigo.isEmpty) return 0;
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('id')
          .eq('referido_codigo', miCodigo.trim().toUpperCase());
      return (rows as List).length;
    } catch (_) {
      return 0;
    }
  }

  /// Reclama (marca como pagados) los referidos de MI código que aún no me
  /// pagaron el bono. Devuelve cuántos nuevos hay para acreditarme.
  static Future<int> reclamarReferidor(String miCodigo) async {
    if (!disponible || miCodigo.isEmpty) return 0;
    try {
      final cod = miCodigo.trim().toUpperCase();
      final rows = await SupabaseService.client
          .from(_tabla)
          .select('id')
          .eq('referido_codigo', cod)
          .eq('referidor_dado', false);
      final ids =
          (rows as List).map((r) => (r as Map)['id'].toString()).toList();
      if (ids.isEmpty) return 0;
      await SupabaseService.client
          .from(_tabla)
          .update({'referidor_dado': true}).inFilter('id', ids);
      return ids.length;
    } catch (_) {
      return 0;
    }
  }
}
