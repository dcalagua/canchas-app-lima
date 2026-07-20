import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import 'models.dart';

/// Tipo de plan que ofrece una academia.
enum TipoPlan {
  mensual('Mensualidad'),
  prepago('Paquete de meses'),
  porClase('Por clase');

  final String etiqueta;
  const TipoPlan(this.etiqueta);
}

/// Un plan/paquete que la academia vende a sus alumnos.
/// - [mensual]/[prepago]: genera [meses] cuotas mensuales de [precioMes] c/u.
/// - [porClase]: no genera cuotas por adelantado; cada clase suelta cobra
///   [precioMes] (se reusa el campo como "precio por clase").
class Plan {
  final String id;
  final String nombre;
  final TipoPlan tipo;
  final double precioMes; // S/ por mes (o por clase si tipo == porClase)
  final int meses; // duración: 1 (mensual) o N (prepago); 0 si porClase
  /// Tarifario por PROGRAMA y FRECUENCIA (academias tipo Jartur El Bosque):
  /// [programa] agrupa (ej. "Bola Roja y Naranja"); [frecuenciaSemana] es las
  /// veces por semana (2–5). Vacío/0 = plan simple (sin matriz). [precioMes] es
  /// la tarifa SOCIO; la de invitado se deriva con `Academia.recargoInvitado`.
  final String programa;
  final int frecuenciaSemana;
  /// Descripción de la ETAPA/EDAD del programa (ej. "Iniciación e intermedio ·
  /// 5 a 10 años"). Compartida por todas las frecuencias del mismo programa.
  final String etapaEdad;
  /// Duración de la clase (ej. "1 h 30 min", "2 h"). Igual dentro del programa.
  final String duracionClase;

  const Plan({
    required this.id,
    required this.nombre,
    required this.tipo,
    required this.precioMes,
    this.meses = 1,
    this.programa = '',
    this.frecuenciaSemana = 0,
    this.etapaEdad = '',
    this.duracionClase = '',
  });

  /// Total del plan (para mostrar "paga todo").
  double get total => tipo == TipoPlan.porClase ? precioMes : precioMes * meses;

  /// Etiqueta corta de frecuencia: 3 → "3x/sem" (vacío si no aplica).
  String get frecuenciaLabel =>
      frecuenciaSemana > 0 ? '${frecuenciaSemana}x/sem' : '';

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'tipo': tipo.name,
        'precioMes': precioMes,
        'meses': meses,
        'programa': programa,
        'frecuenciaSemana': frecuenciaSemana,
        'etapaEdad': etapaEdad,
        'duracionClase': duracionClase,
      };

  factory Plan.fromJson(Map<String, dynamic> j) => Plan(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        tipo: TipoPlan.values.firstWhere(
            (t) => t.name == j['tipo'], orElse: () => TipoPlan.mensual),
        precioMes: ((j['precioMes'] ?? 0) as num).toDouble(),
        meses: ((j['meses'] ?? 1) as num).toInt(),
        programa: (j['programa'] ?? '') as String,
        frecuenciaSemana: ((j['frecuenciaSemana'] ?? 0) as num).toInt(),
        etapaEdad: (j['etapaEdad'] ?? '') as String,
        duracionClase: (j['duracionClase'] ?? '') as String,
      );
}

