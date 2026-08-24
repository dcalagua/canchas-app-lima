import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/bodega.dart';
import '../services/supabase_service.dart';

/// MI BODEGA en Supabase (tablas `pichangol_bodega_productos` y
/// `pichangol_bodega_ventas`). Fail-safe: sin backend no rompe la app.
/// SQL: docs/piloto/supabase_bodega.sql.
class BodegaRepo {
  static const _tProductos = 'pichangol_bodega_productos';
  static const _tVentas = 'pichangol_bodega_ventas';

  /// Id PÚBLICO de la carta digital del dueño (/b/{cartaId}) derivado del
  /// correo con FNV-1a 64 bits: estable entre dispositivos y NO expone el
  /// correo en la URL (Ley 29733: el correo es dato personal).
  static String cartaIdDe(String email) {
    final e = email.trim().toLowerCase();
    // FNV-1a de 32 bits, dos pasadas con seed distinta (aritmética de 32 bits:
    // siempre positiva y estable en cualquier plataforma Dart).
    int fnv(String s, int seed) {
      var h = (0x811c9dc5 ^ seed) & 0xFFFFFFFF;
      for (final c in s.codeUnits) {
        h ^= c;
        h = (h * 0x01000193) & 0xFFFFFFFF;
      }
      return h;
    }

    final a = fnv(e, 0).toRadixString(16).padLeft(8, '0');
    final b = fnv(e, 0x9e3779b9).toRadixString(16).padLeft(8, '0');
    return 'b${(a + b).substring(0, 12)}';
  }

