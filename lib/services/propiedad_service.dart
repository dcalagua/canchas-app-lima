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
  // Clave compartida app↔backend (viene de --dart-define en el build). El backend
  // solo acepta llamadas del APK oficial que la traiga en X-App-Key.
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  /// Cabeceras para el backend: envía la clave de app (si está compilada) y, en
  /// los POST, Content-Type JSON.
  static Map<String, String> _appHeaders({bool json = false}) => {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
        if (json) 'Content-Type': 'application/json',
      };

  /// URL del panel web de administración (Pichangol + EBIM) donde el admin
  /// aprueba las canchas desde el navegador. Vacía si el backend no está activo.
  static String get panelUrl => disponible ? '$_baseUrl/admin' : '';

  /// Consulta el DNI (identidad de la persona) vía backend → Factiliza.
  /// Devuelve {ok, nombre_completo, ...} o null si no se pudo.
  static Future<Map<String, dynamic>?> consultarDni(String dni) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/dni/$dni');
      final resp = await http.get(uri, headers: _appHeaders()).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Consulta la CÉDULA ecuatoriana (identidad) vía backend → CipherByte.
  /// Devuelve {ok, nombre_completo, ...} o null si no se pudo.
  static Future<Map<String, dynamic>?> consultarCedula(String cedula) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/cedula/$cedula');
      final resp = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Verifica identidad por documento con la regla ANTI-FRAUDE
  /// **1 documento = 1 cuenta**. Valida contra el registro oficial del país
  /// ([pais]: 'PE' → DNI/RENIEC; 'EC' → cédula) y liga el documento (solo su
  /// hash) al correo. Devuelve {ok, nombre_completo, fecha_nacimiento} o
  /// {ok:false, error:'dni_en_uso'|...}.
  static Future<Map<String, dynamic>?> verificarDni(
      String dni, String email, {String pais = 'PE'}) async {
    if (!disponible) return null;
    try {
      final resp = await http
          .post(Uri.parse('$_baseUrl/propiedad/verificar-dni'),
              headers: _appHeaders(json: true),
              body: jsonEncode({'dni': dni, 'email': email, 'pais': pais}))
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Consulta el RUC (negocio) vía backend → Factiliza.
  /// Devuelve {ok, razon_social, ...} o null si no se pudo.
  static Future<Map<String, dynamic>?> consultarRuc(String ruc) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/ruc/$ruc');
      final resp = await http.get(uri, headers: _appHeaders()).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Consulta el ESTADO del reclamo/propiedad de una cancha en el backend.
  /// Devuelve {existe, estado, panel_desbloqueado, verificada, ...} o null.
  /// Sirve para que la app "se entere" cuando el admin aprueba en el panel.
  /// [solicitante] (opcional): si se pasa, el backend responde `es_mio` = si el
  /// reclamo es de ese correo (para asignar dueño sin apropiaciones).
  static Future<Map<String, dynamic>?> estado(String canchaId,
      {String? solicitante}) async {
    if (!disponible) return null;
    try {
      var uri = Uri.parse('$_baseUrl/propiedad/reclamo/$canchaId');
      if (solicitante != null && solicitante.isNotEmpty) {
        uri = uri.replace(queryParameters: {'solicitante': solicitante});
      }
      final resp = await http.get(uri, headers: _appHeaders()).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Borra en el servidor (torre de control) los reclamos que inició [email].
  /// Lo usa "Dejar en virgen" para que las canchas reclamadas por el dueño
  /// desaparezcan también del backend y pueda reclamarlas de cero. Devuelve
  /// cuántos se borraron, o null si no se pudo (best-effort).
  static Future<int?> borrarMisReclamos(String email) async {
    if (!disponible || email.trim().isEmpty) return null;
    try {
      final resp = await http
          .post(Uri.parse('$_baseUrl/propiedad/reclamos/borrar-mios'),
              headers: _appHeaders(json: true),
              body: jsonEncode({'solicitante': email.trim()}))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      final m = Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
      return (m['borrados'] as num?)?.toInt() ?? 0;
    } catch (_) {
      return null;
    }
  }

  /// ¿Este lugar (lat/lng, o [canchaId]) ya tiene un reclamo activo? Devuelve
  /// {reclamada, estado, por_mi} o null. Sirve para bloquear el botón "Reclamar"
  /// de una cancha descubierta si ya la reclamó otro usuario.
  static Future<Map<String, dynamic>?> lugarReclamado({
    required double lat,
    required double lng,
    String canchaId = '',
    String solicitante = '',
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/lugar-reclamado')
          .replace(queryParameters: {
        'lat': '$lat',
        'lng': '$lng',
        if (canchaId.isNotEmpty) 'cancha_id': canchaId,
        if (solicitante.isNotEmpty) 'solicitante': solicitante,
      });
      final resp = await http.get(uri, headers: _appHeaders()).timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  /// Crea una SOLICITUD DE RECLAMO (modelo concierge): avisa al admin de
  /// Pichangol por WhatsApp con un código para que vetee al reclamante antes de
  /// activar nada. Devuelve {ok, reclamo_id, codigo, estado} o null si falló.
  static Future<Map<String, dynamic>?> crearReclamo({
    required String canchaId,
    required String solicitanteId,
    required String nombreLocal,
    String solicitanteNombre = '',
    String? telefonoContacto,
    String? dni,
    String? ruc,
    String? relacion,
    LatLng? ubicacion,
    LatLng? solicitanteUbicacion,
  }) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/propiedad/reclamo');
      final resp = await http
          .post(uri,
              headers: _appHeaders(json: true),
              body: jsonEncode({
                'cancha_id': canchaId,
                'solicitante_id': solicitanteId,
                if (solicitanteNombre.trim().isNotEmpty)
                  'solicitante_nombre': solicitanteNombre.trim(),
                'nombre_local': nombreLocal,
                if (telefonoContacto != null && telefonoContacto.isNotEmpty)
                  'telefono_contacto': telefonoContacto,
                if (dni != null && dni.isNotEmpty) 'dni': dni,
                if (ruc != null && ruc.isNotEmpty) 'ruc': ruc,
                if (relacion != null && relacion.isNotEmpty) 'relacion': relacion,
                if (ubicacion != null) 'lat': ubicacion.latitude,
                if (ubicacion != null) 'lng': ubicacion.longitude,
                if (solicitanteUbicacion != null)
                  'solicitante_lat': solicitanteUbicacion.latitude,
                if (solicitanteUbicacion != null)
                  'solicitante_lng': solicitanteUbicacion.longitude,
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
              headers: _appHeaders(json: true),
              body: jsonEncode({'cancha_id': canchaId, 'telefono': telefono}))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(resp.body) as Map);
    } catch (_) {
      return null;
    }
  }

  // NOTA: la administración de reclamos (listar/triage/aprobar/rechazar y el
  // modo de aprobación) NO vive en el APK — es la TORRE DE CONTROL web /admin
  // (protegida por token) + aprobación por WhatsApp. Sus endpoints /propiedad/*
  // exigen X-Admin-Token en el backend; la app del dueño no los usa.

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
              headers: _appHeaders(json: true),
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
              headers: _appHeaders(json: true),
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
