import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

import '../config/pais.dart';
import '../models/models.dart';
import '../utils/geo.dart';
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
/// Un lugar sugerido por el autocompletado (nombre + dirección + coordenadas).
/// Se usa para que el usuario ELIJA su sede filtrando por ubicación real de
/// Google, en vez de escribir texto libre sin geolocalizar.
class LugarSugerido {
  final String nombre;
  final String direccion;
  final LatLng ubicacion;
  const LugarSugerido(
      {required this.nombre, required this.direccion, required this.ubicacion});

  /// Texto para la caja de opciones: "Nombre — dirección" (si hay dirección).
  String get etiqueta =>
      direccion.trim().isEmpty ? nombre : '$nombre — $direccion';
}

class PlacesService {
  // Key dedicada a Places (web service). Si no se define, cae a la del mapa.
  static const _placesKey = String.fromEnvironment('PLACES_API_KEY');
  static const _mapsKey = String.fromEnvironment('MAPS_API_KEY');
  static String get _key => _placesKey.isNotEmpty ? _placesKey : _mapsKey;

  static bool get disponible => _key.isNotEmpty;

  /// URL de un MAPA ESTÁTICO (Google Static Maps) centrado en (lat,lng) con un
  /// pin rojo — para la previsualización de ubicación en el chat, estilo
  /// WhatsApp. Devuelve '' si no hay key (la tarjeta cae a un placeholder).
  static String mapaEstaticoUrl(double lat, double lng,
      {int zoom = 15, int w = 640, int h = 320}) {
    // Static Maps es una llamada WEB → usa la key web (Places) si está, que no
    // suele tener la restricción de Android de la key del mapa.
    if (!disponible) return '';
    final c = '$lat,$lng';
    return 'https://maps.googleapis.com/maps/api/staticmap'
        '?center=$c&zoom=$zoom&size=${w}x$h&scale=2'
        '&markers=color:red%7C$c&key=$_key';
  }

