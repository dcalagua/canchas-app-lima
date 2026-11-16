import 'dart:math' as math;

import 'models.dart';

/// JUEGA YA: catálogos ESPEJO de `backend/growth/juego.py` (al cambiar uno,
/// cambiar el otro). Todo se elige por selección, sin texto libre.
class Juego {
  Juego._();

  /// Deportes donde existe "Busco partner" (raqueta activos).
  static const deportesPartner = [Deporte.tenis, Deporte.pickleball];
  static const radios = [5, 10, 20, 30];
  static const radioDefault = 10;
  static const maxEtiquetas = 4;

  /// (clave, etiqueta, jugadores en total incluyéndome).
  static const modalidades = [
    ('singles', 'Singles', 2),
    ('dobles', 'Dobles', 4),
    ('pelotear', 'Pelotear', 2),
  ];

  /// Bandas sobre el nivel 1.0–7.0 (sin dato = 3.0 → intermedio).
  static const niveles = [
    ('inicial', '🌱 Principiante', 0.0, 2.5),
    ('intermedio', '⚡ Intermedio', 2.5, 4.0),
    ('avanzado', '🔥 Avanzado', 4.0, 5.5),
    ('competitivo', '🏆 Competitivo', 5.5, 99.0),
  ];
  static const nivelSinDato = 3.0;

  /// clave → (emoji, texto, deportes donde aplica; vacío = todos).
  static const etiquetas = <String, (String, String, List<Deporte>)>{
    'cancha_reservada': ('✅', 'Cancha ya reservada', []),
    'se_divide': ('💵', 'Se divide la cancha', []),
    'amistoso': ('🤝', 'Amistoso, sin presión', []),
    'traer_pechera': ('🦺', 'Llevar pechera', [Deporte.futbol]),
    'falta_arquero': ('🧤', 'Falta arquero', [Deporte.futbol]),
    'llevo_pelotas': ('🎾', 'Llevo pelotas', [Deporte.tenis, Deporte.pickleball]),
    'mixto': ('👫', 'Mixto', []),
    'solo_mujeres': ('👩', 'Solo mujeres', []),
    'mayores_35': ('🧓', 'Mayores de 35', []),
  };

  static const franjas = [
    ('manana', '🌅 Mañana'),
    ('tarde', '☀️ Tarde'),
    ('noche', '🌙 Noche'),
  ];
  static const dias = [
    ('todos', 'Cualquier día'),
    ('semana', 'Lunes a viernes'),
    ('finde', 'Fin de semana'),
  ];

  static String nivelBanda(double? n) {
    final v = n ?? nivelSinDato;
    for (final b in niveles) {
      if (v >= b.$3 && v < b.$4) return b.$1;
    }
    return niveles.last.$1;
  }

  static String etiquetaNivel(String clave) {
    for (final b in niveles) {
      if (b.$1 == clave) return b.$2;
    }
    return 'Todos los niveles';
  }

  static (String, String, int)? modalidad(String clave) {
    for (final m in modalidades) {
      if (m.$1 == clave) return m;
    }
    return null;
  }

  static List<String> etiquetasPara(Deporte d) => [
        for (final e in etiquetas.entries)
          if (e.value.$3.isEmpty || e.value.$3.contains(d)) e.key
      ];

  static String etiquetaFranja(String k) =>
      franjas.firstWhere((f) => f.$1 == k, orElse: () => (k, '')).$2;

  static double km(double aLat, double aLng, double bLat, double bLng) {
    const r = 6371.0;
    double rad(double x) => x * math.pi / 180;
    final dLat = rad(bLat - aLat), dLng = rad(bLng - aLng);
    final h = math.pow(math.sin(dLat / 2), 2) +
        math.cos(rad(aLat)) * math.cos(rad(bLat)) * math.pow(math.sin(dLng / 2), 2);
    return 2 * r * math.asin(math.min(1.0, math.sqrt(h)));
  }

  static String fmtKm(double k) {
    if (k < 1) return '< 1';
    var t = k.toStringAsFixed(1);
    if (t.endsWith('.0')) t = t.substring(0, t.length - 2);
    return t.replaceAll('.', ',');
  }
}

/// Preferencias de juego del usuario (vive en el backend: `/juego/prefs`).
class PrefsJuego {
  final List<String> deportes;
  final int radioKm;
  final List<String> franjas;
  final String dias;
  final bool avisos;
  final bool disponible;
  final bool tieneUbicacion;

  const PrefsJuego({
    this.deportes = const [],
    this.radioKm = Juego.radioDefault,
    this.franjas = const [],
    this.dias = 'todos',
    this.avisos = false,
    this.disponible = false,
    this.tieneUbicacion = false,
  });

  factory PrefsJuego.de(Map m) => PrefsJuego(
        deportes: [for (final d in (m['deportes'] as List? ?? const [])) d.toString()],
        radioKm: (m['radio_km'] as num?)?.toInt() ?? Juego.radioDefault,
        franjas: [for (final f in (m['franjas'] as List? ?? const [])) f.toString()],
        dias: (m['dias'] ?? 'todos').toString(),
        avisos: m['avisos'] == true,
        disponible: m['disponible'] == true,
        tieneUbicacion: m['tiene_ubicacion'] == true,
      );

  Map<String, dynamic> toJson() => {
        'deportes': deportes,
        'radio_km': radioKm,
        'franjas': franjas,
        'dias': dias,
        'avisos': avisos,
        'disponible': disponible,
        'tiene_ubicacion': tieneUbicacion,
      };
}

/// Un jugador disponible cerca (sin coordenadas: solo la distancia redondeada).
class JugadorDisponible {
  final String email;
  final String nombre;
  final String foto;
  final double? nivel;
  final String banda;
  final double km;
  final List<String> franjas;

  const JugadorDisponible({
    required this.email,
    required this.nombre,
    required this.foto,
    required this.nivel,
    required this.banda,
    required this.km,
    required this.franjas,
  });

  factory JugadorDisponible.de(Map m) => JugadorDisponible(
        email: (m['email'] ?? '').toString(),
        nombre: (m['nombre'] ?? '').toString(),
        foto: (m['foto'] ?? '').toString(),
        nivel: (m['nivel'] as num?)?.toDouble(),
        banda: (m['banda'] ?? 'intermedio').toString(),
        km: (m['km'] as num?)?.toDouble() ?? 0,
        franjas: [for (final f in (m['franjas'] as List? ?? const [])) f.toString()],
      );
}
