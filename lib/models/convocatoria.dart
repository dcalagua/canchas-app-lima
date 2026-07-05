/// Modelos de CONVOCATORIAS ("pichangas" programadas). Espejo de los contratos
/// del backend growth (`convocatorias/service.py`). No se persisten localmente:
/// la fuente de verdad es el backend (fail-safe si no está disponible).

/// Modos de asignación de cupos configurables por el admin del club.
enum ModoAsignacion { ordenLlegada, sorteo, equidad }

extension ModoAsignacionX on ModoAsignacion {
  String get clave => switch (this) {
        ModoAsignacion.ordenLlegada => 'orden_llegada',
        ModoAsignacion.sorteo => 'sorteo',
        ModoAsignacion.equidad => 'equidad',
      };

  String get etiqueta => switch (this) {
        ModoAsignacion.ordenLlegada => 'Orden de llegada',
        ModoAsignacion.sorteo => 'Sorteo',
        ModoAsignacion.equidad => 'Equidad',
      };

  String get descripcion => switch (this) {
        ModoAsignacion.ordenLlegada =>
          'El que se anota primero entra. Confirma al instante.',
        ModoAsignacion.sorteo =>
          'Ventana de inscripción; al cerrar se sortea de forma justa.',
        ModoAsignacion.equidad =>
          'Al cerrar prioriza a quien más quedó fuera y mejor asiste.',
      };

  static ModoAsignacion desde(String? clave) => switch (clave) {
        'sorteo' => ModoAsignacion.sorteo,
        'equidad' => ModoAsignacion.equidad,
        _ => ModoAsignacion.ordenLlegada,
      };
}

/// Estado efectivo de un socio en una convocatoria (para la ficha del jugador).
enum EstadoSocio { sinInscripcion, confirmado, listaEspera, enBolsa }

extension EstadoSocioX on EstadoSocio {
  static EstadoSocio desde(String? v) => switch (v) {
        'confirmado' => EstadoSocio.confirmado,
        'lista_espera' => EstadoSocio.listaEspera,
        'en_bolsa' => EstadoSocio.enBolsa,
        _ => EstadoSocio.sinInscripcion,
      };
}

/// Una convocatoria (resumen o cabecera del detalle).
class Convocatoria {
  final int id;
  final String clubId;
  final String titulo;
  final String deporte;
  final int cupos;
  final String estado; // abierta | cerrada
  final String? categoria; // master | menor | libre
  final String? fechaPartido;
  final String? modoAsignacion; // override elegido al crear (puede ser null)
  final String modoEfectivo; // el que realmente aplica
  final bool abiertaAhora;
  final int cuposLibres;
  final int totalInscritos;
  final int confirmadosN;
  final int esperaN;

  const Convocatoria({
    required this.id,
    required this.clubId,
    required this.titulo,
    required this.deporte,
    required this.cupos,
    required this.estado,
    required this.modoEfectivo,
    this.categoria,
    this.fechaPartido,
    this.modoAsignacion,
    this.abiertaAhora = false,
    this.cuposLibres = 0,
    this.totalInscritos = 0,
    this.confirmadosN = 0,
    this.esperaN = 0,
  });

  bool get cerrada => estado == 'cerrada';
  ModoAsignacion get modo => ModoAsignacionX.desde(modoEfectivo);

  /// Parsea un item del listado (`GET /convocatorias`), que ya trae los conteos.
  factory Convocatoria.fromListado(Map<String, dynamic> j) => Convocatoria(
        id: (j['id'] as num).toInt(),
        clubId: j['club_id'] as String? ?? '',
        titulo: j['titulo'] as String? ?? '',
        deporte: j['deporte'] as String? ?? 'futbol',
        cupos: (j['cupos'] as num?)?.toInt() ?? 0,
        estado: j['estado'] as String? ?? 'abierta',
        categoria: j['categoria'] as String?,
        fechaPartido: j['fecha_partido'] as String?,
        modoAsignacion: j['modo_asignacion'] as String?,
        modoEfectivo: j['modo_efectivo'] as String? ?? 'orden_llegada',
        abiertaAhora: j['abierta_ahora'] as bool? ?? false,
        cuposLibres: (j['cupos_libres'] as num?)?.toInt() ?? 0,
        totalInscritos: (j['total_inscritos'] as num?)?.toInt() ?? 0,
        confirmadosN: (j['confirmados_n'] as num?)?.toInt() ?? 0,
        esperaN: (j['espera_n'] as num?)?.toInt() ?? 0,
      );

