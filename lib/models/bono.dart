/// BONO de horas prepagadas que un dueño ofrece para su local (pack de N horas
/// a un precio con descuento). Se guarda en Supabase (`pichangol_bonos`).
class BonoOferta {
  final String id;
  final String dueno; // correo del dueño
  final String club; // nombre del local
  final String nombre;
  final int horas;
  final double precio;
  final bool activo;
  final DateTime creado;

  const BonoOferta({
    required this.id,
    required this.dueno,
    required this.club,
    required this.nombre,
    required this.horas,
    required this.precio,
    this.activo = true,
    required this.creado,
  });

  /// Precio por hora del pack (para mostrar el ahorro vs. la tarifa suelta).
  double get precioHora => horas <= 0 ? precio : precio / horas;

  BonoOferta copyWith(
          {String? nombre, int? horas, double? precio, bool? activo}) =>
      BonoOferta(
        id: id,
        dueno: dueno,
        club: club,
        nombre: nombre ?? this.nombre,
        horas: horas ?? this.horas,
        precio: precio ?? this.precio,
        activo: activo ?? this.activo,
        creado: creado,
      );

  Map<String, dynamic> toRow() => {
        'id': id,
        'dueno': dueno.trim().toLowerCase(),
        'club': club,
        'nombre': nombre,
        'horas': horas,
        'precio': precio,
        'activo': activo,
      };

  factory BonoOferta.fromRow(Map<String, dynamic> r) => BonoOferta(
        id: (r['id'] ?? '').toString(),
        dueno: (r['dueno'] ?? '').toString(),
        club: (r['club'] ?? '').toString(),
        nombre: (r['nombre'] ?? '').toString(),
        horas: ((r['horas'] ?? 0) as num).toInt(),
        precio: ((r['precio'] ?? 0) as num).toDouble(),
        activo: (r['activo'] ?? true) == true,
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}

/// CRÉDITO de un bono comprado por un jugador. El saldo disponible es
/// `horasTotal - horasUsadas`. Se guarda en `pichangol_bonos_comprados`.
class BonoComprado {
  final String id;
  final String bonoId;
  final String dueno;
  final String club;
  final String comprador; // correo del jugador
  final String compradorNombre;
  final int horasTotal;
  final int horasUsadas;
  final double precio;
  final String ventaId;
  final DateTime creado;

  const BonoComprado({
    required this.id,
    required this.bonoId,
    required this.dueno,
    required this.club,
    required this.comprador,
    required this.compradorNombre,
    required this.horasTotal,
    this.horasUsadas = 0,
    required this.precio,
    this.ventaId = '',
    required this.creado,
  });

  int get saldo => (horasTotal - horasUsadas).clamp(0, horasTotal);

  Map<String, dynamic> toRow() => {
        'id': id,
        'bono_id': bonoId,
        'dueno': dueno.trim().toLowerCase(),
        'club': club,
        'comprador': comprador.trim().toLowerCase(),
        'comprador_nombre': compradorNombre,
        'horas_total': horasTotal,
        'horas_usadas': horasUsadas,
        'precio': precio,
        'venta_id': ventaId,
      };

  factory BonoComprado.fromRow(Map<String, dynamic> r) => BonoComprado(
        id: (r['id'] ?? '').toString(),
        bonoId: (r['bono_id'] ?? '').toString(),
        dueno: (r['dueno'] ?? '').toString(),
        club: (r['club'] ?? '').toString(),
        comprador: (r['comprador'] ?? '').toString(),
        compradorNombre: (r['comprador_nombre'] ?? '').toString(),
        horasTotal: ((r['horas_total'] ?? 0) as num).toInt(),
        horasUsadas: ((r['horas_usadas'] ?? 0) as num).toInt(),
        precio: ((r['precio'] ?? 0) as num).toDouble(),
        ventaId: (r['venta_id'] ?? '').toString(),
        creado: DateTime.tryParse((r['creado'] ?? '').toString())?.toLocal() ??
            DateTime.now(),
      );
}
