import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Cliente de PAGOS (Culqi, modelo inDrive). Dos capas:
/// 1. **Tokenización** con la llave PÚBLICA contra `secure.culqi.com` (tarjeta o
///    Yape) — se hace en el celular; nunca manda datos de tarjeta a nuestro
///    backend, solo el `token` resultante.
/// 2. **Cobro** llamando a nuestro backend (`/pagos/*`), que crea el cargo con la
///    llave SECRETA y acredita el saldo del dueño.
///
/// La llave pública se obtiene de `/pagos/config` (no se hardcodea en el APK).
class PagosService {
  static const _baseUrl = String.fromEnvironment('GROWTH_API_URL');
  static const _appKey = String.fromEnvironment('APP_API_KEY');
  static const _culqiSecure = 'https://secure.culqi.com/v2';

  static bool get disponible => _baseUrl.isNotEmpty;

  static Map<String, String> _appHeaders({bool json = false}) => {
        if (_appKey.isNotEmpty) 'X-App-Key': _appKey,
        if (json) 'Content-Type': 'application/json',
      };

  static int solesACentimos(double soles) => (soles * 100).round();

  // --- 1) Config pública (llave pk, modo, comisión) -----------------------
  static Future<Map<String, dynamic>?> config() async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/pagos/config');
      final r = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      return Map<String, dynamic>.from(jsonDecode(r.body) as Map);
    } catch (_) {
      return null;
    }
  }

  // --- 2) Tokenización con la llave PÚBLICA (Culqi secure) -----------------
  /// Tokeniza una TARJETA. Devuelve {ok, token} o {ok:false, error}.
  static Future<Map<String, dynamic>> tokenizarTarjeta({
    required String publicKey,
    required String numero,
    required String cvv,
    required int mesExp,
    required int anioExp,
    required String email,
  }) async {
    try {
      final r = await http.post(
        Uri.parse('$_culqiSecure/tokens'),
        headers: {
          'Authorization': 'Bearer $publicKey',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'card_number': numero.replaceAll(' ', ''),
          'cvv': cvv,
          'expiration_month': mesExp,
          'expiration_year': anioExp,
          'email': email,
        }),
      ).timeout(const Duration(seconds: 20));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      if (r.statusCode == 200 || r.statusCode == 201) {
        return {'ok': true, 'token': j['id']};
      }
      return {'ok': false, 'error': _errCulqi(j, 'Tarjeta rechazada')};
    } catch (e) {
      return {'ok': false, 'error': 'No se pudo procesar la tarjeta.'};
    }
  }

  /// Arma un mensaje de error legible con la pista técnica de Culqi (code) para
  /// poder diagnosticar (ej. yape no habilitado vs código inválido).
  static String _errCulqi(Map<String, dynamic> j, String fallback) {
    final msg = (j['user_message'] ?? j['merchant_message'] ?? fallback).toString();
    final code = (j['code'] ?? j['type'] ?? '').toString();
    return code.isEmpty ? msg : '$msg  [$code]';
  }

  /// Tokeniza un pago YAPE. El usuario genera un código en su app Yape (Yape →
  /// "Código de aprobación") y lo ingresa junto a su celular. Devuelve
  /// {ok, token} o {ok:false, error}.
  static Future<Map<String, dynamic>> tokenizarYape({
    required String publicKey,
    required String celular,
    required String otp,
    required int montoCentimos,
  }) async {
    try {
      final r = await http.post(
        Uri.parse('$_culqiSecure/tokens/yape'),
        headers: {
          'Authorization': 'Bearer $publicKey',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'amount': montoCentimos,
          'number_phone': celular.replaceAll(RegExp(r'[^0-9]'), ''),
          'otp': otp.replaceAll(RegExp(r'[^0-9]'), ''),
        }),
      ).timeout(const Duration(seconds: 20));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      if (r.statusCode == 200 || r.statusCode == 201) {
        return {'ok': true, 'token': j['id']};
      }
      return {'ok': false, 'error': _errCulqi(j, 'No se pudo validar el Yape')};
    } catch (e) {
      return {'ok': false, 'error': 'No se pudo procesar el Yape.'};
    }
  }

  // --- 3) Cobro en nuestro backend (crea el cargo con la sk) ---------------
  /// Recarga el saldo prepago del dueño. Devuelve {ok, saldoSoles} o {ok:false}.
  static Future<Map<String, dynamic>> recargar({
    required String token,
    required String duenoId,
    required String email,
    required double montoSoles,
  }) async {
    if (!disponible) {
      return {'ok': false, 'error': 'Falta GROWTH_API_URL en el APK.'};
    }
    try {
      final r = await http.post(
        Uri.parse('$_baseUrl/pagos/recarga'),
        headers: _appHeaders(json: true),
        body: jsonEncode({
          'token': token,
          'dueno_id': duenoId,
          'email': email,
          'monto_soles': montoSoles,
        }),
      ).timeout(const Duration(seconds: 40));
      Map<String, dynamic> j = {};
      try {
        j = jsonDecode(r.body) as Map<String, dynamic>;
      } catch (_) {}
      if (r.statusCode == 200 && j['ok'] == true) {
        return {'ok': true, 'saldoSoles': (j['saldo_soles'] as num?)?.toDouble() ?? 0};
      }
      // Mensaje preciso: detalle del backend + código/merchant de Culqi.
      final det = (j['error'] ?? j['detail'] ?? '').toString();
      final code = (j['codigo'] ?? '').toString();
      final merch = (j['merchant'] ?? '').toString();
      final extra = [
        if (code.isNotEmpty) 'cód: $code',
        if (merch.isNotEmpty && merch != det) merch,
      ].join(' · ');
      return {
        'ok': false,
        'error': 'HTTP ${r.statusCode}: ${det.isEmpty ? '(sin detalle)' : det}'
            '${extra.isEmpty ? '' : '\n$extra'}',
      };
    } on TimeoutException {
      return {'ok': false, 'error': 'El servidor de pagos no respondió (timeout). Reintenta.'};
    } catch (e) {
      return {'ok': false, 'error': 'No se pudo contactar el backend [${e.runtimeType}].'};
    }
  }

  /// Cobra al jugador [montoSoles] (tarjeta nueva tkn_ o guardada crd_) a la
  /// cuenta de Pichangol. Para reservas y matrículas. {ok, chargeId} o {ok:false}.
  static Future<Map<String, dynamic>> cobrar({
    required String token,
    required String email,
    required double montoSoles,
    required String concepto,
    String tipo = 'cobro',
  }) async {
    if (!disponible) return {'ok': false, 'error': 'Falta GROWTH_API_URL en el APK.'};
    try {
      final r = await http.post(
        Uri.parse('$_baseUrl/pagos/cobrar'),
        headers: _appHeaders(json: true),
        body: jsonEncode({
          'token': token,
          'email': email,
          'monto_soles': montoSoles,
          'concepto': concepto,
          'tipo': tipo,
        }),
      ).timeout(const Duration(seconds: 40));
      Map<String, dynamic> j = {};
      try {
        j = jsonDecode(r.body) as Map<String, dynamic>;
      } catch (_) {}
      if (r.statusCode == 200 && j['ok'] == true) {
        return {'ok': true, 'chargeId': j['charge_id']};
      }
      final det = (j['error'] ?? j['detail'] ?? '').toString();
      final code = (j['codigo'] ?? '').toString();
      final merch = (j['merchant'] ?? '').toString();
      final extra = [
        if (code.isNotEmpty) 'cód: $code',
        if (merch.isNotEmpty && merch != det) merch,
      ].join(' · ');
      return {
        'ok': false,
        'error': 'HTTP ${r.statusCode}: ${det.isEmpty ? '(sin detalle)' : det}'
            '${extra.isEmpty ? '' : '\n$extra'}',
      };
    } on TimeoutException {
      return {'ok': false, 'error': 'El servidor de pagos no respondió (timeout).'};
    } catch (e) {
      return {'ok': false, 'error': 'No se pudo contactar el backend [${e.runtimeType}].'};
    }
  }

  /// Cobra al jugador solo la comisión (fallback saldo cero). {ok, chargeId}.
  static Future<Map<String, dynamic>> feeReserva({
    required String token,
    required String email,
    required double montoSoles,
    required String concepto,
    String? reservaId,
  }) async {
    if (!disponible) return {'ok': false, 'error': 'Pagos no disponibles.'};
    try {
      final r = await http.post(
        Uri.parse('$_baseUrl/pagos/fee-reserva'),
        headers: _appHeaders(json: true),
        body: jsonEncode({
          'token': token,
          'email': email,
          'monto_soles': montoSoles,
          'concepto': concepto,
          'reserva_id': reservaId,
        }),
      ).timeout(const Duration(seconds: 25));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      if (r.statusCode == 200 && j['ok'] == true) {
        return {'ok': true, 'chargeId': j['charge_id']};
      }
      return {'ok': false, 'error': j['error'] ?? 'No se pudo cobrar.'};
    } catch (e) {
      return {'ok': false, 'error': 'Sin conexión con el servidor de pagos.'};
    }
  }

  /// Descuenta la COMISIÓN de Pichangol del saldo del DUEÑO cuando entra una
  /// reserva pagada en efectivo (el jugador pagó la cancha; PCG cobra del saldo
  /// prepago del dueño). Idempotente por [reservaId] en el backend: seguro de
  /// reintentar. Best-effort: si no hay red, devuelve null y la reserva igual
  /// queda hecha (se reconcilia en la próxima). No bloquea al jugador.
  static Future<Map<String, dynamic>?> comisionReserva({
    required String duenoId,
    required double montoSoles,
    required String reservaId,
    String? concepto,
  }) async {
    if (!disponible || duenoId.isEmpty) return null;
    try {
      final r = await http
          .post(
            Uri.parse('$_baseUrl/pagos/comision-reserva'),
            headers: _appHeaders(json: true),
            body: jsonEncode({
              'dueno_id': duenoId,
              'monto_soles': montoSoles,
              'reserva_id': reservaId,
              if (concepto != null) 'concepto': concepto,
            }),
          )
          .timeout(const Duration(seconds: 15));
      if (r.statusCode == 200) {
        return jsonDecode(r.body) as Map<String, dynamic>;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  // --- 4) Métodos de pago guardados (Culqi One Click) ---------------------
  /// Lista las tarjetas guardadas del usuario: [{id, marca, ultimos4}].
  static Future<List<Map<String, dynamic>>> metodos(String userId) async {
    if (!disponible) return [];
    try {
      final uri = Uri.parse('$_baseUrl/pagos/metodos/$userId');
      final r = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return [];
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return ((j['metodos'] as List?) ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Guarda una tarjeta (token temporal → tarjeta permanente en Culqi).
  /// {ok, metodo} o {ok:false, error}.
  static Future<Map<String, dynamic>> guardarMetodo({
    required String token,
    required String userId,
    required String email,
    String nombre = '',
    String apellido = '',
  }) async {
    if (!disponible) return {'ok': false, 'error': 'Pagos no disponibles.'};
    try {
      final r = await http.post(
        Uri.parse('$_baseUrl/pagos/metodos'),
        headers: _appHeaders(json: true),
        body: jsonEncode({
          'token': token,
          'user_id': userId,
          'email': email,
          'nombre': nombre,
          'apellido': apellido,
        }),
      ).timeout(const Duration(seconds: 25));
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      if (r.statusCode == 200 && j['ok'] == true) {
        return {'ok': true, 'metodo': j['metodo']};
      }
      return {'ok': false, 'error': j['error'] ?? 'No se pudo guardar la tarjeta.'};
    } catch (e) {
      return {'ok': false, 'error': 'Sin conexión con el servidor de pagos.'};
    }
  }

  /// Elimina una tarjeta guardada. Devuelve true si se borró.
  static Future<bool> eliminarMetodo(String userId, String cardId) async {
    if (!disponible) return false;
    try {
      final r = await http.delete(
        Uri.parse('$_baseUrl/pagos/metodos/$userId/$cardId'),
        headers: _appHeaders(),
      ).timeout(const Duration(seconds: 15));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Saldo actual del dueño (en soles). Null si no se pudo.
  static Future<double?> saldo(String duenoId) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/pagos/saldo/$duenoId');
      final r = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return (j['saldo_soles'] as num?)?.toDouble();
    } catch (_) {
      return null;
    }
  }

  /// Conjunto de dueños DESTACADOS (saldo prepago > 0) con su nivel (1-3).
  /// El APK resalta las canchas de estos dueños en Explorar (más saldo = más
  /// visibilidad). Devuelve {duenoId(lowercase): nivel} o null si no se pudo.
  static Future<Map<String, int>?> destacados() async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/pagos/destacados');
      final r = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      final lst = (j['destacados'] as List?) ?? const [];
      final map = <String, int>{};
      for (final e in lst) {
        if (e is! Map) continue;
        final id = (e['dueno_id'] as String?)?.toLowerCase().trim();
        if (id != null && id.isNotEmpty) {
          map[id] = (e['nivel'] as num?)?.toInt() ?? 1;
        }
      }
      return map;
    } catch (_) {
      return null;
    }
  }

  // Impresiones ya enviadas en esta sesión (dedup: no inflar el conteo).
  static final Set<String> _vistasEnviadas = {};

  /// Registra una IMPRESIÓN (vista de destacado) por cada id NUEVO en esta
  /// sesión — dedup para no contar la misma vista dos veces. Fire-and-forget.
  /// El id es el dueno (correo) para canchas o el id de la academia.
  static Future<void> registrarVistasUnaVez(List<String> ids) async {
    if (!disponible) return;
    final nuevos = ids
        .map((e) => e.toLowerCase().trim())
        .where((e) => e.isNotEmpty && _vistasEnviadas.add(e))
        .toList();
    if (nuevos.isEmpty) return;
    try {
      await http
          .post(Uri.parse('$_baseUrl/pagos/vistas/registrar'),
              headers: _appHeaders(json: true),
              body: jsonEncode({'ids': nuevos}))
          .timeout(const Duration(seconds: 8));
    } catch (_) {}
  }

  /// Resumen de impresiones de [ids] (dueño/academia): {semana, total}. Null si
  /// no se pudo. Para "X jugadores vieron tu cancha destacada".
  static Future<Map<String, int>?> resumenVistas(List<String> ids) async {
    if (!disponible) return null;
    final limpio = ids
        .map((e) => e.toLowerCase().trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (limpio.isEmpty) return null;
    try {
      final r = await http
          .post(Uri.parse('$_baseUrl/pagos/vistas/consultar'),
              headers: _appHeaders(json: true),
              body: jsonEncode({'ids': limpio}))
          .timeout(const Duration(seconds: 10));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      return {
        'semana': (j['semana'] as num?)?.toInt() ?? 0,
        'total': (j['total'] as num?)?.toInt() ?? 0,
      };
    } catch (_) {
      return null;
    }
  }

  /// Historial de movimientos de saldo del dueño (recargas), del backend, del
  /// más reciente al más antiguo. Sobrevive a reinstalar la app (el local no).
  /// Cada item: {tipo, monto_soles, concepto, creado_en}. Null si no se pudo.
  static Future<List<Map<String, dynamic>>?> movimientos(String duenoId) async {
    if (!disponible) return null;
    try {
      final uri = Uri.parse('$_baseUrl/pagos/movimientos/$duenoId');
      final r = await http.get(uri, headers: _appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      final lst = (j['movimientos'] as List?) ?? const [];
      return lst.cast<Map<String, dynamic>>();
    } catch (_) {
      return null;
    }
  }
}
