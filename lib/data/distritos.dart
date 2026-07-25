import '../config/pais.dart';

/// Catálogo de DISTRITOS (o su equivalente local) por país, para el selector de
/// zona del circuito. La idea: el jugador no escribe texto libre crudo (que sale
/// "Urb Santa Maria de Chosica" del GPS), sino que elige un distrito estándar
/// (San Isidro, San Borja, Miraflores…). En Perú son los distritos de Lima +
/// Callao y algunas ciudades grandes; en Bolivia/Ecuador, sus ciudades/zonas.
/// Misma lógica en todos los países: sugerir el nombre "bonito" y dejar escribir
/// si vive en otra parte.
const Map<String, List<String>> distritosPorPais = {
  // Lima Metropolitana (43) + Callao (regional) + principales ciudades del país.
  'PE': [
    // Lima "moderna" primero (lo más buscado del piloto).
    'Miraflores', 'San Isidro', 'San Borja', 'Santiago de Surco', 'La Molina',
    'Barranco', 'Surquillo', 'Jesús María', 'Magdalena del Mar', 'Pueblo Libre',
    'Lince', 'San Miguel', 'Chorrillos', 'San Luis',
    // Resto de Lima Metropolitana (alfabético).
    'Ancón', 'Ate', 'Breña', 'Carabayllo', 'Chaclacayo', 'Cieneguilla', 'Comas',
    'El Agustino', 'Independencia', 'La Victoria', 'Lima (Cercado)', 'Los Olivos',
    'Lurigancho (Chosica)', 'Lurín', 'Pachacámac', 'Pucusana', 'Puente Piedra',
    'Punta Hermosa', 'Punta Negra', 'Rímac', 'San Bartolo',
    'San Juan de Lurigancho', 'San Juan de Miraflores', 'San Martín de Porres',
    'Santa Anita', 'Santa María del Mar', 'Santa Rosa', 'Villa El Salvador',
    'Villa María del Triunfo',
    // Callao (Provincia Constitucional).
    'Callao', 'Bellavista', 'Carmen de la Legua', 'La Perla', 'La Punta',
    'Ventanilla', 'Mi Perú',
    // Principales ciudades del interior (para "otro lado del Perú").
    'Arequipa', 'Trujillo', 'Chiclayo', 'Piura', 'Cusco', 'Huancayo', 'Tacna',
    'Iquitos', 'Chimbote', 'Ica', 'Cajamarca', 'Puno', 'Pucallpa', 'Tarapoto',
  ],
  // Bolivia: ciudades y zonas conocidas.
  'BO': [
    'La Paz', 'El Alto', 'Santa Cruz de la Sierra', 'Cochabamba', 'Sucre',
    'Oruro', 'Tarija', 'Potosí', 'Trinidad',
    // Zonas típicas de Santa Cruz / La Paz.
    'Equipetrol', 'Zona Sur', 'Sopocachi', 'Calacoto', 'San Miguel',
  ],
  // Ecuador: ciudades y parroquias conocidas.
  'EC': [
    'Quito', 'Guayaquil', 'Cuenca', 'Ambato', 'Manta', 'Loja', 'Machala',
    'Samborondón', 'Cumbayá', 'Tumbaco',
  ],
};

/// Lista del país ACTUAL (cae a Perú si el país no está en el catálogo).
List<String> _catalogoActual() =>
    distritosPorPais[paisActual.iso] ?? distritosPorPais['PE']!;

/// Quita tildes y baja a minúsculas para comparar sin fricción ("Jesús" ~
/// "jesus"). Suficiente para matching de nombres de distrito.
String _norm(String s) {
  var x = s.trim().toLowerCase();
  const acc = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u'};
  acc.forEach((k, v) => x = x.replaceAll(k, v));
  return x;
}

/// Sugerencias de distrito para el país actual filtradas por lo que escribió el
/// usuario. Con [query] vacío devuelve los "populares" (los primeros del
/// catálogo, que son los más buscados). Limita a [max] para no saturar la UI.
List<String> sugerenciasDistrito(String query, {int max = 8}) {
  final cat = _catalogoActual();
  final q = _norm(query);
  if (q.isEmpty) return cat.take(max).toList();
  // Primero los que EMPIEZAN con el texto, luego los que lo contienen.
  final empiezan = <String>[];
  final contienen = <String>[];
  for (final d in cat) {
    final n = _norm(d);
    if (n.startsWith(q)) {
      empiezan.add(d);
    } else if (n.contains(q)) {
      contienen.add(d);
    }
  }
  return [...empiezan, ...contienen].take(max).toList();
}

/// Dado lo que devolvió el reverse-geocode (varios campos: barrio, distrito,
/// ciudad), elige el mejor nombre de DISTRITO: si alguno calza con el catálogo
/// del país, usa el nombre estándar del catálogo; si no, el primer campo no
/// vacío que parezca un distrito (evita quedarse con la urbanización cruda).
String normalizarDistrito(List<String> candidatos) {
  final cat = _catalogoActual();
  // 1) ¿Algún candidato calza con el catálogo? (contains en ambos sentidos:
  //    "Lurigancho" ~ "Lurigancho (Chosica)"; "Chosica" también).
  for (final c in candidatos) {
    final nc = _norm(c);
    if (nc.isEmpty) continue;
    for (final d in cat) {
      final nd = _norm(d);
      if (nd == nc || nd.contains(nc) || nc.contains(nd)) return d;
    }
  }
  // 2) Sin match: el primer candidato no vacío (ya viene priorizado por el
  //    llamador: distrito antes que barrio).
  return candidatos.firstWhere((c) => c.trim().isNotEmpty, orElse: () => '');
}
