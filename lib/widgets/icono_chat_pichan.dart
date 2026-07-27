import 'package:flutter/material.dart';

/// Ícono propio de la mensajería Pichangol ("Pichan"): una burbuja de chat con
/// degradado verde de marca (lima → teal, el mismo del header) y la "P" de Pichan
/// en blanco. Se lee como "chat", es identidad propia (NO el logo de WhatsApp) y
/// va "con vida" (regla de UI Airbnb): no se apaga a gris; solo baja un poco de
/// opacidad cuando la pestaña no está seleccionada. Dibujado con CustomPainter →
/// nítido a cualquier tamaño, sin asset externo.
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan({super.key, this.size = 24, this.activo = true});
  final double size;

  /// Si false (pestaña no seleccionada), se muestra con un poco menos de opacidad.
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: activo ? 1 : 0.72,
      child: SizedBox(
        width: size,
        height: size,
        child: const CustomPaint(painter: _PichanPainter()),
      ),
    );
  }
}

class _PichanPainter extends CustomPainter {
  const _PichanPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width;
    final paint = Paint()
      ..isAntiAlias = true
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF128C7E), Color(0xFF008489)], // lima → teal (marca)
      ).createShader(Offset.zero & size);

    // Cuerpo de la burbuja (cuadrado muy redondeado, estilo WhatsApp).
    final m = s * 0.06;
    final body = RRect.fromRectAndRadius(
      Rect.fromLTRB(m, m, s - m, s * 0.80),
      Radius.circular(s * 0.26),
    );
    canvas.drawRRect(body, paint);

    // Colita de la burbuja (abajo a la izquierda).
    final tail = Path()
      ..moveTo(s * 0.24, s * 0.70)
      ..lineTo(s * 0.20, s * 0.95)
      ..lineTo(s * 0.44, s * 0.76)
      ..close();
    canvas.drawPath(tail, paint);

    // La "P" de Pichan, calada en blanco, centrada en el cuerpo (arriba de la cola).
    final tp = TextPainter(
      text: TextSpan(
        text: 'P',
        style: TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w900,
          fontSize: s * 0.52,
          height: 1,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(
        canvas, Offset(s / 2 - tp.width / 2, s * 0.40 - tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant _PichanPainter oldDelegate) => false;
}
