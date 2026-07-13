import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../utils/geo.dart';
import 'models.dart';

/// Vista de "club": un local que agrupa varias canchas (posiblemente de
/// distintos deportes). No es una entidad persistida: se deriva en runtime
/// agrupando las canchas por club, alineado al rediseño (un local = N canchas).
class Club {
  final String id; // clave de agrupación
  final String nombre;
  final List<Cancha> canchas;

  Club({required this.id, required this.nombre, required this.canchas});

  Cancha get principal => canchas.first;
  LatLng get ubicacion => principal.ubicacion;
  Distrito get distrito => principal.distrito;
  String get barrio => principal.distrito.etiqueta;
  String? get direccion =>
      canchas.map((c) => c.direccion).firstWhere((d) => d != null, orElse: () => null);

  bool get clubFundador => canchas.any((c) => c.clubFundador);
  bool get registrada => canchas.any((c) => c.registrada);

  /// Palabras que delatan un CLUB formal (membresía / country club) en el
  /// nombre del local. Sirve para separarlos de las canchas de alquiler suelto.
  static const _palabrasClub = [
    'club',
    'country',
    'villa',
    'lawn',
    'golf',
    'regatas',
    'campestre',
    'terrazas',
    'racquet',
    'raqueta',
    'polo',
  ];

  /// ¿Es un CLUB formal (Country Club El Bosque, Villa Club, Regatas…)? Se
  /// agrupa aparte del alquiler suelto. Regla: nombre con palabra de club, o
  /// club fundador del piloto. OJO: tener varios deportes NO basta para ser
  /// "club" (p. ej. "Campo Deportivo Machuca" alquila fútbol y tenis, pero no es
  /// un club de membresía). Solo cuenta el nombre o el sello fundador.
  bool get esClubFormal {
    final n = nombre.toLowerCase();
    if (_palabrasClub.any(n.contains)) return true;
    return clubFundador;
  }

  /// Club verificado: está en Pichangol y al menos una de sus canchas pasó la
  /// verificación. Habilita el sello público "✓ Verificada".
  bool get verificada => registrada && canchas.any((c) => c.verificada);

  /// Deportes únicos del club, en orden de aparición. Incluye TODOS los deportes
  /// de cada cancha (una loza multiuso aporta fútbol + vóley + básquet).
  List<Deporte> get deportes {
    final vistos = <Deporte>[];
    for (final c in canchas) {
      for (final d in c.deportesJugables) {
        if (!vistos.contains(d)) vistos.add(d);
      }
    }
    return vistos;
  }

  /// Precio "desde" entre las canchas con precio conocido (>0).
  double? get precioDesde {
    final precios = canchas.where((c) => c.precioHora > 0).map((c) => c.precioHora);
    if (precios.isEmpty) return null;
    return precios.reduce((a, b) => a < b ? a : b);
  }

  /// Rating presentacional, determinístico por nombre (4.6–4.9) hasta tener
  /// reseñas reales. Los clubes descubiertos (sin registrar) no muestran rating.
  double get rating {
    final h = nombre.codeUnits.fold<int>(0, (a, b) => a + b);
    return 4.6 + (h % 4) * 0.1;
  }

  /// Agrupa una lista de canchas en clubes. Las registradas se agrupan por el
  /// nombre del club; las descubiertas (Google) quedan como un club propio.
  static List<Club> agrupar(List<Cancha> canchas) {
    final orden = <String>[];
    final mapa = <String, List<Cancha>>{};
    for (final c in canchas) {
      final key = c.registrada ? 'club:${c.club}' : 'gp:${c.id}';
      mapa.putIfAbsent(key, () {
        orden.add(key);
        return [];
      }).add(c);
    }
    final clubs = [
      for (final key in orden)
        Club(
          id: key,
          nombre: key.startsWith('gp:')
              ? mapa[key]!.first.nombre
              : mapa[key]!.first.club,
          canchas: mapa[key]!,
        ),
    ];
    return _fusionarEnClubCercano(clubs);
  }

  /// Radio para considerar que un pin de Google es parte del MISMO recinto que
  /// un club formal (un country club ocupa varias hectáreas y aparece en Google
  /// como varios lugares: el club + sus canchas + atracciones).
  static const double _fusionRadioKm = 0.5; // 500 m (country clubs son grandes)

  /// Absorbe lugares DESCUBIERTOS (Google, aún sin reclamar) dentro de un CLUB
  /// formal cercano, para que un mismo recinto no salga como varias tarjetas.
  /// Solo fusiona HACIA clubes formales (Regatas, Country Club…): nunca junta
  /// canchas sueltas entre sí. Los clubes ya registrados no se tocan.
  static List<Club> _fusionarEnClubCercano(List<Club> clubs) {
    final formales = clubs
        .where((c) => c.id.startsWith('gp:') && c.esClubFormal)
        .toList();
    if (formales.isEmpty) return clubs;
    final absorbidos = <String>{};
    for (final c in clubs) {
      if (!c.id.startsWith('gp:') || c.esClubFormal) continue; // solo pins sueltos
      for (final f in formales) {
        if (distanciaKm(f.ubicacion, c.ubicacion) <= _fusionRadioKm) {
          f.canchas.addAll(c.canchas); // pasa a ser una cancha del club
          absorbidos.add(c.id);
          break;
        }
      }
    }
    if (absorbidos.isEmpty) return clubs;
    return clubs.where((c) => !absorbidos.contains(c.id)).toList();
  }
}
