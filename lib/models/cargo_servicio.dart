import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../services/growth_service.dart';
import '../services/pagos_service.dart';

/// CARGO POR SERVICIO Pichangol al cliente (fase 3 del diseño aprobado por el
/// director el 27-sep-2026, `docs/diseno-cargo-por-servicio.md`).
///
/// Dos lados como Airbnb: quien RECIBE (dueño/academia) paga la comisión de
/// siempre y quien PAGA ve una línea aparte "Cargo por servicio Pichangol"
/// (5 % sobre los primeros S/ 500 + 2 % del excedente, mínimo S/ 2; en $ y Bs
/// sus propios tramos). La FUENTE DE VERDAD es el backend
/// (`pagos/cargo_servicio.py`): el APK pide la cotización a `POST
/// /pagos/cotizar` (incluye la red de seguridad con la tarifa real de la
/// pasarela) y solo si no hay respuesta calcula la regla visible en local con
/// los parámetros cacheados (`GET /config/cargo-servicio`, cache-first como el
/// catálogo de servicios extra). Con la línea APAGADA en la torre la
/// cotización vuelve con cargo 0 y el checkout no muestra nada.
class ComponenteCargo {
  final String clave;
  final String nombre;
  final double pct;
  final String detalle;
  final int montoCentimos;

  const ComponenteCargo({
    required this.clave,
    required this.nombre,
    required this.pct,
    required this.detalle,
    required this.montoCentimos,
  });

  double get monto => montoCentimos / 100.0;

  Map<String, dynamic> toJson() => {
        'clave': clave,
        'nombre': nombre,
        'pct': pct,
        'detalle': detalle,
        'monto_centimos': montoCentimos,
      };

  factory ComponenteCargo.fromJson(Map<String, dynamic> j) => ComponenteCargo(
        clave: (j['clave'] ?? '').toString(),
        nombre: (j['nombre'] ?? '').toString(),
        pct: ((j['pct'] ?? 0) as num).toDouble(),
        detalle: (j['detalle'] ?? '').toString(),
        montoCentimos: ((j['monto_centimos'] ?? 0) as num).round(),
      );

  static List<ComponenteCargo> listaDe(dynamic raw) {
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((m) => ComponenteCargo.fromJson(Map<String, dynamic>.from(m)))
        .toList();
  }
}

/// Resultado de una cotización: lo que se muestra en el checkout y lo que
/// viaja con la contabilidad (céntimos, desglose congelado, ajuste).
class CotizacionCargo {
  final String linea;
  final String moneda; // ISO
  final String simbolo;
  final bool activo;
  final int baseCentimos;
  final int cargoCentimos;
  final int totalCentimos;
  final int ajusteCentimos; // red de seguridad (solo la calcula el servidor)
  final int ahorroCentimos; // por pagar junto (carrito), 0 si una sola parte
  final String regla;
  final String titulo;
  final List<ComponenteCargo> desglose;
  final bool delServidor;
  // Medio con el que se cotizó ('yape' | 'tarjeta' | '' = sin medio). En el
  // MODELO 2 de reservas el cargo depende del medio (Yape es más barato).
  final String medio;

  const CotizacionCargo({
    required this.linea,
    required this.moneda,
    required this.simbolo,
    required this.activo,
    required this.baseCentimos,
    required this.cargoCentimos,
    required this.totalCentimos,
    this.ajusteCentimos = 0,
    this.ahorroCentimos = 0,
    this.regla = '',
    this.titulo = 'Cargo por servicio Pichangol',
    this.desglose = const [],
    this.delServidor = false,
    this.medio = '',
  });

  bool get hayCargo => activo && cargoCentimos > 0;
  double get base => baseCentimos / 100.0;
  double get cargo => cargoCentimos / 100.0;
  double get total => totalCentimos / 100.0;
  double get ahorro => ahorroCentimos / 100.0;

  List<Map<String, dynamic>> get desgloseJson =>
      desglose.map((c) => c.toJson()).toList();

