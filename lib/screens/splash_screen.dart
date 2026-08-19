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
const _verdeLogo = Color(0xFF0B8E40); // verde del pin
const _verdeClaroLogo = Color(0xFF70B32F); // verde claro del degradado
const _naranjaLogo = Color(0xFFF58000); // naranja del swoosh
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
  // PRELOAD "pelotas": la pelota que rebota cambiando de deporte es el loader
  // (decisión del director), pintada con la PALETA DEL LOGO para congruencia
  // con el logotipo y el splash nativo.
  static const _deportes = <IconData>[
    Icons.sports_soccer,
    Icons.sports_tennis,
    Icons.sports_basketball,
    Icons.sports_volleyball,
    Icons.sports_baseball,
  ];
  // Color de la burbuja por deporte: rota entre los colores del logo.
  static const _coloresPelota = <Color>[
    _verdeLogo,
    _naranjaLogo,
    _navyLogo,
    _verdeClaroLogo,
    _verdeLogo,
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
            // LOGO OFICIAL (pin + wordmark), estático y protagonista. Fallback
            // al wordmark clásico si el asset faltara.
            Image.asset(
              'assets/brand/logo_pichangol.png',
              width: 250,
              errorBuilder: (_, __, ___) => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: PichangolWordmark(fontSize: 40),
              ),
            ),
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
            const SizedBox(height: 30),
            // PRELOAD "pelotas" (el loader de marca): la pelota rebota y va
            // cambiando de deporte, con la burbuja rotando por los COLORES DEL
            // LOGO (verde pin → naranja swoosh → navy → verde claro).
            AnimatedBuilder(
              animation: _rebote,
              builder: (context, child) {
                final dy = -10 * Curves.easeInOut.transform(_rebote.value);
                return Transform.translate(offset: Offset(0, dy), child: child);
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: _coloresPelota[_i],
                  shape: BoxShape.circle,
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x33000000),
                        blurRadius: 14,
                        offset: Offset(0, 7)),
                  ],
                ),
                child: Center(
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 260),
                    transitionBuilder: (child, anim) => ScaleTransition(
                      scale: anim,
                      child: FadeTransition(opacity: anim, child: child),
                    ),
                    child: Icon(
                      _deportes[_i],
                      key: ValueKey(_i),
                      color: Colors.white,
                      size: 34,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),
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
