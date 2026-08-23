/// MI BODEGA (POS ligero del dueño, función Pro): productos con stock y
/// ventas de la caja rápida. La plata NO pasa por Pichangol (el dueño cobra
/// con su Yape/efectivo); aquí solo se registra la venta y baja el stock.
library;

/// Un producto de la bodega del local (cerveza, gaseosa, agua, snack…).
class ProductoBodega {
  final String id;
  final String dueno; // correo del dueño (filtra su bodega)
  final String cartaId; // id PÚBLICO de la carta digital /b/{cartaId}
  final String nombre;
  final String categoria; // Bebidas / Cervezas / Snacks / Deportivo / Otros
  final double precio;
  final int stock;
  final int stockMin; // alerta de reposición cuando stock <= stockMin
  final String? fotoUrl;
  /// Símbolo de la moneda del local ('S/', 'Bs', r'$'): la bodega se muestra
  /// y registra en la moneda del PAÍS del dueño.
  final String moneda;

  const ProductoBodega({
    required this.id,
    required this.dueno,
    required this.cartaId,
    required this.nombre,
    this.categoria = 'Otros',
    this.precio = 0,
    this.stock = 0,
    this.stockMin = 0,
    this.fotoUrl,
    this.moneda = 'S/',
  });

  bool get stockBajo => stock <= stockMin;

  ProductoBodega copyWith({
    String? nombre,
    String? categoria,
    double? precio,
    int? stock,
    int? stockMin,
    String? fotoUrl,
  }) =>
      ProductoBodega(
        id: id,
        dueno: dueno,
        cartaId: cartaId,
        nombre: nombre ?? this.nombre,
        categoria: categoria ?? this.categoria,
        precio: precio ?? this.precio,
        stock: stock ?? this.stock,
        stockMin: stockMin ?? this.stockMin,
        fotoUrl: fotoUrl ?? this.fotoUrl,
        moneda: moneda,
      );

  Map<String, dynamic> toRow() => {
        'id': id,
        'dueno': dueno,
        'carta_id': cartaId,
        'nombre': nombre,
        'categoria': categoria,
        'precio': precio,
        'stock': stock,
        'stock_min': stockMin,
        'foto_url': fotoUrl,
        'moneda': moneda,
        'eliminado': false,
      };

  factory ProductoBodega.fromRow(Map<String, dynamic> r) => ProductoBodega(
        id: (r['id'] ?? '') as String,
        dueno: (r['dueno'] ?? '') as String,
        cartaId: (r['carta_id'] ?? '') as String,
        nombre: (r['nombre'] ?? '') as String,
        categoria: (r['categoria'] ?? 'Otros') as String,
        precio: (r['precio'] as num?)?.toDouble() ?? 0,
        stock: (r['stock'] as num?)?.toInt() ?? 0,
        stockMin: (r['stock_min'] as num?)?.toInt() ?? 0,
        fotoUrl: r['foto_url'] as String?,
        moneda: (r['moneda'] ?? 'S/') as String,
      );
}

/// Una línea del ticket de la caja rápida.
class ItemVentaBodega {
  final String productoId;
  final String nombre;
  final int cantidad;
  final double precio; // unitario al momento de la venta

  const ItemVentaBodega({
    required this.productoId,
    required this.nombre,
    required this.cantidad,
    required this.precio,
  });

  double get subtotal => precio * cantidad;

  Map<String, dynamic> toJson() => {
        'producto_id': productoId,
        'nombre': nombre,
        'cantidad': cantidad,
        'precio': precio,
      };

  factory ItemVentaBodega.fromJson(Map<String, dynamic> j) => ItemVentaBodega(
        productoId: (j['producto_id'] ?? '') as String,
        nombre: (j['nombre'] ?? '') as String,
        cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
        precio: (j['precio'] as num?)?.toDouble() ?? 0,
      );
}

/// Una venta registrada en la caja (puede tener varios items).
class VentaBodega {
  final String id;
  final String dueno;
  final List<ItemVentaBodega> items;
  final double total;
  final String medioPago; // efectivo | yape | cortesia
  final DateTime creado;

  const VentaBodega({
    required this.id,
    required this.dueno,
    required this.items,
    required this.total,
    required this.medioPago,
    required this.creado,
  });

  Map<String, dynamic> toRow() => {
        'id': id,
        'dueno': dueno,
        'items': items.map((i) => i.toJson()).toList(),
        'total': total,
        'medio_pago': medioPago,
      };

  factory VentaBodega.fromRow(Map<String, dynamic> r) => VentaBodega(
        id: (r['id'] ?? '') as String,
        dueno: (r['dueno'] ?? '') as String,
        items: ((r['items'] as List?) ?? const [])
            .map((e) =>
                ItemVentaBodega.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        total: (r['total'] as num?)?.toDouble() ?? 0,
        medioPago: (r['medio_pago'] ?? 'efectivo') as String,
        creado: DateTime.tryParse((r['creado'] ?? '') as String) ??
            DateTime.now(),
      );
}
