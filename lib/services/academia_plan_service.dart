import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/academia.dart';
import 'pagos_service.dart';

/// Estado del PLAN ACADEMIA de una academia (`GET /academias/plan/{id}`).
/// estado: `prueba` · `activa` · `vencida` · `libre` (modelo "comision": todo
/// abierto, como siempre).
class PlanAcademiaEstado {
  final String estado;
  final bool beneficios;
  final String vence; // ISO
  final String venceTxt; // "12 nov 2026"
  final int? diasRestantes;
  final double precio;
  final String simbolo;
  final String moneda; // ISO
  final bool autoRenovar;
  final bool pagado;
  final CobroDirecto? cobroDirecto;

  const PlanAcademiaEstado({
    required this.estado,
    required this.beneficios,
    this.vence = '',
    this.venceTxt = '',
    this.diasRestantes,
    this.precio = 0,
    this.simbolo = 'S/',
    this.moneda = 'PEN',
    this.autoRenovar = true,
    this.pagado = false,
    this.cobroDirecto,
  });

  bool get enPrueba => estado == 'prueba';
  bool get activa => estado == 'activa';
  bool get vencida => estado == 'vencida';
  bool get libre => estado == 'libre';

  factory PlanAcademiaEstado.deJson(Map<String, dynamic> j) {
    final p = j['precio'];
    final d = j['dias_restantes'];
    return PlanAcademiaEstado(
      estado: (j['estado'] ?? 'libre').toString(),
      beneficios: j['beneficios'] != false,
      vence: (j['vence'] ?? '').toString(),
      venceTxt: (j['vence_txt'] ?? '').toString(),
      diasRestantes: d is num ? d.toInt() : null,
      precio: p is num ? p.toDouble() : double.tryParse('${p ?? ''}') ?? 0,
      simbolo: (j['simbolo'] ?? 'S/').toString(),
      moneda: (j['moneda'] ?? 'PEN').toString(),
      autoRenovar: j['auto_renovar'] != false,
      pagado: j['pagado'] == true,
      cobroDirecto: CobroDirecto.deJson(j['cobro_directo']),
    );
  }

  Map<String, dynamic> toJson() => {
        'estado': estado,
        'beneficios': beneficios,
        'vence': vence,
        'vence_txt': venceTxt,
        'dias_restantes': diasRestantes,
        'precio': precio,
        'simbolo': simbolo,
        'moneda': moneda,
        'auto_renovar': autoRenovar,
        'pagado': pagado,
        if (cobroDirecto != null) 'cobro_directo': cobroDirecto!.toJson(),
      };
}

/// Un pago directo (Yape) reportado por un alumno y pendiente de que la
/// academia lo confirme (`GET /academias/pago-directo/pendientes`).
class PagoPorConfirmar {
  final String academiaId;
  final String academia;
  final String alumnoId;
  final String alumno;
  final String pagador;
  final String codigo;
  final String operacion;
  final String fecha;
  final String simbolo;
  final List<({String id, String concepto, double monto})> cuotas;
  final double total;
  /// 'yape' | 'qr'. En QR no hay código: se compara el MONTO ÚNICO.
  final String medio;
  final double? montoUnico;

  bool get esQr => medio == 'qr';

  const PagoPorConfirmar({
    required this.academiaId,
    required this.academia,
    required this.alumnoId,
    required this.alumno,
    required this.pagador,
    required this.codigo,
    required this.operacion,
    required this.fecha,
    required this.simbolo,
    required this.cuotas,
    required this.total,
    this.medio = 'yape',
    this.montoUnico,
  });

