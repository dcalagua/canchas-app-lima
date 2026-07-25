import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

/// Jerarquía administrativa del Perú (UBIGEO INEI): Departamento → Provincia →
/// Distrito. Se carga UNA vez desde el asset `assets/geo/peru_ubigeo.json`
/// (compacto, ~26 KB) y queda en memoria para el selector en cascada de la zona
/// del circuito. Fail-safe: si el asset no carga, queda vacío y la UI cae al
/// campo de texto libre.
class GeoPeru {
  GeoPeru._();

  /// { Departamento: { Provincia: [Distritos...] } }
  static Map<String, Map<String, List<String>>> _arbol = {};
  static bool _cargado = false;

  static bool get disponible => _arbol.isNotEmpty;

  /// Carga perezosa e idempotente. La llama la hoja al abrirse.
  static Future<void> cargar() async {
    if (_cargado) return;
    _cargado = true;
    try {
      final raw = await rootBundle.loadString('assets/geo/peru_ubigeo.json');
      final data = json.decode(raw) as Map<String, dynamic>;
      _arbol = data.map((dep, provs) => MapEntry(
            dep,
            (provs as Map<String, dynamic>).map((prov, dists) => MapEntry(
                  prov,
                  (dists as List).map((e) => e.toString()).toList(),
                )),
          ));
    } catch (_) {
      _arbol = {}; // fail-safe: la UI usará texto libre
    }
  }

  static List<String> departamentos() => _arbol.keys.toList();

  static List<String> provincias(String departamento) =>
      _arbol[departamento]?.keys.toList() ?? const [];

  static List<String> distritos(String departamento, String provincia) =>
      _arbol[departamento]?[provincia] ?? const [];

  // ── Emparejar lo que devuelve el GPS con la jerarquía ─────────────────────
  static String _norm(String s) {
    var x = s.trim().toLowerCase();
    const acc = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u'};
    acc.forEach((k, v) => x = x.replaceAll(k, v));
    return x;
  }

  /// Busca el departamento cuyo nombre calza (sin tildes) con [texto].
  static String? matchDepartamento(String texto) {
    final n = _norm(texto);
    if (n.isEmpty) return null;
    for (final d in _arbol.keys) {
      if (_norm(d) == n) return d;
    }
    return null;
  }

  static String? matchProvincia(String departamento, String texto) {
    final n = _norm(texto);
    if (n.isEmpty) return null;
    for (final p in provincias(departamento)) {
      if (_norm(p) == n) return p;
    }
    return null;
  }

  static String? matchDistrito(
      String departamento, String provincia, String texto) {
    final n = _norm(texto);
    if (n.isEmpty) return null;
    for (final d in distritos(departamento, provincia)) {
      if (_norm(d) == n) return d;
    }
    return null;
  }
}
