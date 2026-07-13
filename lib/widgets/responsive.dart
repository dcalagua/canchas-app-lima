import 'package:flutter/material.dart';

/// Ancho (dp) a partir del cual la app se comporta como tablet/escritorio:
/// navegación lateral, master-detail, grillas y contenido centrado.
const double kAnchoTablet = 720;

/// ¿La pantalla es ancha (tablet u horizontal)?
bool esTablet(BuildContext context) =>
    MediaQuery.of(context).size.width >= kAnchoTablet;

/// Centra y limita el ancho del contenido en pantallas anchas para que no se
/// estire feo (formularios, fichas, listas de una columna). En móvil vertical
/// no cambia nada.
class AnchoTablet extends StatelessWidget {
  const AnchoTablet({super.key, required this.child, this.maxWidth = 760});
  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    if (!esTablet(context)) return child;
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}

/// Número de columnas recomendado para una grilla de tarjetas según el ancho
/// disponible: 1 (móvil), 2 (tablet) o 3 (pantallas muy anchas).
int columnasTablet(double anchoDisponible) {
  if (anchoDisponible < kAnchoTablet) return 1;
  if (anchoDisponible >= 1100) return 3;
  return 2;
}
