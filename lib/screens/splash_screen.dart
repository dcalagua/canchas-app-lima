import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../widgets/logo_vivo.dart';
import 'app_shell.dart';
import 'onboarding_screen.dart';

const _indigo = Color(0xFFFFFFFF); // fondo del splash (blanco, look Airbnb)

// Paleta del LOGO nuevo (muestreada de docs/marca/logo_original.jpg) — SOLO
// para el splash/preload; la paleta interna del app no cambia (opción A).
const _navyLogo = Color(0xFF0A1F3C); // azul marino del wordmark/pelota

/// Splash de marca: el LOGO "en vivo" (pin quieto, la pelota de adentro
/// cambiando de deporte como un gif) + eslogan + "Cargando…". Gancho visual
/// de ~1.8s la primera vez; corto en arranques siguientes.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _arrancar();
  }

  Future<void> _arrancar() async {
    await appState.cargarSesion();
    appState.sincronizarSaldo(); // saldo real del backend (sobrevive reinstalar)
    appState.sincronizarPro(); // membresía Pichangol Pro del jugador
    appState.cargarPuntosCanjeados(); // canjes de puntos (disponibles reales)
    appState.cargarPuntosBodega(); // puntos de bodega (pagados con saldo)
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
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _indigo,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // LOGO "EN VIVO" (widget compartido con el loader de marca): el
            // pin quieto y la pelota de adentro cambiando de deporte.
            const LogoPichangolVivo(ancho: 250),
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
