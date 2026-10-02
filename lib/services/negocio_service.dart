import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'auth_service.dart';

/// Respuesta del backend del negocio. [status] 0 = sin red / sin respuesta.
class RespuestaNegocio {
  final int status;
  final Map<String, dynamic> cuerpo;

  const RespuestaNegocio(this.status, this.cuerpo);

  bool get ok => status == 200 && cuerpo['ok'] == true;

  /// Sin red, servidor caído o saturado: se reintenta más tarde (cola).
  /// Un 4xx (dato inválido, cancha ajena…) NO se reintenta.
  bool get reintentar =>
      status == 0 || status >= 500 || status == 408 || status == 429;

  String get error {
    final e = (cuerpo['error'] ?? cuerpo['detail'] ?? '').toString();
    if (e.isNotEmpty) return e;
    return status == 0
        ? 'Sin conexión. Se guardará apenas vuelva la señal.'
        : 'No se pudo guardar. Intenta de nuevo.';
  }
}

/// NEGOCIO DEL DUEÑO en el backend (`/negocio/*`, `backend/growth/negocio_app.py`):
/// cierres de caja, reservas fijas, notas privadas de clientes y "ya
/// recordado". Es la MISMA fuente que usa la web (modo anfitrión), así el
/// dueño ve lo mismo en el app y en el navegador. El APK guarda una copia en
/// el teléfono solo como caché (device-first) y una cola para lo hecho sin red.
class NegocioService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get disponible => _baseUrl.isNotEmpty;

  static Future<Map<String, String>> _headers({bool json = false}) async {
    final h = <String, String>{
      if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
      if (json) 'Content-Type': 'application/json',
    };
    final t = await AuthService.idToken();
    if (t != null && t.isNotEmpty) h['X-User-Token'] = t;
    return h;
  }

  static RespuestaNegocio _leer(http.Response r) {
    try {
      final j = jsonDecode(r.body);
      if (j is Map) {
        return RespuestaNegocio(r.statusCode, Map<String, dynamic>.from(j));
      }
    } catch (_) {}
    return RespuestaNegocio(r.statusCode, const <String, dynamic>{});
  }

  static Future<RespuestaNegocio> _post(
      String ruta, Map<String, dynamic> body) async {
    if (!disponible) return const RespuestaNegocio(0, <String, dynamic>{});
    try {
      final r = await http
          .post(Uri.parse('$_baseUrl$ruta'),
              headers: await _headers(json: true), body: jsonEncode(body))
          .timeout(const Duration(seconds: 20));
      return _leer(r);
    } catch (_) {
      return const RespuestaNegocio(0, <String, dynamic>{});
    }
  }

  /// Estado completo {cierres, fijas, notas, recordados}. Con [autocerrar] el
  /// servidor primero genera los cierres automáticos de días pasados.
  static Future<RespuestaNegocio> estado(String email,
      {bool autocerrar = false}) async {
    if (!disponible) return const RespuestaNegocio(0, <String, dynamic>{});
    try {
      final r = await http
          .get(
              Uri.parse('$_baseUrl/negocio/estado').replace(queryParameters: {
                'email': email.trim().toLowerCase(),
                if (autocerrar) 'autocerrar': '1',
              }),
              headers: await _headers())
          .timeout(const Duration(seconds: 20));
      return _leer(r);
    } catch (_) {
      return const RespuestaNegocio(0, <String, dynamic>{});
    }
  }

  /// Ejecuta una operación de la cola (ver `AppState._negocioPend`). Cada
  /// operación lleva `tipo` y sus datos; el correo va en `email`.
  static Future<RespuestaNegocio> ejecutar(Map<String, dynamic> op) {
    final email = (op['email'] ?? '').toString();
    switch (op['tipo']) {
      case 'cerrar':
        return _post('/negocio/caja/cerrar', {
          'email': email,
          'fecha': op['fecha'],
          'moneda': op['moneda'],
        });
      case 'reabrir':
        return _post('/negocio/caja/reabrir', {
          'email': email,
          'fecha': op['fecha'],
          'moneda': op['moneda'],
        });
      case 'fija_crear':
        return _post('/negocio/fijas', {
          'email': email,
          'id': op['id'],
          'cancha_id': op['canchaId'],
          'dia': op['diaSemana'],
          'hora': op['hora'],
          'nombre': op['clienteNombre'],
          'telefono': op['clienteTelefono'],
          'cliente_email': op['clienteEmail'],
        });
      case 'fija_activo':
        return _post('/negocio/fijas/${Uri.encodeComponent('${op['id']}')}/activo',
            {'email': email, 'activo': op['activo'] == true});
      case 'fija_quitar':
        return _post('/negocio/fijas/${Uri.encodeComponent('${op['id']}')}/quitar',
            {'email': email});
      case 'nota':
        return _post('/negocio/notas', {
          'email': email,
          'clave': op['clave'],
          'texto': op['texto'],
        });
      case 'recordado':
        return _post('/negocio/recordados', {
          'email': email,
          'clave': op['clave'],
          'cuando': op['cuando'],
        });
      default:
        // Operación desconocida (de una versión futura): se descarta.
        return Future.value(
            const RespuestaNegocio(400, <String, dynamic>{'ok': false}));
    }
  }

  /// Completa en el SERVIDOR las próximas 4 semanas de las fijas activas
  /// (respeta bloqueos, turnos pasados y fechas ya generadas). {creadas}.
  static Future<RespuestaNegocio> generarFijas(String email) =>
      _post('/negocio/fijas/generar', {'email': email.trim().toLowerCase()});

  /// Borra TODO el negocio del dueño en el backend ("Dejar en virgen" /
  /// "Eliminar mi cuenta"). Best-effort.
  static Future<bool> borrar(String email) async =>
      (await _post('/negocio/borrar', {'email': email.trim().toLowerCase()}))
          .ok;

  /// Sube UNA vez por equipo lo que el teléfono tenía guardado de antes.
  static Future<RespuestaNegocio> migrar({
    required String email,
    required String dispositivo,
    required List<dynamic> cierres,
    required List<dynamic> fijas,
    required Map<String, dynamic> notas,
    required Map<String, dynamic> recordados,
  }) =>
      _post('/negocio/migrar', {
        'email': email.trim().toLowerCase(),
        'dispositivo': dispositivo,
        'cierres': cierres,
        'fijas': fijas,
        'notas': notas,
        'recordados': recordados,
      });
}
