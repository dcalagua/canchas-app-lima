import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente de FIDELIDAD (backend growth, `/puntos/*`): el jugador acumula
/// puntos por sus reservas efectivamente PAGADAS (online al pagar; efectivo
/// cuando el dueño marca pagado) y los canjea como descuento. La fuente de
/// verdad vive en el backend (anti-trampa, idempotente por reserva); el APK
/// solo cachea. Fail-safe: sin backend, nada se rompe.
class PuntosService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  static Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
      };

  /// Saldo del jugador: {disponible, pendiente, por_vencer_30d,
  /// vence_proximo, valor_100_puntos}. null si no se pudo.
  static Future<Map<String, dynamic>?> saldo(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return null;
    try {
      final resp = await http
          .get(Uri.parse('$_baseUrl/puntos/saldo/${Uri.encodeComponent(e)}'))
          .timeout(const Duration(seconds: 8));
      if (resp.statusCode != 200) return null;
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// Movimientos de puntos del jugador (acreditaciones), más recientes
  /// primero. Lista vacía si no se pudo.
  static Future<List<Map<String, dynamic>>> movimientos(String email) async {
    final e = email.trim().toLowerCase();
    if (!disponible || e.isEmpty) return const [];
    try {
      final resp = await http
          .get(Uri.parse(
              '$_baseUrl/puntos/movimientos/${Uri.encodeComponent(e)}'))
          .timeout(const Duration(seconds: 8));
      if (resp.statusCode != 200) return const [];
      final l = jsonDecode(resp.body) as List;
      return [
        for (final m in l.reversed) Map<String, dynamic>.from(m as Map),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Acredita los puntos de una reserva PAGADA. Idempotente por [reservaId]
  /// (reintentar es seguro). null = no llegó al backend (reintentar luego).
  static Future<Map<String, dynamic>?> acreditarReserva({
    required String email,
    required double monto,
    required String moneda,
    required String reservaId,
  }) async {
    if (!disponible) return null;
    try {
      final resp = await http
          .post(Uri.parse('$_baseUrl/puntos/acreditar-reserva'),
              headers: _headers,
              body: jsonEncode({
                'usuario_id': email.trim().toLowerCase(),
                'monto': monto,
                'moneda': moneda,
                'reserva_id': reservaId,
              }))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// Canjea [puntos] por un VALE de descuento. Devuelve el canje del backend
  /// ({ok, valor_soles, vale_id, saldo_disponible}) o null si no se pudo.
  static Future<Map<String, dynamic>?> canjear({
    required String email,
    required int puntos,
  }) async {
    if (!disponible) return null;
    try {
      final resp = await http
          .post(Uri.parse('$_baseUrl/puntos/canjear'),
              headers: _headers,
              body: jsonEncode({
                'usuario_id': email.trim().toLowerCase(),
                'puntos_usados': puntos,
                'tipo_premio': 'descuento_reserva',
              }))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }
}
