/// CIERRE DE CAJA de un día: la foto de lo que el dueño cuadró al cerrar la
/// jornada (cuánto cobró, cuánto quedó por cobrar, cuántas reservas). Es el
/// "arqueo" del día — queda como registro histórico.
class CierreCaja {
  final String fecha; // ISO 'YYYY-MM-DD'
  final int cobrado;
  final int porCobrar;
  final int reservas;
  final DateTime cerradaEn;

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
  });

  Map<String, dynamic> toJson() => {
        'fecha': fecha,
        'cobrado': cobrado,
        'porCobrar': porCobrar,
        'reservas': reservas,
        'cerradaEn': cerradaEn.toIso8601String(),
        'automatico': automatico,
      };

  factory CierreCaja.fromJson(Map<String, dynamic> j) => CierreCaja(
        fecha: (j['fecha'] ?? '') as String,
        cobrado: ((j['cobrado'] ?? 0) as num).toInt(),
        porCobrar: ((j['porCobrar'] ?? 0) as num).toInt(),
        reservas: ((j['reservas'] ?? 0) as num).toInt(),
        cerradaEn:
            DateTime.tryParse((j['cerradaEn'] ?? '') as String) ?? DateTime.now(),
        automatico: (j['automatico'] ?? false) == true,
      );
}
