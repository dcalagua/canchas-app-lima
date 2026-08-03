import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';

/// Clasificación GRUESA heredada del piloto de Lima. Ya NO se muestra al usuario
/// directamente: la zona visible es [Cancha.zonaMostrable], que usa el barrio
/// real (reverse-geocode) y cae a esta etiqueta solo si aún no hay barrio (datos
/// viejos). Se conserva por compatibilidad de datos, no como fuente de display.
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
  pickleball('Pickleball'),
  voley('Vóley'),
  basquet('Básquet'),
  natacion('Natación');

  final String etiqueta;
  const Deporte(this.etiqueta);

  /// Deportes de RAQUETA. El CIRCUITO Pichangol (ranking, retos, Pro, jugadores
  /// disponibles) es hoy una capa de TENIS para fortalecer academias, y aplica a
  /// deportes de raqueta. El fútbol (y otros) usan solo reservar + partidos; su
  /// circuito será otro tema más adelante.
  bool get esRaqueta =>
      this == Deporte.tenis ||
      this == Deporte.padel ||
      this == Deporte.pickleball;
}

/// Deportes con CIRCUITO (raqueta). Ver `Deporte.esRaqueta`.
const List<Deporte> deportesCircuito = [
  Deporte.tenis,
  Deporte.padel,
  Deporte.pickleball,
];

/// Parsea un nombre de `Deporte` de forma segura (null si no existe, p. ej. un
/// valor viejo/desconocido en datos persistidos). Evita que `byName` reviente.
Deporte? deportePorNombre(String? s) {
  for (final d in Deporte.values) {
    if (d.name == s) return d;
  }
  return null;
}

/// Deportes que la app OFRECE al usuario (selectores, filtros, secciones).
/// Pádel se retiró del piloto: sigue en el enum para no romper datos antiguos
/// al cargarlos, pero no se muestra ni se puede elegir. Muchos locales alquilan
/// también vóley y básquet (misma loza multiuso), por eso entran al catálogo.
const List<Deporte> deportesActivos = [
  Deporte.futbol,
  Deporte.tenis,
  Deporte.pickleball,
  Deporte.voley,
  Deporte.basquet,
];

/// Deportes ofrecibles al crear una ACADEMIA. Incluye natación (disciplina de
/// academia/clases, no de cancha reservable), por eso va aparte de
/// [deportesActivos] (que alimenta filtros de canchas y registro de canchas).
const List<Deporte> deportesAcademia = [
  Deporte.futbol,
  Deporte.tenis,
  Deporte.pickleball,
  Deporte.voley,
  Deporte.basquet,
  Deporte.natacion,
];

/// Un servicio EXTRA de pago que una cancha ofrece como add-on de la reserva
/// (árbitro, pelotero, alquiler de pelota, pecheras…). El jugador los elige al
/// reservar y suman al total; el dueño los ve en sus cobros. Distinto de
/// `amenidades` (servicios GRATIS del local, sin precio).
class ServicioExtra {
  final String clave;
  final double precio;
  const ServicioExtra({required this.clave, required this.precio});

  /// Catálogo de servicios ofrecibles: clave → nombre visible. El ícono se
  /// resuelve en la UI (el modelo no depende de Flutter/material).
  static const catalogo = <String, String>{
    'arbitro': 'Árbitro',
    'pelotero': 'Pelotero (recoge pelotas)',
    'pelota': 'Alquiler de pelota',
    'pecheras': 'Petos / pecheras',
    'hidratacion': 'Hidratación',
    'parrilla': 'Parrilla / grill',
  };

  String get nombre => catalogo[clave] ?? clave;

  ServicioExtra copyWith({double? precio}) =>
      ServicioExtra(clave: clave, precio: precio ?? this.precio);

  Map<String, dynamic> toJson() => {'clave': clave, 'precio': precio};

  factory ServicioExtra.fromJson(Map<String, dynamic> j) => ServicioExtra(
        clave: (j['clave'] ?? '').toString(),
        precio: ((j['precio'] ?? 0) as num).toDouble(),
      );

  static List<ServicioExtra> listaDe(dynamic raw) {
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((e) => ServicioExtra.fromJson(Map<String, dynamic>.from(e)))
        .where((s) => s.clave.isNotEmpty)
        .toList();
  }
}

