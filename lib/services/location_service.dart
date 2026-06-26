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

  /// Posición actual con precisión **baja** (suficiente para "canchas cerca" en
  /// un radio de varios km, y bastante más rápida que `medium`/`high`) y un
  /// límite de tiempo corto para no colgar la UI. Si falla o expira, cae a la
  /// última conocida.
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
        // 'low' (~500 m) basta para ordenar canchas cercanas y llega mucho
        // antes que un fix preciso; el GPS fino no aporta a este caso de uso.
        desiredAccuracy: LocationAccuracy.low,
        timeLimit: const Duration(seconds: 5),
      );
      return LatLng(pos.latitude, pos.longitude);
    } catch (_) {
      // Timeout o error del fix: usa lo último conocido para no hacer esperar.
      return ultimaConocida();
    }
  }
}
