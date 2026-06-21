import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Ubicación del usuario (GPS) para mostrar canchas cercanas.
class LocationService {
  /// Última posición conocida (caché del sistema). Es **instantánea**: la usamos
  /// para centrar los cards de inmediato mientras llega el fix preciso. Puede ser
  /// null en el primer arranque (aún sin ninguna lectura).
  static Future<LatLng?> ultimaConocida() async {
    try {
      final pos = await Geolocator.getLastKnownPosition();
      return pos == null ? null : LatLng(pos.latitude, pos.longitude);
    } catch (_) {
      return null;
    }
  }

  /// Posición actual con precisión **media** (más rápida que `high`, suficiente
  /// para "canchas cerca") y un límite de tiempo para no colgar la UI. Si falla o
  /// expira, cae a la última conocida.
  static Future<LatLng?> ubicacionActual() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return ultimaConocida();
      var permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied) {
        permiso = await Geolocator.requestPermission();
      }
      if (permiso == LocationPermission.denied ||
          permiso == LocationPermission.deniedForever) {
        return null;
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 8),
        ),
      );
      return LatLng(pos.latitude, pos.longitude);
    } catch (_) {
      // Timeout o error del fix preciso: usa lo último conocido para no esperar.
      return ultimaConocida();
    }
  }
}
