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
  padel('Pádel'),
  futbol('Fútbol');

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
  final String? direccion; // dirección real (texto), si se registró por dirección
  final bool registrada; // false = descubierta (Google Places), aún no en Pichangol
  final String? fotoUrl; // foto de portada (= primera de la galería)
  final List<String> fotos; // galería de fotos (URLs en Supabase Storage)

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
    this.direccion,
    this.registrada = true,
    this.fotoUrl,
    this.fotos = const [],
  });

  /// Precio referencial por hora (S/). Si la cancha ya fue reclamada usa su
  /// precio real; si es descubierta (Google, aún sin precio) estima según el
  /// deporte para mostrar un número en el mapa en vez de un texto genérico.
  int get precioReferencial {
    if (precioHora > 0) return precioHora;
    switch (deporte) {
      case Deporte.futbol:
        return 120;
      case Deporte.padel:
        return 90;
      case Deporte.tenis:
        return 70;
    }
  }

  Cancha copyWith({
    String? nombre,
    String? club,
    Distrito? distrito,
    Deporte? deporte,
    int? precioHora,
    LatLng? ubicacion,
    String? direccion,
    String? fotoUrl,
    List<String>? fotos,
  }) {
    return Cancha(
      id: id,
      nombre: nombre ?? this.nombre,
      club: club ?? this.club,
      distrito: distrito ?? this.distrito,
      deporte: deporte ?? this.deporte,
      precioHora: precioHora ?? this.precioHora,
      ubicacion: ubicacion ?? this.ubicacion,
      clubFundador: clubFundador,
      digitalizada: digitalizada,
      direccion: direccion ?? this.direccion,
      registrada: registrada,
      fotoUrl: fotoUrl ?? this.fotoUrl,
      fotos: fotos ?? this.fotos,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'club': club,
        'distrito': distrito.name,
        'deporte': deporte.name,
        'precioHora': precioHora,
        'lat': ubicacion.latitude,
        'lng': ubicacion.longitude,
        'clubFundador': clubFundador,
        'digitalizada': digitalizada,
        'direccion': direccion,
        'registrada': registrada,
        'fotoUrl': fotoUrl,
        'fotos': fotos,
      };

  factory Cancha.fromJson(Map<String, dynamic> j) => Cancha(
        id: j['id'] as String,
        nombre: j['nombre'] as String,
        club: j['club'] as String,
        distrito: Distrito.values.byName(j['distrito'] as String),
        deporte: Deporte.values.byName(j['deporte'] as String),
        precioHora: j['precioHora'] as int,
        ubicacion: LatLng(
            (j['lat'] as num).toDouble(), (j['lng'] as num).toDouble()),
        clubFundador: j['clubFundador'] as bool,
        digitalizada: j['digitalizada'] as bool,
        direccion: j['direccion'] as String?,
        registrada: (j['registrada'] ?? true) as bool,
        fotoUrl: j['fotoUrl'] as String?,
        fotos: (j['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
      );
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
  final String usuario; // correo del jugador (para "mis reservas" entre dispositivos)

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
    this.usuario = '',
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'canchaId': canchaId,
        'jugador': jugador,
        'nivel': nivel,
        'dia': dia,
        'horaInicio': horaInicio,
        'horaFin': horaFin,
        'estado': estado.name,
        'traidaPorApp': traidaPorApp,
        'precio': precio,
        'sena': sena,
        'usuario': usuario,
      };

  factory Reserva.fromJson(Map<String, dynamic> j) => Reserva(
        id: j['id'] as String,
        canchaId: j['canchaId'] as String,
        jugador: j['jugador'] as String,
        nivel: j['nivel'] as String,
        dia: j['dia'] as String,
        horaInicio: j['horaInicio'] as String,
        horaFin: j['horaFin'] as String,
        estado: EstadoReserva.values.byName(j['estado'] as String),
        traidaPorApp: j['traidaPorApp'] as bool,
        precio: j['precio'] as int,
        sena: j['sena'] as int,
        usuario: (j['usuario'] ?? '') as String,
      );
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

  Map<String, dynamic> toJson() =>
      {'tipo': tipo.name, 'monto': monto, 'concepto': concepto, 'cuando': cuando};

  factory MovimientoSaldo.fromJson(Map<String, dynamic> j) => MovimientoSaldo(
        tipo: TipoMovimiento.values.byName(j['tipo'] as String),
        monto: j['monto'] as int,
        concepto: j['concepto'] as String,
        cuando: j['cuando'] as String,
      );
}
