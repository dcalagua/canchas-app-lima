import 'package:flutter/material.dart';

/// Marcas de medios de pago dibujadas con widgets (sin imágenes externas):
/// evita depender de assets/red y respeta los colores de cada marca.

const _yapeMorado = Color(0xFF742284);

/// Badge de Yape: cuadrado morado con el wordmark. Aproximación de marca para
/// el selector de método de pago (no es el logo oficial vectorial).
class YapeBadge extends StatelessWidget {
  const YapeBadge({super.key, this.alto = 30});
  final double alto;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: alto,
      padding: EdgeInsets.symmetric(horizontal: alto * 0.34),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: _yapeMorado,
        borderRadius: BorderRadius.circular(alto * 0.28),
      ),
      child: Text(
        'Yape',
        style: TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w800,
          fontSize: alto * 0.5,
          letterSpacing: -0.3,
        ),
      ),
    );
  }
}

/// Marca de Mastercard: dos círculos superpuestos (rojo + naranja).
class MastercardMark extends StatelessWidget {
  const MastercardMark({super.key, this.alto = 24});
  final double alto;

  @override
  Widget build(BuildContext context) {
    final d = alto;
    return SizedBox(
      width: d * 1.62,
      height: d,
      child: Stack(
        children: [
          Positioned(
            left: 0,
            child: Container(
              width: d,
              height: d,
              decoration: const BoxDecoration(
                  color: Color(0xFFEB001B), shape: BoxShape.circle),
            ),
          ),
          Positioned(
            right: 0,
            child: Container(
              width: d,
              height: d,
              decoration: BoxDecoration(
                color: const Color(0xFFF79E1B).withOpacity(0.92),
                shape: BoxShape.circle,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Marca de Visa: wordmark "VISA" en azul.
class VisaMark extends StatelessWidget {
  const VisaMark({super.key, this.alto = 20});
  final double alto;

  @override
  Widget build(BuildContext context) {
    return Text(
      'VISA',
      style: TextStyle(
        color: const Color(0xFF1A1F71),
        fontWeight: FontWeight.w900,
        fontStyle: FontStyle.italic,
        fontSize: alto,
        letterSpacing: 0.5,
      ),
    );
  }
}

/// Fila Visa + Mastercard para el método "Tarjeta".
class MarcasTarjeta extends StatelessWidget {
  const MarcasTarjeta({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: const [
        VisaMark(alto: 16),
        SizedBox(width: 8),
        MastercardMark(alto: 22),
      ],
    );
  }
}
