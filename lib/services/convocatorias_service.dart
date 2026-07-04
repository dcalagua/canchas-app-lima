import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/convocatoria.dart';

/// Cliente del módulo **CONVOCATORIAS** ("pichangas" programadas) del backend
/// growth. Reusa la misma URL base (`--dart-define=GROWTH_API_URL`). Si no está
/// definida, el servicio queda inactivo (fail-safe) y la UI muestra un aviso.
class ConvocatoriasService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');

  static bool get disponible => _baseUrl.isNotEmpty;

  static const _headers = {'Content-Type': 'application/json'};

  /// Convierte el nombre de un club en un id estable (slug) para agrupar sus
  /// convocatorias. Debe ser consistente entre crear y listar.
  static String slugClub(String nombre) {
    final n = nombre
        .toLowerCase()
        .replaceAll(RegExp(r'[áàä]'), 'a')
        .replaceAll(RegExp(r'[éèë]'), 'e')
        .replaceAll(RegExp(r'[íìï]'), 'i')
        .replaceAll(RegExp(r'[óòö]'), 'o')
        .replaceAll(RegExp(r'[úùü]'), 'u')
        .replaceAll(RegExp(r'ñ'), 'n');
    final s = n.replaceAll(RegExp(r'[^a-z0-9]+'), '_').replaceAll(RegExp(r'^_+|_+$'), '');
    return s.isEmpty ? 'club' : s;
  }

  /// Lista las convocatorias de un club (opcionalmente por estado).
  static Future<List<Convocatoria>> listar(String clubId, {String? estado}) async {
    if (!disponible) return [];
    try {
      final uri = Uri.parse('$_baseUrl/convocatorias').replace(queryParameters: {
        'club_id': clubId,
        if (estado != null && estado.isNotEmpty) 'estado': estado,
      });
      final resp = await http.get(uri).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return [];
      final data = jsonDecode(resp.body);
      if (data is! List) return [];
      return data
          .map((e) => Convocatoria.fromListado(Map<String, dynamic>.from(e as Map)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Detalle de una convocatoria; si se pasa [socio], incluye "mi estado".
  static Future<ConvocatoriaDetalle?> detalle(int convId, {String? socio}) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/convocatorias/$convId').replace(
          queryParameters:
              (socio != null && socio.isNotEmpty) ? {'socio': socio} : null);
      final resp = await http.get(uri).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      final j = Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
      if (j['ok'] != true) return null;
      return ConvocatoriaDetalle.fromJson(j);
    } catch (_) {
      return null;
    }
  }

  /// Crea una convocatoria (acción del admin/dueño del club).
  static Future<ConvocatoriaDetalle?> crear({
    required String clubId,
    required String titulo,
    required int cupos,
    String deporte = 'futbol',
    String? categoria,
    String? fechaPartido,
    String? cierre,
    ModoAsignacion? modo,
    String creadoPor = '',
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/convocatorias');
      final resp = await http
          .post(uri,
              headers: _headers,
              body: jsonEncode({
                'club_id': clubId,
                'titulo': titulo,
                'deporte': deporte,
                'cupos': cupos,
                if (categoria != null) 'categoria': categoria,
                if (fechaPartido != null && fechaPartido.isNotEmpty)
                  'fecha_partido': fechaPartido,
                if (cierre != null && cierre.isNotEmpty) 'cierre': cierre,
                if (modo != null) 'modo_asignacion': modo.clave,
                'creado_por': creadoPor,
              }))
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      final j = Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
      if (j['ok'] != true) return null;
      return ConvocatoriaDetalle.fromJson(j);
    } catch (_) {
      return null;
    }
  }

  /// Anota a un socio. Devuelve el mapa de respuesta (con estado efectivo) o null.
  static Future<Map<String, dynamic>?> inscribir(
      int convId, String socioId, String socioNombre) async {
    return _post('$_baseUrl/convocatorias/$convId/inscribir',
        {'socio_id': socioId, 'socio_nombre': socioNombre});
  }

  /// Cancela la inscripción de un socio (auto-promueve al primero de la espera).
  static Future<Map<String, dynamic>?> cancelar(int convId, String socioId) {
    return _post(
        '$_baseUrl/convocatorias/$convId/cancelar', {'socio_id': socioId});
  }

  /// Cierra la convocatoria y resuelve la asignación según el modo (dueño).
  static Future<Map<String, dynamic>?> cerrar(int convId, {String? semilla}) {
    return _post('$_baseUrl/convocatorias/$convId/cerrar',
        {if (semilla != null && semilla.isNotEmpty) 'semilla': semilla});
  }

  /// Reabre una convocatoria cerrada por error (dueño).
  static Future<Map<String, dynamic>?> reabrir(int convId) {
    return _post('$_baseUrl/convocatorias/$convId/reabrir', {});
  }

  /// Marca asistencia real tras el partido (alimenta equidad y ranking).
  static Future<Map<String, dynamic>?> asistencia(
      int convId, Map<String, bool> asistencias) {
    final lista = asistencias.entries
        .map((e) => {'socio_id': e.key, 'asistio': e.value})
        .toList();
    return _post(
        '$_baseUrl/convocatorias/$convId/asistencia', {'asistencias': lista});
  }

  /// Ranking de recurrencia por socio (trazabilidad).
  static Future<List<Map<String, dynamic>>> ranking(String clubId) async {
    if (!disponible) return [];
    try {
      final uri = Uri.parse('$_baseUrl/convocatorias/ranking')
          .replace(queryParameters: {'club_id': clubId});
      final resp = await http.get(uri).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return [];
      final data = jsonDecode(resp.body);
      if (data is! List) return [];
      return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<Map<String, dynamic>?> _post(
      String url, Map<String, dynamic> body) async {
    if (!disponible) return null;
    try {
      final resp = await http
          .post(Uri.parse(url), headers: _headers, body: jsonEncode(body))
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }
}
