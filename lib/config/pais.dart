import 'package:shared_preferences/shared_preferences.dart';

import '../utils/moneda.dart';

/// Configuración por PAÍS. El flujo del producto (reservas, reclamos,
/// destacados, saldos) es idéntico en todos lados; lo único que cambia por país
/// es la **moneda** (símbolo/ISO) y la **pasarela de pago** que se usa para
/// cobrar/recargar. Este archivo es la **fuente única** de esa configuración.
///
/// OJO — display-only por ahora: cambiar el símbolo NO convierte montos
/// (S/ 30 no se vuelve Bs 30). La conversión de tarifas reales por país es una
/// fase aparte. La **pasarela** concreta (Culqi / Libélula / …) se enchufa
/// cuando se defina; aquí solo se declara cuál corresponde a cada país.
class PaisConfig {
  /// Código ISO-3166 alpha-2 en mayúsculas: 'PE', 'BO', 'EC'.
  final String iso;

  /// Nombre legible para la UI ("Perú", "Bolivia").
  final String nombre;

  /// Símbolo de moneda para mostrar: 'S/', 'Bs', '$'.
  final String moneda;

  /// Código ISO de la moneda: 'PEN', 'BOB', 'USD'.
  final String monedaIso;

  /// Identificador de la pasarela de pago que corresponde a este país. Se usa
  /// para decidir qué integración de cobro/recarga activar. `'culqi'` (Perú),
  /// `'libelula'` (Bolivia, agregador: QR interoperable + tarjeta + Tigo Money),
  /// `'manual'` (aún sin pasarela: cobro fuera de app / por definir).
  final String pasarela;

  /// Nombre legible de la pasarela, para textos de diagnóstico/config.
  final String pasarelaNombre;

  /// Código telefónico internacional SIN el "+": '51' (PE), '591' (BO).
  final String codigoTel;

  /// Emoji de la bandera, para el prefijo de teléfono: '🇵🇪', '🇧🇴'.
  final String bandera;

  /// Nombre corto del documento de identidad del país: 'DNI' (PE), 'CI' (BO).
  final String docId;

  /// Longitud EXACTA del celular local (sin código de país): 9 (PE), 8 (BO).
  final int telLongitud;

  /// Longitud EXACTA del documento de identidad, o null si es variable (en
  /// Bolivia el CI no tiene largo fijo). Cuando es null no se valida el largo.
  final int? docLongitud;

  /// ¿Hay consulta automática del documento (RENIEC/Factiliza)? Solo Perú (DNI).
  final bool consultaDoc;

  /// Sufijo que se agrega al geocodificar una dirección escrita, para acotar la
  /// búsqueda al país correcto (ej. "Lima, Perú" / "Bolivia"). Evita que una
  /// dirección boliviana se resuelva en Perú.
  final String geocodeHint;

  /// Zonas operativas del país (slugs) para la cola del **Verificador de campo**:
  /// agrupan las visitas por área de la ciudad. Se muestran reemplazando "_" por
  /// espacio. En Perú son las zonas de Lima; en Bolivia/Ecuador, sus ciudades.
  final List<String> zonas;

  const PaisConfig({
    required this.iso,
    required this.nombre,
    required this.moneda,
    required this.monedaIso,
    required this.pasarela,
    required this.pasarelaNombre,
    required this.codigoTel,
    required this.bandera,
    required this.docId,
    required this.telLongitud,
    required this.docLongitud,
    required this.consultaDoc,
    required this.geocodeHint,
    required this.zonas,
  });
}

