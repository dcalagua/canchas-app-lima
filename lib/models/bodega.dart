/// MI BODEGA (POS ligero del dueño, función Pro): productos con stock y
/// ventas de la caja rápida. La plata NO pasa por Pichangol (el dueño cobra
/// con su Yape/efectivo); aquí solo se registra la venta y baja el stock.
library;

/// "Imagen" AUTOMÁTICA del producto: emoji grande según QUÉ es (no la
/// marca), así funciona igual en los 3 países (Pilsen, Paceña y Pilsener
/// son 🍺). La foto real del dueño (fotoUrl) siempre manda si existe.
String emojiProductoBodega(String nombre, String categoria) {
  final n = nombre.toLowerCase();
  if (n.contains('agua')) return '💧';
  if (n.contains('jugo') || n.contains('frugos') || n.contains('cifrut')) {
    return '🧃';
  }
  if (n.contains('gatorade') ||
      n.contains('powerade') ||
      n.contains('sporade') ||
      n.contains('volt') ||
      n.contains('profit')) {
    return '⚡';
  }
  if (n.contains('paleta')) return '🏓';
  if (n.contains('pelota')) return '🎾';
  if (n.contains('papita') ||
      n.contains('lays') ||
      n.contains('dorito') ||
      n.contains('chifle') ||
      n.contains('chizito') ||
      n.contains('kchito')) {
    return '🍟';
  }
  if (n.contains('galleta')) return '🍪';
  if (n.contains('chocolate') || n.contains('sublime')) return '🍫';
  if (n.contains('maní') || n.contains('mani')) return '🥜';
  if (n.contains('sandwich') || n.contains('sánguche')) return '🥪';
  if (n.contains('hielo')) return '🧊';
  if (n.contains('cigarro')) return '🚬';
  if (n.contains('gorra')) return '🧢';
  return switch (categoria) {
    'Cervezas' => '🍺',
    'Bebidas' => '🥤',
    'Deportivo' => '🎽',
    'Snacks' => '🍿',
    _ => '🛒',
  };
}

/// TIPO de packshot IA del producto: imagen GENÉRICA sin marca que sirve el
/// backend (`GET /bodega/packshot/{tipo}`). Sin logos oficiales (Pilsen,
/// Paceña… son marcas registradas): el packshot muestra QUÉ es el producto,
/// igual en los 3 países. La foto real del dueño siempre manda; si el
/// packshot no carga se cae al emoji.
String packshotTipoDe(String nombre, String categoria) {
  final n = nombre.toLowerCase();
  if (n.contains('cerveza')) return 'cerveza';
  if (n.contains('agua')) return 'agua';
  if (n.contains('jugo') || n.contains('frugos') || n.contains('cifrut')) {
    return 'jugo';
  }
  if (n.contains('gatorade') ||
      n.contains('powerade') ||
      n.contains('sporade') ||
      n.contains('volt') ||
      n.contains('profit')) {
    return 'rehidratante';
  }
  if (n.contains('paleta')) return 'paleta';
  if (n.contains('pelota')) return 'pelotas';
  if (n.contains('papita') ||
      n.contains('lays') ||
      n.contains('dorito') ||
      n.contains('chifle') ||
      n.contains('chizito') ||
      n.contains('kchito')) {
    return 'papitas';
  }
  if (n.contains('galleta')) return 'galletas';
  if (n.contains('chocolate') || n.contains('sublime')) return 'chocolate';
  if (n.contains('maní') || n.contains('mani')) return 'mani';
  if (n.contains('sandwich') || n.contains('sánguche')) return 'sandwich';
  if (n.contains('hielo')) return 'hielo';
  if (n.contains('gorra')) return 'gorra';
  if (n.contains('toalla')) return 'toalla';
  return switch (categoria) {
    'Cervezas' => 'cerveza',
    'Bebidas' => 'gaseosa',
    'Snacks' => 'papitas',
    'Deportivo' => 'pelotas',
    _ => 'generico',
  };
}

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

  /// Emoji-imagen del producto (cuando no hay foto real).
  String get emoji => emojiProductoBodega(nombre, categoria);

  /// Tipo de packshot IA genérico (imagen automática sin marca).
  String get packshotTipo => packshotTipoDe(nombre, categoria);

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

/// Configuración de la bodega (Fase 2, pedidos a la cancha): si el dueño
/// acepta pedidos y las ZONAS de entrega (Cancha 1, Mesa…). Apagado por
/// defecto: cada local decide si tiene quién lleve.
class ConfigBodega {
  final String dueno;
  final bool aceptaPedidos;
  final List<String> zonas;

  /// CUENTA ABIERTA ("apúntamelo, pago al salir"): el dueño decide si la
  /// ofrece. Apagada por defecto — es SU riesgo de cobranza.
  final bool permiteCuenta;

  /// Tope por cuenta en la moneda del local (0 = sin tope): al llegar, los
  /// siguientes consumos se cobran al entregar.
  final double topeCuenta;

  const ConfigBodega({
    required this.dueno,
    this.aceptaPedidos = false,
    this.zonas = const ['Cancha 1', 'Cancha 2', 'Mesa', 'Mostrador'],
    this.permiteCuenta = false,
    this.topeCuenta = 100,
  });

  ConfigBodega copyWith({
    bool? aceptaPedidos,
    List<String>? zonas,
    bool? permiteCuenta,
    double? topeCuenta,
  }) =>
      ConfigBodega(
        dueno: dueno,
        aceptaPedidos: aceptaPedidos ?? this.aceptaPedidos,
        zonas: zonas ?? this.zonas,
        permiteCuenta: permiteCuenta ?? this.permiteCuenta,
        topeCuenta: topeCuenta ?? this.topeCuenta,
      );