/// Una cancha en el marketplace.
class Cancha {
  final String id;
  final String nombre;
  final String club;
  final Distrito distrito;
  /// Barrio/zona REAL de la cancha (ej. "Sopocachi", "Equipetrol", "San Borja"),
  /// obtenido del reverse-geocode de sus coordenadas al registrarla. Es la zona
  /// que ve el usuario en cualquier país. Vacío = dato viejo o cancha descubierta
  /// → NO se muestra zona (la dirección real va aparte). Usar [zonaMostrable].
  final String barrio;
  final Deporte deporte; // deporte PRINCIPAL (ícono/color/categoría en el mapa)
  /// Todos los deportes que se pueden jugar en ESTA cancha (loza multiuso). Si
  /// está vacío, se asume que solo ofrece [deporte] (compat. con datos viejos).
  /// La agenda es COMPARTIDA: reservar un slot ocupa la cancha para todos los
  /// deportes (es la misma superficie física). Usar el getter [deportesJugables].
  final List<Deporte> deportes;
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
  /// Símbolo de moneda de ESTA cancha, congelado al registrarla según el país
  /// donde se creó ('S/' Perú, 'Bs' Bolivia…). El precio vive en esta moneda: no
  /// cambia aunque el dueño abra la app desde otro país. Vacío = 'S/' (todas las
  /// canchas del piloto nacieron en Perú). Usar el getter [monedaSimbolo].
  final String moneda;
  /// Servicios EXTRA de pago que ofrece la cancha (árbitro, pelotero…). El
  /// jugador los agrega al reservar. Vacío = la cancha no ofrece ninguno.
  final List<ServicioExtra> serviciosExtra;
  /// "Hora feliz": descuento (%) que aplica el dueño a las horas VALLE (mañanas)
  /// para llenar cancha vacía. 0 = sin descuento. Gana el dueño (más ocupación)
  /// y el jugador (más barato).
  final int descuentoValle;

  /// SEÑA anti no-show: % del precio que el jugador paga por adelantado (Culqi)
  /// al reservar para GARANTIZAR el slot. 0 = sin seña (reserva sin adelanto).
  /// Es NO REEMBOLSABLE: si el jugador no se presenta, el dueño se queda la seña.
  /// El resto se paga en la cancha. Configurable por el dueño en "Editar cancha".
  final int senaPct;

  /// ¿Esta cancha exige seña al reservar? (dueño la configuró > 0).
  bool get exigeSena => senaPct > 0;

  /// Monto de la seña (redondeado) para un precio de slot dado.
  int senaDe(int precioSlot) =>
      senaPct <= 0 ? 0 : (precioSlot * senaPct.clamp(0, 100) / 100).round();

  /// ¿Una hora ("07:00") cae en el valle (mañana)? Regla simple: antes de mediodía.
  static bool horaEsValle(String hora) => hora.compareTo('12:00') < 0;

  /// Precio efectivo por hora en un horario dado (aplica el descuento de hora
  /// feliz si corresponde). Fuente única para mostrar y para cobrar.
  double precioEn(String hora) =>
      (descuentoValle > 0 && horaEsValle(hora))
          ? precioHora * (100 - descuentoValle.clamp(0, 90)) / 100
          : precioHora;

  const Cancha({
    required this.id,
    required this.nombre,
    required this.club,
    required this.distrito,
    this.barrio = '',
    required this.deporte,
    this.deportes = const [],
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
    this.moneda = '',
    this.serviciosExtra = const [],
    this.descuentoValle = 0,
    this.senaPct = 0,
  });

  /// Símbolo de moneda de la cancha. La UBICACIÓN de la cancha es la fuente de
  /// verdad (una cancha en La Paz cobra en Bs, aunque el dueño la registrara
  /// desde Perú): se deriva del país donde caen sus coordenadas. Esto además
  /// auto-corrige canchas viejas que quedaron con la moneda del dispositivo del
  /// dueño. Si por algún motivo no se puede derivar, cae a la moneda congelada
  /// al registrarla y, en última instancia, a 'S/'.
  String get monedaSimbolo =>
      monedaDeCoordenadas(ubicacion.latitude, ubicacion.longitude);

