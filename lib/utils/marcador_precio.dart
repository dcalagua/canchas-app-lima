import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Pines-pastilla estilo Airbnb para el mapa de canchas, dibujados en canvas:
/// pastilla blanca redondeada con sombra suave y el precio en negrita; la
/// seleccionada se invierte (fondo charcoal, texto blanco). Para lugares SIN
/// precio (descubiertos en Google) se usa una pastilla-punto chiquita, igual
/// que los alojamientos sin precio de Airbnb.
///
/// Los descriptores se cachean por (texto, seleccionado): dibujar es barato
/// pero no hay que repetirlo en cada rebuild del mapa.
class MarcadorPrecio {
  static final Map<String, BitmapDescriptor> _cache = {};

  /// Escala de dibujo (nitidez en pantallas densas).
  static const double _k = 3.0;

  /// [esEmoji]: pastilla cuyo contenido es un emoji (deporte). Seleccionada NO
  /// se invierte a charcoal (el emoji sobre negro se ve sucio): queda blanca,
  /// más grande y con un anillo charcoal — resalta igual que en Airbnb los
  /// pines sin precio.
  static Future<BitmapDescriptor> pastilla(String texto,
      {bool seleccionado = false, bool esEmoji = false}) async {
    final clave = '${seleccionado ? 's' : 'n'}${esEmoji ? 'e' : ''}:$texto';
    final hit = _cache[clave];
    if (hit != null) return hit;
    final desc = texto.isEmpty
        ? await _dibujarPunto(seleccionado)
        : await _dibujarPastilla(texto, seleccionado, esEmoji);
    _cache[clave] = desc;
    return desc;
  }

  static Future<BitmapDescriptor> _dibujarPastilla(
      String texto, bool sel, bool esEmoji) async {
    // Emoji seleccionado: crece un poco (resalta sin invertirse).
    final crecer = esEmoji && sel ? 1.18 : 1.0;
    final tp = TextPainter(
      text: TextSpan(
        text: texto,
        style: TextStyle(
          color: sel && !esEmoji ? Colors.white : const Color(0xFF222222),
          fontSize: 12.5 * _k * crecer,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.2,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final padH = 10.0 * _k * crecer,
        padV = 6.5 * _k * crecer,
        margen = 6.0 * _k;
    final w = tp.width + padH * 2, h = tp.height + padV * 2;
    return _pintar(w, h, margen, sel, esEmoji, (canvas, rrect) {
      tp.paint(canvas, Offset(margen + padH, margen + padV));
    });
  }

  static Future<BitmapDescriptor> _dibujarPunto(bool sel) async {
    final w = 22.0 * _k, h = 14.0 * _k, margen = 5.0 * _k;
    return _pintar(w, h, margen, sel, false, (_, __) {});
  }

  /// Dibuja la pastilla (sombra + fondo + borde) y encima [contenido].
  static Future<BitmapDescriptor> _pintar(
    double w,
    double h,
    double margen,
    bool sel,
    bool esEmoji,
    void Function(Canvas, RRect) contenido,
  ) async {
    final rec = ui.PictureRecorder();
    final canvas = Canvas(rec);
    final rrect = RRect.fromRectAndRadius(
      Rect.fromLTWH(margen, margen, w, h),
      Radius.circular(h / 2),
    );
    // Sombra suave hacia abajo (el margen deja sitio para el blur).
    canvas.drawRRect(
      rrect.shift(Offset(0, 1.6 * _k)),
      Paint()
        ..color = const Color(0x33000000)
        ..maskFilter = ui.MaskFilter.blur(ui.BlurStyle.normal, 2.2 * _k),
    );
    // Fondo: SOLO la pastilla de precio se invierte a charcoal al seleccionar.
    final invertida = sel && !esEmoji;
    canvas.drawRRect(
        rrect,
        Paint()
          ..color = invertida ? const Color(0xFF222222) : Colors.white
          ..isAntiAlias = true);
    // Borde: anillo charcoal para el emoji seleccionado; gris sutil si no.
    final anillo = sel && esEmoji;
    canvas.drawRRect(
        rrect,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = (anillo ? 2.2 : 1.0) * _k
          ..color =
              anillo ? const Color(0xFF222222) : const Color(0x14000000));
    contenido(canvas, rrect);
    final img = await rec
        .endRecording()
        .toImage((w + margen * 2).ceil(), (h + margen * 2).ceil());
    final bytes = await img.toByteData(format: ui.ImageByteFormat.png);
    return BitmapDescriptor.fromBytes(bytes!.buffer.asUint8List());
  }
}
