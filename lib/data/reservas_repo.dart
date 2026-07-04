import 'package:supabase_flutter/supabase_flutter.dart' show PostgrestException;

import '../models/models.dart';
import '../services/supabase_service.dart';

/// Resultado de intentar reservar un slot. [ocupado] = otro jugador ganó el
/// mismo (cancha, fecha, hora) — el constraint UNIQUE de Supabase lo rechazó.
enum ResultadoReserva { ok, ocupado, sinConexion, error }

/// Acceso a reservas en Supabase (tabla `pichangol_reservas`). Fail-safe:
/// si Supabase no está disponible o falla, no rompe la app (queda local).
///
/// Las reservas se guardan globales para que la disponibilidad de horarios se
/// comparta entre dispositivos; "Mis reservas" se filtra por correo en la app.
///
/// Anti-doble-reserva: la tabla debe tener
/// `UNIQUE (cancha_id, fecha, hora_inicio)`. Cuando dos jugadores piden el mismo
/// slot, el segundo INSERT viola el UNIQUE (código Postgres 23505) y devolvemos
/// [ResultadoReserva.ocupado] — la fuente de verdad es la base, no el dispositivo.
class ReservasRepo {
  static const _tabla = 'pichangol_reservas';

  static Future<List<Reserva>> fetchRemotas() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client.from(_tabla).select();
      return (rows as List)
          .map((r) => _fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Inserta una reserva validando el slot contra el constraint UNIQUE. Es el
  /// camino que da garantía real anti-doble-reserva entre dispositivos.
  static Future<ResultadoReserva> insertarSegura(Reserva r) async {
    if (!SupabaseService.disponible) return ResultadoReserva.sinConexion;
    try {
      await SupabaseService.client.from(_tabla).insert(_toRow(r));
      return ResultadoReserva.ok;
    } on PostgrestException catch (e) {
      // 23505 = unique_violation → el slot ya estaba tomado.
      if (e.code == '23505') return ResultadoReserva.ocupado;
      return ResultadoReserva.error;
    } catch (_) {
      return ResultadoReserva.error;
    }
  }

  /// Insert best-effort (sin reportar colisión). Se mantiene por compatibilidad;
  /// para reservar usar [insertarSegura].
  static Future<void> insertar(Reserva r) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).insert(_toRow(r));
    } catch (_) {}
  }

  /// Elimina TODAS las reservas de una cancha (p. ej. cuando el admin rechaza/
  /// revoca la cancha y deja de ser reservable). Libera los slots. Fail-safe.
  static Future<void> eliminarDeCancha(String canchaId) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .delete()
          .eq('cancha_id', canchaId);
    } catch (_) {}
  }

  /// Actualiza una reserva existente (estado / pago) por id. Fail-safe.
  static Future<void> actualizar(Reserva r) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update(_toRow(r))
          .eq('id', r.id);
    } catch (_) {}
  }

  static Map<String, dynamic> _toRow(Reserva r) => {
        'id': r.id,
        'cancha_id': r.canchaId,
        'jugador': r.jugador,
        'nivel': r.nivel,
        'fecha': r.fecha,
        'dia': r.dia,
        'hora_inicio': r.horaInicio,
        'hora_fin': r.horaFin,
        'estado': r.estado.name,
        'traida_por_app': r.traidaPorApp,
        'precio': r.precio,
        'sena': r.sena,
        'pagado': r.pagado,
        'usuario': r.usuario,
      };

  static Reserva _fromRow(Map<String, dynamic> r) => Reserva(
        id: r['id'].toString(),
        canchaId: (r['cancha_id'] ?? '').toString(),
        jugador: (r['jugador'] ?? 'Jugador') as String,
        nivel: (r['nivel'] ?? '') as String,
        fecha: (r['fecha'] ?? '') as String,
        dia: (r['dia'] ?? 'Hoy') as String,
        horaInicio: (r['hora_inicio'] ?? '') as String,
        horaFin: (r['hora_fin'] ?? '') as String,
        estado: _estado(r['estado'] as String?),
        traidaPorApp: (r['traida_por_app'] ?? true) as bool,
        precio: ((r['precio'] ?? 0) as num).toInt(),
        sena: ((r['sena'] ?? 0) as num).toInt(),
        pagado: (r['pagado'] ?? false) as bool,
        usuario: (r['usuario'] ?? '') as String,
      );

  static EstadoReserva _estado(String? s) {
    for (final e in EstadoReserva.values) {
      if (e.name == s) return e;
    }
    return EstadoReserva.confirmada;
  }
}
