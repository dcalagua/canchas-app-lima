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
