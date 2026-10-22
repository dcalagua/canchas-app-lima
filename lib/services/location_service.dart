import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Por qué no hay GPS para el reclamo (para decirle al dueño qué hacer).
enum EstadoGpsReclamo { ok, servicioApagado, sinPermiso, permisoBloqueado, sinSenal }

/// Lectura del GPS para reclamar una cancha: el punto (si hay) y el estado.
class LecturaGpsReclamo {
  final EstadoGpsReclamo estado;
  final LatLng? punto;
  const LecturaGpsReclamo(this.estado, [this.punto]);
}

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

  /// Posición actual con precisión **alta** para el anti-fraude del reclamo
  /// ("¿estás en la cancha?"). Aquí sí importa el fix fino (radio ~150 m), así
  /// que pedimos `high` con un timeout mayor. Si falla, cae a la última conocida.
  static Future<LatLng?> ubicacionPrecisa() async {
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
        desiredAccuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 10),
      );
      return LatLng(pos.latitude, pos.longitude);
    } catch (_) {
      return ultimaConocida();
    }
  }

  /// GPS para RECLAMAR una cancha ("¿estás en el local?"). A diferencia de
  /// [ubicacionPrecisa], dice POR QUÉ falta (servicio apagado, permiso…) y
  /// solo acepta la última posición conocida si es reciente (≤ 2 min): una
  /// posición vieja de otro lugar no prueba que el dueño esté en el local.
  static Future<LecturaGpsReclamo> leerParaReclamo() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return const LecturaGpsReclamo(EstadoGpsReclamo.servicioApagado);
      }
      var permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied) {
        permiso = await Geolocator.requestPermission();
      }
      if (permiso == LocationPermission.deniedForever) {
        return const LecturaGpsReclamo(EstadoGpsReclamo.permisoBloqueado);
      }
      if (permiso == LocationPermission.denied) {
        return const LecturaGpsReclamo(EstadoGpsReclamo.sinPermiso);
      }
      try {
        final pos = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high,
          timeLimit: const Duration(seconds: 12),
        );
        return LecturaGpsReclamo(
            EstadoGpsReclamo.ok, LatLng(pos.latitude, pos.longitude));
      } catch (_) {
        final ult = await Geolocator.getLastKnownPosition();
        if (ult != null &&
            DateTime.now().difference(ult.timestamp).inMinutes.abs() <= 2) {
          return LecturaGpsReclamo(
              EstadoGpsReclamo.ok, LatLng(ult.latitude, ult.longitude));
        }
        return const LecturaGpsReclamo(EstadoGpsReclamo.sinSenal);
      }
    } catch (_) {
      return const LecturaGpsReclamo(EstadoGpsReclamo.sinSenal);
    }
  }

  /// Abre los ajustes de ubicación del sistema (servicio apagado).
  static Future<void> abrirAjustesUbicacion() async {
    try {
      await Geolocator.openLocationSettings();
    } catch (_) {}
  }

  /// Abre los ajustes de la app (permiso negado para siempre).
  static Future<void> abrirAjustesApp() async {
    try {
      await Geolocator.openAppSettings();
    } catch (_) {}
  }
}