/// Una academia (marca independiente). Rota de sede: `sedeClub` es cambiable y
/// su historia (alumnos, cuotas) no depende del local. Ver docs/flujo-academias.
class Academia {
  final String id;
  final String nombre;
  final Deporte deporte;
  final String dueno; // correo del profe
  final String whatsapp; // contacto (para que el alumno la ubique)
  final String descripcion;
  final String sedeClub; // dónde entrena AHORA (nombre del club/local)
  final LatLng? sedeUbicacion;
  final List<Plan> planes;
  final String? logoUrl; // logo de la academia (si tiene)
  final Map<String, String> redes; // red → handle/url (instagram, tiktok…)
  final List<String> fotos; // feed propio (URLs de fotos subidas por el profe)
  /// Moneda de la academia, congelada al crearla según el país ('' = 'S/', Perú).
  /// Los precios de los planes se muestran en esta moneda sin importar el país
  /// desde donde se abra la app.
  final String moneda;
  /// Recargo FIJO (S/) que paga un INVITADO (no socio de la sede/club) sobre la
  /// tarifa socio del plan. 0 = la academia no distingue socio/invitado (un solo
  /// precio). Caso Jartur (Country Club El Bosque): 50.
  final double recargoInvitado;
  /// Descuentos CONFIGURABLES (%), 0 = sin descuento. Se aplican al inscribir:
  /// [descuentoHermano2] al 2º hermano, [descuentoHermano3] al 3º en adelante,
  /// [descuentoPrepago] al pagar un paquete de meses por adelantado (prepago).
  /// Caso Jartur: 10 / 20 / 5. Son ADITIVOS entre sí (2º hermano + prepago =
  /// 10 + 5 = 15%).
  final double descuentoHermano2;
  final double descuentoHermano3;
  final double descuentoPrepago;
  /// Retribución (%) que la academia le paga al CLUB/sede sobre lo EFECTIVAMENTE
  /// cobrado (liquidación). CONFIGURABLE; 0 = la academia no le paga nada al club
  /// (clubes que no usan esta opción). Caso Jartur (El Bosque): 11.
  final double retribucionClubPct;

  const Academia({
    required this.id,
    required this.nombre,
    required this.deporte,
    required this.dueno,
    this.whatsapp = '',
    this.descripcion = '',
    this.sedeClub = '',
    this.sedeUbicacion,
    this.planes = const [],
    this.logoUrl,
    this.redes = const {},
    this.fotos = const [],
    this.moneda = '',
    this.recargoInvitado = 0,
    this.descuentoHermano2 = 0,
    this.descuentoHermano3 = 0,
    this.descuentoPrepago = 0,
    this.retribucionClubPct = 0,
  });

  /// ¿La academia distingue tarifa socio vs invitado (según la sede/club)?
  bool get tieneTarifaInvitado => recargoInvitado > 0;

  /// Tarifa mensual efectiva de un plan según sea socio (de la sede) o invitado.
  double precioDePlan(Plan p, {required bool socio}) =>
      socio ? p.precioMes : p.precioMes + recargoInvitado;

  /// ¿La academia tiene algún descuento configurado?
  bool get tieneDescuentos =>
      descuentoHermano2 > 0 || descuentoHermano3 > 0 || descuentoPrepago > 0;

  /// ¿Distingue descuento por orden de hermano (2º / 3º)?
  bool get tieneDescuentoHermanos =>
      descuentoHermano2 > 0 || descuentoHermano3 > 0;

  /// % de descuento por orden de hermano (1 = único/1º sin dto, 2 = 2º, 3+ = 3º
  /// o más).
  double descuentoHermanoPct(int orden) {
    if (orden >= 3) return descuentoHermano3;
    if (orden == 2) return descuentoHermano2;
    return 0;
  }

  /// % total de descuento aplicable (hermano + prepago), aditivo, tope 100.
  double descuentoTotalPct({int ordenHermano = 1, bool prepago = false}) {
    var d = descuentoHermanoPct(ordenHermano);
    if (prepago) d += descuentoPrepago;
    return d > 100 ? 100 : d;
  }

  /// Precio final de un plan tras aplicar tarifa socio/invitado y descuentos.
  double precioFinal(Plan p,
      {required bool socio, int ordenHermano = 1, bool prepago = false}) {
    final base = precioDePlan(p, socio: socio);
    final f = base *
        (1 - descuentoTotalPct(ordenHermano: ordenHermano, prepago: prepago) / 100);
    return f < 0 ? 0 : f;
  }

  /// ¿La academia le retribuye un % al club/sede (liquidación)?
  bool get tieneRetribucionClub => retribucionClubPct > 0;

  /// Monto a pagar al club sobre lo EFECTIVAMENTE cobrado.
  double retribucionClub(double cobrado) => cobrado * retribucionClubPct / 100;

  /// Planes agrupados por programa (para el tarifario matriz), preservando el
  /// orden de aparición. Los planes sin programa quedan bajo la clave ''.
  Map<String, List<Plan>> get planesPorPrograma {
    final m = <String, List<Plan>>{};
    for (final p in planes) {
      (m[p.programa] ??= []).add(p);
    }
    for (final lista in m.values) {
      lista.sort((a, b) => a.frecuenciaSemana.compareTo(b.frecuenciaSemana));
    }
    return m;
  }

