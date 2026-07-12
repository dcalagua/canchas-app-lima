import 'package:flutter/material.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'academias_screen.dart';
import 'ajustes_screen.dart';
import 'anfitrion_screen.dart';
import 'login_google_sheet.dart';
import 'metodos_pago_screen.dart';

/// Pestaña PERFIL del jugador: sesión (login/logout), lo del jugador (academias,
/// métodos de pago) y el acceso a **Modo anfitrión** (todo lo del anfitrión va
/// ahí, estilo Airbnb).
class PerfilScreen extends StatelessWidget {
  const PerfilScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final u = appState.usuario;
          return ListView(
            padding: EdgeInsets.zero,
            children: [
              // Header sage con la ficha del usuario.
              Container(
                width: double.infinity,
                padding: EdgeInsets.fromLTRB(
                    22, 20 + MediaQuery.of(context).padding.top, 22, 22),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [sage, verde, bosque],
                  ),
                  borderRadius:
                      BorderRadius.vertical(bottom: Radius.circular(24)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Perfil',
                        style: t.headlineSmall?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 28,
                          backgroundColor: Colors.white24,
                          backgroundImage: u?.fotoUrl != null
                              ? NetworkImage(u!.fotoUrl!)
                              : null,
                          child: u?.fotoUrl == null
                              ? const Icon(Icons.person, color: Colors.white)
                              : null,
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(u?.nombre ?? 'Invitado',
                                  style: t.titleMedium?.copyWith(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w700)),
                              Text(u?.email ?? 'Inicia sesión para reservar',
                                  style: t.bodySmall
                                      ?.copyWith(color: Colors.white70)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 18),
                child: Column(
                  children: [
                    if (u == null) ...[
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: () => LoginGoogleSheet.mostrar(context),
                          icon: const Icon(Icons.login),
                          label: const Text('Iniciar sesión con Google'),
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],

                    // --- Jugador ---
                    _Tile(
                      icon: Icons.school,
                      title: 'Academias',
                      subtitle: 'Clases de tenis, fútbol y más cerca de ti',
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => const AcademiasScreen())),
                    ),
                    if (u != null)
                      _Tile(
                        icon: Icons.credit_card,
                        title: 'Métodos de pago',
                        subtitle: 'Tus tarjetas guardadas para pagar rápido',
                        onTap: () => Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => const MetodosPagoScreen())),
                      ),

                    // --- Ajustes (tema claro/oscuro) ---
                    _Tile(
                      icon: Icons.tune,
                      title: 'Ajustes',
                      subtitle: 'Tema claro u oscuro y preferencias',
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => const AjustesScreen())),
                    ),

                    const SizedBox(height: 8),
                    // --- Modo anfitrión (Airbnb-style) ---
                    _ModoAnfitrion(
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => const AnfitrionScreen())),
                    ),

                    if (u != null) ...[
                      const SizedBox(height: 10),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => appState.cerrarSesionUsuario(),
                          icon:
                              const Icon(Icons.logout, color: Colors.redAccent),
                          label: const Text('Cerrar sesión',
                              style: TextStyle(color: Colors.redAccent)),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 22),
              Center(
                child: Text(kBrandEslogan,
                    style: t.bodySmall?.copyWith(color: textoTenue)),
              ),
              const SizedBox(height: 30),
            ],
          );
        },
      ),
    );
  }
}

/// Tarjeta DESTACADA para entrar al Modo anfitrión (estilo "cambiar a anfitrión"
/// de Airbnb): resalta como acción principal sin ser un bloque negro.
/// Claro: lima suave + verde bosque (liviano, premium). Oscuro: superficie del
/// tema con acento lima. Theme-aware.
class _ModoAnfitrion extends StatelessWidget {
  const _ModoAnfitrion({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final fondo = oscuro ? cs.surface : limaSuave;
    final borde =
        oscuro ? cs.outlineVariant.withOpacity(0.4) : lima.withOpacity(0.7);
    final acento = oscuro ? lima : bosque; // título + chevron
    return Material(
      color: fondo,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: borde),
          ),
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              // Chip de marca: cuadrado bosque con ícono lima (resalta en claro
              // y en oscuro).
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                    color: oscuro ? lima.withOpacity(0.2) : bosque,
                    borderRadius: BorderRadius.circular(12)),
                child: const Icon(Icons.real_estate_agent, color: lima),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Modo anfitrión',
                        style: t.titleMedium?.copyWith(
                            color: acento, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text('Publica tu cancha o academia y recibe reservas',
                        style: t.bodySmall?.copyWith(
                            color: oscuro
                                ? cs.onSurface.withOpacity(0.7)
                                : bosque.withOpacity(0.7))),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: acento),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 3)),
        ],
      ),
      child: ListTile(
        leading: CircleAvatar(
          radius: 20,
          backgroundColor: limaSuave,
          child: Icon(icon, color: bosque, size: 20),
        ),
        title: Text(title,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle,
            style: t.bodySmall?.copyWith(color: textoTenue)),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
      ),
    );
  }
}
