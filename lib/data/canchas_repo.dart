import 'dart:typed_data';

import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/models.dart';
import '../services/supabase_service.dart';

/// Acceso a canchas en Supabase (tabla `pichangol_canchas`). Todo es fail-safe:
/// si Supabase no está disponible o falla, devuelve vacío / no hace nada y la
/// app sigue con datos locales.
class CanchasRepo {
  static const _tabla = 'pichangol_canchas';

  static Future<List<Cancha>> fetchRemotas() async {
    if (!SupabaseService.disponible) return [];
    try {
      final rows = await SupabaseService.client.from(_tabla).select();
      return (rows as List)
          .map((r) => _fromRow(r as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> insertar(Cancha c) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).insert(_toRow(c));
    } catch (_) {}
  }

  /// Actualiza una cancha existente (edición del dueño). Fail-safe.
  static Future<void> actualizar(Cancha c) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from(_tabla)
          .update(_toRow(c))
          .eq('id', c.id);
    } catch (_) {}
  }

  /// Elimina una cancha. Fail-safe.
  static Future<void> eliminar(String id) async {
    if (!SupabaseService.disponible) return;
    try {
      await SupabaseService.client.from(_tabla).delete().eq('id', id);
    } catch (_) {}
  }

  /// Sube una foto de portada al bucket `canchas` y devuelve su URL pública.
  /// Requiere un bucket público llamado `canchas` en Supabase Storage. Fail-safe:
  /// si no está configurado o falla, devuelve null y la cancha queda sin foto.
  static Future<String?> subirFoto(String canchaId, Uint8List bytes) async {
    if (!SupabaseService.disponible) return null;
    try {
      final ruta = '$canchaId.jpg';
      final storage = SupabaseService.client.storage.from('canchas');
      await storage.uploadBinary(
        ruta,
        bytes,
        fileOptions: const FileOptions(upsert: true, contentType: 'image/jpeg'),
      );
      // Cache-busting para que se vea la foto nueva tras editar.
      final base = storage.getPublicUrl(ruta);
      return '$base?v=${DateTime.now().millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }

  static Map<String, dynamic> _toRow(Cancha c) => {
        'id': c.id,
        'nombre': c.nombre,
        'club': c.club,
        'distrito': c.distrito.name,
        'deporte': c.deporte.name,
        'precio_hora': c.precioHora,
        'lat': c.ubicacion.latitude,
        'lng': c.ubicacion.longitude,
        'club_fundador': c.clubFundador,
        'digitalizada': c.digitalizada,
        'direccion': c.direccion,
        'registrada': c.registrada,
        'foto_url': c.fotoUrl,
      };

  static Cancha _fromRow(Map<String, dynamic> r) => Cancha(
        id: r['id'].toString(),
        nombre: (r['nombre'] ?? 'Cancha') as String,
        club: (r['club'] ?? '') as String,
        distrito: _enumDistrito(r['distrito'] as String?),
        deporte: _enumDeporte(r['deporte'] as String?),
        precioHora: ((r['precio_hora'] ?? 100) as num).toInt(),
        ubicacion: LatLng(
          ((r['lat'] ?? -12.108) as num).toDouble(),
          ((r['lng'] ?? -76.978) as num).toDouble(),
        ),
        clubFundador: (r['club_fundador'] ?? false) as bool,
        digitalizada: (r['digitalizada'] ?? true) as bool,
        direccion: r['direccion'] as String?,
        registrada: (r['registrada'] ?? true) as bool,
        fotoUrl: r['foto_url'] as String?,
      );

  static Distrito _enumDistrito(String? s) {
    for (final d in Distrito.values) {
      if (d.name == s) return d;
    }
    return Distrito.sanBorja;
  }

  static Deporte _enumDeporte(String? s) {
    for (final d in Deporte.values) {
      if (d.name == s) return d;
    }
    return Deporte.futbol;
  }
}