  /// Zona/barrio VISIBLE de la cancha, en cualquier país. Usa SOLO el barrio real
  /// (reverse-geocode de sus coordenadas al registrarla). Si aún no hay barrio
  /// (dato viejo o cancha descubierta de Google), queda **vacío**: NO se inventa
  /// el distrito (`Distrito.sanBorja` es solo un valor referencial y mostrarlo
  /// haría aparecer "San Borja" en canchas que no están ahí). La dirección real
  /// se muestra aparte. Puede quedar vacío: los llamadores deben tolerarlo.
  String get zonaMostrable => barrio.trim();

  /// Deportes jugables en esta cancha, garantizando al menos el principal.
  /// Es la fuente de verdad para filtros/visibilidad (una loza multiuso aparece
  /// en cada deporte que ofrece) y para elegir deporte al reservar.
  List<Deporte> get deportesJugables =>
      deportes.isEmpty ? [deporte] : deportes;

  /// ¿Esta cancha permite jugar [d]? (para filtros por deporte).
  bool ofrece(Deporte d) => deportesJugables.contains(d);

  /// ¿Es una cancha multideporte (loza multiuso con más de un deporte)?
  bool get esMultideporte => deportesJugables.length > 1;

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
      case Deporte.voley:
        return 80;
      case Deporte.basquet:
        return 90;
      case Deporte.natacion:
        return 0; // natación es disciplina de academia, no cancha reservable
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
    var fin = horaEnMinutos(horaCierre);
    final paso = duracionSlotMin <= 0 ? 60 : duracionSlotMin;
    if (ini == null || fin == null) return const [];
    // Cierre que CRUZA MEDIANOCHE: si el cierre es <= apertura, cae al día
    // siguiente. Cubre los 3 casos: "hasta medianoche" (07:00→00:00), cancha
    // nocturna (18:00→02:00) y 24 horas (00:00→00:00). Se le suma un día.
    if (fin <= ini) fin += 24 * 60;
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

  /// ¿El slot [hora] cae en la MADRUGADA del día SIGUIENTE? Pasa cuando el
  /// horario CRUZA medianoche (cierre <= apertura) y la hora del slot es menor
  /// que la apertura (ej. cancha 18:00→02:00: los slots 00:00 y 01:00 son de la
  /// madrugada del día siguiente). Sirve para ligar la reserva a su FECHA
  /// CALENDARIO real (no a la "jornada" elegida).
  bool slotEsMadrugada(String hora) {
    final ap = horaEnMinutos(horaApertura);
    final sl = horaEnMinutos(hora);
    if (ap == null || sl == null) return false;
    return sl < ap;
  }