  /// Productos vigentes del dueño (orden: categoría, nombre).
  static Future<List<ProductoBodega>> fetchProductos(String dueno) async {
    if (!SupabaseService.disponible || dueno.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tProductos)
          .select()
          .eq('dueno', dueno.toLowerCase())
          .eq('eliminado', false)
          .order('categoria')
          .order('nombre');
      return [
        for (final r in (rows as List))
          ProductoBodega.fromRow(Map<String, dynamic>.from(r as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Crea/actualiza un producto (upsert por id). Devuelve true si persistió.
  /// Tolerante a schema drift: si la columna `moneda` aún no existe en la BD
  /// (falta correr supabase_bodega_moneda.sql), reintenta sin ella.
  static Future<bool> guardarProducto(ProductoBodega p) async {
    if (!SupabaseService.disponible) return false;
    final fila = p.toRow();
    try {
      await SupabaseService.client.from(_tProductos).upsert(fila);
      return true;
    } catch (_) {
      try {
        fila.remove('moneda');
        await SupabaseService.client.from(_tProductos).upsert(fila);
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  /// Borrado LÓGICO (el producto sale de la carta y de la caja).
  static Future<bool> eliminarProducto(String id) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client
          .from(_tProductos)
          .update({'eliminado': true}).eq('id', id);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Sube la foto del producto al bucket público. Devuelve la URL o null.
  static Future<String?> subirFoto(String productoId, List<int> bytes) async {
    if (!SupabaseService.disponible || productoId.isEmpty) return null;
    try {
      final ruta = 'bodega/$productoId.jpg';
      final storage = SupabaseService.client.storage.from('canchas');
      await storage.uploadBinary(ruta, Uint8List.fromList(bytes),
          fileOptions:
              const FileOptions(upsert: true, contentType: 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }

  /// Registra la venta y DESCUENTA el stock de cada producto (update por
  /// item, best-effort: si un update falla, la venta ya quedó registrada y
  /// el stock se corrige en el próximo refresco/edición).
  static Future<bool> registrarVenta(
      VentaBodega v, Map<String, int> nuevoStockPorProducto) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tVentas).insert(v.toRow());
    } catch (_) {
      return false;
    }
    for (final e in nuevoStockPorProducto.entries) {
      try {
        await SupabaseService.client
            .from(_tProductos)
            .update({'stock': e.value}).eq('id', e.key);
      } catch (_) {}
    }
    return true;
  }

  // ── Fase 2: PEDIDOS A LA CANCHA ────────────────────────────────────────────
  static const _tPedidos = 'pichangol_bodega_pedidos';
  static const _tConfig = 'pichangol_bodega_config';

  /// Config de la bodega del dueño (acepta pedidos + zonas). Default: NO
  /// acepta (cada local decide si tiene quién lleve). Fail-safe.
  static Future<ConfigBodega> fetchConfig(String dueno) async {
    final d = dueno.trim().toLowerCase();
    if (!SupabaseService.disponible || d.isEmpty) {
      return ConfigBodega(dueno: d);
    }
    try {
      final rows = await SupabaseService.client
          .from(_tConfig)
          .select()
          .eq('dueno', d)
          .limit(1);
      final lista = rows as List;
      if (lista.isEmpty) return ConfigBodega(dueno: d);
      return ConfigBodega.fromRow(Map<String, dynamic>.from(lista.first as Map));
    } catch (_) {
      return ConfigBodega(dueno: d);
    }
  }

  /// Tolerante a schema drift: si las columnas de cuenta abierta aún no
  /// existen (falta correr supabase_bodega_cuentas.sql), reintenta sin ellas.
  static Future<bool> guardarConfig(ConfigBodega c) async {
    if (!SupabaseService.disponible) return false;
    final fila = c.toRow();
    try {
      await SupabaseService.client.from(_tConfig).upsert(fila);
      return true;
    } catch (_) {
      try {
        fila.remove('permite_cuenta');
        fila.remove('tope_cuenta');
        await SupabaseService.client.from(_tConfig).upsert(fila);
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  /// Crea el pedido del cliente. Devuelve true si quedó registrado.
  /// Tolerante a schema drift SOLO si el pedido NO va pagado: sin la columna
  /// `pagado` (falta supabase_bodega_pago.sql) reintenta sin ella. Un pedido
  /// PAGADO es estricto: si la columna falta, mejor fallar (y no cobrar) que
  /// registrar un pedido pagado que el dueño cobraría de nuevo.
  static Future<bool> crearPedido(PedidoBodega p) async {
    if (!SupabaseService.disponible) return false;
    final fila = p.toRow();
    try {
      await SupabaseService.client.from(_tPedidos).insert(fila);
      return true;
    } catch (_) {
      if (p.pagado) return false;
      try {
        fila.remove('pagado');
        await SupabaseService.client.from(_tPedidos).insert(fila);
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  /// Pedidos del DUEÑO de los últimos 2 días (pendientes arriba en la UI).
  static Future<List<PedidoBodega>> fetchPedidosDueno(String dueno) async {
    final d = dueno.trim().toLowerCase();
    if (!SupabaseService.disponible || d.isEmpty) return const [];
    try {
      final desde = DateTime.now().subtract(const Duration(days: 2));
      final rows = await SupabaseService.client
          .from(_tPedidos)
          .select()
          .eq('dueno', d)
          .gte('creado', desde.toUtc().toIso8601String())
          .order('creado', ascending: false)
          .limit(100);
      return [
        for (final r in (rows as List))
          PedidoBodega.fromRow(Map<String, dynamic>.from(r as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Pedidos del CLIENTE con este dueño en las últimas 12 h (para ver el
  /// estado del que acaba de hacer).
  static Future<List<PedidoBodega>> fetchPedidosCliente(
      String cliente, String dueno) async {
    final c = cliente.trim().toLowerCase();
    if (!SupabaseService.disponible || c.isEmpty) return const [];
    try {
      // 30 días: la pantalla del cliente separa los ACTIVOS (arriba, con su
      // recorrido) del HISTORIAL agrupado por fecha.
      final desde = DateTime.now().subtract(const Duration(days: 30));
      final rows = await SupabaseService.client
          .from(_tPedidos)
          .select()
          .eq('cliente', c)
          .eq('dueno', dueno.trim().toLowerCase())
          .gte('creado', desde.toUtc().toIso8601String())
          .order('creado', ascending: false)
          .limit(50);
      return [
        for (final r in (rows as List))
          PedidoBodega.fromRow(Map<String, dynamic>.from(r as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// Cambia el estado de un pedido (confirmado/entregado/rechazado/cancelado).
  static Future<bool> actualizarEstadoPedido(String id, String estado) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tPedidos).update({
        'estado': estado,
        'actualizado': DateTime.now().toUtc().toIso8601String(),
      }).eq('id', id);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Cambia el estado SOLO si el pedido sigue en [desde] — candado de
  /// concurrencia (mismo espíritu que la doble reserva: el PRIMERO gana y el
  /// segundo se entera). Cubre: el cliente cancela mientras el dueño
  /// confirma, y el dueño con dos equipos cobrando el mismo pedido.
  /// Devuelve (ok, estadoActual): ok=true → cambió; ok=false con
  /// estadoActual → otro le ganó y ese es el estado vigente en la nube;
  /// ok=false y estadoActual=null → error de red (no se sabe, no tocar UI).
  static Future<(bool, String?)> cambiarEstadoPedidoSi(
      String id, String nuevo,
      {required String desde}) async {
    if (!SupabaseService.disponible) return (false, null);
    try {
      final rows = await SupabaseService.client
          .from(_tPedidos)
          .update({
            'estado': nuevo,
            'actualizado': DateTime.now().toUtc().toIso8601String(),
          })
          .eq('id', id)
          .eq('estado', desde)
          .select('estado');
      if ((rows as List).isNotEmpty) return (true, null);
      // No matcheó: alguien cambió el estado primero. ¿En qué quedó?
      final cur = await SupabaseService.client
          .from(_tPedidos)
          .select('estado')
          .eq('id', id)
          .limit(1);
      final lista = cur as List;
      if (lista.isEmpty) return (false, null);
      return (false, ((lista.first as Map)['estado'] ?? '') as String);
    } catch (_) {
      return (false, null);
    }
  }

  // ── CUENTA ABIERTA ("apúntamelo, pago al salir") ───────────────────────────
  static const _tCuentas = 'pichangol_bodega_cuentas';

  /// Descuenta stock SIN registrar venta (consumos anotados a una cuenta:
  /// la venta se registra recién al CERRAR la cuenta, pero el stock baja al
  /// entregar). Best-effort por producto.
  static Future<void> actualizarStock(
      Map<String, int> nuevoStockPorProducto) async {
    if (!SupabaseService.disponible) return;
    for (final e in nuevoStockPorProducto.entries) {
      try {
        await SupabaseService.client
            .from(_tProductos)
            .update({'stock': e.value}).eq('id', e.key);
      } catch (_) {}
    }
  }

  /// Cuentas del dueño de los últimos 30 días (abiertas y cerradas; la UI
  /// ordena abiertas primero). Fail-safe.
  static Future<List<CuentaBodega>> fetchCuentas(String dueno) async {
    final d = dueno.trim().toLowerCase();
    if (!SupabaseService.disponible || d.isEmpty) return const [];
    try {
      final desde = DateTime.now().subtract(const Duration(days: 30));
      final rows = await SupabaseService.client
          .from(_tCuentas)
          .select()
          .eq('dueno', d)
          .gte('creado', desde.toUtc().toIso8601String())
          .order('creado', ascending: false)
          .limit(100);
      return [
        for (final r in (rows as List))
          CuentaBodega.fromRow(Map<String, dynamic>.from(r as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }

  /// La cuenta ABIERTA del cliente con este local (para que el cliente vea
  /// "llevas S/ X" en vivo). null si no tiene.
  static Future<CuentaBodega?> fetchCuentaAbiertaCliente(
      String cliente, String dueno) async {
    final c = cliente.trim().toLowerCase();
    if (!SupabaseService.disponible || c.isEmpty) return null;
    try {
      final rows = await SupabaseService.client
          .from(_tCuentas)
          .select()
          .eq('cliente', c)
          .eq('dueno', dueno.trim().toLowerCase())
          .eq('estado', 'abierta')
          .order('creado', ascending: false)
          .limit(1);
      final lista = rows as List;
      if (lista.isEmpty) return null;
      return CuentaBodega.fromRow(
          Map<String, dynamic>.from(lista.first as Map));
    } catch (_) {
      return null;
    }
  }

  /// ANOTA consumo a la cuenta abierta del cliente (la crea si no existe).
  /// Devuelve la cuenta resultante o null si no se pudo persistir.
  static Future<CuentaBodega?> anotarACuenta({
    required String dueno,
    required String cliente,
    required String clienteNombre,
    required List<ItemVentaBodega> items,
    required String moneda,
  }) async {
    if (!SupabaseService.disponible || items.isEmpty) return null;
    final agregado =
        items.fold<double>(0, (a, i) => a + i.subtotal);
    final abierta = await fetchCuentaAbiertaCliente(cliente, dueno);
    try {
      if (abierta == null) {
        final nueva = CuentaBodega(
          id: 'bc_${DateTime.now().microsecondsSinceEpoch}',
          dueno: dueno.trim().toLowerCase(),
          cliente: cliente.trim().toLowerCase(),
          clienteNombre: clienteNombre,
          items: items,
          total: agregado,
          moneda: moneda,
          creado: DateTime.now(),
        );
        await SupabaseService.client.from(_tCuentas).insert(nueva.toRow());
        return nueva;
      }
      final combinados = [...abierta.items, ...items];
      final total = abierta.total + agregado;
      // Candado suave: solo suma si la cuenta SIGUE abierta (si el otro
      // equipo la cerró hace un segundo, mejor fallar y que se reintente
      // como cuenta nueva desde la UI refrescada).
      final rows = await SupabaseService.client
          .from(_tCuentas)
          .update({
            'items': combinados.map((i) => i.toJson()).toList(),
            'total': total,
            'actualizado': DateTime.now().toUtc().toIso8601String(),
          })
          .eq('id', abierta.id)
          .eq('estado', 'abierta')
          .select('id');
      if ((rows as List).isEmpty) return null;
      return CuentaBodega(
        id: abierta.id,
        dueno: abierta.dueno,
        cliente: abierta.cliente,
        clienteNombre: abierta.clienteNombre,
        items: combinados,
        total: total,
        moneda: abierta.moneda,
        creado: abierta.creado,
      );
    } catch (_) {
      return null;
    }
  }

  /// CIERRA la cuenta (candado: solo si sigue abierta — con dos equipos solo
  /// uno cobra). Devuelve true si este equipo ganó el cierre.
  static Future<bool> cerrarCuentaSi(String id, String medioPago) async {
    if (!SupabaseService.disponible) return false;
    try {
      final ahora = DateTime.now().toUtc().toIso8601String();
      final rows = await SupabaseService.client
          .from(_tCuentas)
          .update({
            'estado': 'cerrada',
            'medio_pago': medioPago,
            'cerrado': ahora,
            'actualizado': ahora,
          })
          .eq('id', id)
          .eq('estado', 'abierta')
          .select('id');
      return (rows as List).isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  /// Ventas del dueño desde [desde] (para el reporte). Más recientes primero.
  static Future<List<VentaBodega>> fetchVentas(String dueno,
      {required DateTime desde}) async {
    if (!SupabaseService.disponible || dueno.isEmpty) return const [];
    try {
      final rows = await SupabaseService.client
          .from(_tVentas)
          .select()
          .eq('dueno', dueno.toLowerCase())
          .gte('creado', desde.toUtc().toIso8601String())
          .order('creado', ascending: false)
          .limit(500);
      return [
        for (final r in (rows as List))
          VentaBodega.fromRow(Map<String, dynamic>.from(r as Map)),
      ];
    } catch (_) {
      return const [];
    }
  }
}
