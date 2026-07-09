import 'package:google_maps_flutter/google_maps_flutter.dart';

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

  const Plan({
    required this.id,
    required this.nombre,
    required this.tipo,
    required this.precioMes,
    this.meses = 1,
  });

  /// Total del plan (para mostrar "paga todo").
  double get total => tipo == TipoPlan.porClase ? precioMes : precioMes * meses;

  Map<String, dynamic> toJson() => {
        'id': id,
        'nombre': nombre,
        'tipo': tipo.name,
        'precioMes': precioMes,
        'meses': meses,
      };

  factory Plan.fromJson(Map<String, dynamic> j) => Plan(
        id: j['id'] as String,
        nombre: (j['nombre'] ?? '') as String,
        tipo: TipoPlan.values.firstWhere(
            (t) => t.name == j['tipo'], orElse: () => TipoPlan.mensual),
        precioMes: ((j['precioMes'] ?? 0) as num).toDouble(),
        meses: ((j['meses'] ?? 1) as num).toInt(),
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
  });

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
      );
}

/// Un alumno inscrito en una academia.
class Alumno {
  final String id;
  final String academiaId;
  final String nombre;
  final String whatsapp;

  const Alumno({
    required this.id,
    required this.academiaId,
    required this.nombre,
    this.whatsapp = '',
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'nombre': nombre,
        'whatsapp': whatsapp,
      };

  factory Alumno.fromJson(Map<String, dynamic> j) => Alumno(
        id: j['id'] as String,
        academiaId: (j['academiaId'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        whatsapp: (j['whatsapp'] ?? '') as String,
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

  const Cuota({
    required this.id,
    required this.academiaId,
    required this.alumnoId,
    required this.concepto,
    required this.monto,
    required this.vencimiento,
    this.pagada = false,
  });

  /// Vencida = no pagada y ya pasó su fecha de vencimiento.
  bool vencidaAl(DateTime hoy) =>
      !pagada && vencimiento.isBefore(DateTime(hoy.year, hoy.month, hoy.day));

  Cuota copyWith({bool? pagada}) => Cuota(
        id: id,
        academiaId: academiaId,
        alumnoId: alumnoId,
        concepto: concepto,
        monto: monto,
        vencimiento: vencimiento,
        pagada: pagada ?? this.pagada,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'concepto': concepto,
        'monto': monto,
        'vencimiento': vencimiento.toIso8601String(),
        'pagada': pagada,
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
