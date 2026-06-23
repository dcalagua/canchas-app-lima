import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente de **verificación de PROPIEDAD** (backend/growth, módulo propiedad).
/// Envía un código OTP por WhatsApp al teléfono del local y lo confirma. Esto es
/// lo único que vuelve "verificada" (reservable) una cancha reclamada: existir no
/// es lo mismo que ser el dueño.
///
/// Reusa la misma URL base del backend de crecimiento (`GROWTH_API_URL`). Si no
/// está configurada, el servicio queda inactivo (fail-safe).
class PropiedadService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Pide enviar un código al teléfono del local. Devuelve el resultado del
  /// servidor (ok, telefono_enmascarado, via, expira_seg) o null si falló.
  static Future<Map<String, dynamic>?> solicitarOtp({
    required String canchaId,
    required String telefono,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/otp/solicitar');
      final resp = await http
          .post(uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'cancha_id': canchaId, 'telefono': telefono}))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Confirma el código. Si `estado == 'confirmada'`, la propiedad quedó probada.
  /// `telefonoPublico` (opcional) es el teléfono del local que trajo Google/redes;
  /// si se manda y coincide con el del OTP, la confirmación es automática.
  static Future<Map<String, dynamic>?> confirmarOtp({
    required String canchaId,
    required String codigo,
    required String solicitanteId,
    String? telefonoPublico,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/otp/confirmar');
      final resp = await http
          .post(uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'cancha_id': canchaId,
                'codigo': codigo,
                'solicitante_id': solicitanteId,
                if (telefonoPublico != null && telefonoPublico.isNotEmpty)
                  'telefono_publico': telefonoPublico,
              }))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }
}