  factory PagoPorConfirmar.deJson(Map<String, dynamic> j) {
    double n(dynamic v) =>
        v is num ? v.toDouble() : double.tryParse('${v ?? ''}') ?? 0;
    final cs = <({String id, String concepto, double monto})>[];
    final l = j['cuotas'];
    if (l is List) {
      for (final c in l) {
        if (c is! Map) continue;
        cs.add((
          id: (c['id'] ?? '').toString(),
          concepto: (c['concepto'] ?? '').toString(),
          monto: n(c['monto']),
        ));
      }
    }
    return PagoPorConfirmar(
      academiaId: (j['academia_id'] ?? '').toString(),
      academia: (j['academia'] ?? '').toString(),
      alumnoId: (j['alumno_id'] ?? '').toString(),
      alumno: (j['alumno'] ?? '').toString(),
      pagador: (j['pagador'] ?? '').toString(),
      codigo: (j['codigo'] ?? '').toString(),
      operacion: (j['operacion'] ?? '').toString(),
      fecha: (j['fecha'] ?? '').toString(),
      simbolo: (j['simbolo'] ?? 'S/').toString(),
      cuotas: cs,
      total: n(j['total']),
      medio: (j['medio'] ?? 'yape').toString(),
      montoUnico: j['monto_unico'] == null ? null : n(j['monto_unico']),
    );
  }
}

/// Pago por QR con MONTO ÚNICO (Ecuador / Bolivia): lo que devuelve
/// `/academias/pago-qr/*`. estado: `esperando` · `reportado` (el alumno tocó
/// "Ya pagué") · `confirmado` · `vencido` · `reemplazado` · `rechazado`.
class PagoQr {
  final String id;
  final String estado;
  final String academia;
  final String simbolo;
  final double monto;
  final String montoTxt;
  final String extraTxt;
  final String qrUrl;
  final String appNombre;
  final String titular;
  final String vence;
  const PagoQr({
    required this.id,
    required this.estado,
    required this.academia,
    required this.simbolo,
    required this.monto,
    required this.montoTxt,
    required this.extraTxt,
    required this.qrUrl,
    required this.appNombre,
    required this.titular,
    required this.vence,
  });

  bool get vivo => estado == 'esperando' || estado == 'reportado';
  bool get confirmado => estado == 'confirmado';

  factory PagoQr.deJson(Map j) {
    final m = j['monto'];
    return PagoQr(
      id: (j['id'] ?? '').toString(),
      estado: (j['estado'] ?? '').toString(),
      academia: (j['academia'] ?? '').toString(),
      simbolo: (j['simbolo'] ?? '').toString(),
      monto: m is num ? m.toDouble() : double.tryParse('${m ?? ''}') ?? 0,
      montoTxt: (j['monto_txt'] ?? '').toString(),
      extraTxt: (j['extra_txt'] ?? '').toString(),
      qrUrl: (j['qr_url'] ?? '').toString(),
      appNombre: (j['app_nombre'] ?? '').toString(),
      titular: (j['titular'] ?? '').toString(),
      vence: (j['vence'] ?? '').toString(),
    );
  }
}

/// PLAN ACADEMIA (decisión del director, 10-oct-2026): las academias pagan a
/// Pichangol una suscripción mensual (con prueba gratis) y sus alumnos les
/// pagan DIRECTO por Yape (reportando el código de seguridad de 3 dígitos).
/// Con el modelo "comision" (o si la config nunca cargó) el APK se comporta
/// EXACTAMENTE como antes: por eso el default es "comision".
class AcademiaPlanService {
  static const _kConfig = 'academias_config_json';
  static const _kPlanes = 'academias_plan_cache_json';

  /// Config pública (`GET /config/academias`). Vacía = nunca cargó.
  static Map<String, dynamic> config = {};

  /// Estado del plan por academia (cache-first: memoria + SharedPreferences).
  static final Map<String, PlanAcademiaEstado> _planes = {};
  static bool _planesLeidos = false;

  /// Avisa a las pantallas cuando cambia la config o el estado de un plan.
  static final ValueNotifier<int> cambios = ValueNotifier<int>(0);

  static String get modelo => (config['modelo'] ?? 'comision').toString();

  /// ¿Academias por SUSCRIPCIÓN? (si no, todo como siempre).
  static bool get esSuscripcion => modelo == 'suscripcion';

