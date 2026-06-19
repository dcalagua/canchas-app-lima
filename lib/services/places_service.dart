import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';
import 'supabase_service.dart';

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
  // Key dedicada a Places (web service). Si no se define, cae a la del mapa.
  static const _placesKey = String.fromEnvironment('PLACES_API_KEY');
  static const _mapsKey = String.fromEnvironment('MAPS_API_KEY');
  static String get _key => _placesKey.isNotEmpty ? _placesKey : _mapsKey;

  static bool get disponible => _key.isNotEmpty;

  /// Consultas de texto que cubren los deportes del marketplace en Lima.
  static const _consultas = [
    'canchas de fútbol',
    'cancha sintética de fútbol',
    'club de tenis',
    'cancha de pádel',
  ];

  /// Busca canchas cerca de [centro] dentro de [radioMetros].
  ///
  /// Preferimos la **Edge Function de Supabase** (`places-cerca`), que guarda la
  /// API key del lado servidor (no viaja en el APK). Si la función no está
  /// desplegada, cae al llamado directo a Google con la key del cliente.
  static Future<List<Cancha>> canchasCerca(
    LatLng centro, {
    double radioMetros = 4000,
  }) async {
    final viaFuncion = await _viaEdgeFunction(centro, radioMetros);
    if (viaFuncion != null) return viaFuncion;

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

  /// Intenta vía Edge Function de Supabase. Devuelve la lista (posiblemente
  /// vacía) si la función respondió; o null si no está disponible/desplegada,
  /// para que el caller use el fallback directo a Google.
  static Future<List<Cancha>?> _viaEdgeFunction(
      LatLng centro, double radioMetros) async {
    if (!SupabaseService.disponible) return null;
    try {
      final res = await SupabaseService.client.functions.invoke(
        'places-cerca',
        body: {
          'lat': centro.latitude,
          'lng': centro.longitude,
          'radius': radioMetros,
        },
      );
      final data = res.data;
      if (data is! Map) return null; // respuesta inesperada → fallback
      final places = data['places'];
      if (places is! List) return null;
      final porId = <String, Cancha>{};
      for (final p in places) {
        if (p is Map) {
          final c = _aCancha(Map<String, dynamic>.from(p));
          if (c != null) porId[c.id] = c;
        }
      }
      return porId.values.toList();
    } catch (_) {
      return null; // función no desplegada o error → fallback directo
    }
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

  // Tipos de Google que NO son canchas (descartar aunque el nombre confunda).
  static const _tiposExcluidos = {
    'gym', 'store', 'shopping_mall', 'clothing_store', 'school',
    'university', 'lodging', 'gas_station', 'supermarket', 'restaurant',
    'bar', 'doctor', 'hospital', 'pharmacy', 'bank',
  };

  // Palabras en el nombre que delatan que NO es una cancha de alquiler.
  static const _palabrasExcluidas = [
    'gimnasio', 'gym', 'tienda', 'store', 'academia', 'colegio',
    'universidad', 'federación', 'federacion', 'crossfit', 'spinning',
    'natación', 'natacion', 'piscina', 'billar', 'bowling',
  ];

  /// Heurística de deporte por nombre/tipos del lugar. Devuelve null si no
  /// parece una cancha de alquiler (gimnasios, tiendas, etc. quedan fuera).
  static Deporte? _deporteDe(String nombre, List<String> tipos) {
    final n = nombre.toLowerCase();

    // 1) Descartes duros por tipo o por nombre.
    if (tipos.any(_tiposExcluidos.contains)) return null;
    if (_palabrasExcluidas.any(n.contains)) return null;

    // 2) Señal positiva por deporte en el nombre.
    if (n.contains('pádel') || n.contains('padel')) return Deporte.padel;
    if (n.contains('tenis') || n.contains('tennis')) return Deporte.tenis;
    if (n.contains('fútbol') ||
        n.contains('futbol') ||
        n.contains('cancha') ||
        n.contains('canchita') ||
        n.contains('sintétic') ||
        n.contains('sintetic') ||
        n.contains('grass') ||
        n.contains('loza deportiva') ||
        n.contains('complejo deportivo') ||
        n.contains('fulbito') ||
        n.contains('futsal')) {
      return Deporte.futbol;
    }

    // 3) Sin señal en el nombre: solo si Google lo marca como recinto deportivo.
    if (tipos.contains('stadium') ||
        tipos.contains('sports_complex') ||
        tipos.contains('athletic_field')) {
      return Deporte.futbol;
    }
    return null; // por defecto, no lo metemos (evita falsos positivos)
  }
}
