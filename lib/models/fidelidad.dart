import '../services/pagos_service.dart';

/// FIDELIDAD DEL LOCAL — "cada N reservas, una hora gratis o un descuento"
/// (pedido del director, 28-sep-2026). Espejo de `backend/growth/fidelidad.py`.
///
/// El dueño la configura UNA vez por local (se copia a todas sus canchas, como
/// los servicios extra de ámbito local): meta de reservas, premio (hora gratis
/// o % de descuento), ventana de días que cuenta y qué reservas cuentan. El
/// jugador ve su progreso en la ficha y, al llegar a la meta, el premio se
/// aplica solo en el checkout. El conteo y el canje los decide SIEMPRE el
/// backend (`/fidelidad/*`): el APK solo muestra y pide.
class FidelidadConfig {
  final bool activa;
  final int meta;
  final String premio; // hora_gratis | descuento
  final int descuentoPct;
  final int ventanaDias; // 0 = sin límite
  final String aplica; // todas | online

  const FidelidadConfig({
    this.activa = false,
    this.meta = 5,
    this.premio = 'hora_gratis',
    this.descuentoPct = 20,
    this.ventanaDias = 180,
    this.aplica = 'todas',
  });

  static const metas = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20];
  static const descuentos = [10, 15, 20, 25, 30, 50];
  static const ventanas = [0, 90, 180, 365];
  static const etiquetaVentana = {
    0: 'Sin límite',
    90: '90 días',
    180: '6 meses',
    365: '1 año',
  };

  /// Config saneada desde el JSON de la cancha (puede venir vacío o viejo).
  factory FidelidadConfig.de(Map<String, dynamic>? j) {
    j ??= const {};
    int entero(dynamic v, int def) =>
        v is num ? v.toInt() : (int.tryParse('${v ?? ''}') ?? def);
    final meta = entero(j['meta'], 5);
    final pct = entero(j['descuentoPct'], 20);
    final ventana = entero(j['ventanaDias'], 180);
    final premio = (j['premio'] ?? 'hora_gratis').toString();
    final aplica = (j['aplica'] ?? 'todas').toString();
    return FidelidadConfig(
      activa: j['activa'] == true,
      meta: metas.contains(meta) ? meta : 5,
      premio: premio == 'descuento' ? 'descuento' : 'hora_gratis',
      descuentoPct: descuentos.contains(pct) ? pct : 20,
      ventanaDias: ventanas.contains(ventana) ? ventana : 180,
      aplica: aplica == 'online' ? 'online' : 'todas',
    );
  }

  Map<String, dynamic> toJson() => {
        'activa': activa,
        'meta': meta,
        'premio': premio,
        'descuentoPct': descuentoPct,
        'ventanaDias': ventanaDias,
        'aplica': aplica,
      };

  FidelidadConfig copyWith({
    bool? activa,
    int? meta,
    String? premio,
    int? descuentoPct,
    int? ventanaDias,
    String? aplica,
  }) =>
      FidelidadConfig(
        activa: activa ?? this.activa,
        meta: meta ?? this.meta,
        premio: premio ?? this.premio,
        descuentoPct: descuentoPct ?? this.descuentoPct,
        ventanaDias: ventanaDias ?? this.ventanaDias,
        aplica: aplica ?? this.aplica,
      );

  bool get esHoraGratis => premio == 'hora_gratis';
  String get nombrePremio =>
      esHoraGratis ? 'una hora gratis' : '$descuentoPct % de descuento';
  String get premioCorto => esHoraGratis ? 'Hora gratis' : '−$descuentoPct %';

  /// Descuento (total, por slot) sobre los precios del bloque, ESPEJO de
  /// `fidelidad.descuento_para`: hora gratis = el turno más barato a 0;
  /// descuento = % por turno (redondeado por turno).
  (int, List<int>) descuentoPara(List<int> precios) {
    if (precios.isEmpty) return (0, const []);
    if (esHoraGratis) {
      var iMin = 0;
      for (var i = 1; i < precios.length; i++) {
        if (precios[i] < precios[iMin]) iMin = i;
      }
      final por = List<int>.filled(precios.length, 0);
      por[iMin] = precios[iMin];
      return (precios[iMin], por);
    }
    final por = [for (final p in precios) (p * descuentoPct / 100).round()];
    return (por.fold(0, (a, b) => a + b), por);
  }
}

/// Progreso del jugador en la tarjeta de UN local (lo devuelve el backend).
class EstadoFidelidad {
  final bool activa;
  final int meta;
  final String premio;
  final int descuentoPct;
  final int conteo;
  final int faltan;
  final bool disponible;
  final String nombrePremio;
  final String premioCorto;
  final String local;
  final int usados;

  const EstadoFidelidad({
    required this.activa,
    required this.meta,
    required this.premio,
    required this.descuentoPct,
    required this.conteo,
    required this.faltan,
    required this.disponible,
    required this.nombrePremio,
    required this.premioCorto,
    required this.local,
    required this.usados,
  });

  factory EstadoFidelidad.fromJson(Map<String, dynamic> j) => EstadoFidelidad(
        activa: j['activa'] == true,
        meta: ((j['meta'] ?? 5) as num).toInt(),
        premio: (j['premio'] ?? 'hora_gratis').toString(),
        descuentoPct: ((j['descuentoPct'] ?? 0) as num).toInt(),
        conteo: ((j['conteo'] ?? 0) as num).toInt(),
        faltan: ((j['faltan'] ?? 0) as num).toInt(),
        disponible: j['disponible'] == true,
        nombrePremio: (j['nombrePremio'] ?? '').toString(),
        premioCorto: (j['premioCorto'] ?? '').toString(),
        local: (j['local'] ?? '').toString(),
        usados: ((j['usados'] ?? 0) as num).toInt(),
      );

  FidelidadConfig get config => FidelidadConfig(
      activa: activa, meta: meta, premio: premio, descuentoPct: descuentoPct);
}

/// Llamadas al backend (todas fail-safe: sin red → null / false y el checkout
/// sigue sin premio; nunca se descuenta sin que el servidor lo aparte).
class Fidelidad {
  static Future<EstadoFidelidad?> estado(String email, String canchaId) async {
    final j = await PagosService.fidelidadEstado(email: email, canchaId: canchaId);
    if (j == null || j['ok'] != true) return null;
    return EstadoFidelidad.fromJson(j);
  }

  /// Aparta el premio para una reserva (hold) o lo usa directo (`confirmar`).
  static Future<bool> reservarCanje({
    required String email,
    required String canchaId,
    required String reservaRef,
    required List<String> reservaIds,
    required int descuento,
    bool confirmar = false,
  }) async {
    final j = await PagosService.fidelidadCanjeReservar(
        email: email,
        canchaId: canchaId,
        reservaRef: reservaRef,
        reservaIds: reservaIds,
        descuento: descuento,
        confirmar: confirmar);
    return j != null && j['ok'] == true;
  }

  static Future<bool> confirmar(String reservaRef) async {
    final j = await PagosService.fidelidadCanjeConfirmar(reservaRef);
    return j != null && j['ok'] == true;
  }

  static Future<bool> revertir(String reservaRef) async {
    final j = await PagosService.fidelidadCanjeRevertir(reservaRef);
    return j != null && j['ok'] == true;
  }
}
