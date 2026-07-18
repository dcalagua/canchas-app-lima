import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

/// Resultado del carril de verificación física (backend/growth).
/// [verificada] true = la IA ya la dio por buena (sin visita); false = quedó una
/// visita agendada. [via] = 'ia' | 'fisica'.
class ResultadoFisica {
  final bool verificada;
  final String via;
  final int score;
  const ResultadoFisica(
      {required this.verificada, required this.via, required this.score});
}

/// Cliente del backend de **crecimiento** (puntos, solicitudes por zona y
/// verificación física / carril informal).
///
/// La URL base llega por `--dart-define=GROWTH_API_URL`. Si no está definida, el
/// servicio queda inactivo (fail-safe) y la app sigue con la verificación de
/// existencia directa.
class GrowthService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Carril informal: corre la IA primero (reusa el módulo de existencia en el
  /// servidor) y, si no concluye, agenda una visita. Devuelve null si el servicio
  /// no está configurado / no respondió.
  static Future<ResultadoFisica?> evaluarFisica({
    required String canchaId,
    required String direccion,
    String? ruc,
    LatLng? ubicacion,
    int? solicitudId,
    String motivo = 'sin_documentos',
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/verificacion-fisica/evaluar');
      final resp = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'cancha_id': canchaId,
              'direccion': direccion,
              if (ruc != null && ruc.isNotEmpty) 'ruc': ruc,
              if (ubicacion != null) 'lat': ubicacion.latitude,
              if (ubicacion != null) 'lng': ubicacion.longitude,
              if (solicitudId != null) 'solicitud_id': solicitudId,
              'motivo': motivo,
            }),
          )
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      return ResultadoFisica(
        verificada: (j['verificada'] as bool?) ?? false,
        via: (j['via'] as String?) ?? 'fisica',
        score: (j['score'] as num?)?.toInt() ?? 0,
      );
    } catch (_) {
      return null; // fail-safe: cae a la verificación de existencia directa
    }
  }

  /// Cola de visitas del verificador (agendada/en_sitio), priorizada por demanda
  /// (las canchas más pedidas primero).
  static Future<List<Map<String, dynamic>>> visitas({
    String? zona,
    double? lat,
    double? lng,
    double? radioKm,
  }) async {
    if (!disponible) return [];
    try {
      final params = <String, String>{
        if (zona != null && zona.isNotEmpty) 'zona': zona,
        if (lat != null) 'lat': '$lat',
        if (lng != null) 'lng': '$lng',
        if (radioKm != null) 'radio_km': '$radioKm',
      };
      final q = params.isEmpty
          ? ''
          : '?${params.entries.map((e) => '${e.key}=${e.value}').join('&')}';
      final uri = Uri.parse('$_baseUrl/verificacion-fisica/visitas$q');
      final resp = await http.get(uri).timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return [];
      final data = jsonDecode(resp.body);
      if (data is! List) return [];
      return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  /// El verificador captura fotos GEO del sitio, confirma coincidencia y firma.
  /// Devuelve el resultado del servidor (ok/estado/coincide/distancia/insignia).
  static Future<Map<String, dynamic>?> captura({
    required int vfId,
    required List<String> fotosGeoUrls,
    required double latSitio,
    required double lngSitio,
    required String firma,
    String? observaciones,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/verificacion-fisica/$vfId/captura');
      final resp = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'fotos_geo_urls': fotosGeoUrls,
              'lat_sitio': latSitio,
              'lng_sitio': lngSitio,
              'firma_verificador': firma,
              if (observaciones != null) 'observaciones': observaciones,
            }),
          )
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }
}
