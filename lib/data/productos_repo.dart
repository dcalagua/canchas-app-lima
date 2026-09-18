import 'dart:typed_data';

import 'package:supabase_flutter/supabase_flutter.dart' show FileOptions;

import '../models/producto.dart';
import '../services/supabase_service.dart';
import 'storage_limpieza.dart';

/// Acceso a los productos del Marketplace en Supabase (tabla
/// `pichangol_productos`). Todo fail-safe: sin Supabase o ante error devuelve
/// vacío / no hace nada y la app sigue. La foto va al bucket público
/// `productos`.
class ProductosRepo {
  static const _tabla = 'pichangol_productos';
  static const _bucket = 'productos';

  /// Todos los productos ACTIVOS (feed del comprador), más nuevos primero.
  static Future<List<Producto>> fetchActivos() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('activo', true)
          .order('creado_en', ascending: false);
      return (rows as List)
          .map((r) => Producto.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Productos de un vendedor (su tienda), incluidos los pausados.
  static Future<List<Producto>> fetchDeVendedor(String email) async {
    if (!SupabaseService.disponible || email.trim().isEmpty) return [];
    try {
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .eq('vendedor_email', email.trim().toLowerCase())
          .order('creado_en', ascending: false);
      return (rows as List)
          .map((r) => Producto.fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Crea o actualiza un producto (upsert por id). Fail-safe.
  static Future<bool> guardar(Producto p) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).upsert(p.toRow());
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Borra un producto del vendedor. Fail-safe.
  static Future<bool> eliminar(String id) async {
    if (!SupabaseService.disponible) return false;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
      // Su foto no debe quedar huérfana en el bucket.
      await StorageLimpieza.borrar(_bucket, ['$id.jpg']);
      return true;
    } catch (_) {
      return false;
    }
  }

  static String? ultimoErrorFoto;

  /// Sube la foto del producto al bucket público `productos` y devuelve su URL.
  /// Null si falla (motivo en [ultimoErrorFoto]).
  static Future<String?> subirFoto(String productoId, Uint8List bytes) async {
    if (!SupabaseService.disponible) {
      ultimoErrorFoto = 'Supabase no está configurado en esta app.';
      return null;
    }
    try {
      final ruta = '$productoId.jpg';
      final storage = SupabaseService.client.storage.from(_bucket);
      await storage.uploadBinary(ruta, bytes,
          fileOptions: const FileOptions(
              upsert: true, contentType: 'image/jpeg'));
      final base = storage.getPublicUrl(ruta);
      ultimoErrorFoto = null;
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (e) {
      final s = e.toString().toLowerCase();
      if (s.contains('bucket') || s.contains('not found')) {
        ultimoErrorFoto =
            'Falta el bucket "productos" en Supabase Storage (créalo público).';
      } else if (s.contains('policy') ||
          s.contains('row-level') ||
          s.contains('403') ||
          s.contains('unauthorized')) {
        ultimoErrorFoto =
            'El bucket "productos" no permite subir fotos (falta la política).';
      } else {
        ultimoErrorFoto = 'No se pudo subir la foto. Detalle: $e';
      }
      return null;
    }
  }
}
