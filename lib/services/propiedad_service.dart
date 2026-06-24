import 'dart:convert';

import 'package:google_maps_flutter/google_maps_flutter.dart';
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

  /// Crea una SOLICITUD DE RECLAMO (modelo concierge): avisa al admin de
  /// Pichangol por WhatsApp con un código para que vetee al reclamante antes de
  /// activar nada. Devuelve {ok, reclamo_id, codigo, estado} o null si falló.
  static Future<Map<String, dynamic>?> crearReclamo({
    required String canchaId,
    required String solicitanteId,
    required String nombreLocal,
    String? telefonoContacto,
    LatLng? ubicacion,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/reclamo');
      final resp = await http
          .post(uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'cancha_id': canchaId,
                'solicitante_id': solicitanteId,
                'nombre_local': nombreLocal,
                if (telefonoContacto != null && telefonoContacto.isNotEmpty)
                  'telefono_contacto': telefonoContacto,
                if (ubicacion != null) 'lat': ubicacion.latitude,
                if (ubicacion != null) 'lng': ubicacion.longitude,
              }))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

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

  /// Lista los reclamos (para el panel admin). `estado` opcional para filtrar
  /// (p. ej. 'pendiente_triage').
  static Future<List<Map<String, dynamic>>> listarReclamos({String? estado}) async {
    if (!disponible) return [];
    try {
      final q = estado != null && estado.isNotEmpty ? '?estado=$estado' : '';
      final uri = Uri.parse('$_baseUrl/propiedad/reclamos$q');
      final resp = await http.get(uri).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return [];
      final data = jsonDecode(resp.body);
      if (data is! List) return [];
      return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  /// El admin aprueba o rechaza un reclamo (triage). Al aprobar, el dueño puede
  /// configurar su cancha.
  static Future<Map<String, dynamic>?> triageReclamo({
    required int reclamoId,
    required bool aprobado,
    String? revisor,
    String? nota,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/reclamo/$reclamoId/triage');
      final resp = await http
          .post(uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'aprobado': aprobado,
                if (revisor != null) 'revisor': revisor,
                if (nota != null) 'nota': nota,
              }))
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// El motorizado valida un reclamo EN SITIO: ingresa el código y manda su GPS.
  /// El servidor exige que la ubicación coincida con la de la cancha.
  static Future<Map<String, dynamic>?> validarReclamo({
    required String codigo,
    required double lat,
    required double lng,
    String? validador,
    List<String> fotosUrls = const [],
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/reclamo/validar');
      final resp = await http
          .post(uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'codigo': codigo,
                'lat': lat,
                'lng': lng,
                if (validador != null) 'validador': validador,
                'fotos_urls': fotosUrls,
              }))
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
