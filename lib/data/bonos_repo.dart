import '../models/bono.dart';
import '../services/supabase_service.dart';

/// Bonos de horas prepagadas en Supabase (`pichangol_bonos` = ofertas del dueño,
/// `pichangol_bonos_comprados` = créditos del jugador). Fail-safe: sin backend,
/// devuelve vacío y las escrituras fallan en silencio (la UI lo maneja).
class BonosRepo {
  static const _tablaOf = 'pichangol_bonos';
  static const _tablaComp = 'pichangol_bonos_comprados';

  static bool get disponible => SupabaseService.disponible;

  // ── Ofertas (dueño) ────────────────────────────────────────────────────────

  /// Ofertas ACTIVAS de un local (lo que ve el jugador).
  static Future<List<BonoOferta>> ofertasDeClub(String club) async {
    if (!disponible || club.isEmpty) return const <BonoOferta>[];
    try {
      final rows = await SupabaseService.client
          .from(_tablaOf)
          .select()
          .eq('club', club)
          .eq('activo', true)
          .order('horas', ascending: true);
      return (rows as List)
          .map((r) => BonoOferta.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <BonoOferta>[];
    }
  }

  /// TODAS las ofertas del dueño (activas o no), para administrarlas.
  static Future<List<BonoOferta>> ofertasDeDueno(String dueno) async {
    final e = dueno.trim().toLowerCase();
    if (!disponible || e.isEmpty) return const <BonoOferta>[];
    try {
      final rows = await SupabaseService.client
          .from(_tablaOf)
          .select()
          .eq('dueno', e)
          .order('creado', ascending: false);
      return (rows as List)
          .map((r) => BonoOferta.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <BonoOferta>[];
    }
  }

  /// Crea o edita una oferta (upsert por id). Devuelve true si se guardó.
  static Future<bool> guardarOferta(BonoOferta b) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tablaOf).upsert(b.toRow());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Elimina una oferta (el dueño la retira). Best-effort.
  static Future<void> eliminarOferta(String id) async {
    if (!disponible || id.isEmpty) return;
    try {
      await SupabaseService.client.from(_tablaOf).delete().eq('id', id);
    } catch (_) {}
  }

  // ── Créditos comprados (jugador) ────────────────────────────────────────────

  /// Créditos comprados por un jugador (todos los locales), recientes primero.
  static Future<List<BonoComprado>> comprasDe(String comprador) async {
    final e = comprador.trim().toLowerCase();
    if (!disponible || e.isEmpty) return const <BonoComprado>[];
    try {
      final rows = await SupabaseService.client
          .from(_tablaComp)
          .select()
          .eq('comprador', e)
          .order('creado', ascending: false);
      return (rows as List)
          .map((r) => BonoComprado.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <BonoComprado>[];
    }
  }

  /// Créditos comprados en los locales de un dueño (para que vea sus ventas).
  static Future<List<BonoComprado>> comprasDeDueno(String dueno) async {
    final e = dueno.trim().toLowerCase();
    if (!disponible || e.isEmpty) return const <BonoComprado>[];
    try {
      final rows = await SupabaseService.client
          .from(_tablaComp)
          .select()
          .eq('dueno', e)
          .order('creado', ascending: false);
      return (rows as List)
          .map((r) => BonoComprado.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const <BonoComprado>[];
    }
  }

  /// Registra la compra de un bono (tras el pago). Upsert por id (idempotente).
  static Future<bool> registrarCompra(BonoComprado c) async {
    if (!disponible) return false;
    try {
      await SupabaseService.client.from(_tablaComp).upsert(c.toRow());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Actualiza las horas usadas de un crédito (canje). Best-effort.
  static Future<bool> actualizarUsadas(String id, int horasUsadas) async {
    if (!disponible || id.isEmpty) return false;
    try {
      await SupabaseService.client
          .from(_tablaComp)
          .update({'horas_usadas': horasUsadas}).eq('id', id);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra ofertas y créditos de un dueño (para "Dejar en virgen").
  static Future<void> eliminarDeDueno(String dueno) async {
    final e = dueno.trim().toLowerCase();
    if (!disponible || e.isEmpty) return;
    try {
      await SupabaseService.client.from(_tablaOf).delete().eq('dueno', e);
      await SupabaseService.client.from(_tablaComp).delete().eq('dueno', e);
    } catch (_) {}
  }
}