  /// Fecha ISO ('YYYY-MM-DD') REAL de un slot dado el día base [baseIso]: la
  /// misma, o la del día SIGUIENTE si el slot cruzó medianoche ([slotEsMadrugada]).
  String fechaRealSlot(String baseIso, String hora) {
    if (!slotEsMadrugada(hora)) return baseIso;
    final b = DateTime.tryParse(baseIso);
    if (b == null) return baseIso;
    final d = b.add(const Duration(days: 1));
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  /// ¿La reserva (`rFecha`,`rHora`) pertenece a la SESIÓN de la jornada [baseIso]?
  /// La sesión de un día abarca desde la apertura hasta el cierre, incluida la
  /// MADRUGADA del día siguiente (turnos con hora < apertura viven en baseIso+1).
  /// Se usa en la agenda, que muestra la jornada completa aunque cruce medianoche.
  bool reservaEnSesion(String baseIso, String rFecha, String rHora) =>
      rFecha == fechaRealSlot(baseIso, rHora);

  Cancha copyWith({
    String? nombre,
    String? club,
    Distrito? distrito,
    String? barrio,
    Deporte? deporte,
    List<Deporte>? deportes,
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
    String? moneda,
    List<ServicioExtra>? serviciosExtra,
    int? descuentoValle,
    int? senaPct,
  }) {
    return Cancha(
      id: id,
      nombre: nombre ?? this.nombre,
      club: club ?? this.club,
      distrito: distrito ?? this.distrito,
      barrio: barrio ?? this.barrio,
      deporte: deporte ?? this.deporte,
      deportes: deportes ?? this.deportes,
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
      moneda: moneda ?? this.moneda,
      serviciosExtra: serviciosExtra ?? this.serviciosExtra,
      descuentoValle: descuentoValle ?? this.descuentoValle,
      senaPct: senaPct ?? this.senaPct,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'club': club,
        'distrito': distrito.name,
        'barrio': barrio,
        'deporte': deporte.name,
        'deportes': deportesJugables.map((e) => e.name).toList(),
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
        'moneda': moneda,
        'serviciosExtra': serviciosExtra.map((s) => s.toJson()).toList(),
        'descuentoValle': descuentoValle,
        'senaPct': senaPct,
      };

  factory Cancha.fromJson(Map<String, dynamic> j) => Cancha(
        id: j['id'] as String,
        nombre: j['nombre'] as String,
        club: j['club'] as String,
        distrito: Distrito.values.firstWhere(
            (d) => d.name == j['distrito'],
            orElse: () => Distrito.sanBorja),
        barrio: (j['barrio'] ?? '') as String,
        deporte: Deporte.values.byName(j['deporte'] as String),
        deportes: (j['deportes'] as List?)
                ?.map((e) => deportePorNombre(e.toString()))
                .whereType<Deporte>()
                .toList() ??
            const [],
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
        moneda: (j['moneda'] ?? '') as String,
        serviciosExtra: ServicioExtra.listaDe(j['serviciosExtra']),
        descuentoValle: (j['descuentoValle'] ?? 0) as int,
        senaPct: ((j['senaPct'] ?? 0) as num).toInt(),
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
  // % 24 para envolver el cruce de medianoche: 1440 → '00:00', 1500 → '01:00'
  // (en vez de '24:00'/'25:00'). Así los turnos de madrugada se ven bien.
  final h = ((min ~/ 60) % 24).toString().padLeft(2, '0');
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
  /// Medio de pago: 'tarjeta' | 'yape' (online, ya cobrado por Culqi) |
  /// 'efectivo' (paga en la cancha, el dueño cobra) | 'sena' (adelantó una parte
  /// online y paga el resto en efectivo) | '' (desconocido/legado). Trazabilidad.
  final String medioPago;
  final String usuario; // correo del jugador (para "mis reservas" entre dispositivos)
  final String deporte; // deporte elegido para este slot (Deporte.name); '' = el principal de la cancha
  final String moneda; // símbolo de moneda de la cancha al reservar ('' = 'S/')
  final List<ServicioExtra> extras; // servicios extra elegidos al reservar
  final String telefono; // teléfono del cliente (solo en reservas manuales del dueño)
  // Agrupa las horas de UNA reserva de varias horas seguidas (18:00–20:00 = 2
  // Reservas con el mismo grupo). '' = reserva suelta de una sola hora (legado).
  final String grupoReservaId;

  /// Moneda de la reserva (default 'S/'), congelada de la cancha al reservar.
  String get monedaSimbolo => moneda.isNotEmpty ? moneda : 'S/';

  /// Suma de los servicios extra elegidos (0 si ninguno).
  double get extrasTotal => extras.fold(0.0, (a, s) => a + s.precio);

  /// Total que paga el jugador: precio de la cancha + servicios extra.
  double get totalConExtras => precio + extrasTotal;

  /// La reserva se pagó CANJEANDO un bono de horas prepagadas: el dinero ya
  /// entró (una sola vez) al COMPRAR el bono, no aquí. Por eso NO cuenta como
  /// ingreso fresco en la caja/reportes del día del canje (evita doble conteo).
  bool get esBono => medioPago == 'bono';

  /// Dinero FRESCO que entra por esta reserva el día que ocurre: 0 si se cubrió
  /// con bono (ya cobrado en el paquete), si no el total con extras.
  double get ingresoFresco => esBono ? 0 : totalConExtras;

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
    this.deporte = '',
    this.moneda = '',
    this.extras = const [],
    this.telefono = '',
    this.grupoReservaId = '',
    this.medioPago = '',
  });

  Reserva copyWith({EstadoReserva? estado, bool? pagado, String? medioPago}) =>
      Reserva(
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
        deporte: deporte,
        moneda: moneda,
        extras: extras,
        telefono: telefono,
        grupoReservaId: grupoReservaId,
        medioPago: medioPago ?? this.medioPago,
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
        'deporte': deporte,
        'moneda': moneda,
        'extras': extras.map((s) => s.toJson()).toList(),
        'telefono': telefono,
        'grupoReservaId': grupoReservaId,
        'medioPago': medioPago,
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
        deporte: (j['deporte'] ?? '') as String,
        moneda: (j['moneda'] ?? '') as String,
        extras: ServicioExtra.listaDe(j['extras']),
        telefono: (j['telefono'] ?? '') as String,
        grupoReservaId: (j['grupoReservaId'] ?? '') as String,
        medioPago: (j['medioPago'] ?? '') as String,
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
/// Tipo de movimiento del dueño: recarga (entra saldo), consumo (comisión que
/// sale del saldo por reserva en efectivo) y liquidacion (reserva online: el
/// jugador pagó a Pichangol y le queda un NETO por recibir; no toca el saldo).
enum TipoMovimiento { recarga, consumo, liquidacion }

class MovimientoSaldo {
  final TipoMovimiento tipo;
  final int monto; // soles (redondeado, para la lista)
  final String concepto;
  final String cuando; // etiqueta simple ("Ahora", "Hoy", etc.)
  /// Solo para [TipoMovimiento.liquidacion]: ¿Pichangol ya transfirió el neto?
  /// false = "por recibir"; true = "recibido".
  final bool liquidado;
  /// Monto EXACTO con decimales (para el recibo). Puede ser negativo (egreso).
  final double montoSoles;
  /// N.º de comprobante (id del pago en el backend). 0 = sin comprobante.
  final int comprobante;
  /// Fecha ISO del movimiento (para el recibo). Vacío si no se conoce.
  final String fechaIso;
  /// Monto BRUTO de la reserva (lo que pagó el jugador). Solo liquidaciones.
  final double brutoSoles;
  /// Comisión de Pichangol de esta reserva (para el recibo). Solo liquidaciones.
  final double comisionSoles;
  /// De dónde salió la comisión: 'saldo' (de tu billetera prepago),
  /// 'transaccion' (del pago del jugador, recibes el neto) o '' (no aplica).
  final String fuente;

  const MovimientoSaldo({
    required this.tipo,
    required this.monto,
    required this.concepto,
    required this.cuando,
    this.liquidado = false,
    this.montoSoles = 0,
    this.comprobante = 0,
    this.fechaIso = '',
    this.brutoSoles = 0,
    this.comisionSoles = 0,
    this.fuente = '',
  });

  bool get esIngreso =>
      tipo == TipoMovimiento.recarga || tipo == TipoMovimiento.liquidacion;

  Map<String, dynamic> toJson() => {
        'tipo': tipo.name,
        'monto': monto,
        'concepto': concepto,
        'cuando': cuando,
        'liquidado': liquidado,
        'montoSoles': montoSoles,
        'comprobante': comprobante,
        'fechaIso': fechaIso,
        'brutoSoles': brutoSoles,
        'comisionSoles': comisionSoles,
        'fuente': fuente,
      };

  factory MovimientoSaldo.fromJson(Map<String, dynamic> j) => MovimientoSaldo(
        tipo: TipoMovimiento.values.byName(j['tipo'] as String),
        monto: j['monto'] as int,
        concepto: j['concepto'] as String,
        cuando: j['cuando'] as String,
        liquidado: (j['liquidado'] ?? false) as bool,
        montoSoles: ((j['montoSoles'] ?? 0) as num).toDouble(),
        comprobante: ((j['comprobante'] ?? 0) as num).toInt(),
        fechaIso: (j['fechaIso'] ?? '') as String,
        brutoSoles: ((j['brutoSoles'] ?? 0) as num).toDouble(),
        comisionSoles: ((j['comisionSoles'] ?? 0) as num).toDouble(),
        fuente: (j['fuente'] ?? '') as String,
      );
}
