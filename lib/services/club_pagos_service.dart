import 'dart:convert';

import 'package:http/http.dart' as http;

import 'pagos_service.dart';

/// Resultado de una llamada al backend: `ok` + datos o `error` (código del
/// servidor, p. ej. `operacion_repetida`) + mensaje para mostrar.
class RespuestaClub {
  final bool ok;
  final Map<String, dynamic> datos;
  final String error;
  const RespuestaClub(this.ok, this.datos, [this.error = '']);

  String get mensaje => (datos['mensaje'] ?? '').toString().isNotEmpty
      ? datos['mensaje'].toString()
      : mensajeDeError(error);

  /// Textos humanos de los códigos de error del backend (CanchaLibre).
  static String mensajeDeError(String e) => switch (e) {
        '' => '',
        'sesion_requerida' => 'Inicia sesión con Google para continuar.',
        'llaves_invalidas' =>
          'Revisa las llaves: la pública empieza con pk_ y la secreta con sk_.',
        'llaves_de_distinto_modo' =>
          'Las dos llaves deben ser del mismo modo (ambas de prueba o ambas live).',
        'llave_rechazada_por_culqi' =>
          'Culqi no aceptó la llave secreta. Cópiala de nuevo desde tu panel de Culqi.',
        'cifrado_no_configurado' =>
          'Los cobros con tu propio Culqi aún no están habilitados. Escríbenos.',
        'celular_invalido' => 'El celular debe tener 9 dígitos y empezar con 9.',
        'titular_requerido' => 'Escribe el nombre del titular de la cuenta.',
        'cuenta_requerida' => 'Indica el banco y el número de cuenta o CCI.',
        'cci_invalido' => 'El CCI tiene 20 dígitos.',
        'qr_o_numero_requerido' => 'Agrega el número o la imagen del QR.',
        'operacion_repetida' =>
          'Ese número de operación ya se usó para otra reserva de este club.',
        'voucher_repetido' => 'Esa imagen ya se usó para otra reserva.',
        'operacion_requerida' => 'Escribe el número de operación de tu pago.',
        'imagen_invalida' => 'No pudimos leer la imagen. Toma la captura de nuevo.',
        'hold_vencido' =>
          'Tu horario se liberó porque pasó el tiempo de apartado. Vuelve a elegirlo.',
        'club_suspendido' =>
          'Este club no está recibiendo pagos en línea por ahora. Puedes pagar en la cancha.',
        'medio_no_disponible' => 'Ese medio de pago ya no está disponible.',
        'no_es_tu_cancha' => 'Solo el dueño de la cancha puede hacer esto.',
        'reglas_no_disponibles' =>
          'Las reglas de reserva se están habilitando. Inténtalo más tarde.',
        'ya_resuelto' => 'Este pago ya fue revisado.',
        'ocupado' => 'Ese horario acaba de tomarse. Elige otro.',
        'min_turnos' => 'Este club pide reservar más turnos seguidos.',
        'max_turnos' => 'Superas el máximo de turnos seguidos de este club.',
        'tope_reservas_dia' => 'Ya tienes el máximo de reservas de ese día en este club.',
        'sin_conexion' => 'Sin conexión. Revisa tu internet e inténtalo otra vez.',
        _ => 'No pudimos completar la operación. Inténtalo otra vez.',
      };
}

/// Cliente de los endpoints de COBRO DIRECTO AL CLUB y REGLAS DE RESERVA
/// (backend `web/cobro_directo_web.py`, `reservas/router.py`). Todo viaja con
/// la identidad VERIFICADA del usuario (ID token de Google), nunca con un correo
/// escrito por la app.
class ClubPagosService {
  static String get _base => PagosService.baseUrl;
  static bool get disponible => _base.isNotEmpty || simulador != null;

  /// SOLO tests (golden / widget): responde en lugar del backend.
  static Future<RespuestaClub> Function(String metodo, String ruta, Object? cuerpo)? simulador;

