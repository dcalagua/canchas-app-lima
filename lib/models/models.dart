import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Distritos del piloto (densidad geográfica antes que cobertura amplia).
enum Distrito {
  sanBorja('San Borja'),
  surco('Surco'),
  laMolina('La Molina');

  final String etiqueta;
  const Distrito(this.etiqueta);
}

enum Deporte {
  tenis('Tenis'),
  padel('Pádel');

  final String etiqueta;
  const Deporte(this.etiqueta);
}

/// Una cancha en el marketplace.
class Cancha {
  final String id;
  final String nombre;
  final String club;
  final Distrito distrito;
  final Deporte deporte;
  final int precioHora; // soles por hora
  final LatLng ubicacion;
  final bool clubFundador; // sello "Club Fundador" de su distrito
  final bool digitalizada; // false = aún en cuaderno/WhatsApp (objetivo prioritario)

  const Cancha({
    required this.id,
    required this.nombre,
    required this.club,
    required this.distrito,
    required this.deporte,
    required this.precioHora,
    required this.ubicacion,
    required this.clubFundador,
    required this.digitalizada,
  });
}

enum EstadoReserva {
  nueva('Nueva'), // entró por la app, sin confirmar
  confirmada('Confirmada'), // seña pagada
  completada('Completada'),
  noShow('No-show');

  final String etiqueta;
  const EstadoReserva(this.etiqueta);
}

/// Una reserva. [traidaPorApp] distingue una reserva NUEVA de un cliente de siempre.
class Reserva {
  final String id;
  final String canchaId;
  final String jugador;
  final String nivel; // ej. "Intermedio 3.5" (ángulo social / por nivel)
  final String dia; // ej. "Hoy", "Mañana", "Lun 22"
  final String horaInicio; // "07:00"
  final String horaFin; // "08:00"
  final EstadoReserva estado;
  final bool traidaPorApp; // true = reserva nueva (genera comisión en Fase 2)
  final int precio;
  final int sena; // monto de seña/garantía con tarjeta (anti no-show)

  const Reserva({
    required this.id,
    required this.canchaId,
    required this.jugador,
    required this.nivel,
    required this.dia,
    required this.horaInicio,
    required this.horaFin,
    required this.estado,
    required this.traidaPorApp,
    required this.precio,
    required this.sena,
  });
}

/// Un bloque horario de una cancha en la agenda de hoy.
class BloqueHorario {
  final String canchaId;
  final String hora; // "07:00"
  final bool esHoraValle; // mañanas / inicios de semana = el oro de la Fase 1
  final bool disponible; // el dueño la abrió en la app
  final String? reservaId; // ocupada si != null

  const BloqueHorario({
    required this.canchaId,
    required this.hora,
    required this.esHoraValle,
    required this.disponible,
    this.reservaId,
  });

  BloqueHorario copyWith({bool? disponible, String? reservaId, bool limpiarReserva = false}) {
    return BloqueHorario(
      canchaId: canchaId,
      hora: hora,
      esHoraValle: esHoraValle,
      disponible: disponible ?? this.disponible,
      reservaId: limpiarReserva ? null : (reservaId ?? this.reservaId),
    );
  }
}

/// Movimiento del saldo prepago del club (modelo estilo inDrive).
enum TipoMovimiento { recarga, consumo }

class MovimientoSaldo {
  final TipoMovimiento tipo;
  final int monto; // soles
  final String concepto;
  final String cuando; // etiqueta simple ("Ahora", "Hoy", etc.)

  const MovimientoSaldo({
    required this.tipo,
    required this.monto,
    required this.concepto,
    required this.cuando,
  });
}
