import 'package:flutter/material.dart';

/// Centra y limita el ancho del contenido en pantallas ANCHAS (tablet / modo
/// horizontal) para que no se estire de borde a borde y se lea cómodo. En móvil
/// (o cuando el ancho es menor al máximo) no cambia nada: devuelve el hijo tal
/// cual. Pensado para envolver el `body:` de un Scaffold — el AppBar y el
/// FloatingActionButton no se ven afectados.
class AnchoLectura extends StatelessWidget {
  const AnchoLectura({super.key, required this.child, this.max = 900});

  final Widget child;
  final double max;

  @override
  Widget build(BuildContext context) {
    final ancho = MediaQuery.of(context).size.width;
    if (ancho <= max) return child;
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: max),
        child: child,
      ),
    );
  }
}