  factory CotizacionCargo.fromJson(Map<String, dynamic> j,
      {bool delServidor = true}) {
    final base = ((j['base_centimos'] ?? 0) as num).round();
    final cargo = ((j['cargo_centimos'] ?? 0) as num).round();
    return CotizacionCargo(
      linea: (j['linea'] ?? 'reservas').toString(),
      moneda: (j['moneda'] ?? 'PEN').toString(),
      simbolo: (j['simbolo'] ?? 'S/').toString(),
      activo: j['activo'] == true,
      baseCentimos: base,
      cargoCentimos: cargo,
      totalCentimos: ((j['total_centimos'] ?? (base + cargo)) as num).round(),
      ajusteCentimos: ((j['ajuste_seguridad_centimos'] ?? 0) as num).round(),
      ahorroCentimos: ((j['ahorro_centimos'] ?? 0) as num).round(),
      regla: (j['regla'] ?? '').toString(),
      titulo: (j['titulo'] ?? '').toString().isEmpty
          ? 'Cargo por servicio Pichangol'
          : j['titulo'].toString(),
      desglose: ComponenteCargo.listaDe(j['desglose']),
      delServidor: delServidor,
      medio: (j['medio'] ?? '').toString(),
    );
  }

  /// Cotización CONGELADA a partir de lo guardado en una reserva/cuota (para
  /// el comprobante: monto + desglose tal como se pagó).
  factory CotizacionCargo.congelada({
    required String linea,
    required String moneda,
    required double baseSoles,
    required double cargoSoles,
    List<Map<String, dynamic>> desglose = const [],
  }) {
    final iso = CargoServicio.monedaIsoDe(moneda);
    final base = (baseSoles * 100).round();
    final cargo = (cargoSoles * 100).round();
    return CotizacionCargo(
      linea: linea,
      moneda: iso,
      simbolo: CargoServicio.simboloDe(iso),
      activo: cargo > 0,
      baseCentimos: base,
      cargoCentimos: cargo,
      totalCentimos: base + cargo,
      regla: CargoServicio.reglaTexto(iso),
      desglose: ComponenteCargo.listaDe(desglose),
      delServidor: true,
    );
  }

  /// Cotización "sin cargo" (línea apagada o base 0): total = base.
  factory CotizacionCargo.inactiva(String linea, String monedaIso, int base) =>
      CotizacionCargo(
        linea: linea,
        moneda: monedaIso,
        simbolo: CargoServicio.simboloDe(monedaIso),
        activo: false,
        baseCentimos: base,
        cargoCentimos: 0,
        totalCentimos: base,
      );
}

class CargoServicio {
  CargoServicio._();

  static const _kPrefs = 'cargo_servicio_config';
  static const lineas = ['reservas', 'academias', 'marketplace', 'torneos'];

  /// Respuesta de `GET /config/cargo-servicio` (`cargo_servicio.publico()`):
  /// {version, activo:{linea:bool}, monedas:{ISO:{pct,min,tramo,pct_exc,
  /// margen_min,simbolo}}, regla:{ISO:texto}, textos:{linea:{titulo,
  /// componentes, por_deporte}}, comision:{linea:[…]}}. Vacía = sin cargar.
  static Map<String, dynamic> config = const {};

  /// Cotizaciones del servidor ya pedidas (misma base → misma respuesta): así
  /// un rebuild del checkout no vuelve a la red.
  static final Map<String, CotizacionCargo> _cache = {};

  static bool get cargada => config.isNotEmpty;

  /// ¿La línea está ENCENDIDA en la torre? Sin config cargada → false (el
  /// checkout no muestra nada que el backend no vaya a cobrar).
  static bool activo(String linea) {
    final a = config['activo'];
    return a is Map && a[linea] == true;
  }

  /// ¿El cargo de esta línea DEPENDE DEL MEDIO de pago? Solo en el MODELO 2
  /// de reservas (`modelo_reservas` = "2" en `/config/cargo-servicio`) y en
  /// soles, donde hay dos medios con tarifa distinta (Yape más barato que
  /// tarjeta). En USD/BOB hay un solo medio (pasarela hospedada) y en el
  /// modelo 1 el medio no cambia el cargo visible → false (todo como antes).
  static bool dependeDelMedio(String linea, String moneda) =>
      linea == 'reservas' &&
      monedaIsoDe(moneda) == 'PEN' &&
      (config['modelo_reservas'] ?? '1').toString() == '2';

