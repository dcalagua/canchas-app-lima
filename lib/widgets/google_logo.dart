import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Logo "G" oficial de Google (multicolor), dibujado con CustomPaint para no
/// depender de imágenes/red. Rojo arriba, amarillo a la izquierda, verde abajo,
/// azul a la derecha + barra horizontal.
class GoogleLogo extends StatelessWidget {
  const GoogleLogo({super.key, this.size = 20});
  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(painter: _GooglePainter()),
    );
  }
}

class _GooglePainter extends CustomPainter {
  double _d(double deg) => deg * math.pi / 180;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final sw = w * 0.26; // grosor del anillo
    final rect = Rect.fromCircle(center: Offset(w / 2, w / 2), radius: (w - sw) / 2);
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = sw
      ..strokeCap = StrokeCap.butt;

    p.color = const Color(0xFF4285F4); // azul (derecha)
    canvas.drawArc(rect, _d(-14), _d(66), false, p);
    p.color = const Color(0xFF34A853); // verde (abajo)
    canvas.drawArc(rect, _d(52), _d(76), false, p);
    p.color = const Color(0xFFFBBC05); // amarillo (izquierda)
    canvas.drawArc(rect, _d(128), _d(76), false, p);
    p.color = const Color(0xFFEA4335); // rojo (arriba)
    canvas.drawArc(rect, _d(204), _d(80), false, p);

    // Barra horizontal azul (el travesaño de la G).
    p
      ..style = PaintingStyle.fill
      ..color = const Color(0xFF4285F4);
    canvas.drawRect(
        Rect.fromLTRB(w * 0.5, w / 2 - sw / 2, w - sw * 0.35, w / 2 + sw / 2), p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
