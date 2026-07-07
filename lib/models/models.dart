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
  futbol('Fútbol'),
  pickleball('Pickleball');

  final String etiqueta;
  const Deporte(this.etiqueta);
}

/// Deportes que la app OFRECE al usuario (selectores, filtros, secciones).
/// Pádel se retiró del piloto: sigue en el enum para no romper datos antiguos
/// al cargarlos, pero no se muestra ni se puede elegir. Foco: fútbol y tenis.
const List<Deporte> deportesActivos = [
  Deporte.futbol,
  Deporte.tenis,
  Deporte.pickleball,
];

/// Una cancha en el marketplace.
class Cancha {
  final String id;
  final String nombre;
  final String club;
  final Distrito distrito;
  final Deporte deporte;
  final double precioHora; // soles por hora (admite 2 decimales)
  final LatLng ubicacion;
  final bool clubFundador; // sello "Club Fundador" de su distrito
  final bool digitalizada; // false = aún en cuaderno/WhatsApp (objetivo prioritario)
  final String? direccion; // dirección real (texto), si se registró por dirección
  final bool registrada; // false = descubierta (Google Places), aún no en Pichangol
  final String? fotoUrl; // foto de portada (= primera de la galería)
  final List<String> fotos; // galería de fotos (URLs en Supabase Storage)
  final String dueno; // correo del dueño (para "Mis canchas" entre dispositivos)
  final bool verificada; // true = propiedad verificada; false = reclamo pendiente
  final String horaApertura; // inicio de atención, ej. "07:00"
  final String horaCierre; // fin de atención, ej. "23:00"
  final int duracionSlotMin; // duración del bloque reservable (60 / 90 / 120 min)
  final bool eliminada; // borrado lógico durable en la nube (sobrevive reinstalar)
  final List<String> amenidades; // claves de servicios (vestuario, parking…), editable por el dueño
  final String superficie; // tipo de piso: arcilla, loza, grass sintético… (según deporte)

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
    this.dueno = '',
    this.verificada = true,
    this.horaApertura = '07:00',
    this.horaCierre = '23:00',
    this.duracionSlotMin = 60,
    this.eliminada = false,
    this.amenidades = const [],
    this.superficie = '',
  });

  /// Se puede reservar online solo si está en Pichangol y su propiedad fue
  /// verificada (evita reservas en canchas reclamadas por alguien sin validar).
  bool get reservable => registrada && verificada;

  /// Reclamada/registrada pero aún sin verificar la propiedad del dueño.
  bool get pendienteVerificacion => registrada && !verificada;

  /// Precio referencial por hora (S/). Si la cancha ya fue reclamada usa su
  /// precio real; si es descubierta (Google, aún sin precio) estima según el
  /// deporte para mostrar un número en el mapa en vez de un texto genérico.
  double get precioReferencial {
    if (precioHora > 0) return precioHora;
    switch (deporte) {
      case Deporte.futbol:
        return 120;
      case Deporte.padel:
        return 90;
      case Deporte.tenis:
        return 70;
      case Deporte.pickleball:
        return 80;
    }
  }

  /// Horas de INICIO reservables entre apertura y cierre, en pasos de
  /// [duracionSlotMin]. Ej. apertura 07:00, cierre 23:00, slot 90 min →
  /// 07:00, 08:30, 10:00, … Solo se incluye un slot si cabe completo antes
  /// del cierre. Fuente de la grilla que ve el jugador (reemplaza el array fijo).
  ///
  /// Si se pasa [desdeMinutos] (minutos desde medianoche), se omiten los slots
  /// cuyo inicio ya pasó — se usa para el día de HOY, para no ofrecer horas
  /// pasadas.
  List<String> horariosSlots({int? desdeMinutos}) {
    final ini = horaEnMinutos(horaApertura);
    final fin = horaEnMinutos(horaCierre);
    final paso = duracionSlotMin <= 0 ? 60 : duracionSlotMin;
    if (ini == null || fin == null || fin <= ini) return const [];
    final slots = <String>[];
    for (var m = ini; m + paso <= fin; m += paso) {
      if (desdeMinutos != null && m < desdeMinutos) continue; // ya pasó
      slots.add(minutosEnHora(m));
    }
    return slots;
  }

  /// Hora de fin de un slot que arranca en [inicio] (= inicio + duración).
  String horaFinDe(String inicio) {
    final m = horaEnMinutos(inicio);
    if (m == null) return inicio;
    final paso = duracionSlotMin <= 0 ? 60 : duracionSlotMin;
    return minutosEnHora(m + paso);
  }

  Cancha copyWith({
    String? nombre,
    String? club,
    Distrito? distrito,
    Deporte? deporte,
    double? precioHora,
    LatLng? ubicacion,
    String? direccion,
    bool? registrada,
    String? fotoUrl,
    List<String>? fotos,
    String? dueno,
    bool? verificada,
    String? horaApertura,
    String? horaCierre,
    int? duracionSlotMin,
    bool? eliminada,
    List<String>? amenidades,
    String? superficie,
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
      registrada: registrada ?? this.registrada,
      fotoUrl: fotoUrl ?? this.fotoUrl,
      fotos: fotos ?? this.fotos,
      dueno: dueno ?? this.dueno,
      verificada: verificada ?? this.verificada,
      horaApertura: horaApertura ?? this.horaApertura,
      horaCierre: horaCierre ?? this.horaCierre,
      duracionSlotMin: duracionSlotMin ?? this.duracionSlotMin,
      eliminada: eliminada ?? this.eliminada,
      amenidades: amenidades ?? this.amenidades,
      superficie: superficie ?? this.superficie,
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
        'dueno': dueno,
        'verificada': verificada,
        'horaApertura': horaApertura,
        'horaCierre': horaCierre,
        'duracionSlotMin': duracionSlotMin,
        'eliminada': eliminada,
        'amenidades': amenidades,
        'superficie': superficie,
      };

  factory Cancha.fromJson(Map<String, dynamic> j) => Cancha(
        id: j['id'] as String,
        nombre: j['nombre'] as String,
        club: j['club'] as String,
        distrito: Distrito.values.byName(j['distrito'] as String),
        deporte: Deporte.values.byName(j['deporte'] as String),
        precioHora: (j['precioHora'] as num).toDouble(),
        ubicacion: LatLng(
            (j['lat'] as num).toDouble(), (j['lng'] as num).toDouble()),
        clubFundador: j['clubFundador'] as bool,
        digitalizada: j['digitalizada'] as bool,
        direccion: j['direccion'] as String?,
        registrada: (j['registrada'] ?? true) as bool,
        fotoUrl: j['fotoUrl'] as String?,
        fotos: (j['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        dueno: (j['dueno'] ?? '') as String,
        verificada: (j['verificada'] ?? true) as bool,
        horaApertura: (j['horaApertura'] ?? '07:00') as String,
        horaCierre: (j['horaCierre'] ?? '23:00') as String,
        duracionSlotMin: ((j['duracionSlotMin'] ?? 60) as num).toInt(),
        eliminada: (j['eliminada'] ?? false) as bool,
        amenidades: (j['amenidades'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        superficie: (j['superficie'] ?? '') as String,
      );
}

/// Convierte "HH:MM" a minutos desde medianoche (null si no parsea).
int? horaEnMinutos(String hhmm) {
  final partes = hhmm.split(':');
  if (partes.length < 2) return null;
  final h = int.tryParse(partes[0]);
  final m = int.tryParse(partes[1]);
  if (h == null || m == null) return null;
  return h * 60 + m;
}

/// Convierte minutos desde medianoche a "HH:MM".
String minutosEnHora(int min) {
  final h = (min ~/ 60).toString().padLeft(2, '0');
  final m = (min % 60).toString().padLeft(2, '0');
  return '$h:$m';
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
  final String fecha; // fuente de verdad del día reservado, ISO "2026-06-27"
  final String dia; // etiqueta visible ("Hoy", "Mañana", "Lun 22")
  final String horaInicio; // "07:00"
  final String horaFin; // "08:00"
  final EstadoReserva estado;
  final bool traidaPorApp; // true = reserva nueva (genera comisión en Fase 2)
  final int precio;
  final int sena; // monto de seña/garantía con tarjeta (anti no-show)
  final bool pagado; // el dueño confirmó el pago (efectivo en cancha)
  final String usuario; // correo del jugador (para "mis reservas" entre dispositivos)

  const Reserva({
    required this.id,
    required this.canchaId,
    required this.jugador,
    required this.nivel,
    this.fecha = '',
    required this.dia,
    required this.horaInicio,
    required this.horaFin,
    required this.estado,
    required this.traidaPorApp,
    required this.precio,
    required this.sena,
    this.pagado = false,
    this.usuario = '',
  });

  Reserva copyWith({EstadoReserva? estado, bool? pagado}) => Reserva(
        id: id,
        canchaId: canchaId,
        jugador: jugador,
        nivel: nivel,
        fecha: fecha,
        dia: dia,
        horaInicio: horaInicio,
        horaFin: horaFin,
        estado: estado ?? this.estado,
        traidaPorApp: traidaPorApp,
        precio: precio,
        sena: sena,
        pagado: pagado ?? this.pagado,
        usuario: usuario,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'canchaId': canchaId,
        'jugador': jugador,
        'nivel': nivel,
        'fecha': fecha,
        'dia': dia,
        'horaInicio': horaInicio,
        'horaFin': horaFin,
        'estado': estado.name,
        'traidaPorApp': traidaPorApp,
        'precio': precio,
        'sena': sena,
        'pagado': pagado,
        'usuario': usuario,
      };

  factory Reserva.fromJson(Map<String, dynamic> j) => Reserva(
        id: j['id'] as String,
        canchaId: j['canchaId'] as String,
        jugador: j['jugador'] as String,
        nivel: j['nivel'] as String,
        fecha: (j['fecha'] ?? '') as String,
        dia: j['dia'] as String,
        horaInicio: j['horaInicio'] as String,
        horaFin: j['horaFin'] as String,
        estado: EstadoReserva.values.byName(j['estado'] as String),
        traidaPorApp: j['traidaPorApp'] as bool,
        precio: j['precio'] as int,
        sena: j['sena'] as int,
        pagado: (j['pagado'] ?? false) as bool,
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
