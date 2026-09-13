/// Plan de trabajo del profe: una malla de CLASES (sesiones) por deporte y nivel,
/// con las HABILIDADES que se evalúan. El profe usa una plantilla de Pichangol
/// (editable) o crea/duplica la suya. Sobre este plan evalúa a cada alumno.
///
/// Persistencia LOCAL (SharedPreferences) vía AppState, igual que alumnos/cuotas.

/// Nivel de logro de una habilidad (rúbrica simple estilo colegio).
enum NivelLogro {
  inicial('Inicial', 0),
  enProceso('En proceso', 1),
  logrado('Logrado', 2);

  final String etiqueta;
  final int valor;
  const NivelLogro(this.etiqueta, this.valor);

  static NivelLogro? porNombre(String? n) {
    for (final v in NivelLogro.values) {
      if (v.name == n) return v;
    }
    return null;
  }
}

/// Una SESIÓN (clase) del plan: número, título, objetivo y contenidos (drills).
class SesionPlan {
  final int numero;
  final String titulo;
  final String objetivo;
  final List<String> contenidos; // ejercicios / drills de la clase

  const SesionPlan({
    required this.numero,
    required this.titulo,
    this.objetivo = '',
    this.contenidos = const [],
  });

  SesionPlan copyWith({
    int? numero,
    String? titulo,
    String? objetivo,
    List<String>? contenidos,
  }) =>
      SesionPlan(
        numero: numero ?? this.numero,
        titulo: titulo ?? this.titulo,
        objetivo: objetivo ?? this.objetivo,
        contenidos: contenidos ?? this.contenidos,
      );

  Map<String, dynamic> toJson() => {
        'numero': numero,
        'titulo': titulo,
        'objetivo': objetivo,
        'contenidos': contenidos,
      };

