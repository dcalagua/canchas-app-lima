import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

/// División político-administrativa de 3 niveles por PAÍS, para el selector en
/// cascada de la zona (circuito y academias). Cada país trae su propia jerarquía
/// y sus propias ETIQUETAS:
///   Perú     → Departamento → Provincia → Distrito   (UBIGEO INEI)
///   Bolivia  → Departamento → Provincia → Municipio
///   Ecuador  → Provincia    → Cantón    → Parroquia
/// Los datos viven en assets `assets/geo/{iso}_geo.json` (compactos), se cargan
/// una vez por país y quedan en memoria. Todo es fail-safe: si un asset no carga
/// el país queda vacío y la UI lo indica (sin texto libre).
class GeoAdmin {
  GeoAdmin._();

  /// Etiquetas de los 3 niveles por país (nivel1, nivel2, nivel3).
  static const Map<String, List<String>> _labels = {
    'PE': ['Departamento', 'Provincia', 'Distrito'],
    'BO': ['Departamento', 'Provincia', 'Municipio'],
    'EC': ['Provincia', 'Cantón', 'Parroquia'],
  };

  static const Map<String, String> _asset = {
    'PE': 'assets/geo/pe_geo.json',
    'BO': 'assets/geo/bo_geo.json',
    'EC': 'assets/geo/ec_geo.json',
  };

  /// { ISO: { nivel1: { nivel2: [nivel3...] } } }
  static final Map<String, Map<String, Map<String, List<String>>>> _cache = {};
  static final Set<String> _intentados = {};

  /// ¿Hay jerarquía para este país? (aunque aún no esté cargada).
  static bool soportado(String iso) => _asset.containsKey(iso.toUpperCase());

  /// Etiquetas [nivel1, nivel2, nivel3] del país (cae a la peruana).
  static List<String> labels(String iso) =>
      _labels[iso.toUpperCase()] ?? const ['Departamento', 'Provincia', 'Distrito'];

  /// ¿Ya está cargada y con datos?
  static bool disponible(String iso) =>
      _cache[iso.toUpperCase()]?.isNotEmpty ?? false;

  /// Carga perezosa e idempotente del asset del país.
  static Future<void> cargar(String isoRaw) async {
    final iso = isoRaw.toUpperCase();
    if (_cache.containsKey(iso)) return;
    if (!_asset.containsKey(iso) || _intentados.contains(iso)) return;
    _intentados.add(iso);
    try {
      final raw = await rootBundle.loadString(_asset[iso]!);
      final data = json.decode(raw) as Map<String, dynamic>;
      _cache[iso] = data.map((n1, provs) => MapEntry(
            n1,
            (provs as Map<String, dynamic>).map((n2, hijos) => MapEntry(
                  n2,
                  (hijos as List).map((e) => e.toString()).toList(),
                )),
          ));
    } catch (_) {
      _cache[iso] = {}; // fail-safe
    }
  }

  static List<String> nivel1(String iso) =>
      _cache[iso.toUpperCase()]?.keys.toList() ?? const [];

  static List<String> nivel2(String iso, String n1) =>
      _cache[iso.toUpperCase()]?[n1]?.keys.toList() ?? const [];

  static List<String> nivel3(String iso, String n1, String n2) =>
      _cache[iso.toUpperCase()]?[n1]?[n2] ?? const [];

  // ── Utilidades de emparejamiento (sin tildes) ─────────────────────────────
  static String _norm(String s) {
    var x = s.trim().toLowerCase();
    const acc = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u'};
    acc.forEach((k, v) => x = x.replaceAll(k, v));
    return x;
  }

  /// Ubica una HOJA guardada (distrito/municipio/parroquia) dentro del árbol y
  /// devuelve [nivel1, nivel2, nivel3] para preseleccionar los dropdowns. Si no
  /// la encuentra, devuelve [null, null, null].
  static List<String?> ubicar(String iso, String hoja) {
    final nz = _norm(hoja);
    if (nz.isEmpty) return [null, null, null];
    final arbol = _cache[iso.toUpperCase()] ?? const {};
    for (final n1 in arbol.keys) {
      for (final n2 in arbol[n1]!.keys) {
        for (final n3 in arbol[n1]![n2]!) {
          if (_norm(n3) == nz) return [n1, n2, n3];
        }
      }
    }
    return [null, null, null];
  }

  static String? _matchEn(List<String> opciones, String texto) {
    final n = _norm(texto);
    if (n.isEmpty) return null;
    for (final o in opciones) {
      if (_norm(o) == n) return o;
    }
    // tolerante: contiene (p. ej. "Lima Metropolitana" ~ "Lima")
    for (final o in opciones) {
      final no = _norm(o);
      if (no.contains(n) || n.contains(no)) return o;
    }
    return null;
  }

  /// Empareja lo que devuelve el reverse-geocode (nivel1/2/3 aprox.) con el
  /// árbol del país y devuelve [nivel1, nivel2, nivel3] (los que calcen).
  static List<String?> emparejarGps(
      String iso, String texto1, String texto2, List<String> textos3) {
    final n1 = _matchEn(nivel1(iso), texto1);
    if (n1 == null) return [null, null, null];
    final n2 = _matchEn(nivel2(iso, n1), texto2);
    if (n2 == null) return [n1, null, null];
    String? n3;
    for (final t in textos3) {
      n3 = _matchEn(nivel3(iso, n1, n2), t);
      if (n3 != null) break;
    }
    return [n1, n2, n3];
  }
}
