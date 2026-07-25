import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente de RETOS P2P contra el backend growth (`/retos/*`). Un jugador reta a
/// otro (por correo); coordinan la cancha y reportan el resultado, que suma al
/// ranking global. Todo fail-safe: si no hay backend, devuelve vacío/false.
class RetosService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  static Map<String, String> _headers({bool json = false}) => {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
        if (json) 'Content-Type': 'application/json',
      };

  /// Crea un reto. Devuelve la respuesta completa del backend
  /// (`{ok, reto}` o `{ok:false, error, ...}`), o null si falló la red.
  static Future<Map<String, dynamic>?> crear({
    required String retadorEmail,
    required String retadorNombre,
    required String retadoEmail,
    required String retadoNombre,
    required String deporte,
    String zona = '',
    String mensaje = '',
  }) async {
    if (!disponible) return null;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/retos/crear'),
          headers: _headers(json: true),
          body: jsonEncode({
            'retador_email': retadorEmail,
            'retador_nombre': retadorNombre,
            'retado_email': retadoEmail,
            'retado_nombre': retadoNombre,
            'deporte': deporte,
            'zona': zona,
            'mensaje': mensaje,
          })).timeout(const Duration(seconds: 15));
      return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// Retos del usuario: {recibidos:[...], enviados:[...]}.
  static Future<Map<String, dynamic>?> mios(String email) async {
    if (!disponible || email.isEmpty) return null;
    try {
      final r = await http.get(Uri.parse('$_baseUrl/retos/$email'),
          headers: _headers()).timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// El retado acepta (true) o rechaza (false). Devuelve true si se pudo.
  static Future<bool> responder(int id, bool aceptar) async {
    if (!disponible) return false;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/retos/$id/responder'),
          headers: _headers(json: true),
          body: jsonEncode({'aceptar': aceptar}))
          .timeout(const Duration(seconds: 15));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Reporta el resultado (ganador + marcador). Queda POR CONFIRMAR hasta que el
  /// otro lo confirme o venza el plazo. [reportadoPor] = correo de quien reporta.
  static Future<bool> resultado(int id, String ganadorEmail,
      {String marcador = '', String reportadoPor = ''}) async {
    if (!disponible) return false;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/retos/$id/resultado'),
          headers: _headers(json: true),
          body: jsonEncode({
            'ganador_email': ganadorEmail,
            'marcador': marcador,
            'reportado_por': reportadoPor,
          }))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return false;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return j['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  /// El OTRO jugador CONFIRMA (acepta=true) o DISPUTA (acepta=false) el resultado
  /// reportado. Solo cuenta al ranking si se confirma.
  static Future<bool> confirmar(int id, String porEmail,
      {required bool acepta}) async {
    if (!disponible) return false;
    try {
      final r = await http.post(Uri.parse('$_baseUrl/retos/$id/confirmar'),
          headers: _headers(json: true),
          body: jsonEncode({'por_email': porEmail, 'acepta': acepta}))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return false;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return j['ok'] == true;
    } catch (_) {
      return false;
    }
  }

  /// Retos JUGADOS (para sumar al ranking global). Filtra por deporte/zona.
  static Future<List<Map<String, dynamic>>> resultados(
      {String? deporte, String? zona}) async {
    if (!disponible) return const [];
    try {
      final q = <String, String>{
        if (deporte != null && deporte.isNotEmpty) 'deporte': deporte,
        if (zona != null && zona.isNotEmpty) 'zona': zona,
      };
      final uri =
          Uri.parse('$_baseUrl/retos').replace(queryParameters: q.isEmpty ? null : q);
      final r = await http.get(uri, headers: _headers())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return const [];
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return ((j['resultados'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return const [];
    }
  }
}