  factory SesionPlan.fromJson(Map<String, dynamic> j) => SesionPlan(
        numero: ((j['numero'] ?? 0) as num).toInt(),
        titulo: (j['titulo'] ?? '') as String,
        objetivo: (j['objetivo'] ?? '') as String,
        contenidos: (j['contenidos'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );
}

/// Un PLAN DE TRABAJO de una academia: nombre, deporte, nivel, la lista de
/// HABILIDADES a evaluar y las SESIONES (clases). [esPlantilla] marca las
/// semillas de Pichangol (para ofrecerlas como base).
class PlanTrabajo {
  final String id;
  final String academiaId;
  final String deporte; // Deporte.name (tenis, futbol, padel…)
  final String nombre;
  final String nivel; // ej. "Iniciación", "Intermedio", "Avanzado"
  final List<String> habilidades; // habilidades a evaluar (nombres)
  final List<SesionPlan> sesiones;
  final bool esPlantilla; // true = semilla Pichangol (no editable en sitio)

  const PlanTrabajo({
    required this.id,
    required this.academiaId,
    required this.deporte,
    required this.nombre,
    this.nivel = '',
    this.habilidades = const [],
    this.sesiones = const [],
    this.esPlantilla = false,
  });

  int get totalClases => sesiones.length;

  PlanTrabajo copyWith({
    String? id,
    String? academiaId,
    String? deporte,
    String? nombre,
    String? nivel,
    List<String>? habilidades,
    List<SesionPlan>? sesiones,
    bool? esPlantilla,
  }) =>
      PlanTrabajo(
        id: id ?? this.id,
        academiaId: academiaId ?? this.academiaId,
        deporte: deporte ?? this.deporte,
        nombre: nombre ?? this.nombre,
        nivel: nivel ?? this.nivel,
        habilidades: habilidades ?? this.habilidades,
        sesiones: sesiones ?? this.sesiones,
        esPlantilla: esPlantilla ?? this.esPlantilla,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'deporte': deporte,
        'nombre': nombre,
        'nivel': nivel,
        'habilidades': habilidades,
        'sesiones': sesiones.map((s) => s.toJson()).toList(),
        'esPlantilla': esPlantilla,
      };

  factory PlanTrabajo.fromJson(Map<String, dynamic> j) => PlanTrabajo(
        id: (j['id'] ?? '') as String,
        academiaId: (j['academiaId'] ?? '') as String,
        deporte: (j['deporte'] ?? 'tenis') as String,
        nombre: (j['nombre'] ?? '') as String,
        nivel: (j['nivel'] ?? '') as String,
        habilidades: (j['habilidades'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        sesiones: (j['sesiones'] as List?)
                ?.map((e) => SesionPlan.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        esPlantilla: (j['esPlantilla'] ?? false) as bool,
      );
}

/// Evaluación de UNA habilidad de UN alumno dentro de UN plan (upsert por la
/// terna alumno+plan+habilidad). Guarda el último nivel alcanzado.
class EvaluacionAlumno {
  final String alumnoId;
  final String planId;
  final String habilidad;
  final NivelLogro nivel;
  final DateTime cuando;

  const EvaluacionAlumno({
    required this.alumnoId,
    required this.planId,
    required this.habilidad,
    required this.nivel,
    required this.cuando,
  });

  /// Clave lógica (para upsert / dedup).
  String get clave => '$alumnoId|$planId|$habilidad';

  Map<String, dynamic> toJson() => {
        'alumnoId': alumnoId,
        'planId': planId,
        'habilidad': habilidad,
        'nivel': nivel.name,
        'ts': cuando.millisecondsSinceEpoch,
      };

  factory EvaluacionAlumno.fromJson(Map<String, dynamic> j) => EvaluacionAlumno(
        alumnoId: (j['alumnoId'] ?? '') as String,
        planId: (j['planId'] ?? '') as String,
        habilidad: (j['habilidad'] ?? '') as String,
        nivel: NivelLogro.porNombre(j['nivel'] as String?) ?? NivelLogro.inicial,
        cuando: DateTime.fromMillisecondsSinceEpoch(
            (j['ts'] as num?)?.toInt() ?? 0),
      );
}

/// Desempeño de UNA clase (la evaluación rápida del día, tipo semáforo).
enum DesempenoClase {
  muyBien('Muy bien', 2),
  bien('Bien', 1),
  aReforzar('A reforzar', 0);

  final String etiqueta;
  final int valor;
  const DesempenoClase(this.etiqueta, this.valor);

  static DesempenoClase? porNombre(String? n) {
    for (final v in DesempenoClase.values) {
      if (v.name == n) return v;
    }
    return null;
  }
}

/// BITÁCORA DE CLASE: la evaluación DIARIA que el profe hace del alumno en cada
/// sesión (asistió + cómo le fue + observación). Es distinta de [EvaluacionAlumno]
/// (rúbrica acumulada por habilidad): aquí hay UNA entrada por clase con fecha, y
/// se guarda el historial (no se sobrescribe). Alimenta el diario del alumno y el
/// avance del plan (qué clase se dio).
class NotaClase {
  final String id;
  final String academiaId;
  final String alumnoId;
  final String planId; // plan de referencia ('' si es una nota suelta)
  final int sesionNumero; // clase del plan (0 = sin clase específica)
  final String fecha; // 'YYYY-MM-DD'
  final DesempenoClase desempeno;
  final String nota; // observación libre del profe
  final DateTime creado;

  const NotaClase({
    required this.id,
    required this.academiaId,
    required this.alumnoId,
    required this.planId,
    required this.sesionNumero,
    required this.fecha,
    required this.desempeno,
    required this.nota,
    required this.creado,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'academiaId': academiaId,
        'alumnoId': alumnoId,
        'planId': planId,
        'sesionNumero': sesionNumero,
        'fecha': fecha,
        'desempeno': desempeno.name,
        'nota': nota,
        'ts': creado.millisecondsSinceEpoch,
      };

  factory NotaClase.fromJson(Map<String, dynamic> j) => NotaClase(
        id: (j['id'] ?? '') as String,
        academiaId: (j['academiaId'] ?? '') as String,
        alumnoId: (j['alumnoId'] ?? '') as String,
        planId: (j['planId'] ?? '') as String,
        sesionNumero: ((j['sesionNumero'] ?? 0) as num).toInt(),
        fecha: (j['fecha'] ?? '') as String,
        desempeno:
            DesempenoClase.porNombre(j['desempeno'] as String?) ??
                DesempenoClase.bien,
        nota: (j['nota'] ?? '') as String,
        creado: DateTime.fromMillisecondsSinceEpoch(
            (j['ts'] as num?)?.toInt() ?? 0),
      );
}
