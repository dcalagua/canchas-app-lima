import 'dart:async';

import 'package:flutter/material.dart';

import '../services/marca_remota.dart';
import 'marca.dart';

const _navyLogo = Color(0xFF0A1F3C); // azul marino de la pelota del logo

/// El LOGO "EN VIVO" de la marca (CanchaLibre) (regla del director para todo preload): el
/// pin del logo quieto y la PELOTA DE ADENTRO cambiando de deporte (fútbol →
/// tenis → básquet → vóley → béisbol) como un gif, con giro+fade al cambiar y
/// un pulso suave continuo. La pelota animada se pinta ENCIMA de la pelota
/// impresa del asset, en su posición exacta (medida del PNG real). Lo usan el
/// splash inicial y el loader de marca [CargandoPichangol].
class LogoPichangolVivo extends StatefulWidget {
  const LogoPichangolVivo({super.key, this.ancho = 250});

  /// Lado del logo (el asset es cuadrado, 640×640).
  final double ancho;

  @override
  State<LogoPichangolVivo> createState() => _LogoPichangolVivoState();
}

class _LogoPichangolVivoState extends State<LogoPichangolVivo>
    with SingleTickerProviderStateMixin {
  static const _deportes = <IconData>[
    Icons.sports_soccer,
    Icons.sports_tennis,
    Icons.sports_basketball,
    Icons.sports_volleyball,
    Icons.sports_baseball,
  ];
  int _i = 0;
  Timer? _ciclo;
  late final AnimationController _pulso = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 560))
    ..repeat(reverse: true);

  @override
  void initState() {
    super.initState();
    _ciclo = Timer.periodic(const Duration(milliseconds: 520), (_) {
      if (mounted) setState(() => _i = (_i + 1) % _deportes.length);
    });
  }

  @override
  void dispose() {
    _ciclo?.cancel();
    _pulso.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lado = widget.ancho;
    if (MarcaRemota.logoUrl.value.isNotEmpty) {
      // Logo propio de la torre: el mismo pulso suave, sin la pelota animada
      // (su posición se midió sobre el logo de siempre).
      return SizedBox(
        width: lado,
        height: lado,
        child: AnimatedBuilder(
          animation: _pulso,
          builder: (context, child) => Transform.scale(
              scale: 1 + 0.05 * Curves.easeInOut.transform(_pulso.value),
              child: child),
          child: LogoMarcaImagen(
              asset: 'assets/brand/logo_pichangol.png',
              width: lado * 0.8,
              height: lado * 0.8),
        ),
      );
    }
    // Sin logo de la torre: marca DIBUJADA (rebrand CanchaLibre, oct-2026).
    // El PNG anterior traía el texto "Pichangol"; ahora la pelota que cambia
    // de deporte va sobre el círculo de la marca y debajo el nombre vigente
    // (`kBrandName`), así un cambio de marca no exige assets nuevos.
    final bola = lado * 0.46;
    return SizedBox(
      width: lado,
      height: lado,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AnimatedBuilder(
            animation: _pulso,
            builder: (context, child) {
              final s = 1 + 0.07 * Curves.easeInOut.transform(_pulso.value);
              return Transform.scale(scale: s, child: child);
            },
            child: Container(
              width: bola,
              height: bola,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF0B7A57), Color(0xFF08654A)],
                ),
              ),
              child: Center(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 280),
                  transitionBuilder: (child, anim) => RotationTransition(
                    turns: Tween(begin: 0.85, end: 1.0).animate(anim),
                    child: ScaleTransition(
                      scale: anim,
                      child: FadeTransition(opacity: anim, child: child),
                    ),
                  ),
                  child: Icon(
                    _deportes[_i],
                    key: ValueKey(_i),
                    color: Colors.white,
                    size: bola * 0.56,
                  ),
                ),
              ),
            ),
          ),
          SizedBox(height: lado * 0.07),
          PichangolWordmark(fontSize: lado * 0.13),
        ],
      ),
    );
  }
}
