import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'app_shell.dart';
import 'onboarding_screen.dart';

const _amarillo = Color(0xFFFFC400); // amarillo fuerte (energía)

/// Splash de marca ENERGÉTICO: fondo amarillo fuerte + una pelota que va
/// cambiando de deporte (fútbol, tenis, básquet, vóley…) con rebote, la marca
/// Pichangol y un "Cargando…". Gancho visual de ~1.8s antes del mapa.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  // Deportes que van rotando en la pelota central (íconos Material).
  static const _deportes = <IconData>[
    Icons.sports_soccer,
    Icons.sports_tennis,
    Icons.sports_basketball,
    Icons.sports_volleyball,
    Icons.sports_baseball,
  ];
  int _i = 0;
  Timer? _ciclo;
  late final AnimationController _rebote = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 560))
    ..repeat(reverse: true);

  @override
  void initState() {
    super.initState();
    _ciclo = Timer.periodic(const Duration(milliseconds: 520), (_) {
      if (mounted) setState(() => _i = (_i + 1) % _deportes.length);
    });
    _arrancar();
  }

  Future<void> _arrancar() async {
    await appState.cargarSesion();
    appState.cargarCanchasRemotas() // canchas compartidas (best-effort)
        .then((_) => appState.sincronizarPropiedades()); // ¿el admin ya aprobó?
    appState.cargarReservasRemotas(); // reservas compartidas (best-effort)
    appState.cargarAcademiasRemotas(); // academias (sobreviven reinstalación)
    appState.enriquecerSembradas(); // fotos reales de los clubes sembrados
    bool onboardingVisto = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      onboardingVisto = prefs.getBool(kPrefOnboardingVisto) ?? false;
    } catch (_) {}

    await Future.delayed(const Duration(milliseconds: 1800));
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 500),
        pageBuilder: (_, __, ___) =>
            onboardingVisto ? const AppShell() : const OnboardingScreen(),
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
      ),
    );
  }

  @override
  void dispose() {
    _ciclo?.cancel();
    _rebote.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _amarillo,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Pelota que rebota y cambia de deporte.
            AnimatedBuilder(
              animation: _rebote,
              builder: (context, child) {
                final dy = -12 * Curves.easeInOut.transform(_rebote.value);
                return Transform.translate(offset: Offset(0, dy), child: child);
              },
              child: Container(
                width: 118,
                height: 118,
                decoration: const BoxDecoration(
                  color: bosque,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                        color: Color(0x33000000),
                        blurRadius: 18,
                        offset: Offset(0, 10)),
                  ],
                ),
                child: Center(
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 280),
                    transitionBuilder: (child, anim) => ScaleTransition(
                      scale: anim,
                      child: FadeTransition(opacity: anim, child: child),
                    ),
                    child: Icon(
                      _deportes[_i],
                      key: ValueKey(_i),
                      color: _amarillo,
                      size: 58,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text(
              kBrandName,
              style: const TextStyle(
                color: bosque,
                fontSize: 42,
                fontWeight: FontWeight.w900,
                letterSpacing: -0.5,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              kBrandTagline,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: bosque.withOpacity(0.75),
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 34),
            // Cargando…
            const SizedBox(
              width: 26,
              height: 26,
              child: CircularProgressIndicator(strokeWidth: 3, color: bosque),
            ),
            const SizedBox(height: 12),
            Text('Cargando…',
                style: TextStyle(
                    color: bosque.withOpacity(0.7),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
