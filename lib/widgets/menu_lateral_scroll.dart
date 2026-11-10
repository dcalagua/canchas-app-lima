import 'package:flutter/material.dart';

/// Hace SCROLLEABLE un [NavigationRail] cuando sus ítems no caben a lo alto
/// (pantallas bajas / muchos ítems). Patrón oficial de Flutter: el rail necesita
/// una altura acotada, así que dentro del scroll lo forzamos a ocupar al menos el
/// alto visible y a crecer si hace falta (IntrinsicHeight), permitiendo el scroll.
class MenuLateralScroll extends StatelessWidget {
  const MenuLateralScroll({super.key, required this.rail});

  /// El NavigationRail a envolver.
  final Widget rail;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: IntrinsicHeight(child: rail),
        ),
      ),
    );
  }
}
