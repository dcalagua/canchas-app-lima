import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente de VENTAS del Marketplace (escrow) contra el backend growth
/// (`/ventas/*`). El comprador paga (Culqi) y el neto queda RETENIDO hasta que
/// confirme la recepción. Todo fail-safe.
class VentasService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  static Map<String, String> _headers({bool json = false}) => {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
        if (json) 'Content-Type': 'application/json',
      };

  /// Mis COMPRAS (soy comprador): [{..., estado, liberado, neto_soles}].
  static Future<List<Map<String, dynamic>>> misCompras(String email) =>
      _lista('comprador', email);

  /// Mis VENTAS (soy vendedor) + resumen retenido/liberado.
  static Future<Map<String, dynamic>> misVentas(String email) async {
    if (!disponible || email.isEmpty) {
      return {'ventas': const [], 'retenido_soles': 0, 'liberado_soles': 0};
    }
    try {
      final r = await http
          .get(Uri.parse('$_baseUrl/ventas/vendedor/$email'),
              headers: _headers())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) {
        return {'ventas': const [], 'retenido_soles': 0, 'liberado_soles': 0};
      }
      return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {
      return {'ventas': const [], 'retenido_soles': 0, 'liberado_soles': 0};
    }
  }

  static Future<List<Map<String, dynamic>>> _lista(
      String rol, String email) async {
    if (!disponible || email.isEmpty) return const [];
    try {
      final r = await http
          .get(Uri.parse('$_baseUrl/ventas/$rol/$email'), headers: _headers())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return const [];
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return ((j['ventas'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// El VENDEDOR marca que entregó.
  static Future<bool> entregado(int id, String porEmail) =>
      _accion(id, 'entregado', porEmail);

  /// El COMPRADOR confirma la recepción → libera el pago.
  static Future<bool> recibido(int id, String porEmail) =>
      _accion(id, 'recibido', porEmail);

  /// El COMPRADOR abre una disputa.
  static Future<bool> disputa(int id, String porEmail) =>
      _accion(id, 'disputa', porEmail);

  static Future<bool> _accion(int id, String accion, String porEmail) async {
    if (!disponible) return false;
    try {
      final r = await http
          .post(Uri.parse('$_baseUrl/ventas/$id/$accion'),
              headers: _headers(json: true),
              body: jsonEncode({'por_email': porEmail}))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return false;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return j['ok'] == true;
    } catch (_) {
      return false;
    }
  }
}
