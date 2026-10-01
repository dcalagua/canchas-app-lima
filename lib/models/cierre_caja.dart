/// CIERRE DE CAJA de un día: la foto de lo que el dueño cuadró al cerrar la
/// jornada (cuánto cobró, cuánto quedó por cobrar, cuántas reservas). Es el
/// "arqueo" del día — queda como registro histórico.
///
/// Vive en el BACKEND (`/negocio/*`, el mismo registro que ve la web): un
/// cierre por DÍA y por MONEDA (un dueño con canchas en Perú y Ecuador cierra
/// soles y dólares por separado; nunca se suman). El teléfono guarda una copia
/// como caché.
class CierreCaja {
  final String fecha; // ISO 'YYYY-MM-DD'
  final int cobrado;
  final int porCobrar;
  final int reservas;
  final DateTime cerradaEn;

  /// ISO de la moneda del cierre ('PEN' | 'USD' | 'BOB').
  final String moneda;

  /// Cobrado por medio de pago ('yape', 'tarjeta', 'efectivo', 'manual',
  /// 'sena', 'online'), como lo calculó el servidor al cerrar.
  final Map<String, int> medios;

  /// true = lo cerró el SISTEMA (respaldo, sin confirmación del dueño); false =
  /// arqueo CONFIRMADO por el dueño. Un cierre automático se puede confirmar o
  /// reabrir. No se finge un arqueo verificado que nadie hizo.
  final bool automatico;

  const CierreCaja({
    required this.fecha,
    required this.cobrado,
    required this.porCobrar,
    required this.reservas,
    required this.cerradaEn,
    this.automatico = false,
    this.moneda = 'PEN',
    this.medios = const <String, int>{},
  });

  Map<String, dynamic> toJson() => {
        'fecha': fecha,
        'cobrado': cobrado,
        'porCobrar': porCobrar,
        'reservas': reservas,
        'cerradaEn': cerradaEn.toUtc().toIso8601String(),
        'automatico': automatico,
        'moneda': moneda,
        'medios': medios,
      };

  factory CierreCaja.fromJson(Map<String, dynamic> j) {
    final medios = <String, int>{};
    final m = j['medios'];
    if (m is Map) {
      m.forEach((k, v) {
        if (v is num) medios[k.toString()] = v.toInt();
      });
    }
    final mon = (j['moneda'] ?? '').toString().trim().toUpperCase();
    return CierreCaja(
      fecha: (j['fecha'] ?? '').toString(),
      cobrado: ((j['cobrado'] ?? 0) as num).toInt(),
      porCobrar: ((j['porCobrar'] ?? 0) as num).toInt(),
      reservas: ((j['reservas'] ?? 0) as num).toInt(),
      cerradaEn: (DateTime.tryParse((j['cerradaEn'] ?? '').toString()) ??
              DateTime.now())
          .toLocal(),
      automatico: (j['automatico'] ?? false) == true,
      moneda: mon.isEmpty ? 'PEN' : mon,
      medios: medios,
    );
  }
}
