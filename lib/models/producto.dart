/// Un PRODUCTO del Marketplace Pichangol: lo que un dueño de cancha o academia
/// publica para vender (raquetas, pelotas, grips, indumentaria, etc.). El
/// comprador paga dentro de la app (Culqi) y coordina la entrega por chat con el
/// vendedor. Pichangol se queda una comisión. Se guarda en Supabase
/// (`pichangol_productos`); la foto va a un bucket público `productos`.
class Producto {
  final String id;
  final String vendedorEmail; // dueño/academia que publica (identidad = correo)
  final String vendedorNombre;
  final String nombre;
  final String descripcion;
  final double precio;
  final String moneda; // símbolo: 'S/', 'Bs', '$'
  final String categoria; // clave de [categorias]
  final String fotoUrl;
  final int? stock; // null = no aplica / ilimitado
  final bool activo; // pausado = false (no aparece en el feed)
  final DateTime creadoEn;

  const Producto({
    required this.id,
    required this.vendedorEmail,
    required this.vendedorNombre,
    required this.nombre,
    required this.precio,
    this.descripcion = '',
    this.moneda = 'S/',
    this.categoria = 'otros',
    this.fotoUrl = '',
    this.stock,
    this.activo = true,
    required this.creadoEn,
  });

  /// Categorías del marketplace: clave → etiqueta visible. La primera es el
  /// "todos" para el filtro (no se usa como categoría de un producto).
  static const categorias = <String, String>{
    'raquetas': 'Raquetas',
    'pelotas': 'Pelotas',
    'indumentaria': 'Indumentaria',
    'calzado': 'Calzado',
    'accesorios': 'Accesorios',
    'nutricion': 'Nutrición',
    'otros': 'Otros',
  };

  String get categoriaEtiqueta => categorias[categoria] ?? 'Otros';
  String get precioTexto => '$moneda ${precio.toStringAsFixed(2)}';
  bool get agotado => stock != null && stock! <= 0;

  Producto copyWith({
    String? nombre,
    String? descripcion,
    double? precio,
    String? categoria,
    String? fotoUrl,
    int? stock,
    bool? activo,
    String? moneda,
  }) =>
      Producto(
        id: id,
        vendedorEmail: vendedorEmail,
        vendedorNombre: vendedorNombre,
        nombre: nombre ?? this.nombre,
        descripcion: descripcion ?? this.descripcion,
        precio: precio ?? this.precio,
        moneda: moneda ?? this.moneda,
        categoria: categoria ?? this.categoria,
        fotoUrl: fotoUrl ?? this.fotoUrl,
        stock: stock ?? this.stock,
        activo: activo ?? this.activo,
        creadoEn: creadoEn,
      );

  Map<String, dynamic> toRow() => {
        'id': id,
        'vendedor_email': vendedorEmail,
        'vendedor_nombre': vendedorNombre,
        'nombre': nombre,
        'descripcion': descripcion,
        'precio': precio,
        'moneda': moneda,
        'categoria': categoria,
        'foto_url': fotoUrl,
        'stock': stock,
        'activo': activo,
        'creado_en': creadoEn.toIso8601String(),
      };

  factory Producto.fromRow(Map<String, dynamic> r) => Producto(
        id: r['id'].toString(),
        vendedorEmail: (r['vendedor_email'] ?? '').toString(),
        vendedorNombre: (r['vendedor_nombre'] ?? '').toString(),
        nombre: (r['nombre'] ?? 'Producto').toString(),
        descripcion: (r['descripcion'] ?? '').toString(),
        precio: ((r['precio'] ?? 0) as num).toDouble(),
        moneda: (r['moneda'] ?? 'S/').toString(),
        categoria: (r['categoria'] ?? 'otros').toString(),
        fotoUrl: (r['foto_url'] ?? '').toString(),
        stock: r['stock'] == null ? null : (r['stock'] as num).toInt(),
        activo: (r['activo'] ?? true) as bool,
        creadoEn:
            DateTime.tryParse((r['creado_en'] ?? '').toString()) ??
                DateTime.fromMillisecondsSinceEpoch(0),
      );
}