  /// Símbolo de moneda de la academia. La UBICACIÓN de la sede es la fuente de
  /// verdad (una academia en Lima cobra en S/, aunque el profe abra la app desde
  /// Bolivia): se deriva del país donde cae la sede. Esto auto-corrige academias
  /// que quedaron con la moneda del dispositivo del profe. Si no hay sede
  /// ubicada, cae a la moneda congelada al crear y, por último, a 'S/'.
  String get monedaSimbolo {
    final u = sedeUbicacion;
    if (u != null) return monedaDeCoordenadas(u.latitude, u.longitude);
    return moneda.isNotEmpty ? moneda : 'S/';
  }

  /// País (config) de la academia según su sede; si no hay sede ubicada, cae al
  /// país activo. Fuente del prefijo telefónico y la moneda en el editor.
  PaisConfig get pais {
    final u = sedeUbicacion;
    return u != null ? paisDeCoordenadas(u.latitude, u.longitude) : paisActual;
  }

  /// Código corto y ESTABLE para que un alumno se una desde la app
  /// ("Unirme con código"). Se deriva del [id] (hash FNV-1a → base32), así que
  /// no necesita almacenarse ni migrarse y es el mismo en todos los
  /// dispositivos. 6 caracteres sin ambiguos (sin 0/O/1/I).
  String get codigo => _codigoDeId(id);

  static const _alfabeto = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; // 32 símbolos

  static String _codigoDeId(String id) {
    var h = 0x811c9dc5; // FNV-1a 32-bit offset basis
    for (final c in id.codeUnits) {
      h = (h ^ c) & 0xFFFFFFFF;
      h = (h * 0x01000193) & 0xFFFFFFFF; // FNV prime
    }
    final sb = StringBuffer();
    for (var i = 0; i < 6; i++) {
      sb.write(_alfabeto[(h >> (i * 5)) & 31]);
    }
    return sb.toString();
  }

  /// Normaliza un código tecleado por el alumno para compararlo con [codigo]:
  /// mayúsculas y conserva solo los símbolos válidos del alfabeto (descarta
  /// espacios, guiones y ambiguos 0/O/1/I que el usuario pudiera teclear).
  static String normalizarCodigo(String entrada) {
    final sb = StringBuffer();
    for (final ch in entrada.toUpperCase().split('')) {
      if (_alfabeto.contains(ch)) sb.write(ch);
    }
    return sb.toString();
  }

  Academia copyWith({
    String? nombre,
    Deporte? deporte,
    String? whatsapp,
    String? descripcion,
    String? sedeClub,
    LatLng? sedeUbicacion,
    List<Plan>? planes,
    String? logoUrl,
    Map<String, String>? redes,
    List<String>? fotos,
    String? moneda,
    double? recargoInvitado,
    double? descuentoHermano2,
    double? descuentoHermano3,
    double? descuentoPrepago,
    double? retribucionClubPct,
  }) =>
      Academia(
        id: id,
        nombre: nombre ?? this.nombre,
        deporte: deporte ?? this.deporte,
        dueno: dueno,
        whatsapp: whatsapp ?? this.whatsapp,
        descripcion: descripcion ?? this.descripcion,
        sedeClub: sedeClub ?? this.sedeClub,
        sedeUbicacion: sedeUbicacion ?? this.sedeUbicacion,
        planes: planes ?? this.planes,
        logoUrl: logoUrl ?? this.logoUrl,
        redes: redes ?? this.redes,
        fotos: fotos ?? this.fotos,
        moneda: moneda ?? this.moneda,
        recargoInvitado: recargoInvitado ?? this.recargoInvitado,
        descuentoHermano2: descuentoHermano2 ?? this.descuentoHermano2,
        descuentoHermano3: descuentoHermano3 ?? this.descuentoHermano3,
        descuentoPrepago: descuentoPrepago ?? this.descuentoPrepago,
        retribucionClubPct: retribucionClubPct ?? this.retribucionClubPct,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'deporte': deporte.name,
        'dueno': dueno,
        'whatsapp': whatsapp,
        'descripcion': descripcion,
        'sedeClub': sedeClub,
        if (sedeUbicacion != null) 'lat': sedeUbicacion!.latitude,
        if (sedeUbicacion != null) 'lng': sedeUbicacion!.longitude,
        'planes': planes.map((p) => p.toJson()).toList(),
        if (logoUrl != null) 'logoUrl': logoUrl,
        'redes': redes,
        'fotos': fotos,
        'moneda': moneda,
        'recargoInvitado': recargoInvitado,
        'descuentoHermano2': descuentoHermano2,
        'descuentoHermano3': descuentoHermano3,
        'descuentoPrepago': descuentoPrepago,
        'retribucionClubPct': retribucionClubPct,
      };

