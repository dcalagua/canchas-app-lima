import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'pagos_service.dart';

import '../brand.dart';
/// YAPE AUTOMÁTICO (fase 2 del Plan Academia, 10-oct-2026): el celular Android
/// de la academia lee la notificación de su Yape (servicio nativo
/// `YapeListener`, MethodChannel `pichangol/yape_auto`) y el backend confirma
/// solo el pago que el alumno reportó con el mismo código de seguridad y monto
/// (`yape_auto.py`). En Ecuador / Bolivia escucha además las apps de cobro que
/// el dueño eligió (QR con monto único). Solo Android: en iPhone la academia
/// confirma a mano.
class YapeAutoService {
  static const _canal = MethodChannel('pichangol/yape_auto');
  static const _appKey = String.fromEnvironment('APP_API_KEY');

  static bool get soportado {
    try {
      return Platform.isAndroid && PagosService.disponible;
    } catch (_) {
      return false;
    }
  }

  /// ¿El usuario ya dio "Acceso a notificaciones" a Pichangol?
  static Future<bool> permisoActivo() async {
    if (!soportado) return false;
    try {
      return await _canal.invokeMethod<bool>('permisoActivo') ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<bool> abrirPermiso() async {
    try {
      return await _canal.invokeMethod<bool>('abrirPermiso') ?? false;
    } catch (_) {
      return false;
    }
  }

  /// Info de la app (para "Permitir ajustes restringidos" en Android 13+
  /// cuando el APK no vino de Play).
  static Future<bool> abrirInfoApp() async {
    try {
      return await _canal.invokeMethod<bool>('abrirInfoApp') ?? false;
    } catch (_) {
      return false;
    }
  }

  /// Estado local del servicio nativo: {activo, vinculado, pendientes}.
  static Future<Map<String, dynamic>> estadoLocal() async {
    if (!soportado) return const {};
    try {
      final r = await _canal.invokeMethod<Map>('estado');
      return r == null ? const {} : Map<String, dynamic>.from(r);
    } catch (_) {
      return const {};
    }
  }

  /// Estado en el backend: {vinculado, recibidas, confirmadas, activo, paquetes}.
  static Future<Map<String, dynamic>?> estado(String email) async {
    final e = email.trim().toLowerCase();
    if (!soportado || e.isEmpty) return null;
    try {
      final r = await http
          .get(
              Uri.parse('${PagosService.baseUrl}/academias/yape/estado'
                  '?email=${Uri.encodeQueryComponent(e)}'),
              headers: await PagosService.headersUsuario())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body);
      return j is Map ? Map<String, dynamic>.from(j) : null;
    } catch (_) {
      return null;
    }
  }

  static Future<Map<String, dynamic>> _post(
      String ruta, Map<String, dynamic> cuerpo) async {
    try {
      final r = await http
          .post(Uri.parse('${PagosService.baseUrl}$ruta'),
              headers: await PagosService.headersUsuario(json: true),
              body: jsonEncode(cuerpo))
          .timeout(const Duration(seconds: 20));
      final j = jsonDecode(r.body);
      if (j is Map) {
        final m = Map<String, dynamic>.from(j);
        if (r.statusCode != 200 && m['ok'] == null) m['ok'] = false;
        return m;
      }
    } catch (_) {}
    return {
      'ok': false,
      'mensaje': 'Sin conexión. Revisa tu internet y reintenta.'
    };
  }

  static List<String> _paquetes(dynamic l) => [
        if (l is List)
          for (final p in l)
            if (p.toString().trim().isNotEmpty) p.toString().trim()
      ];

  /// Vincula ESTE celular (token nuevo) y enciende el servicio nativo.
  static Future<Map<String, dynamic>> activar(String email) async {
    final e = email.trim().toLowerCase();
    if (!soportado || e.isEmpty) {
      return {'ok': false, 'mensaje': 'Disponible solo en Android.'};
    }
    final r = await _post('/academias/yape/vincular', {'email': e});
    if (r['ok'] != true) return r;
    try {
      await _canal.invokeMethod('configurar', {
        'url': PagosService.baseUrl,
        'appKey': _appKey,
        'email': e,
        'token': (r['token'] ?? '').toString(),
        'paquetes': _paquetes(r['paquetes']),
        'activo': true,
      });
    } catch (_) {
      return {
        'ok': false,
        'mensaje': 'Esta versión del app aún no puede leer notificaciones. '
            'Actualiza $kBrandName.'
      };
    }
    return {'ok': true};
  }

  /// Apaga el servicio nativo y desvincula el celular en el backend.
  static Future<void> desactivar(String email) async {
    try {
      await _canal.invokeMethod('configurar', {
        'url': PagosService.baseUrl,
        'appKey': _appKey,
        'email': email.trim().toLowerCase(),
        'token': '',
        'paquetes': const <String>[],
        'activo': false,
      });
    } catch (_) {}
    await _post(
        '/academias/yape/desvincular', {'email': email.trim().toLowerCase()});
  }

  /// Apps instaladas con ícono (paquete, nombre) para elegir dónde recibe la
  /// academia sus cobros por QR. Vacío si el APK es anterior o falla.
  static Future<List<(String, String)>> appsInstaladas() async {
    if (!soportado) return const [];
    try {
      final l = await _canal.invokeMethod<List>('apps');
      return [
        for (final x in l ?? const [])
          if (x is Map && (x['paquete'] ?? '').toString().isNotEmpty)
            ((x['paquete']).toString(), (x['nombre'] ?? x['paquete']).toString()),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Guarda en el backend las apps de cobro elegidas (QR) y le pasa al
  /// servicio nativo la lista completa (Yape + esas apps).
  static Future<Map<String, dynamic>> elegirApps(
      String email, List<String> paquetes) async {
    final e = email.trim().toLowerCase();
    final r = await _post('/academias/yape/apps', {'email': e, 'paquetes': paquetes});
    if (r['ok'] != true) return r;
    try {
      await _canal.invokeMethod('configurar', {
        'url': PagosService.baseUrl,
        'appKey': _appKey,
        'email': e,
        'token': '',
        'paquetes': _paquetes(r['paquetes']),
        'activo': true,
      });
    } catch (_) {}
    return r;
  }

  /// Al abrir la pantalla: si el servicio está encendido, actualiza los
  /// paquetes de Yape que manda la torre y reintenta lo que quedó en cola.
  static Future<void> sincronizar(String email, List<dynamic>? paquetes) async {
    final loc = await estadoLocal();
    if (loc['activo'] != true) return;
    try {
      if (paquetes != null && paquetes.isNotEmpty) {
        await _canal.invokeMethod('configurar', {
          'url': PagosService.baseUrl,
          'appKey': _appKey,
          'email': email.trim().toLowerCase(),
          'token': '',
          'paquetes': _paquetes(paquetes),
          'activo': true,
        });
      } else {
        await _canal.invokeMethod('reintentar');
      }
    } catch (_) {}
  }
}
