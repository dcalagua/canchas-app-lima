import 'dart:typed_data';

import 'package:image/image.dart' as img;

import '../models/models.dart';

/// Resultado de la detección de deporte por imagen.
class DeteccionDeporte {
  final Deporte deporte;
  final double confianza; // 0..1
  const DeteccionDeporte(this.deporte, this.confianza);
}

/// Detector del deporte de una cancha a partir de una foto.
///
/// Implementación actual: HEURÍSTICA DE VISIÓN por color dominante (corre 100%
/// en el dispositivo, sin red ni API). Es un placeholder honesto de IA:
///  • mucho verde → fútbol (grass sintético)
///  • mucho azul  → pádel (canchas azules)
///  • mucho naranja/arcilla → tenis
///
/// Para producción se reemplaza por un modelo real (ML Kit on-device, o un
/// modelo de visión en la nube tipo Gemini/Claude). La interfaz no cambia.
class SportDetector {
  static Future<DeteccionDeporte> detectar(Uint8List bytes) async {
    try {
      final original = img.decodeImage(bytes);
      if (original == null) return const DeteccionDeporte(Deporte.futbol, 0.5);
      final im = img.copyResize(original, width: 64);

      int verde = 0, azul = 0, naranja = 0, total = 0;
      for (var y = 0; y < im.height; y++) {
        for (var x = 0; x < im.width; x++) {
          final p = im.getPixel(x, y);
          final r = p.r.toDouble(), g = p.g.toDouble(), b = p.b.toDouble();
          total++;
          if (g > r * 1.1 && g > b * 1.1) {
            verde++;
          } else if (b > r * 1.05 && b > g * 1.05) {
            azul++;
          } else if (r > g && r > b && (r - b) > 35) {
            naranja++;
          }
        }
      }
      if (total == 0) return const DeteccionDeporte(Deporte.futbol, 0.5);

      final fVerde = verde / total;
      final fAzul = azul / total;
      final fNaranja = naranja / total;

      final maxF = [fVerde, fAzul, fNaranja].reduce((a, b) => a > b ? a : b);
      Deporte dep;
      if (maxF == fAzul && fAzul > 0.18) {
        dep = Deporte.padel;
      } else if (maxF == fNaranja && fNaranja > 0.18) {
        dep = Deporte.tenis;
      } else {
        dep = Deporte.futbol; // verde dominante o indefinido
      }
      final confianza = (0.55 + maxF * 0.45).clamp(0.55, 0.95);
      return DeteccionDeporte(dep, confianza.toDouble());
    } catch (_) {
      return const DeteccionDeporte(Deporte.futbol, 0.5);
    }
  }
}