  static Future<RespuestaClub> _llamar(String metodo, String ruta, {Object? cuerpo}) async {
    final sim = simulador;
    if (sim != null) return sim(metodo, ruta, cuerpo);
    if (!disponible) return const RespuestaClub(false, {}, 'sin_conexion');
    try {
      final h = await PagosService.headersUsuario(json: cuerpo != null);
      final uri = Uri.parse('$_base$ruta');
      final body = cuerpo == null ? null : jsonEncode(cuerpo);
      final http.Response r = switch (metodo) {
        'PUT' => await http.put(uri, headers: h, body: body).timeout(const Duration(seconds: 25)),
        'POST' => await http.post(uri, headers: h, body: body).timeout(const Duration(seconds: 25)),
        'DELETE' => await http.delete(uri, headers: h).timeout(const Duration(seconds: 15)),
        _ => await http.get(uri, headers: h).timeout(const Duration(seconds: 15)),
      };
      Map<String, dynamic> j = {};
      try {
        final d = jsonDecode(r.body);
        if (d is Map) j = Map<String, dynamic>.from(d);
      } catch (_) {}
      if (r.statusCode >= 400) {
        return RespuestaClub(false, j, (j['detail'] ?? j['error'] ?? 'error').toString());
      }
      final ok = j['ok'] != false;
      return RespuestaClub(ok, j, ok ? '' : (j['error'] ?? 'error').toString());
    } catch (_) {
      return const RespuestaClub(false, {}, 'sin_conexion');
    }
  }

  // ── reglas de reserva (dueño) ──
  static Future<RespuestaClub> reglas(String canchaId) => _llamar('GET', '/reservas/reglas/$canchaId');
  static Future<RespuestaClub> guardarReglas(List<String> canchaIds, Map<String, dynamic> reglas) =>
      _llamar('PUT', '/reservas/reglas', cuerpo: {'cancha_ids': canchaIds, 'reglas': reglas});
  static Future<RespuestaClub> politica(String canchaId) => _llamar('GET', '/reservas/politica/$canchaId');

  // ── cobros del club (dueño) ──
  static Future<RespuestaClub> miConfig() => _llamar('GET', '/club/pagos');
  static Future<RespuestaClub> guardarCulqi(String pk, String sk) =>
      _llamar('PUT', '/club/pagos/culqi', cuerpo: {'public_key': pk, 'secret_key': sk});
  static Future<RespuestaClub> borrarCulqi() => _llamar('DELETE', '/club/pagos/culqi');
  static Future<RespuestaClub> guardarMedios(List<Map<String, dynamic>> medios) =>
      _llamar('PUT', '/club/pagos/medios', cuerpo: {'medios': medios});
  static Future<RespuestaClub> vouchers({bool pendientes = true}) =>
      _llamar('GET', '/club/pagos/vouchers?estado=${pendientes ? 'en_revision' : 'resueltos'}');
  static Future<RespuestaClub> aprobarVoucher(String id) => _llamar('POST', '/club/pagos/vouchers/$id/aprobar');
  static Future<RespuestaClub> rechazarVoucher(String id, String motivo) =>
      _llamar('POST', '/club/pagos/vouchers/$id/rechazar', cuerpo: {'motivo': motivo});

  /// URL + cabeceras para ver la foto del voucher (solo el dueño).
  static String urlImagenVoucher(String id) => '$_base/club/pagos/vouchers/$id/imagen';
  static Future<Map<String, String>> cabecerasImagen() async =>
      simulador != null ? const {} : PagosService.headersUsuario();

  // ── jugador ──
  static Future<RespuestaClub> checkout(String canchaId) => _llamar('GET', '/club/pagos/checkout/$canchaId');

  /// Aparta el bloque EN EL SERVIDOR (precio, reglas y apartado los decide el
  /// backend; mismo flujo que la web).
  static Future<RespuestaClub> apartar({
    required String canchaId,
    required String nombre,
    required String email,
    required String celular,
    required List<({String fecha, String hora})> horas,
    String deporte = '',
    bool sena = false,
  }) =>
      _llamar('POST', '/web/asegurar', cuerpo: {
        'cancha_id': canchaId,
        'nombre': nombre,
        'email': email,
        'celular': celular,
        'deporte': deporte,
        'pago': sena ? 'sena' : 'total',
        'horas': [for (final h in horas) {'fecha': h.fecha, 'hora': h.hora}],
      });

  static Future<RespuestaClub> pagar({
    required List<String> ids,
    required String firma,
    required String token,
    required String medio,
  }) =>
      _llamar('POST', '/web/pagar', cuerpo: {'ids': ids, 'firma': firma, 'token': token, 'medio': medio});

  static Future<RespuestaClub> subirVoucher({
    required List<String> ids,
    required String firma,
    required String medio,
    required String operacion,
    required String imagenBase64,
  }) =>
      _llamar('POST', '/web/voucher', cuerpo: {
        'ids': ids,
        'firma': firma,
        'medio': medio,
        'operacion': operacion,
        'imagen': imagenBase64,
      });

  static Future<RespuestaClub> liberar(List<String> ids, String firma) =>
      _llamar('POST', '/web/liberar', cuerpo: {'ids': ids, 'firma': firma});
}