  /// AUTOCOMPLETADO de lugares por texto, filtrando por UBICACIÓN. Devuelve
  /// sugerencias reales de Google (nombre + dirección + coordenadas) para que el
  /// usuario elija su sede en vez de escribir texto sin geolocalizar. Sesga por
  /// [centro] si se pasa (locationBias) y por el país activo (regionCode).
  /// Fail-safe: [] ante error/timeout o sin key.
  static Future<List<LugarSugerido>> autocompletarLugar(String query,
      {LatLng? centro}) async {
    final q = query.trim();
    if (q.length < 3 || !disponible) return const [];
    try {
      final uri = Uri.https('places.googleapis.com', '/v1/places:searchText');
      final body = <String, dynamic>{
        'textQuery': q,
        'languageCode': 'es',
        'regionCode': paisActual.iso,
        'maxResultCount': 6,
      };
      if (centro != null) {
        body['locationBias'] = {
          'circle': {
            'center': {
              'latitude': centro.latitude,
              'longitude': centro.longitude,
            },
            'radius': 30000.0, // 30 km alrededor de la referencia
          },
        };
      }
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              'X-Goog-Api-Key': _key,
              'X-Goog-FieldMask':
                  'places.displayName,places.formattedAddress,places.location',
            },
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return const [];
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final out = <LugarSugerido>[];
      for (final p in (data['places'] as List? ?? const [])) {
        final m = p as Map<String, dynamic>;
        final loc = m['location'] as Map<String, dynamic>?;
        if (loc == null) continue;
        final nombre = (m['displayName']?['text'] ?? '') as String;
        final dir = (m['formattedAddress'] ?? '') as String;
        out.add(LugarSugerido(
          nombre: nombre.isNotEmpty ? nombre : dir,
          direccion: dir,
          ubicacion: LatLng(
            (loc['latitude'] as num).toDouble(),
            (loc['longitude'] as num).toDouble(),
          ),
        ));
      }
      return out;
    } catch (_) {
      return const [];
    }
  }

  /// Consultas de texto que cubren los deportes del marketplace en Lima.
  /// Incluye jerga peruana (pichanga, fulbito, grass/loza, fútbol 5/6/7) para
  /// no perder canchas informales, y términos de CLUBES deportivos (country
  /// club, polideportivo, racquet) para que también entren al radar.
  static const _consultas = [
    'canchas de fútbol',
    'cancha sintética de fútbol',
    'pichanga',
    'grass sintético',
    'fútbol 7',
    'complejo deportivo',
    'club de tenis',
    'cancha de tenis',
    'cancha de pádel',
    'club de pádel',
    'cancha de pickleball',
    'cancha de vóley',
    'cancha de básquet',
    'club deportivo',
    'polideportivo',
    'country club',
    'racquet club',
    'club de regatas',
    'club campestre',
  ];

  /// Busca canchas cerca de [centro] dentro de [radioMetros].
  ///
  /// Preferimos la **Edge Function de Supabase** (`places-cerca`), que guarda la
  /// API key del lado servidor (no viaja en el APK). Si la función no está
  /// desplegada, cae al llamado directo a Google con la key del cliente.
  ///
  /// [conFotos]: si es false (por defecto) la función NO resuelve las fotos en el
  /// servidor y responde **mucho más rápido** (las canchas salen al instante).
  /// La app vuelve a llamar con `conFotos: true` para enriquecer las fotos luego.
  static Future<List<Cancha>> canchasCerca(
    LatLng centro, {
    double radioMetros = 20000, // 20 km: cubre el corredor Ñaña–Ricardo Palma
    bool conFotos = false,
  }) async {
    final viaFuncion = await _viaEdgeFunction(centro, radioMetros, conFotos);
    if (viaFuncion != null) return viaFuncion;

    if (!disponible) return [];
    final uri = Uri.https('places.googleapis.com', '/v1/places:searchText');
    // Las consultas se lanzan EN PARALELO (antes iban en serie: 11 × hasta 8s).
    // Así el tiempo total ≈ la consulta más lenta, no la suma de todas.
    final listas = await Future.wait(
      _consultas.map((q) => _consultaUna(uri, q, centro, radioMetros)),
    );
    final porId = <String, Cancha>{};
    for (final lista in listas) {
      for (final c in lista) {
        porId[c.id] = c;
      }
    }
    return porId.values.toList();
  }

  /// Una sola consulta de texto a Places (New). Fail-safe: ante error/timeout
  /// devuelve lista vacía para no frenar a las demás (corren en paralelo).
  static Future<List<Cancha>> _consultaUna(
      Uri uri, String q, LatLng centro, double radioMetros) async {
    try {
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              'X-Goog-Api-Key': _key,
              'X-Goog-FieldMask':
                  'places.id,places.displayName,places.location,'
                      'places.formattedAddress,places.types,places.photos',
            },
            body: jsonEncode({
              'textQuery': q,
              'languageCode': 'es',
              'regionCode': paisActual.iso, // país detectado (PE/BO/…), no fijo
              'maxResultCount': 20,
              // Rankear por DISTANCIA (no relevancia): así Google devuelve las
              // canchas MÁS CERCANAS al usuario primero, en vez de las más
              // "populares". Clave para que salga la cancha del barrio.
              'rankPreference': 'DISTANCE',
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
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return const []; // API no habilitada / key
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final out = <Cancha>[];
      for (final p in (body['places'] as List? ?? [])) {
        final c = _aCancha(p as Map<String, dynamic>);
        if (c != null) out.add(c);
      }
      return out;
    } catch (_) {
      return const []; // fail-safe
    }
  }

  /// Busca UN lugar por [nombre] cerca de [centro] y devuelve sus FOTOS reales
  /// de Google. Sirve para enriquecer lugares SEMBRADOS (que no pasan por el
  /// descubrimiento normal). Solo acepta el match si está a ≤1.5 km del punto
  /// esperado (evita traer un homónimo lejano). Fail-safe: [] ante cualquier
  /// error o si no hay key de Places en el cliente.
  static Future<List<String>> fotosDeLugar(String nombre, LatLng centro) async {
    if (!disponible) return const [];
    try {
      final uri = Uri.https('places.googleapis.com', '/v1/places:searchText');
      final resp = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              'X-Goog-Api-Key': _key,
              'X-Goog-FieldMask':
                  'places.id,places.displayName,places.location,places.photos',
            },
            body: jsonEncode({
              'textQuery': nombre,
              'languageCode': 'es',
              'regionCode': paisActual.iso, // país detectado (PE/BO/…), no fijo
              'maxResultCount': 10,
              // Sesgo FUERTE al punto sembrado para que gane la sede local
              // (no el club principal homónimo, que suele estar lejos).
              'locationBias': {
                'circle': {
                  'center': {
                    'latitude': centro.latitude,
                    'longitude': centro.longitude,
                  },
                  'radius': 1500,
                },
              },
            }),
          )
          .timeout(const Duration(seconds: 6));
      if (resp.statusCode != 200) return const [];
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final places = (body['places'] as List?) ?? const [];
      // Toma el lugar MÁS CERCANO al punto esperado (≤2 km), sin filtrar por
      // deporte: solo queremos sus fotos para enriquecer el club sembrado.
      Map<String, dynamic>? mejor;
      double mejorKm = 1e9;
      for (final p in places) {
        final loc = (p as Map)['location'] as Map?;
        if (loc == null) continue;
        final d = distanciaKm(
            centro,
            LatLng((loc['latitude'] as num).toDouble(),
                (loc['longitude'] as num).toDouble()));
        if (d < mejorKm) {
          mejorKm = d;
          mejor = p.cast<String, dynamic>();
        }
      }
      if (mejor == null || mejorKm > 2.0) return const [];
      return _fotosDe(mejor);
    } catch (_) {
      return const [];
    }
  }

  /// Intenta vía Edge Function de Supabase. Devuelve la lista (posiblemente
  /// vacía) si la función respondió; o null si no está disponible/desplegada,
  /// para que el caller use el fallback directo a Google.
  static Future<List<Cancha>?> _viaEdgeFunction(
      LatLng centro, double radioMetros, bool conFotos) async {
    if (!SupabaseService.disponible) return null;
    try {
      final res = await SupabaseService.client.functions.invoke(
        'places-cerca',
        body: {
          'lat': centro.latitude,
          'lng': centro.longitude,
          'radius': radioMetros,
          'fotos': conFotos, // false = respuesta rápida sin resolver fotos
          'region': paisActual.iso, // país detectado (PE/BO/…) para el regionCode
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

    final fotos = _fotosDe(p);

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
      verificada: false, // sin reclamar: NO es verificada (default del modelo es true)
      fotoUrl: fotos.isNotEmpty ? fotos.first : null,
      fotos: fotos,
    );
  }

  /// Fotos reales del lugar. Si vienen de la Edge Function ya son URLs públicas
  /// (`fotos`). Si es el modo directo, construimos la URL de la Place Photo
  /// (New) con la key del cliente (solo en fallback).
  static List<String> _fotosDe(Map<String, dynamic> p) {
    final yaResueltas = p['fotos'];
    if (yaResueltas is List && yaResueltas.isNotEmpty) {
      return yaResueltas.map((e) => e.toString()).toList();
    }
    final photos = p['photos'];
    if (photos is List && _key.isNotEmpty) {
      final urls = <String>[];
      for (final ph in photos.take(3)) {
        final name = (ph is Map) ? ph['name']?.toString() : null;
        if (name != null) {
          urls.add(
              'https://places.googleapis.com/v1/$name/media?maxWidthPx=800&key=$_key');
        }
      }
      return urls;
    }
    return const [];
  }

  // Tipos de Google que NO son canchas (descartar aunque el nombre confunda).
  static const _tiposExcluidos = {
    'gym', 'store', 'shopping_mall', 'clothing_store', 'shoe_store',
    'sporting_goods_store', 'school',
    'university', 'lodging', 'gas_station', 'supermarket', 'restaurant',
    'bar', 'doctor', 'hospital', 'pharmacy', 'bank',
  };

  // Palabras en el nombre que delatan que NO es una cancha de alquiler.
  // (Nota: 'academia' NO se excluye: las academias de tenis/pádel SÍ son canchas.)
  static const _palabrasExcluidas = [
    'gimnasio', 'gym', 'tienda', 'store', 'colegio',
    'universidad', 'federación', 'federacion', 'crossfit', 'spinning',
    'natación', 'natacion', 'piscina', 'billar', 'bowling',
    // Zapaterías/ropa deportiva: "tenis" en jerga = zapatillas. NO son canchas.
    'zapatilla', 'zapato', 'calzado', 'sneaker', 'sport wear', 'sportwear',
    'deportes americano', 'ropa deportiva', 'boutique', 'outlet',
    // Tiendas de artículos deportivos (retail): en LatAm suelen llamarse en
    // inglés "Sport Center" y Google a veces las etiqueta como recinto
    // deportivo. NO son canchas de alquiler (el dueño real puede registrarla
    // a mano por el flujo de dueño).
    'sport center', 'sports center', 'sport centre', 'sports centre',
    'sportcenter', 'sport shop', 'sports shop', 'deportes en general',
    'importadora', 'distribuidora', 'comercializadora', 'ferretería',
    'ferreteria',
    // Deportes que NO son de cancha reservable en el marketplace:
    'skate', 'skatepark', 'patineta', 'patinaje', 'monopatín', 'monopatin',
    'roller', 'bmx', 'ciclovía', 'ciclovia', 'pista atlética', 'pista atletica',
    'atletismo', 'skatboard', 'patinódromo', 'patinodromo',
    // Ciclismo / bicicletas (tiendas, bike parks, pistas): no son canchas.
    'bike', 'bicicleta', 'bici ', 'ciclismo', 'ciclista', 'cycling',
    'mountain bike', 'bikepark', 'bike park', 'downhill', 'mtb ',
    // Atracciones/servicios DENTRO de un club que no son canchas de alquiler:
    'laguna', 'acuático', 'acuatico', 'waterpark', 'parque acuático',
    'restaurante', 'hotel', 'spa', 'juegos para niños', 'zoológico', 'zoologico',
    // Edificios administrativos/religiosos de un club (no son canchas):
    'asociación', 'asociacion', 'oficina', 'administración', 'administracion',
    'capilla', 'parroquia', 'iglesia',
    // Lozas deportivas: canchas públicas municipales de barrio, no locales
    // reclamables/alquilables → fuera del marketplace.
    'loza deportiva', 'losa deportiva', 'loza multideportiva',
    'losa multideportiva', 'loza recreativa', 'losa recreativa',
    'loza multiuso', 'losa multiuso',
    // Gimnasios / fitness / entrenamiento: Google los etiqueta como
    // "sports_activity_location" y se colaban como canchas de fútbol.
    'fitness', 'wellness', 'entrenamiento funcional', 'funcional',
    'aeróbic', 'aerobic', 'aerobicos', 'aeróbicos',
    // Estudios de baile/danza (no son canchas reservables):
    'baile', 'danza', 'dance', 'ballet', 'zumba', 'salsa', 'bachata',
    // Yoga / pilates:
    'yoga', 'pilates',
    // Artes marciales / boxeo (dojos, no canchas de alquiler):
    'artes marciales', 'karate', 'kárate', 'taekwondo', 'taek won do', 'judo',
    'muay thai', 'muaythai', 'kickboxing', 'boxeo', 'box club', 'dojo',
    'jiu jitsu', 'jiujitsu', 'mma',
    // Hípica / ecuestre (clubes de equitación, no canchas del marketplace):
    'ecuestre', 'equitación', 'equitacion', 'hípic', 'hipic', 'equino',
    'equina', 'caballeriza', 'caballo', 'establo', 'club hipico', 'club hípico',
    'polo y equitación', 'polo y equitacion',
  ];

  // Términos en el NOMBRE que gritan "recinto deportivo" con tanta fuerza que un
  // tipo mal puesto por Google (school/university/gym) no debe tumbarlos: muchos
  // complejos deportivos de barrio están dentro de un colegio o mal etiquetados.
  // (Las lozas deportivas municipales se excluyen aparte: ver _palabrasExcluidas.)
  static const _nombreFuerteDeportivo = [
    'complejo deportivo', 'polideportivo', 'centro deportivo', 'club deportivo',
    'campo deportivo', 'villa deportiva',
    'estadio', 'cancha', 'canchita', 'grass sintétic', 'grass sintetic',
  ];

  /// Heurística de deporte por nombre/tipos del lugar. Devuelve null si no
  /// parece una cancha de alquiler (gimnasios, tiendas, etc. quedan fuera).
  static Deporte? _deporteDe(String nombre, List<String> tipos) {
    final n = nombre.toLowerCase();
    final nombreEsDeportivoFuerte = _nombreFuerteDeportivo.any(n.contains);

    // 1) Descartes duros por tipo o por nombre. Si el NOMBRE ya grita "deportivo"
    //    (complejo, polideportivo, estadio, loza…), NO dejamos que los tipos
    //    "gym"/"school"/"university" de Google lo descarten (falso negativo
    //    típico: la única cancha del barrio está en un colegio). Los tipos
    //    claramente no deportivos (tienda, restaurante, hospital…) SÍ siguen
    //    excluyendo aunque el nombre sea deportivo.
    final tiposExcluidosEfectivos = nombreEsDeportivoFuerte
        ? _tiposExcluidos.difference(const {'gym', 'school', 'university'})
        : _tiposExcluidos;
    if (tipos.any(tiposExcluidosEfectivos.contains)) return null;
    if (_palabrasExcluidas.any(n.contains)) return null;

    // Señales de que SÍ es un recinto (para desambiguar nombres tramposos).
    final tiposDeportivos = tipos.any(const {
      'stadium', 'arena', 'sports_complex', 'sports_club',
      'sports_activity_location', 'recreation_center', 'athletic_field',
      'country_club',
    }.contains);
    final coSenalCancha = nombreEsDeportivoFuerte ||
        n.contains('club') ||
        n.contains('academia') ||
        n.contains('court') ||
        n.contains('lawn') ||
        n.contains('sede') ||
        n.contains('country');

    // 2) Señal positiva por deporte en el nombre.
    if (n.contains('pickleball') || n.contains('pickle')) {
      return Deporte.pickleball;
    }
    if (n.contains('pádel') || n.contains('padel')) return Deporte.padel;
    if (n.contains('vóley') ||
        n.contains('voley') ||
        n.contains('voleibol') ||
        n.contains('vóleibol') ||
        n.contains('volley')) {
      return Deporte.voley;
    }
    if (n.contains('básquet') ||
        n.contains('basquet') ||
        n.contains('básket') ||
        n.contains('basket')) {
      return Deporte.basquet;
    }
    // 'raqueta'/'racquet' son inequívocos (deporte de raqueta) → tenis directo.
    if (n.contains('raqueta') || n.contains('racquet')) return Deporte.tenis;
    // 'tenis'/'tennis' es AMBIGUO (en jerga = zapatillas): solo cuenta como
    // cancha si además hay señal de recinto (club/cancha/academia/…) o un tipo
    // deportivo de Google. Así una zapatería "Tenis Americanos" no entra.
    if ((n.contains('tenis') || n.contains('tennis')) &&
        (coSenalCancha || tiposDeportivos)) {
      return Deporte.tenis;
    }
    if (n.contains('fútbol') ||
        n.contains('futbol') ||
        n.contains('pichang') ||      // pichanga / pichanguita (jerga PE)
        n.contains('golazo') ||
        n.contains('fulbito') ||
        n.contains('futsal') ||
        n.contains('cancha') ||
        n.contains('canchita') ||
        n.contains('sintétic') ||
        n.contains('sintetic') ||
        n.contains('grass') ||
        n.contains('complejo deportivo') ||
        n.contains('club deportivo') ||
        n.contains('centro deportivo') ||
        n.contains('polideportivo') ||
        n.contains('country club') ||
        n.contains('club de campo') ||
        n.contains('club campestre') ||
        n.contains('regatas') ||       // Club de Regatas Lima (sedes)
        n.contains('villa club') ||
        n.contains('golf club') ||
        n.contains('club de golf') ||
        n.contains('polo club') ||
        n.contains('lawn tennis') ||
        n.contains('sporting') ||
        n.contains('estadio')) {
      return Deporte.futbol;
    }

    // 3) Sin señal de deporte en el nombre.
    // 3a) Tipos FUERTES de campo/cancha (estadio, arena, complejo, campo,
    //     country club): son inequívocamente recintos de cancha → se aceptan
    //     aunque el nombre no diga nada.
    if (tipos.contains('stadium') ||
        tipos.contains('arena') ||
        tipos.contains('sports_complex') ||
        tipos.contains('athletic_field') ||
        tipos.contains('country_club')) {
      return Deporte.futbol;
    }
    // 3b) Tipos GENÉRICOS (sports_activity_location / recreation_center /
    //     sports_club): Google los usa para gimnasios, estudios de baile, artes
    //     marciales, clubes ecuestres, etc. NO son canchas por sí solos. Solo se
    //     aceptan si el NOMBRE además tiene señal de recinto (club/cancha/
    //     academia/complejo deportivo…). Así "EquiBolivia" o "Burn Fitness
    //     Center" quedan fuera, pero "Cancha X" o "Club Deportivo Y" entran.
    if ((tipos.contains('sports_activity_location') ||
            tipos.contains('recreation_center') ||
            tipos.contains('sports_club')) &&
        coSenalCancha) {
      return Deporte.futbol;
    }
    return null; // por defecto, no lo metemos (evita falsos positivos)
  }
}
