import 'package:flutter/material.dart';

import '../theme.dart';

/// Animación de carga de UBICACIÓN: un pin verde que "late" con ondas expansivas
/// (como buscando en el mapa) + un texto. Reutilizable para "detectando tu
/// ubicación" y "buscando canchas cerca".
class PinCargando extends StatefulWidget {
  const PinCargando({super.key, this.texto = 'Detectando tu ubicación…', this.size = 84});
  final String texto;
  final double size;

  @override
  State<PinCargando> createState() => _PinCargandoState();
}

class _PinCargandoState extends State<PinCargando>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1600))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.size;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: s,
          height: s,
          child: AnimatedBuilder(
            animation: _c,
            builder: (context, _) {
              return Stack(
                alignment: Alignment.center,
                children: [
                  // Dos ondas desfasadas.
                  _onda((_c.value) % 1.0, s),
                  _onda((_c.value + 0.5) % 1.0, s),
                  // Pin que late suave.
                  Transform.scale(
                    scale: 0.92 + 0.08 *
                        (0.5 - (0.5 - (_c.value % 1.0)).abs()) * 2,
                    child: Icon(Icons.location_on, color: verdeCancha, size: s * 0.5),
                  ),
                ],
              );
            },
          ),
        ),
        const SizedBox(height: 12),
        Text(widget.texto,
            style: const TextStyle(
                color: textoTenue, fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _onda(double t, double s) {
    // t va 0→1: crece y se desvanece.
    final size = s * (0.35 + 0.65 * t);
    final opacity = (1 - t) * 0.35;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: verdeCancha.withOpacity(opacity.clamp(0, 1)),
      ),
    );
  }
}
