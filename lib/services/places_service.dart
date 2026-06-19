import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';

/// Descubre canchas REALES cerca de una ubicación usando la **Places API (New)**
/// de Google (endpoint `places:searchText`). Son canchas que existen en Google
/// Maps pero aún no están en Pichangol: las marcamos con `registrada = false`
/// para invitar al dueño a reclamarlas ("ya estás en el mapa, actívala").
///
/// La API key llega por --dart-define=MAPS_API_KEY (misma key del mapa). Para
/// que funcione hay que habilitar **Places API (New)** en Google Cloud y que la
/// key NO esté restringida solo a apps Android (las llamadas web service la
/// rechazarían). Todo es fail-safe: si algo falla, devuelve vacío.
class PlacesService {
  static const _key = String.fromEnvironment('MAPS_API_KEY');

  static bool get disponible => _key.isNotEmpty;

  /// Consultas de texto que cubren los deportes del marketplace en Lima.
  static const _consultas = [
    'canchas de fútbol',
    'cancha sintética de fútbol',
    'club de tenis',
    'cancha de pádel',
  ];

  /// Busca canchas cerca de [centro] dentro de [radioMetros].
  static Future<List<Cancha>> canchasCerca(
    LatLng centro, {
    double radioMetros = 4000,
  }) async {
    if (!disponible) return [];
    final uri = Uri.https('places.googleapis.com', '/v1/places:searchText');
    final porId = <String, Cancha>{};
    for (final q in _consultas) {
      try {
        final resp = await http
            .post(
              uri,
              headers: {
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': _key,
                'X-Goog-FieldMask':
                    'places.id,places.displayName,places.location,'
                        'places.formattedAddress,places.types',
              },
              body: jsonEncode({
                'textQuery': q,
                'languageCode': 'es',
                'regionCode': 'PE',
                'maxResultCount': 20,
                'locationBias': {
                  'circle': {
                    'center': {
                      'latitude': centro.latitude,
                      'longitude': centro.longitude,
                    },
                    'radius': radioMetros,
                  },
                },
              }),
            )
            .timeout(const Duration(seconds: 8));
        if (resp.statusCode != 200) continue; // p.ej. API no habilitada / key
        final body = jsonDecode(resp.body) as Map<String, dynamic>;
        for (final p in (body['places'] as List? ?? [])) {
          final c = _aCancha(p as Map<String, dynamic>);
          if (c != null) porId[c.id] = c;
        }
      } catch (_) {
        // fail-safe: ignora esta consulta y sigue
      }
    }
    return porId.values.toList();
  }

  static Cancha? _aCancha(Map<String, dynamic> p) {
    final id = p['id'] as String?;
    final nombre =
        (p['displayName'] as Map<String, dynamic>?)?['text'] as String?;
    final loc = p['location'] as Map<String, dynamic>?;
    if (id == null || nombre == null || loc == null) return null;
    final lat = (loc['latitude'] as num?)?.toDouble();
    final lng = (loc['longitude'] as num?)?.toDouble();
    if (lat == null || lng == null) return null;

    final tipos = ((p['types'] as List?) ?? []).cast<String>();
    final deporte = _deporteDe(nombre, tipos);
    if (deporte == null) return null; // no parece una cancha deportiva

    return Cancha(
      id: 'gp_$id',
      nombre: nombre,
      club: nombre,
      distrito: Distrito.sanBorja, // referencial; lo real es lat/lng + dirección
      deporte: deporte,
      precioHora: 0, // desconocido hasta que el dueño la reclame
      ubicacion: LatLng(lat, lng),
      clubFundador: false,
      digitalizada: false,
      direccion: p['formattedAddress'] as String?,
      registrada: false, // descubierta en Google, aún no en Pichangol
    );
  }

  /// Heurística de deporte por nombre/tipos del lugar.
  static Deporte? _deporteDe(String nombre, List<String> tipos) {
    final n = nombre.toLowerCase();
    if (n.contains('pádel') || n.contains('padel')) return Deporte.padel;
    if (n.contains('tenis') || n.contains('tennis')) return Deporte.tenis;
    if (n.contains('fútbol') ||
        n.contains('futbol') ||
        n.contains('cancha') ||
        n.contains('sintétic') ||
        n.contains('sintetic') ||
        n.contains('grass') ||
        n.contains('loza') ||
        n.contains('complejo deportivo') ||
        n.contains('sport')) {
      return Deporte.futbol;
    }
    // Si Google lo clasifica como recinto deportivo, asumimos fútbol (lo común).
    if (tipos.contains('stadium') ||
        tipos.contains('sports_complex') ||
        tipos.contains('sports_activity_location')) {
      return Deporte.futbol;
    }
    return null;
  }
}
