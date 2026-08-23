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
