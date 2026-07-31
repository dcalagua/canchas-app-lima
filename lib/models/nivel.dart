import 'dart:math';

/// Nivel de jugador por deporte (estilo Playtomic 0-7; aquí 1.0–7.0). Se siembra
/// en el onboarding con un mini-cuestionario y se AJUSTA con resultados reales
/// (retos, campeonatos) mediante un ELO suave. Se persiste en Supabase
/// (`pichangol_niveles`) y se cachea device-first en el teléfono.
class Nivel {
  const Nivel({
    required this.email,
    required this.deporte,
    this.nivel = 3.0,
    this.partidos = 0,
    this.victorias = 0,
    this.confiabilidad = 1.0,
    this.actualizado,
  });

  final String email;
  final String deporte;
  final double nivel; // 1.0 .. 7.0
  final int partidos;
  final int victorias;
  final double confiabilidad; // 0.0 .. 1.0 (asistencia confirmada vs no-show)
  final DateTime? actualizado;

  /// Etiqueta corta del nivel para el chip del perfil (1 decimal): "4.3".
  String get etiqueta => nivel.toStringAsFixed(1);

  /// Banda de nivel para el matchmaking "juega con parejos": ±[margen].
  bool esParejo(double otro, {double margen = 1.0}) =>
      (nivel - otro).abs() <= margen;

  Nivel copyWith({
    double? nivel,
    int? partidos,
    int? victorias,
    double? confiabilidad,
    DateTime? actualizado,
  }) =>
      Nivel(
        email: email,
        deporte: deporte,
        nivel: nivel ?? this.nivel,
        partidos: partidos ?? this.partidos,
        victorias: victorias ?? this.victorias,
        confiabilidad: confiabilidad ?? this.confiabilidad,
        actualizado: actualizado ?? this.actualizado,
      );

  /// Nivel inicial ESTIMADO desde el auto-cuestionario del onboarding. Sencillo y
  /// acotado; los resultados reales lo corrigen luego. [anios] de práctica,
  /// [frecuenciaSemana] veces que juega por semana, [compite] en torneos/ligas.
  static double seedDesde({
    required int anios,
    required int frecuenciaSemana,
    required bool compite,
  }) {
    var n = 2.0;
    n += (anios.clamp(0, 10)) * 0.25; // hasta +2.5 por experiencia
    n += (frecuenciaSemana.clamp(0, 5)) * 0.2; // hasta +1.0 por frecuencia
    if (compite) n += 1.0;
    return n.clamp(1.0, 7.0).toDouble();
  }

  /// ELO SUAVE: nuevo nivel tras un resultado. Sube más si le ganas a alguien de
  /// mayor nivel; baja poco si pierdes con uno mucho mejor. [k] chico = cambios
  /// graduales (evita saltos). [gane] = true si el jugador ganó.
  static double calcularElo({
    required double miNivel,
    required double rivalNivel,
    required bool gane,
    double k = 0.15,
  }) {
    final esperado = 1 / (1 + pow(10, (rivalNivel - miNivel) / 2));
    final real = gane ? 1.0 : 0.0;
    final nuevo = miNivel + k * (real - esperado);
    return nuevo.clamp(1.0, 7.0).toDouble();
  }

  factory Nivel.fromRow(Map<String, dynamic> r) => Nivel(
        email: (r['email'] ?? '').toString(),
        deporte: (r['deporte'] ?? '').toString(),
        nivel: (r['nivel'] as num?)?.toDouble() ?? 3.0,
        partidos: (r['partidos'] as num?)?.toInt() ?? 0,
        victorias: (r['victorias'] as num?)?.toInt() ?? 0,
        confiabilidad: (r['confiabilidad'] as num?)?.toDouble() ?? 1.0,
        actualizado: DateTime.tryParse((r['actualizado'] ?? '').toString()),
      );

  Map<String, dynamic> toRow() => {
        'email': email,
        'deporte': deporte,
        'nivel': nivel,
        'partidos': partidos,
        'victorias': victorias,
        'confiabilidad': confiabilidad,
        'actualizado': (actualizado ?? DateTime.now()).toIso8601String(),
      };

  Map<String, dynamic> toJson() => toRow();

  factory Nivel.fromJson(Map<String, dynamic> j) => Nivel.fromRow(j);
}
