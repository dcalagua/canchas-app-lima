import 'dart:math';

import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Distancia en kilómetros entre dos puntos (fórmula de Haversine).
double distanciaKm(LatLng a, LatLng b) {
  const radioTierra = 6371.0; // km
  final dLat = _rad(b.latitude - a.latitude);
  final dLon = _rad(b.longitude - a.longitude);
  final lat1 = _rad(a.latitude);
  final lat2 = _rad(b.latitude);
  final h = sin(dLat / 2) * sin(dLat / 2) +
      cos(lat1) * cos(lat2) * sin(dLon / 2) * sin(dLon / 2);
  return 2 * radioTierra * asin(min(1.0, sqrt(h)));
}

double _rad(double grados) => grados * pi / 180.0;
