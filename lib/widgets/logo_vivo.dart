import 'dart:async';

import 'package:flutter/material.dart';

import 'marca.dart';

const _navyLogo = Color(0xFF0A1F3C); // azul marino de la pelota del logo

/// El LOGO "EN VIVO" de Pichangol (regla del director para todo preload): el
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
  // Posición de la pelota dentro de assets/brand/logo_pichangol.png (640×640):
  // centro en (49.9%, 33.0%) y radio ≈10.5% del ancho. Medido del asset real.
  static const double _fx = 0.4994;
  static const double _fy = 0.3300;
  static const double _fd = 0.225; // diámetro (fracción del ancho): cubre la impresa

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
    final d = lado * _fd;
    return SizedBox(
      width: lado,
      height: lado,
      child: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              'assets/brand/logo_pichangol.png',
              fit: BoxFit.contain,
              errorBuilder: (_, __, ___) => const Center(
                child: PichangolWordmark(fontSize: 32),
              ),
            ),
          ),
          // Pelota animada, centrada EXACTO sobre la pelota impresa del logo.
          Positioned(
            left: lado * _fx - d / 2,
            top: lado * _fy - d / 2,
            width: d,
            height: d,
            child: AnimatedBuilder(
              animation: _pulso,
              builder: (context, child) {
                // Pulso suave (1.00→1.07): la pelota "respira".
                final s = 1 + 0.07 * Curves.easeInOut.transform(_pulso.value);
                return Transform.scale(scale: s, child: child);
              },
              child: Container(
                decoration: const BoxDecoration(
                  color: _navyLogo, // mismo navy de la pelota impresa
                  shape: BoxShape.circle,
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
                      size: d * 0.72,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
