/// TEMPORADA del circuito Pichangol. Una temporada es simplemente una **ventana
/// de fechas** (un trimestre del calendario), así que NO necesita tabla ni
/// configuración: se deriva del calendario y el ranking filtra los partidos/retos
/// por su ventana. Cada trimestre el ranking "se reinicia" (arranca vacío) — ese
/// es el gancho para volver a jugar y renovar Pichangol Pro, y para coronar al
/// **campeón de la temporada** cuando cierra.
class Temporada {
  final int anio;
  final int trimestre; // 1..4

  const Temporada(this.anio, this.trimestre);

  /// Id estable, ej. "2026-T3".
  String get id => '$anio-T$trimestre';

  /// Inicio (inclusive): primer día del primer mes del trimestre.
  DateTime get inicio => DateTime(anio, (trimestre - 1) * 3 + 1, 1);

  /// Fin (EXCLUSIVO): primer día del trimestre siguiente.
  DateTime get fin =>
      trimestre >= 4 ? DateTime(anio + 1, 1, 1) : DateTime(anio, trimestre * 3 + 1, 1);

  static const _meses = [
    'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
    'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic'
  ];

  /// Nombre legible, ej. "Jul–Set 2026".
  String get nombre {
    final base = (trimestre - 1) * 3;
    return '${_meses[base]}–${_meses[base + 2]} $anio';
  }

  /// Nombre corto para chips, ej. "T3 2026".
  String get corto => 'T$trimestre $anio';

  /// ¿La fecha [d] cae dentro de la temporada?
  bool contiene(DateTime d) => !d.isBefore(inicio) && d.isBefore(fin);

  /// ¿Es la temporada en curso respecto a [ahora]?
  bool esActual(DateTime ahora) => contiene(ahora);

  /// ¿Ya terminó (cerró) respecto a [ahora]? → se puede coronar campeón.
  bool finalizada(DateTime ahora) => !fin.isAfter(ahora);

  /// Trimestre anterior (cruza de año).
  Temporada get anterior =>
      trimestre <= 1 ? Temporada(anio - 1, 4) : Temporada(anio, trimestre - 1);

  /// La temporada que contiene la fecha [d].
  factory Temporada.de(DateTime d) => Temporada(d.year, ((d.month - 1) ~/ 3) + 1);

  /// Las [n] temporadas más recientes (actual primero), a partir de [ahora].
  static List<Temporada> recientes(DateTime ahora, {int n = 4}) {
    var t = Temporada.de(ahora);
    final l = <Temporada>[];
    for (var i = 0; i < n; i++) {
      l.add(t);
      t = t.anterior;
    }
    return l;
  }

  @override
  bool operator ==(Object other) =>
      other is Temporada && other.anio == anio && other.trimestre == trimestre;

  @override
  int get hashCode => Object.hash(anio, trimestre);
}