  /// Países donde las academias existen para el público (torre → Plan
  /// Academia; decisión del director, 10-oct-2026: ocultas en Bolivia y
  /// Ecuador). Sin config cargada = solo Perú.
  static List<String> get paises {
    final l = config['paises'];
    if (l is List) return [for (final p in l) p.toString().toUpperCase()];
    return const ['PE'];
  }

  static bool paisHabilitado(String iso) =>
      paises.contains(iso.trim().toUpperCase());

  /// ¿Se muestra al público? (país de su sede; sin sede ubicada: su moneda).
  static bool habilitada(Academia a) => paisHabilitado(a.pais.iso);

  static int get pruebaDias {
    final v = config['prueba_dias'];
    return v is num ? v.toInt() : 30;
  }

  /// Precio mensual del plan en la moneda (símbolo o ISO) de la academia.
  static double precioPlan(String moneda) {
    final iso = _iso(moneda);
    final p = config['precios'];
    if (p is Map) {
      final v = p[iso];
      if (v is num) return v.toDouble();
      if (v is String) return double.tryParse(v) ?? 0;
    }
    return switch (iso) { 'USD' => 3.0, 'BOB' => 21.0, _ => 11.5 };
  }

  static String _iso(String m) {
    switch (m.trim().toUpperCase()) {
      case r'$':
      case 'USD':
        return 'USD';
      case 'BS':
      case 'BOB':
        return 'BOB';
      default:
        return 'PEN';
    }
  }

  static void _avisar() => cambios.value = cambios.value + 1;

