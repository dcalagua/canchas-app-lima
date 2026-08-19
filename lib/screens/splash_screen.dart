import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../widgets/marca.dart';
import 'app_shell.dart';
import 'onboarding_screen.dart';

const _indigo = Color(0xFFFFFFFF); // fondo del splash (blanco, look Airbnb)

// Paleta del LOGO nuevo (muestreada de docs/marca/logo_original.jpg) — SOLO
// para el splash/preload; la paleta interna del app no cambia (opción A).
const _navyLogo = Color(0xFF0A1F3C); // azul marino del wordmark/pelota

/// Splash de marca ENERGÉTICO (identidad Cancha nocturna): fondo índigo + una
/// pelota LIMA que va cambiando de deporte (fútbol, tenis, básquet, vóley…) con
/// rebote, la marca Pichangol y un "Cargando…". Gancho visual de ~1.8s.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  // PRELOAD = el LOGO "en vivo" (decisión del director): el pin del logo queda
  // quieto y la PELOTA DE ADENTRO va cambiando de deporte (fútbol → tenis →
  // básquet → vóley…), como un gif. La pelota animada se pinta ENCIMA de la
  // pelota impresa del asset, en su posición exacta (medida del PNG).
  static const _deportes = <IconData>[
    Icons.sports_soccer,
    Icons.sports_tennis,
    Icons.sports_basketball,
    Icons.sports_volleyball,
    Icons.sports_baseball,
  ];
  // Posición de la pelota dentro de assets/brand/logo_pichangol.png (640×640):
  // centro en (49.9%, 33.0%) y radio ≈10.5% del ancho. Medido del asset real.
  static const double _pelotaFx = 0.4994;
  static const double _pelotaFy = 0.3300;
  static const double _pelotaFd = 0.225; // diámetro (fracción del ancho), cubre la impresa
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
    appState.sincronizarSaldo(); // saldo real del backend (sobrevive reinstalar)
    appState.sincronizarPro(); // membresía Pichangol Pro del jugador
    appState.cargarPuntosCanjeados(); // canjes de puntos (disponibles reales)
    appState.cargarRetosResultados(); // retos jugados → ranking global
    appState.cargarRetosPendientes(); // retos por responder/reportar → badge
    appState.cargarMiembrosPro(); // insignia PRO en el ranking
    appState.cargarMiPerfilCircuito(); // ¿ya me uní al circuito?
    appState.cargarDestacados(); // dueños destacados (saldo>0) para resaltar canchas
    appState.cargarCanchasRemotas() // canchas compartidas (best-effort)
        .then((_) => appState.sincronizarPropiedades()); // ¿el admin ya aprobó?
    appState.cargarDescuentosSlot(); // hora feliz por-slot (precio real al reservar)
    appState
        .cargarReservasRemotas() // reservas compartidas (best-effort)
        .then((_) => appState.generarReservasFijas()); // pensionados de la semana
    appState
        .cargarAcademiasRemotas() // academias (sobreviven reinstalación)
        .then((_) => appState.cargarMatriculasRemotas()) // alumnos-app vinculados
        .then((_) => appState.cargarInvitacionesRemotas()) // invitaciones por correo
        .then((_) => appState.cargarCampeonatosRemotos()); // torneos de academias
    appState.enriquecerSembradas(); // fotos reales de los clubes sembrados
    bool onboardingVisto = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      onboardingVisto = prefs.getBool(kPrefOnboardingVisto) ?? false;
    } catch (_) {}

    // Gancho visual COMPLETO (1.8s) solo la 1ª vez (antes del onboarding). En los
    // arranques siguientes —incluye cuando Android mató la app en segundo plano y
    // vuelves— el splash va CORTO para que volver sea casi instantáneo.
    await Future.delayed(
        Duration(milliseconds: onboardingVisto ? 450 : 1800));
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
      backgroundColor: _indigo,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // LOGO "EN VIVO" (el gif del director): el asset del logo quieto y,
            // ENCIMA de su pelota impresa, la pelota animada que cambia de
            // deporte con un pulso suave. Fallback al wordmark clásico si el
            // asset faltara.
            Builder(builder: (context) {
              const double lado = 250; // el PNG es cuadrado (640×640)
              const double d = lado * _pelotaFd;
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
                          child: PichangolWordmark(fontSize: 40),
                        ),
                      ),
                    ),
                    // Pelota animada, centrada EXACTO sobre la del logo.
                    Positioned(
                      left: lado * _pelotaFx - d / 2,
                      top: lado * _pelotaFy - d / 2,
                      width: d,
                      height: d,
                      child: AnimatedBuilder(
                        animation: _rebote,
                        builder: (context, child) {
                          // Pulso suave (late 1.00→1.07): la pelota "respira".
                          final s = 1 +
                              0.07 * Curves.easeInOut.transform(_rebote.value);
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
                              transitionBuilder: (child, anim) =>
                                  RotationTransition(
                                turns: Tween(begin: 0.85, end: 1.0)
                                    .animate(anim),
                                child: ScaleTransition(
                                  scale: anim,
                                  child: FadeTransition(
                                      opacity: anim, child: child),
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
            }),
            const SizedBox(height: 6),
            Text(
              kBrandTagline,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: _navyLogo,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 18),
            Text('Cargando…',
                style: TextStyle(
                    color: _navyLogo.withOpacity(0.6),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
