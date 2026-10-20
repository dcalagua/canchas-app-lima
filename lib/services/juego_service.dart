import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/juego.dart';
import 'pagos_service.dart';

import '../brand.dart';
/// JUEGA YA (backend `juego.py`): preferencias de avisos/disponibilidad y
/// jugadores disponibles cerca. Cache-first: las preferencias se pintan al
/// instante desde el teléfono y se refrescan del backend.
class JuegoService {
  JuegoService._();

  static const _kPrefs = 'juego_prefs_cache';

  static String _cuenta(String email) => email.trim().toLowerCase();

  static Future<PrefsJuego?> prefsCache(String email) async {
    try {
      final sp = await SharedPreferences.getInstance();
      final raw = sp.getString('$_kPrefs:${_cuenta(email)}');
      if (raw == null) return null;
      return PrefsJuego.de(jsonDecode(raw) as Map);
    } catch (_) {
      return null;
    }
  }

  static Future<void> _guardarCache(String email, PrefsJuego p) async {
    try {
      final sp = await SharedPreferences.getInstance();
      await sp.setString('$_kPrefs:${_cuenta(email)}', jsonEncode(p.toJson()));
    } catch (_) {}
  }

  /// Preferencias del backend (y renueva la vigencia de "disponible" con la
  /// ubicación aproximada). Null sin red.
  static Future<PrefsJuego?> prefs(String email, {double? lat, double? lng}) async {
    final e = _cuenta(email);
    if (!PagosService.disponible || e.isEmpty) return null;
    try {
      final q = {
        'email': e,
        if (lat != null) 'lat': lat.toStringAsFixed(4),
        if (lng != null) 'lng': lng.toStringAsFixed(4),
      };
      final r = await http
          .get(Uri.parse('${PagosService.baseUrl}/juego/prefs').replace(queryParameters: q),
              headers: await PagosService.headersUsuario())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body);
      if (j is! Map || j['prefs'] is! Map) return null;
      final p = PrefsJuego.de(j['prefs'] as Map);
      await _guardarCache(e, p);
      return p;
    } catch (_) {
      return null;
    }
  }

  /// Guarda. Devuelve (prefs, null) o (null, mensaje de error).
  static Future<(PrefsJuego?, String?)> guardar(String email, PrefsJuego p,
      {double? lat, double? lng, String nombre = ''}) async {
    final e = _cuenta(email);
    if (!PagosService.disponible || e.isEmpty) {
      return (null, 'Sin conexión con $kBrandName. Reintenta.');
    }
    try {
      final r = await http
          .post(Uri.parse('${PagosService.baseUrl}/juego/prefs'),
              headers: await PagosService.headersUsuario(json: true),
              body: jsonEncode({
                'email': e,
                ...p.toJson(),
                if (lat != null) 'lat': lat,
                if (lng != null) 'lng': lng,
                if (nombre.isNotEmpty) 'nombre': nombre,
              }))
          .timeout(const Duration(seconds: 20));
      final j = jsonDecode(r.body);
      if (r.statusCode == 200 && j is Map && j['prefs'] is Map) {
        final n = PrefsJuego.de(j['prefs'] as Map);
        await _guardarCache(e, n);
        return (n, null);
      }
      return (null, (j is Map ? j['mensaje'] : null)?.toString() ?? 'No se pudo guardar.');
    } catch (_) {
      return (null, 'Sin conexión. Revisa tu internet y reintenta.');
    }
  }

  static Future<List<JugadorDisponible>?> disponibles(
      String email, String deporte, double lat, double lng, int radioKm) async {
    final e = _cuenta(email);
    if (!PagosService.disponible || e.isEmpty) return null;
    try {
      final r = await http
          .get(
              Uri.parse('${PagosService.baseUrl}/juego/disponibles').replace(queryParameters: {
                'email': e,
                'deporte': deporte,
                'lat': lat.toStringAsFixed(4),
                'lng': lng.toStringAsFixed(4),
                'radio_km': '$radioKm',
              }),
              headers: await PagosService.headersUsuario())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body);
      if (j is! Map || j['jugadores'] is! List) return null;
      return [
        for (final x in j['jugadores'] as List)
          if (x is Map) JugadorDisponible.de(x)
      ];
    } catch (_) {
      return null;
    }
  }
}
