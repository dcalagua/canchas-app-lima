import 'package:flutter/material.dart';

/// Líneas de cancha dibujadas sobre el gradiente de deporte (sin fotos reales).
/// Estilo minimalista premium del rediseño: marco + línea central + círculo.
class CourtLines extends StatelessWidget {
  const CourtLines({super.key, this.opacity = 0.55, this.strokeWidth = 2});

  final double opacity;
  final double strokeWidth;

  @override
  Widget build(BuildContext context) {
    return SizedBox.expand(
      child: CustomPaint(
        painter: _CourtLinesPainter(opacity: opacity, strokeWidth: strokeWidth),
      ),
    );
  }
}

class _CourtLinesPainter extends CustomPainter {
  _CourtLinesPainter({required this.opacity, required this.strokeWidth});

  final double opacity;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..color = Colors.white.withOpacity(opacity);

    final inset = size.shortestSide * 0.12;
    final rect = Rect.fromLTRB(
        inset, inset, size.width - inset, size.height - inset);
    // Marco de la cancha.
    canvas.drawRRect(
        RRect.fromRectAndRadius(rect, const Radius.circular(6)), p);
    // Línea central.
    canvas.drawLine(
      Offset(size.width / 2, inset),
      Offset(size.width / 2, size.height - inset),
      p,
    );
    // Círculo central.
    canvas.drawCircle(
        Offset(size.width / 2, size.height / 2), size.shortestSide * 0.14, p);
  }

  @override
  bool shouldRepaint(covariant _CourtLinesPainter old) =>
      old.opacity != opacity || old.strokeWidth != strokeWidth;
}
