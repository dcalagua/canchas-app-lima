import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/models.dart';
import '../services/supabase_service.dart';

/// COSECHA de canchas descubiertas (tabla `pichangol_canchas_cache`).
///
/// Estrategia de costo CERO con Google: la PRIMERA persona que explora una zona
/// la descubre vía Google Places y la app guarda aquí lo esencial (place_id,
/// nombre, dirección, lat/lng, deporte). Desde entonces, TODOS leen de esta
/// tabla (instantáneo, gratis, offline-friendly) y Google solo se consulta para
/// zonas nuevas. NO se guardan fotos de Google (caducan + licencia): la lista
/// usa placeholder por deporte y la foto real llega cuando el dueño reclama.
///
/// Fail-safe total: sin Supabase (o con error) devuelve vacío / no guarda.
class CanchasCacheRepo {
  static const _tabla = 'pichangol_canchas_cache';

  /// Cosecha más RECIENTE (máximo `visto_en`) de la zona del último `cerca()`:
  /// decide si la zona está FRESCA o toca re-consultar Google (frescura + ToS).
  static DateTime? ultimaCosecha;

  /// Canchas cosechadas dentro de un cuadro de ~[radioKm] alrededor de [centro].
  static Future<List<Cancha>> cerca(LatLng centro, double radioKm) async {
    ultimaCosecha = null;
    if (!SupabaseService.disponible) return const [];
    try {
      // Bounding box aproximado (1° lat ≈ 111 km). Suficiente para el radar.
      final dLat = radioKm / 111.0;
      final dLng = radioKm / 111.0; // aproximación válida en latitudes de LatAm
      final rows = await SupabaseService.client
          .from(_tabla)
          .select()
          .gte('lat', centro.latitude - dLat)
          .lte('lat', centro.latitude + dLat)
          .gte('lng', centro.longitude - dLng)
          .lte('lng', centro.longitude + dLng)
          .limit(400);
      final out = <Cancha>[];
      for (final r in (rows as List)) {
        final m = Map<String, dynamic>.from(r as Map);
        final id = (m['id'] ?? '').toString();
        final nombre = (m['nombre'] ?? '').toString();
        final lat = (m['lat'] as num?)?.toDouble();
        final lng = (m['lng'] as num?)?.toDouble();
        if (id.isEmpty || nombre.isEmpty || lat == null || lng == null) {
          continue;
        }
        final visto = DateTime.tryParse((m['visto_en'] ?? '').toString());
        if (visto != null &&
            (ultimaCosecha == null || visto.isAfter(ultimaCosecha!))) {
          ultimaCosecha = visto;
        }
        final deporte = Deporte.values.firstWhere(
          (d) => d.name == (m['deporte'] ?? '').toString(),
          orElse: () => Deporte.futbol,
        );
        out.add(Cancha(
          id: id,
          nombre: nombre,
          club: nombre,
          distrito: Distrito.sanBorja, // referencial; lo real es lat/lng
          deporte: deporte,
          precioHora: 0, // desconocido hasta que el dueño la reclame
          ubicacion: LatLng(lat, lng),
          clubFundador: false,
          digitalizada: false,
          direccion: (m['direccion'] as String?),
          registrada: false, // cosechada: aún no está en Pichangol
          verificada: false,
        ));
      }
      return out;
    } catch (_) {
      return const [];
    }
  }

  /// Guarda (upsert por place_id) las canchas recién descubiertas en Google.
  /// Solo datos estables — NADA de fotos de Google. Best-effort.
  static Future<void> guardar(List<Cancha> descubiertas) async {
    if (!SupabaseService.disponible || descubiertas.isEmpty) return;
    try {
      final filas = [
        for (final c in descubiertas)
          {
            'id': c.id,
            'nombre': c.nombre,
            'direccion': c.direccion,
            'lat': c.ubicacion.latitude,
            'lng': c.ubicacion.longitude,
            'deporte': c.deporte.name,
            'visto_en': DateTime.now().toUtc().toIso8601String(),
          }
      ];
      await SupabaseService.client.from(_tabla).upsert(filas);
    } catch (_) {}
  }
}