  Map<String, dynamic> toRow() => {
        'dueno': dueno,
        'acepta_pedidos': aceptaPedidos,
        'zonas': zonas,
        'permite_cuenta': permiteCuenta,
        'tope_cuenta': topeCuenta,
      };

  factory ConfigBodega.fromRow(Map<String, dynamic> r) => ConfigBodega(
        dueno: (r['dueno'] ?? '') as String,
        aceptaPedidos: (r['acepta_pedidos'] ?? false) as bool,
        zonas: (r['zonas'] as List?)?.map((e) => e.toString()).toList() ??
            const ['Cancha 1', 'Cancha 2', 'Mesa', 'Mostrador'],
        permiteCuenta: (r['permite_cuenta'] ?? false) as bool,
        topeCuenta: (r['tope_cuenta'] as num?)?.toDouble() ?? 100,
      );
}

/// CUENTA ABIERTA de un cliente en la bodega del local: consume durante su
/// estadía (pedidos a la cancha o mostrador) y paga TODO al retirarse. La
/// venta (reporte) se registra recién al CERRARLA; el stock ya se descontó
/// al entregar cada consumo.
class CuentaBodega {
  final String id;
  final String dueno;
  final String cliente; // correo (cliente IDENTIFICADO, requisito)
  final String clienteNombre;
  final List<ItemVentaBodega> items;
  final double total;
  final String moneda;
  final String estado; // abierta | cerrada
  final String medioPago; // con qué pagó al cerrar ('' mientras abierta)
  final DateTime creado;

  const CuentaBodega({
    required this.id,
    required this.dueno,
    required this.cliente,
    required this.clienteNombre,
    required this.items,
    required this.total,
    required this.moneda,
    this.estado = 'abierta',
    this.medioPago = '',
    required this.creado,
  });

  bool get abierta => estado == 'abierta';

  String get resumen =>
      items.map((i) => '${i.cantidad} ${i.nombre}').join(' + ');

  Map<String, dynamic> toRow() => {
        'id': id,
        'dueno': dueno,
        'cliente': cliente,
        'cliente_nombre': clienteNombre,
        'items': items.map((i) => i.toJson()).toList(),
        'total': total,
        'moneda': moneda,
        'estado': estado,
        'medio_pago': medioPago,
      };

  factory CuentaBodega.fromRow(Map<String, dynamic> r) => CuentaBodega(
        id: (r['id'] ?? '') as String,
        dueno: (r['dueno'] ?? '') as String,
        cliente: (r['cliente'] ?? '') as String,
        clienteNombre: (r['cliente_nombre'] ?? '') as String,
        items: ((r['items'] as List?) ?? const [])
            .map((e) =>
                ItemVentaBodega.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        total: (r['total'] as num?)?.toDouble() ?? 0,
        moneda: (r['moneda'] ?? 'S/') as String,
        estado: (r['estado'] ?? 'abierta') as String,
        medioPago: (r['medio_pago'] ?? '') as String,
        creado: DateTime.tryParse((r['creado'] ?? '') as String)?.toLocal() ??
            DateTime.now(),
      );
}

/// Un PEDIDO a la cancha: el jugador lo arma desde su ubicación en el local,
/// el dueño lo confirma y se lo llevan; al entregar se cobra como siempre.
class PedidoBodega {
  final String id;
  final String dueno;
  final String cliente; // correo del que pide
  final String clienteNombre;
  final String zona; // a dónde llevarlo (Cancha 2, Mesa…)
  final List<ItemVentaBodega> items;
  final double total;
  final String moneda;
  final String estado; // pendiente|confirmado|entregado|rechazado|cancelado
  final DateTime creado;

  const PedidoBodega({
    required this.id,
    required this.dueno,
    required this.cliente,
    required this.clienteNombre,
    required this.zona,
    required this.items,
    required this.total,
    required this.moneda,
    this.estado = 'pendiente',
    required this.creado,
  });

  bool get pendiente => estado == 'pendiente';
  bool get confirmado => estado == 'confirmado';

  /// Un pendiente sin respuesta en 10 min se muestra EXPIRADO (no dejar al
  /// cliente colgado); el dueño aún puede confirmarlo si llega a tiempo.
  bool get expirado =>
      pendiente && DateTime.now().difference(creado).inMinutes >= 10;

  String get resumen =>
      items.map((i) => '${i.cantidad} ${i.nombre}').join(' + ');

  PedidoBodega conEstado(String e) => PedidoBodega(
        id: id,
        dueno: dueno,
        cliente: cliente,
        clienteNombre: clienteNombre,
        zona: zona,
        items: items,
        total: total,
        moneda: moneda,
        estado: e,
        creado: creado,
      );

  Map<String, dynamic> toRow() => {
        'id': id,
        'dueno': dueno,
        'cliente': cliente,
        'cliente_nombre': clienteNombre,
        'zona': zona,
        'items': items.map((i) => i.toJson()).toList(),
        'total': total,
        'moneda': moneda,
        'estado': estado,
      };

  factory PedidoBodega.fromRow(Map<String, dynamic> r) => PedidoBodega(
        id: (r['id'] ?? '') as String,
        dueno: (r['dueno'] ?? '') as String,
        cliente: (r['cliente'] ?? '') as String,
        clienteNombre: (r['cliente_nombre'] ?? '') as String,
        zona: (r['zona'] ?? '') as String,
        items: ((r['items'] as List?) ?? const [])
            .map((e) =>
                ItemVentaBodega.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        total: (r['total'] as num?)?.toDouble() ?? 0,
        moneda: (r['moneda'] ?? 'S/') as String,
        estado: (r['estado'] ?? 'pendiente') as String,
        creado: DateTime.tryParse((r['creado'] ?? '') as String)?.toLocal() ??
            DateTime.now(),
      );
}