/// Países soportados por el piloto. Agregar uno nuevo = una entrada aquí.
const Map<String, PaisConfig> paisesSoportados = {
  'PE': PaisConfig(
    iso: 'PE',
    nombre: 'Perú',
    moneda: 'S/',
    monedaIso: 'PEN',
    pasarela: 'culqi',
    pasarelaNombre: 'Culqi (Yape · tarjeta)',
    codigoTel: '51',
    bandera: '🇵🇪',
    docId: 'DNI',
    telLongitud: 9,
    docLongitud: 8, // DNI peruano = 8 dígitos exactos
    consultaDoc: true, // consulta RENIEC vía Factiliza
    geocodeHint: 'Lima, Perú',
    zonas: [
      'lima_norte',
      'lima_sur',
      'lima_este',
      'lima_moderna',
      'callao',
    ],
  ),
  'BO': PaisConfig(
    iso: 'BO',
    nombre: 'Bolivia',
    moneda: 'Bs',
    monedaIso: 'BOB',
    // Pasarela por DEFINIR: Libélula es la candidata (QR interoperable + tarjeta
    // + Tigo Money en una sola integración). Hasta enchufarla, el cobro es
    // 'manual' en la práctica; el identificador queda listo para activar.
    pasarela: 'libelula',
    pasarelaNombre: 'Libélula (QR · tarjeta · Tigo Money)',
    codigoTel: '591',
    bandera: '🇧🇴',
    docId: 'CI', // Cédula de Identidad
    telLongitud: 8, // celular boliviano = 8 dígitos (empieza en 6 o 7)
    docLongitud: null, // el CI boliviano no tiene largo fijo
    consultaDoc: false, // no hay consulta automática de CI
    geocodeHint: 'Bolivia',
    zonas: [
      'la_paz',
      'el_alto',
      'santa_cruz',
      'cochabamba',
      'sucre',
    ],
  ),
  'EC': PaisConfig(
    iso: 'EC',
    nombre: 'Ecuador',
    moneda: '\$',
    monedaIso: 'USD',
    pasarela: 'manual',
    pasarelaNombre: 'Por definir',
    codigoTel: '593',
    bandera: '🇪🇨',
    docId: 'Cédula',
    telLongitud: 9, // celular ecuatoriano sin el 0 inicial = 9 dígitos
    docLongitud: 10, // cédula ecuatoriana = 10 dígitos
    consultaDoc: true, // consulta la cédula vía CipherByte (backend)
    geocodeHint: 'Ecuador',
    zonas: [
      'quito',
      'guayaquil',
      'cuenca',
      'ambato',
    ],
  ),
};

/// País por defecto cuando aún no se detectó/persistió nada (piloto nació en
/// Perú). Se sobreescribe apenas el GPS resuelve el país o se lee el persistido.
const PaisConfig _paisPorDefecto = PaisConfig(
  iso: 'PE',
  nombre: 'Perú',
  moneda: 'S/',
  monedaIso: 'PEN',
  pasarela: 'culqi',
  pasarelaNombre: 'Culqi (Yape · tarjeta)',
  codigoTel: '51',
  bandera: '🇵🇪',
  docId: 'DNI',
  telLongitud: 9,
  docLongitud: 8,
  consultaDoc: true,
  geocodeHint: 'Lima, Perú',
  zonas: [
    'lima_norte',
    'lima_sur',
    'lima_este',
    'lima_moderna',
    'callao',
  ],
);

/// País actualmente activo. La UI de moneda lee de aquí (vía `monedaSimbolo`).
PaisConfig paisActual = _paisPorDefecto;

const String _kPaisIso = 'pais_iso';

/// Aplica un país (por su config), sincroniza el símbolo de moneda global y,
/// si [persistir], lo guarda para el próximo arranque.
Future<void> _aplicarPais(PaisConfig p, {bool persistir = true}) async {
  paisActual = p;
  monedaSimbolo = p.moneda; // mantiene el helper `precio()` en sincronía
  if (persistir) {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kPaisIso, p.iso);
    } catch (_) {
      // Sin persistencia (p. ej. tests): el símbolo igual quedó aplicado.
    }
  }
}

/// Selecciona el país por su código ISO (el que devuelve el reverse-geocode).
/// Si el país no está soportado, mantiene el actual (no rompe la moneda). Es la
/// puerta de entrada desde la detección por GPS.
Future<void> setPaisPorIso(String? iso) async {
  final code = (iso ?? '').toUpperCase().trim();
  final p = paisesSoportados[code];
  if (p == null) return; // país no soportado → no tocar la moneda actual
  if (p.iso == paisActual.iso) return; // sin cambios
  await _aplicarPais(p);
}

/// Carga el país persistido en el arranque, para que la moneda sea correcta
/// desde el primer frame (y offline), antes de que el GPS resuelva. Fail-safe.
Future<void> cargarPaisPersistido() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final iso = prefs.getString(_kPaisIso);
    final p = paisesSoportados[(iso ?? '').toUpperCase()];
    if (p != null) await _aplicarPais(p, persistir: false);
  } catch (_) {
    // Sin persistencia: se queda con el país por defecto.
  }
}

// ── Detección de país por COORDENADAS ───────────────────────────────────────
//
// La moneda de una cancha se congela por el país donde ESTÁ FÍSICAMENTE la
// cancha (una cancha en La Paz cobra en Bs aunque el dueño registre desde Perú),
// no por `paisActual` (que sigue el GPS del dispositivo del dueño). Para eso
// necesitamos mapear lat/lng → país.
//
// Estrategia: cajas (bounding boxes) por país; si el punto cae en UNA sola caja
// se usa esa; si cae en varias (zona fronteriza) o en ninguna, se elige el país
// soportado cuyo centro esté más cerca. Es una heurística suficiente para el
// piloto (ciudades lejos de la frontera: Lima, La Paz, Santa Cruz, Quito).