  factory Academia.fromJson(Map<String, dynamic> j) => Academia(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        deporte: Deporte.values.firstWhere(
            (d) => d.name == j['deporte'], orElse: () => Deporte.tenis),
        dueno: (j['dueno'] ?? '') as String,
        whatsapp: (j['whatsapp'] ?? '') as String,
        descripcion: (j['descripcion'] ?? '') as String,
        sedeClub: (j['sedeClub'] ?? '') as String,
        sedeUbicacion: (j['lat'] != null && j['lng'] != null)
            ? LatLng((j['lat'] as num).toDouble(), (j['lng'] as num).toDouble())
            : null,
        planes: (j['planes'] as List?)
                ?.map((e) => Plan.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        logoUrl: j['logoUrl'] as String?,
        redes: (j['redes'] as Map?)
                ?.map((k, v) => MapEntry(k.toString(), v.toString())) ??
            const {},
        fotos: (j['fotos'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        moneda: (j['moneda'] ?? '') as String,
        recargoInvitado: ((j['recargoInvitado'] ?? 0) as num).toDouble(),
        descuentoHermano2: ((j['descuentoHermano2'] ?? 0) as num).toDouble(),
        descuentoHermano3: ((j['descuentoHermano3'] ?? 0) as num).toDouble(),
        descuentoPrepago: ((j['descuentoPrepago'] ?? 0) as num).toDouble(),
        retribucionClubPct:
            ((j['retribucionClubPct'] ?? 0) as num).toDouble(),
      );
}

/// Un alumno inscrito en una academia.
///
/// [email] no vacío = **alumno-app**: se unió con el código desde la app (la
/// cuenta que lo administra: el propio adulto o un apoderado).
///
/// Menores: un niño NO tiene cuenta propia (Ley 29733). Se registra bajo un
/// **apoderado** (adulto con cuenta): [apoderadoNombre] no vacío ⇒ el alumno es
/// un menor; [nombre] es el nombre del niño y el contacto/pagos van al
/// apoderado ([apoderadoWhatsapp] / [email]).
class Alumno {
  final String id;
  final String academiaId;
  final String nombre; // nombre del alumno (adulto o niño)
  final String whatsapp; // WhatsApp del alumno adulto (si aplica)
  final String email; // cuenta-app que lo administra ('' si manual)
  final String? fotoUrl; // foto del perfil (si el alumno es el adulto)
  final String apoderadoNombre; // '' si el alumno es un adulto; nombre del padre si es menor
  final String apoderadoWhatsapp; // WhatsApp del apoderado (recordatorios de pago)
  final int? edad; // edad del alumno (opcional; útil para menores)
  /// ¿Es SOCIO de la sede/club (ej. Country Club El Bosque)? Define la tarifa:
  /// socio = precio del plan; invitado (false) = precio + recargoInvitado.
  /// Por defecto true (los alumnos fundadores son socios). Lo marca el profe.
  final bool esSocioSede;
  /// Orden de hermano para el descuento familiar configurable de la academia:
  /// 1 = único/1º (sin descuento), 2 = 2º hermano, 3 = 3º o más. Lo marca el
  /// profe al inscribir. Ver `Academia.descuentoHermano2/3`.
  final int ordenHermano;

  const Alumno({
    required this.id,
    required this.academiaId,
    required this.nombre,
    this.whatsapp = '',
    this.email = '',
    this.fotoUrl,
    this.apoderadoNombre = '',
    this.apoderadoWhatsapp = '',
    this.edad,
    this.esSocioSede = true,
    this.ordenHermano = 1,
  });

  /// ¿Es un alumno que usa la app (se unió con código)?
  bool get esApp => email.isNotEmpty;

  /// ¿Es un menor representado por un apoderado?
  bool get esMenor => apoderadoNombre.isNotEmpty;

  /// WhatsApp para contactarlo/recordar pagos: el del apoderado si es menor.
  String get whatsappContacto =>
      esMenor && apoderadoWhatsapp.isNotEmpty ? apoderadoWhatsapp : whatsapp;

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'nombre': nombre,
        'whatsapp': whatsapp,
        'email': email,
        if (fotoUrl != null) 'fotoUrl': fotoUrl,
        'apoderadoNombre': apoderadoNombre,
        'apoderadoWhatsapp': apoderadoWhatsapp,
        if (edad != null) 'edad': edad,
        'esSocioSede': esSocioSede,
        'ordenHermano': ordenHermano,
      };

  factory Alumno.fromJson(Map<String, dynamic> j) => Alumno(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        whatsapp: (j['whatsapp'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        fotoUrl: j['fotoUrl'] as String?,
        apoderadoNombre: (j['apoderadoNombre'] ?? '') as String,
        apoderadoWhatsapp: (j['apoderadoWhatsapp'] ?? '') as String,
        edad: (j['edad'] as num?)?.toInt(),
        esSocioSede: (j['esSocioSede'] ?? true) as bool,
        ordenHermano: ((j['ordenHermano'] ?? 1) as num).toInt(),
      );
}

/// Una cuota de cobro (mensualidad o clase suelta). Modelo estilo "provisión":
/// vencimiento + monto + estado. La mora se calcula al vencer (Fase 1: simple).
class Cuota {
  final String id;
  final String academiaId;
  final String alumnoId;
  final String concepto; // "Mensualidad · Marzo", "Clase suelta 12/03"
  final double monto;
  final DateTime vencimiento;
  final bool pagada;
  final DateTime? fechaPago; // cuándo se cobró (para reportes por fecha)

  const Cuota({
    required this.id,
    required this.academiaId,
    required this.alumnoId,
    required this.concepto,
    required this.monto,
    required this.vencimiento,
    this.pagada = false,
    this.fechaPago,
  });

  /// Vencida = no pagada y ya pasó su fecha de vencimiento.
  bool vencidaAl(DateTime hoy) =>
      !pagada && vencimiento.isBefore(DateTime(hoy.year, hoy.month, hoy.day));

  Cuota copyWith({bool? pagada, DateTime? fechaPago, bool limpiarFechaPago = false}) =>
      Cuota(
        id: id,
        academiaId: academiaId,
        alumnoId: alumnoId,
        concepto: concepto,
        monto: monto,
        vencimiento: vencimiento,
        pagada: pagada ?? this.pagada,
        fechaPago: limpiarFechaPago ? null : (fechaPago ?? this.fechaPago),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'concepto': concepto,
        'monto': monto,
        'vencimiento': vencimiento.toIso8601String(),
        'pagada': pagada,
        if (fechaPago != null) 'fechaPago': fechaPago!.toIso8601String(),
      };

  factory Cuota.fromJson(Map<String, dynamic> j) => Cuota(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        alumnoId: (j['alumnoId'] ?? '') as String,
        concepto: (j['concepto'] ?? '') as String,
        monto: ((j['monto'] ?? 0) as num).toDouble(),
        vencimiento:
            DateTime.tryParse((j['vencimiento'] ?? '') as String) ??
                DateTime.now(),
        pagada: (j['pagada'] ?? false) as bool,
        fechaPago: j['fechaPago'] != null
            ? DateTime.tryParse(j['fechaPago'] as String)
            : null,
      );
}

/// Registro de ASISTENCIA de un alumno a una clase de un día. La clave lógica
/// es (alumnoId + día): marcar/desmarcar presente. [dia] es "YYYY-MM-DD".
class Asistencia {
  final String academiaId;
  final String alumnoId;
  final String dia; // 'YYYY-MM-DD'
  final bool presente;

  const Asistencia({
    required this.academiaId,
    required this.alumnoId,
    required this.dia,
    this.presente = true,
  });

  /// "YYYY-MM-DD" de una fecha (clave de día).
  static String claveDia(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Map<String, dynamic> toJson() => {
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'dia': dia,
        'presente': presente,
      };

  factory Asistencia.fromJson(Map<String, dynamic> j) => Asistencia(
        academiaId: (j['academiaId'] ?? '') as String,
        alumnoId: (j['alumnoId'] ?? '') as String,
        dia: (j['dia'] ?? '') as String,
        presente: (j['presente'] ?? true) as bool,
      );
}
