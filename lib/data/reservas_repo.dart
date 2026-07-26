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
      // 42703 = columna inexistente (p. ej. `deporte` aún sin migrar en la BD):
      // reintenta sin ella para NO perder la garantía anti-doble-reserva.
      if (_columnaFaltante(e)) {
        try {
          await SupabaseService.client
              .from(_tabla)
              .insert(_toRow(r, conDeporte: false));
          return ResultadoReserva.ok;
        } on PostgrestException catch (e2) {
          return e2.code == '23505'
              ? ResultadoReserva.ocupado
              : ResultadoReserva.error;
        } catch (_) {
          return ResultadoReserva.error;
        }
      }
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
    } catch (_) {
      try {
        await SupabaseService.client
            .from(_tabla)
            .insert(_toRow(r, conDeporte: false));
      } catch (_) {}
    }
  }

  /// ¿El error es por columna inexistente en la tabla? (42703 undefined_column).
  static bool _columnaFaltante(PostgrestException e) =>
      e.code == '42703' ||
      (e.message.toLowerCase().contains('column') &&
          e.message.toLowerCase().contains('deporte'));

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

  /// Elimina UNA reserva por id (p. ej. el jugador la cancela). Libera el slot
  /// borrando la fila, así el UNIQUE(cancha, fecha, hora) queda libre y el
  /// horario vuelve a estar disponible. Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
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
    } catch (_) {
      try {
        await SupabaseService.client
            .from(_tabla)
            .update(_toRow(r, conDeporte: false))
            .eq('id', r.id);
      } catch (_) {}
    }
  }

  static Map<String, dynamic> _toRow(Reserva r, {bool conDeporte = true}) => {
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
        // Columnas nuevas: deporte del slot (loza multiuso) + moneda de la
        // cancha + servicios extra elegidos (árbitro/pelotero…, JSONB).
        if (conDeporte) 'deporte': r.deporte,
        if (conDeporte) 'moneda': r.moneda,
        if (conDeporte) 'extras': r.extras.map((s) => s.toJson()).toList(),
        // Teléfono del cliente en reservas manuales del dueño (columna nueva;
        // va bajo el mismo guard para no romper si aún no se corrió el ALTER).
        if (conDeporte && r.telefono.isNotEmpty) 'telefono': r.telefono,
        // Grupo de una reserva de varias horas seguidas (columna nueva; mismo
        // guard para no romper si aún no se corrió el ALTER en Supabase).
        if (conDeporte && r.grupoReservaId.isNotEmpty)
          'grupo_reserva_id': r.grupoReservaId,
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
        deporte: (r['deporte'] ?? '') as String,
        moneda: (r['moneda'] ?? '') as String,
        extras: ServicioExtra.listaDe(r['extras']),
        telefono: (r['telefono'] ?? '') as String,
        grupoReservaId: (r['grupo_reserva_id'] ?? '') as String,
      );

  static EstadoReserva _estado(String? s) {
    for (final e in EstadoReserva.values) {
      if (e.name == s) return e;
    }
    return EstadoReserva.confirmada;
  }
}