  /// Carga cache-first y refresca en silencio. Devuelve true si cambió algo.
  static Future<bool> cargarConfig() async {
    var cambio = false;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (config.isEmpty) {
        final raw = prefs.getString(_kConfig);
        if (raw != null) {
          final j = jsonDecode(raw);
          if (j is Map) {
            config = Map<String, dynamic>.from(j);
            cambio = true;
          }
        }
      }
      if (!PagosService.disponible) {
        if (cambio) _avisar();
        return cambio;
      }
      final r = await http
          .get(Uri.parse('${PagosService.baseUrl}/config/academias'),
              headers: PagosService.appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode == 200) {
        final j = jsonDecode(r.body);
        if (j is Map) {
          final nuevo = Map<String, dynamic>.from(j);
          if (jsonEncode(nuevo) != jsonEncode(config)) {
            config = nuevo;
            cambio = true;
          }
          await prefs.setString(_kConfig, jsonEncode(nuevo));
        }
      }
    } catch (_) {}
    if (cambio) _avisar();
    return cambio;
  }

  static Future<void> _leerPlanesCache() async {
    if (_planesLeidos) return;
    _planesLeidos = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kPlanes);
      if (raw == null) return;
      final j = jsonDecode(raw);
      if (j is! Map) return;
      j.forEach((k, v) {
        if (v is Map && !_planes.containsKey(k.toString())) {
          _planes[k.toString()] =
              PlanAcademiaEstado.deJson(Map<String, dynamic>.from(v));
        }
      });
    } catch (_) {}
  }

  static Future<void> _guardarPlanesCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kPlanes,
          jsonEncode({for (final e in _planes.entries) e.key: e.value.toJson()}));
    } catch (_) {}
  }

  /// Último estado conocido del plan (sin red). null = aún no se sabe.
  static PlanAcademiaEstado? planEnCache(String academiaId) =>
      _planes[academiaId];

  /// ¿La academia tiene los beneficios del plan? Sin suscripción: siempre sí.
  /// Mientras no se sabe el estado se asume que SÍ (no se bloquea a nadie por
  /// falta de red; el backend igual decide).
  static bool tieneBeneficios(String academiaId) {
    if (!esSuscripcion) return true;
    return _planes[academiaId]?.beneficios ?? true;
  }

  static final Map<String, Future<PlanAcademiaEstado?>> _enVuelo = {};
  static final Map<String, DateTime> _ultimaConsulta = {};

  /// Estado del plan: pinta lo cacheado y consulta al backend (throttle 20 s
  /// salvo [forzar]). null si no hay caché ni red.
  static Future<PlanAcademiaEstado?> plan(String academiaId,
      {bool forzar = false}) async {
    if (academiaId.isEmpty) return null;
    await _leerPlanesCache();
    final ult = _ultimaConsulta[academiaId];
    if (!forzar &&
        ult != null &&
        DateTime.now().difference(ult).inSeconds < 20 &&
        _planes.containsKey(academiaId)) {
      return _planes[academiaId];
    }
    final vuelo = _enVuelo[academiaId];
    if (vuelo != null) return vuelo;
    final f = _consultarPlan(academiaId);
    _enVuelo[academiaId] = f;
    try {
      return await f;
    } finally {
      _enVuelo.remove(academiaId);
    }
  }

  static Future<PlanAcademiaEstado?> _consultarPlan(String academiaId) async {
    if (!PagosService.disponible) return _planes[academiaId];
    try {
      final r = await http
          .get(
              Uri.parse('${PagosService.baseUrl}/academias/plan/'
                  '${Uri.encodeComponent(academiaId)}'),
              headers: PagosService.appHeaders())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return _planes[academiaId];
      final j = jsonDecode(r.body);
      if (j is! Map) return _planes[academiaId];
      final e = PlanAcademiaEstado.deJson(Map<String, dynamic>.from(j));
      _ultimaConsulta[academiaId] = DateTime.now();
      final antes = _planes[academiaId];
      _planes[academiaId] = e;
      if (antes == null || jsonEncode(antes.toJson()) != jsonEncode(e.toJson())) {
        _avisar();
        unawaited(_guardarPlanesCache());
      }
      return e;
    } catch (_) {
      return _planes[academiaId];
    }
  }

  static Map<String, dynamic> _sinConexion() =>
      {'ok': false, 'mensaje': 'Sin conexión. Revisa tu internet y reintenta.'};

  static Future<Map<String, dynamic>> _post(
      String ruta, Map<String, dynamic> cuerpo) async {
    if (!PagosService.disponible) return _sinConexion();
    try {
      final r = await http
          .post(Uri.parse('${PagosService.baseUrl}$ruta'),
              headers: await PagosService.headersUsuario(json: true),
              body: jsonEncode(cuerpo))
          .timeout(const Duration(seconds: 20));
      final j = jsonDecode(r.body);
      if (j is Map) {
        final m = Map<String, dynamic>.from(j);
        if (r.statusCode != 200 && m['ok'] == null) {
          return {
            'ok': false,
            'mensaje': (m['mensaje'] ?? m['detail'] ?? 'No se pudo. Reintenta.')
                .toString(),
          };
        }
        return m;
      }
      return {'ok': false, 'mensaje': 'No se pudo. Reintenta.'};
    } catch (_) {
      return _sinConexion();
    }
  }

  /// Paga 1 mes del plan con el SALDO del dueño. {ok, hasta, estado} o
  /// {ok:false, error: no_dueno|moneda_distinta|falta_saldo|sin_plan, mensaje}.
  static Future<Map<String, dynamic>> pagar(
      String academiaId, String email) async {
    final r = await _post(
        '/academias/plan/${Uri.encodeComponent(academiaId)}/pagar',
        {'email': email.trim().toLowerCase()});
    if (r['ok'] == true) await plan(academiaId, forzar: true);
    return r;
  }

  /// Enciende / apaga la renovación automática desde el saldo.
  static Future<Map<String, dynamic>> renovacion(
      String academiaId, String email, bool renovar) async {
    final r = await _post(
        '/academias/plan/${Uri.encodeComponent(academiaId)}/renovacion',
        {'email': email.trim().toLowerCase(), 'renovar': renovar});
    if (r['ok'] == true) await plan(academiaId, forzar: true);
    return r;
  }

  /// El alumno avisa que YAPEÓ a la academia: código de seguridad (3 dígitos)
  /// + N.º de operación opcional. {ok, cuotas, total} o {ok:false, mensaje}.
  static Future<Map<String, dynamic>> reportar({
    required String alumnoId,
    required String email,
    required List<String> cuotaIds,
    required String codigo,
    String operacion = '',
  }) =>
      _post('/academias/pago-directo/reportar', {
        'alumno_id': alumnoId,
        'email': email.trim().toLowerCase(),
        'cuota_ids': cuotaIds,
        'codigo': codigo,
        'operacion': operacion,
      });

  /// La academia confirma (o rechaza con [motivo]) un pago reportado.
  static Future<Map<String, dynamic>> resolver({
    required String academiaId,
    required String alumnoId,
    required String email,
    required List<String> cuotaIds,
    required bool aceptar,
    String motivo = '',
  }) =>
      _post('/academias/pago-directo/resolver', {
        'academia_id': academiaId,
        'alumno_id': alumnoId,
        'email': email.trim().toLowerCase(),
        'cuota_ids': cuotaIds,
        'aceptar': aceptar,
        'motivo': motivo,
      });

  /// Pago por QR: pide (o reusa) un MONTO ÚNICO para [cuotaIds] de
  /// [alumnoId]. (PagoQr, null) o (null, mensaje).
  static Future<(PagoQr?, String?)> iniciarQr({
    required String alumnoId,
    required String email,
    required List<String> cuotaIds,
  }) async {
    final r = await _post('/academias/pago-qr/iniciar', {
      'email': email.trim().toLowerCase(),
      'alumno_id': alumnoId,
      'cuota_ids': cuotaIds,
    });
    if (r['ok'] == true && r['intencion'] is Map) {
      return (PagoQr.deJson(r['intencion'] as Map), null);
    }
    return (null, (r['mensaje'] ?? 'No se pudo preparar el pago. Reintenta.').toString());
  }

  /// "Ya pagué": la academia lo ve por confirmar (y se concilia al instante
  /// si la notificación de su app de cobros ya llegó).
  static Future<(PagoQr?, String?)> marcarPagadoQr(String id, String email) async {
    final r = await _post('/academias/pago-qr/${Uri.encodeComponent(id)}/pagado',
        {'email': email.trim().toLowerCase()});
    if (r['ok'] == true && r['intencion'] is Map) {
      return (PagoQr.deJson(r['intencion'] as Map), null);
    }
    return (null, (r['mensaje'] ?? 'No se pudo avisar tu pago. Reintenta.').toString());
  }

  /// Estado actual del pago por QR (sondeo mientras la hoja está abierta).
  static Future<PagoQr?> estadoQr(String id, String email) async {
    final e = email.trim().toLowerCase();
    if (!PagosService.disponible || e.isEmpty) return null;
    try {
      final r = await http
          .get(
              Uri.parse('${PagosService.baseUrl}/academias/pago-qr/'
                  '${Uri.encodeComponent(id)}?email=${Uri.encodeQueryComponent(e)}'),
              headers: await PagosService.headersUsuario())
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body);
      if (j is Map && j['intencion'] is Map) return PagoQr.deJson(j['intencion'] as Map);
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Pagos reportados por los alumnos de las academias de [email] (dueño).
  /// null = no se pudo consultar (sin red).
  static Future<List<PagoPorConfirmar>?> pendientes(String email) async {
    final e = email.trim().toLowerCase();
    if (!PagosService.disponible || e.isEmpty) return null;
    try {
      final r = await http
          .get(
              Uri.parse('${PagosService.baseUrl}/academias/pago-directo/'
                  'pendientes?email=${Uri.encodeQueryComponent(e)}'),
              headers: await PagosService.headersUsuario())
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      final j = jsonDecode(r.body);
      if (j is! Map) return null;
      final l = j['pagos'];
      if (l is! List) return const [];
      return [
        for (final p in l)
          if (p is Map) PagoPorConfirmar.deJson(Map<String, dynamic>.from(p)),
      ];
    } catch (_) {
      return null;
    }
  }
}