  /// Parsea la cabecera dentro de una respuesta de detalle, tomando los conteos
  /// del envoltorio (`d`).
  factory Convocatoria.fromDetalle(Map<String, dynamic> d) {
    final c = Map<String, dynamic>.from(d['convocatoria'] as Map);
    final conf = (d['confirmados'] as List?) ?? const [];
    final esp = (d['lista_espera'] as List?) ?? const [];
    return Convocatoria(
      id: (c['id'] as num).toInt(),
      clubId: c['club_id'] as String? ?? '',
      titulo: c['titulo'] as String? ?? '',
      deporte: c['deporte'] as String? ?? 'futbol',
      cupos: (c['cupos'] as num?)?.toInt() ?? 0,
      estado: c['estado'] as String? ?? 'abierta',
      categoria: c['categoria'] as String?,
      fechaPartido: c['fecha_partido'] as String?,
      modoAsignacion: c['modo_asignacion'] as String?,
      modoEfectivo: d['modo_efectivo'] as String? ?? 'orden_llegada',
      abiertaAhora: d['abierta_ahora'] as bool? ?? false,
      cuposLibres: (d['cupos_libres'] as num?)?.toInt() ?? 0,
      totalInscritos: (d['total_inscritos'] as num?)?.toInt() ?? 0,
      confirmadosN: conf.length,
      esperaN: esp.length,
    );
  }
}

/// Un socio inscrito a una convocatoria.
class Inscripcion {
  final String socioId;
  final String socioNombre;
  final String estado; // pendiente | confirmado | lista_espera | cancelado
  final int? posicion;
  final bool? asistio;

  const Inscripcion({
    required this.socioId,
    required this.socioNombre,
    required this.estado,
    this.posicion,
    this.asistio,
  });

  factory Inscripcion.fromJson(Map<String, dynamic> j) => Inscripcion(
        socioId: j['socio_id'] as String? ?? '',
        socioNombre: j['socio_nombre'] as String? ?? '',
        estado: j['estado'] as String? ?? 'pendiente',
        posicion: (j['posicion'] as num?)?.toInt(),
        asistio: j['asistio'] as bool?,
      );
}

/// Detalle completo de una convocatoria: cabecera + listas + mi estado.
class ConvocatoriaDetalle {
  final Convocatoria convocatoria;
  final List<Inscripcion> confirmados;
  final List<Inscripcion> listaEspera;
  final EstadoSocio miEstado;
  final int? miPosicion;

  const ConvocatoriaDetalle({
    required this.convocatoria,
    required this.confirmados,
    required this.listaEspera,
    this.miEstado = EstadoSocio.sinInscripcion,
    this.miPosicion,
  });

  factory ConvocatoriaDetalle.fromJson(Map<String, dynamic> d) {
    final mi = d['mi_estado'] as Map?;
    return ConvocatoriaDetalle(
      convocatoria: Convocatoria.fromDetalle(d),
      confirmados: ((d['confirmados'] as List?) ?? const [])
          .map((e) => Inscripcion.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      listaEspera: ((d['lista_espera'] as List?) ?? const [])
          .map((e) => Inscripcion.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      miEstado: EstadoSocioX.desde(mi?['estado_efectivo'] as String?),
      miPosicion: (mi?['posicion'] as num?)?.toInt(),
    );
  }
}
