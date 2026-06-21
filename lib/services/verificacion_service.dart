import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:http/http.dart' as http;

/// Resultado de la verificación de existencia (lo que devuelve el backend
/// `/verificacion/existencia`). Sin datos personales.
class ResultadoExistencia {
  final int score;
  final bool aprobado;
  final String nivel; // alto | medio | bajo
  final String justificacion;

  const ResultadoExistencia({
    required this.score,
    required this.aprobado,
    required this.nivel,
    required this.justificacion,
  });
}

/// Cliente del submódulo de **verificación de existencia** (backend Python).
///
/// La URL base llega por `--dart-define=VERIF_API_URL` (p. ej.
/// `https://verif.midominio.com`). Si no está definida, el servicio queda
/// inactivo y todo sigue funcionando: la cancha simplemente queda **pendiente de
/// verificación** para revisión manual (fail-safe).
class VerificacionService {
  static const _baseUrl = String.fromEnvironment('VERIF_API_URL');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Llama a `POST /verificacion/existencia`. Devuelve el resultado o null si el
  /// servicio no está configurado / no respondió (queda pendiente manual).
  static Future<ResultadoExistencia?> verificarExistencia({
    required String canchaId,
    required String direccion,
    String? ruc,
    String? razonSocial,
    LatLng? ubicacion,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/verificacion/existencia');
      final resp = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'cancha_id': canchaId,
              'direccion': direccion,
              if (ruc != null && ruc.isNotEmpty) 'ruc': ruc,
              if (razonSocial != null && razonSocial.isNotEmpty)
                'razon_social': razonSocial,
              if (ubicacion != null) 'lat': ubicacion.latitude,
              if (ubicacion != null) 'lng': ubicacion.longitude,
            }),
          )
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;
      final j = jsonDecode(resp.body) as Map<String, dynamic>;
      return ResultadoExistencia(
        score: (j['score_existencia'] as num?)?.toInt() ?? 0,
        aprobado: (j['aprobado'] as bool?) ?? false,
        nivel: (j['nivel'] as String?) ?? 'bajo',
        justificacion: (j['justificacion'] as String?) ?? '',
      );
    } catch (_) {
      return null; // fail-safe: queda pendiente de verificación manual
    }
  }
}