class _Caja {
  final double latMin, latMax, lngMin, lngMax;
  final double latC, lngC; // centro aproximado, para el desempate por cercanía
  const _Caja(this.latMin, this.latMax, this.lngMin, this.lngMax, this.latC,
      this.lngC);
  bool contiene(double lat, double lng) =>
      lat >= latMin && lat <= latMax && lng >= lngMin && lng <= lngMax;
  double distancia(double lat, double lng) {
    final dLat = lat - latC, dLng = lng - lngC;
    return dLat * dLat + dLng * dLng; // cuadrado (solo para comparar)
  }
}

/// Ubicación POR DEFECTO (ciudad principal) de cada país. Se usa cuando el GPS
/// no resuelve (mala señal, permiso denegado, sin última ubicación conocida):
/// Explorar muestra canchas de esa ciudad AL INSTANTE en vez de quedarse en
/// blanco esperando el fix, y reordena por cercanía apenas llega el GPS real.
/// Lima (PE), Santa Cruz de la Sierra (BO), Quito (EC).
const Map<String, ({double lat, double lng})> _ciudadPorDefecto = {
  'PE': (lat: -12.0908, lng: -77.0250), // Lima (San Isidro)
  'BO': (lat: -17.7833, lng: -63.1821), // Santa Cruz de la Sierra
  'EC': (lat: -0.1807, lng: -78.4678), // Quito
};

/// Coordenada por defecto del país [iso] (o del país actual si se omite). Nunca
/// es null: cae a Lima si el país no está en el mapa. Fuente del "arranque sin
/// GPS" de Explorar.
({double lat, double lng}) ubicacionPorDefecto([String? iso]) {
  final code = (iso ?? paisActual.iso).toUpperCase();
  return _ciudadPorDefecto[code] ?? _ciudadPorDefecto['PE']!;
}

// Cajas ajustadas para que la zona clara de cada país sea inequívoca. El borde
// este de Perú (-68.6) y el oeste de Bolivia (-69.7) se solapan poco; puntos al
// oeste de -69.7 (p. ej. Puno, -70.0) quedan sólo en Perú.
const Map<String, _Caja> _cajasPais = {
  'PE': _Caja(-18.4, 0.05, -81.4, -68.6, -9.19, -75.02),
  'BO': _Caja(-23.0, -9.6, -69.7, -57.4, -16.29, -63.59),
  'EC': _Caja(-5.1, 1.7, -81.1, -75.1, -1.83, -78.18),
};

/// País soportado al que corresponde una coordenada. Nunca es null: si el punto
/// no cae en ninguna caja, devuelve el país cuyo centro esté más cerca (así una
/// cancha siempre congela ALGUNA moneda coherente). Fuente de la moneda de una
/// cancha por su ubicación real.
PaisConfig paisDeCoordenadas(double lat, double lng) {
  // 1) Países cuya caja contiene el punto.
  final dentro = <String>[
    for (final e in _cajasPais.entries)
      if (e.value.contiene(lat, lng)) e.key,
  ];
  final candidatos = dentro.isNotEmpty ? dentro : _cajasPais.keys.toList();
  // 2) Entre los candidatos, el de centro más cercano.
  String mejor = candidatos.first;
  double mejorDist = _cajasPais[mejor]!.distancia(lat, lng);
  for (final iso in candidatos.skip(1)) {
    final d = _cajasPais[iso]!.distancia(lat, lng);
    if (d < mejorDist) {
      mejorDist = d;
      mejor = iso;
    }
  }
  return paisesSoportados[mejor] ?? paisActual;
}

/// Símbolo de moneda ('S/', 'Bs', '$') que corresponde a una coordenada, para
/// congelar `Cancha.moneda` por la ubicación real de la cancha.
String monedaDeCoordenadas(double lat, double lng) =>
    paisDeCoordenadas(lat, lng).moneda;

// ── Atajos de UI (leen del país actual) ──────────────────────────────────────

/// Prefijo telefónico con "+": "+51" / "+591". Para prefixText de campos WhatsApp.
String get codigoTelActual => '+${paisActual.codigoTel}';

/// Emoji de la bandera del país actual: 🇵🇪 / 🇧🇴.
String get banderaActual => paisActual.bandera;

/// Nombre del documento de identidad del país actual: "DNI" / "CI".
String get docIdActual => paisActual.docId;
