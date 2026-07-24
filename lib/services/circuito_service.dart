import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente del CIRCUITO (`/circuito/*`): onboarding de jugadores al ranking. Un
/// jugador se declara "disponible para retar" (deporte/zona/categoría) y aparece
/// en el directorio aunque no haya jugado. Todo fail-safe.
class CircuitoService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  static Map<String, String> _headers({bool json = false}) => {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
        if (json) 'Content-Type': 'application/json',
      };

  /// El jugador se declara disponible (crea/actualiza su perfil). Devuelve el
  /// perfil o null.
  static Future<Map<String, dynamic>?> unirse({
    required String email,
    required String nombre,
    required String deporte,
    String zona = '',
    String categoria = '',
  }) async {
    if (!disponible || email.isEmpty) return null;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/circuito/unirse'),
          headers: _headers(json: true),
          body: jsonEncode({
            'email': email,
            'nombre': nombre,
            'deporte': deporte,
            'zona': zona,
            'categoria': categoria,
          })).timeout(const Duration(seconds: 15));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return j['ok'] == true ? (j['jugador'] as Map<String, dynamic>?) : null;
    } catch (_) {
      return null;
    }
  }

  /// El jugador se retira del directorio. Devuelve true si se pudo.
  static Future<bool> salir(String email) async {
    if (!disponible || email.isEmpty) return false;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/circuito/salir'),
          headers: _headers(json: true),
          body: jsonEncode({'email': email}))
          .timeout(const Duration(seconds: 15));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Perfil de circuito del jugador (para saber si ya se unió), o null.
  static Future<Map<String, dynamic>?> perfil(String email) async {
    if (!disponible || email.isEmpty) return null;
    try {
      final r = await http.get(Uri.parse('$_baseUrl/circuito/perfil/$email'),
          headers: _headers()).timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return j['jugador'] as Map<String, dynamic>?;
    } catch (_) {
      return null;
    }
  }

  /// Empuja a la torre el ranking global cruzado (que el APK computa con las
  /// academias de Supabase). Best-effort: no bloquea nada.
  static Future<void> publicarRanking(
      {required List<Map<String, dynamic>> deportes, String por = ''}) async {
    if (!disponible || deportes.isEmpty) return;
    try {
      await http.post(Uri.parse('$_baseUrl/circuito/ranking-snapshot'),
          headers: _headers(json: true),
          body: jsonEncode({'deportes': deportes, 'por': por}))
          .timeout(const Duration(seconds: 12));
    } catch (_) {}
  }

  /// Directorio de jugadores disponibles para retar. Filtra por deporte/zona.
  static Future<List<Map<String, dynamic>>> jugadores(
      {String? deporte, String? zona}) async {
    if (!disponible) return const [];
    try {
      final q = <String, String>{
        if (deporte != null && deporte.isNotEmpty) 'deporte': deporte,
        if (zona != null && zona.isNotEmpty) 'zona': zona,
      };
      final uri = Uri.parse('$_baseUrl/circuito/jugadores')
          .replace(queryParameters: q.isEmpty ? null : q);
      final r = await http.get(uri, headers: _headers())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return const [];
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return ((j['jugadores'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return const [];
    }
  }
}
