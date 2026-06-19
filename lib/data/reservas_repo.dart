import '../models/models.dart';
import '../services/supabase_service.dart';

/// Acceso a reservas en Supabase (tabla `pichangol_reservas`). Fail-safe:
/// si Supabase no está disponible o falla, no rompe la app (queda local).
///
/// Las reservas se guardan globales para que la disponibilidad de horarios se
/// comparta entre dispositivos; "Mis reservas" se filtra por correo en la app.
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

  static Future<void> insertar(Reserva r) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).insert(_toRow(r));
    } catch (_) {}
  }

  static Map<String, dynamic> _toRow(Reserva r) => {
        'id': r.id,
        'cancha_id': r.canchaId,
        'jugador': r.jugador,
        'nivel': r.nivel,
        'dia': r.dia,
        'hora_inicio': r.horaInicio,
        'hora_fin': r.horaFin,
        'estado': r.estado.name,
        'traida_por_app': r.traidaPorApp,
        'precio': r.precio,
        'sena': r.sena,
        'usuario': r.usuario,
      };

  static Reserva _fromRow(Map<String, dynamic> r) => Reserva(
        id: r['id'].toString(),
        canchaId: (r['cancha_id'] ?? '').toString(),
        jugador: (r['jugador'] ?? 'Jugador') as String,
        nivel: (r['nivel'] ?? '') as String,
        dia: (r['dia'] ?? 'Hoy') as String,
        horaInicio: (r['hora_inicio'] ?? '') as String,
        horaFin: (r['hora_fin'] ?? '') as String,
        estado: _estado(r['estado'] as String?),
        traidaPorApp: (r['traida_por_app'] ?? true) as bool,
        precio: ((r['precio'] ?? 0) as num).toInt(),
        sena: ((r['sena'] ?? 0) as num).toInt(),
        usuario: (r['usuario'] ?? '') as String,
      );

  static EstadoReserva _estado(String? s) {
    for (final e in EstadoReserva.values) {
      if (e.name == s) return e;
    }
    return EstadoReserva.confirmada;
  }
}
