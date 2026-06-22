import 'package:google_maps_flutter/google_maps_flutter.dart';

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

  /// Club verificado: está en Pichangol y al menos una de sus canchas pasó la
  /// verificación. Habilita el sello público "✓ Verificada".
  bool get verificada => registrada && canchas.any((c) => c.verificada);

  /// Deportes únicos del club, en orden de aparición.
  List<Deporte> get deportes {
    final vistos = <Deporte>[];
    for (final c in canchas) {
      if (!vistos.contains(c.deporte)) vistos.add(c.deporte);
    }
    return vistos;
  }

  /// Precio "desde" entre las canchas con precio conocido (>0).
  int? get precioDesde {
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
    return [
      for (final key in orden)
        Club(
          id: key,
          nombre: key.startsWith('gp:')
              ? mapa[key]!.first.nombre
              : mapa[key]!.first.club,
          canchas: mapa[key]!,
        ),
    ];
  }
}
