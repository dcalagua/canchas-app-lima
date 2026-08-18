import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/marca.dart';
import 'app_shell.dart';
import 'onboarding_screen.dart';

const _indigo = Color(0xFFFFFFFF); // fondo del splash (blanco, look Airbnb)

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
  // Flotado suave del logo (respiración, no rebote brusco).
  late final AnimationController _rebote = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1400))
    ..repeat(reverse: true);

  @override
  void initState() {
    super.initState();
    _arrancar();
  }

  Future<void> _arrancar() async {
    await appState.cargarSesion();
    appState.sincronizarSaldo(); // saldo real del backend (sobrevive reinstalar)
    appState.sincronizarPro(); // membresía Pichangol Pro del jugador
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
            // LOGO OFICIAL (pin + wordmark) con flotado suave. Fallback al
            // wordmark clásico si el asset faltara.
            AnimatedBuilder(
              animation: _rebote,
              builder: (context, child) {
                final dy = -7 * Curves.easeInOut.transform(_rebote.value);
                return Transform.translate(offset: Offset(0, dy), child: child);
              },
              child: Image.asset(
                'assets/brand/logo_pichangol.png',
                width: 250,
                errorBuilder: (_, __, ___) => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: PichangolWordmark(fontSize: 40),
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              kBrandTagline,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: textoTenue,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 34),
            // Cargando…
            const SizedBox(
              width: 26,
              height: 26,
              child: CircularProgressIndicator(strokeWidth: 3, color: lima),
            ),
            const SizedBox(height: 12),
            Text('Cargando…',
                style: TextStyle(
                    color: textoTenue.withOpacity(0.9),
                    fontWeight: FontWeight.w700,
                    fontSize: 13)),
          ],
        ),
      ),
    );
  }
}