  static String monedaIsoDe(String m) {
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

  static String simboloDe(String iso) {
    switch (monedaIsoDe(iso)) {
      case 'USD':
        return r'$';
      case 'BOB':
        return 'Bs';
      default:
        return 'S/';
    }
  }

  static const _paramsDefault = {
    'PEN': {'pct': 5.0, 'min': 2.0, 'tramo': 500.0, 'pct_exc': 2.0},
    'USD': {'pct': 5.0, 'min': 0.5, 'tramo': 140.0, 'pct_exc': 2.0},
    'BOB': {'pct': 5.0, 'min': 3.0, 'tramo': 1000.0, 'pct_exc': 2.0},
  };

  static Map<String, double> params(String moneda) {
    final iso = monedaIsoDe(moneda);
    final base = Map<String, double>.from(_paramsDefault[iso]!);
    final m = config['monedas'];
    if (m is Map && m[iso] is Map) {
      for (final k in base.keys.toList()) {
        final v = (m[iso] as Map)[k];
        if (v is num) base[k] = v.toDouble();
        if (v is String) base[k] = double.tryParse(v) ?? base[k]!;
      }
    }
    return base;
  }

  /// Carga cache-first (SharedPreferences) y refresca en silencio desde el
  /// backend. Fail-safe: sin red conserva lo cacheado; sin caché, la línea se
  /// considera apagada hasta que responda.
  static Future<bool> cargar() async {
    var cambio = false;
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kPrefs);
      if (raw != null && config.isEmpty) {
        final j = jsonDecode(raw);
        if (j is Map) {
          config = Map<String, dynamic>.from(j);
          cambio = true;
        }
      }
      final j = await GrowthService.cargoServicioConfig();
      if (j == null) return cambio;
      final nuevo = Map<String, dynamic>.from(j);
      if (jsonEncode(nuevo) != jsonEncode(config)) {
        config = nuevo;
        _cache.clear();
        cambio = true;
      }
      await prefs.setString(_kPrefs, jsonEncode(nuevo));
    } catch (_) {}
    return cambio;
  }

  static int _redondearArriba(int centimos, int paso) =>
      ((centimos + paso - 1) ~/ paso) * paso;

  /// Regla VISIBLE (espejo de `cargo_centimos` del backend): % base hasta el
  /// tramo + % del excedente, mínimo; redondeo a 0.10 hacia arriba. Sin la red
  /// de seguridad (esa solo la sabe el servidor).
  static int cargoCentimosLocal(int baseCentimos, String moneda) {
    if (baseCentimos <= 0) return 0;
    final p = params(moneda);
    final tramo = (p['tramo']! * 100).round();
    final baseTramo = baseCentimos < tramo ? baseCentimos : tramo;
    final exceso = baseCentimos > tramo ? baseCentimos - tramo : 0;
    final bruto = baseTramo * p['pct']! / 100.0 + exceso * p['pct_exc']! / 100.0;
    final conMin = bruto > p['min']! * 100.0 ? bruto : p['min']! * 100.0;
    return _redondearArriba((conMin - 1e-9).ceil(), 10);
  }

  static String reglaTexto(String moneda) {
    final iso = monedaIsoDe(moneda);
    final r = config['regla'];
    if (r is Map && (r[iso] ?? '').toString().isNotEmpty) {
      return r[iso].toString();
    }
    final p = params(iso);
    final s = simboloDe(iso);
    String n(double v) =>
        v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toString();
    return '${n(p['pct']!)} % sobre los primeros $s ${n(p['tramo']!)} del pago '
        '+ ${n(p['pct_exc']!)} % sobre el excedente, mínimo $s ${p['min']!.toStringAsFixed(2)}';
  }

  static Map<String, dynamic> _textos(String linea) {
    final t = config['textos'];
    if (t is Map && t[linea] is Map) return Map<String, dynamic>.from(t[linea]);
    return const {};
  }

  /// Lo que incluye la COMISIÓN de quien recibe (para mostrar al dueño o a la
  /// academia): [{clave, nombre, pct, detalle}]. Vacío si no hay config.
  static List<Map<String, dynamic>> comisionIncluye(String linea) {
    final c = config['comision'];
    if (c is Map && c[linea] is List) {
      return (c[linea] as List)
          .whereType<Map>()
          .map((m) => Map<String, dynamic>.from(m))
          .toList();
    }
    return const [];
  }

  static List<ComponenteCargo> _desgloseLocal(
      String linea, String iso, int cargo, String deporte) {
    final t = _textos(linea);
    final comps = ((t['componentes'] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => Map<String, dynamic>.from(m))
        .toList();
    if (comps.isEmpty) return const [];
    final porDep = t['por_deporte'];
    final dep = deporte.trim().toLowerCase();
    if (porDep is Map && porDep[dep] is Map) {
      final esp = Map<String, dynamic>.from(porDep[dep]);
      comps[comps.length - 1] = {
        ...comps.last,
        if ((esp['nombre'] ?? '').toString().isNotEmpty) 'nombre': esp['nombre'],
        if ((esp['detalle'] ?? '').toString().isNotEmpty)
          'detalle': esp['detalle'],
      };
    }
    const medios = {'PEN': 'Yape o tarjeta', 'USD': 'tarjeta', 'BOB': 'QR o tarjeta'};
    final totalPct = comps.fold<double>(
        0.0, (a, c) => a + ((c['pct'] ?? 0) as num).toDouble());
    final out = <ComponenteCargo>[];
    var acumulado = 0;
    for (var i = 0; i < comps.length; i++) {
      final c = comps[i];
      final pct = ((c['pct'] ?? 0) as num).toDouble();
      int monto;
      if (i == comps.length - 1) {
        monto = cargo - acumulado;
      } else {
        monto = totalPct > 0 ? (cargo * pct / totalPct).round() : 0;
        acumulado += monto;
      }
      out.add(ComponenteCargo(
        clave: (c['clave'] ?? '').toString(),
        nombre: (c['nombre'] ?? '').toString(),
        pct: pct,
        detalle: (c['detalle'] ?? '')
            .toString()
            .replaceAll('{medios}', medios[iso] ?? 'tarjeta'),
        montoCentimos: monto < 0 ? 0 : monto,
      ));
    }
    return out;
  }

  /// Cotización LOCAL con la regla visible (respaldo si el servidor no responde).
  static CotizacionCargo local({
    required String linea,
    required String moneda,
    required int baseCentimos,
    String deporte = '',
    List<int> partes = const [],
    String medio = '',
  }) {
    final iso = monedaIsoDe(moneda);
    final base = baseCentimos < 0 ? 0 : baseCentimos;
    if (!activo(linea) || base <= 0) {
      return CotizacionCargo.inactiva(linea, iso, base);
    }
    final cargo = cargoCentimosLocal(base, iso);
    var ahorro = 0;
    if (partes.length > 1) {
      final sep = partes.fold<int>(0, (a, p) => a + cargoCentimosLocal(p, iso));
      ahorro = sep - cargo > 0 ? sep - cargo : 0;
    }
    final t = _textos(linea);
    return CotizacionCargo(
      linea: linea,
      moneda: iso,
      simbolo: simboloDe(iso),
      activo: true,
      baseCentimos: base,
      cargoCentimos: cargo,
      totalCentimos: base + cargo,
      ahorroCentimos: ahorro,
      regla: reglaTexto(iso),
      titulo: (t['titulo'] ?? '').toString().isEmpty
          ? 'Cargo por servicio Pichangol'
          : t['titulo'].toString(),
      desglose: _desgloseLocal(linea, iso, cargo, deporte),
      medio: medio,
    );
  }

  /// Cotización para el checkout: servidor (con red de seguridad) → local.
  /// Con la línea apagada devuelve la inactiva sin ir a la red.
  static Future<CotizacionCargo> cotizar({
    required String linea,
    required String moneda,
    required int baseCentimos,
    String deporte = '',
    List<int> partes = const [],
    // 'yape' | 'tarjeta' | '' (sin medio = como siempre; el backend usa
    // tarjeta). Solo se manda cuando el cargo depende del medio.
    String medio = '',
  }) async {
    final iso = monedaIsoDe(moneda);
    final base = baseCentimos < 0 ? 0 : baseCentimos;
    if (!activo(linea) || base <= 0) {
      return CotizacionCargo.inactiva(linea, iso, base);
    }
    final clave =
        '$linea|$iso|$base|${deporte.toLowerCase()}|${partes.join(',')}|$medio';
    final c = _cache[clave];
    if (c != null) return c;
    final j = await PagosService.cotizarCargo(
        linea: linea,
        moneda: iso,
        baseCentimos: base,
        deporte: deporte,
        partes: partes,
        medio: medio);
    if (j != null && j['ok'] == true) {
      final cot = CotizacionCargo.fromJson(j);
      if (cot.baseCentimos == base) {
        _cache[clave] = cot;
        return cot;
      }
    }
    return local(
        linea: linea,
        moneda: iso,
        baseCentimos: base,
        deporte: deporte,
        partes: partes,
        medio: medio);
  }

  /// Cotiza la MISMA base con cada medio de pago de soles (Yape y tarjeta),
  /// en paralelo, para que la hoja de pago muestre el total del medio que el
  /// jugador elige. Solo tiene sentido si [dependeDelMedio]; si no, devuelve
  /// la cotización de siempre (sin medio) para ambos, así nada cambia.
  static Future<Map<String, CotizacionCargo>> cotizarPorMedio({
    required String linea,
    required String moneda,
    required int baseCentimos,
    String deporte = '',
  }) async {
    if (!dependeDelMedio(linea, moneda)) {
      final c = await cotizar(
          linea: linea,
          moneda: moneda,
          baseCentimos: baseCentimos,
          deporte: deporte);
      return {'yape': c, 'tarjeta': c};
    }
    final r = await Future.wait([
      cotizar(
          linea: linea,
          moneda: moneda,
          baseCentimos: baseCentimos,
          deporte: deporte,
          medio: 'yape'),
      cotizar(
          linea: linea,
          moneda: moneda,
          baseCentimos: baseCentimos,
          deporte: deporte,
          medio: 'tarjeta'),
    ]);
    return {'yape': r[0], 'tarjeta': r[1]};
  }

  /// Cotización síncrona ya conocida para esa base (caché del servidor) o la
  /// local: para pintar al instante mientras llega la del servidor.
  static CotizacionCargo inmediata({
    required String linea,
    required String moneda,
    required int baseCentimos,
    String deporte = '',
    List<int> partes = const [],
    String medio = '',
  }) {
    final iso = monedaIsoDe(moneda);
    final clave =
        '$linea|$iso|$baseCentimos|${deporte.toLowerCase()}|${partes.join(',')}|$medio';
    return _cache[clave] ??
        local(
            linea: linea,
            moneda: iso,
            baseCentimos: baseCentimos,
            deporte: deporte,
            partes: partes,
            medio: medio);
  }

  /// Reparte un cargo en céntimos proporcionalmente a [subtotales] (resto al
  /// primero): un pago familiar que cubre VARIAS academias registra su parte
  /// del cargo en cada matrícula.
  static List<int> repartir(int cargoCentimos, List<int> subtotales) {
    final total = subtotales.fold<int>(0, (a, b) => a + b);
    if (subtotales.isEmpty || total <= 0 || cargoCentimos <= 0) {
      return List<int>.filled(subtotales.length, 0);
    }
    final out = subtotales.map((s) => (cargoCentimos * s / total).floor()).toList();
    final resto = cargoCentimos - out.fold<int>(0, (a, b) => a + b);
    if (out.isNotEmpty) out[0] += resto;
    return out;
  }
}
