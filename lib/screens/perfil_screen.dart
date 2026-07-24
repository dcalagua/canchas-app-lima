import 'package:flutter/material.dart';

import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/google_logo.dart';
import 'academias_screen.dart';
import 'ajustes_screen.dart';
import 'anfitrion_screen.dart';
import 'login_google_sheet.dart';
import 'billetera_screen.dart';
import 'editar_perfil_screen.dart';
import 'hazte_pro_screen.dart';
import 'mis_retos_screen.dart';

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
                  // Cabecera VERDE WhatsApp (antes degradaba a charcoal/negro).
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [lima, teal],
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
                        // Editar mi nombre/foto (solo con sesión).
                        if (u != null)
                          IconButton(
                            tooltip: 'Editar mi perfil',
                            icon: const Icon(Icons.edit_outlined,
                                color: Colors.white),
                            onPressed: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                    builder: (_) => const EditarPerfilScreen())),
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
                          onPressed: () => LoginGoogleSheet.mostrar(context,
                              motivo: 'acceder a tu cuenta'),
                          icon: Container(
                            padding: const EdgeInsets.all(3),
                            decoration: const BoxDecoration(
                                color: Colors.white, shape: BoxShape.circle),
                            child: const GoogleLogo(size: 18),
                          ),
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
                    // Circuito (capa de TENIS): estos accesos solo salen si el
                    // usuario YA usa el circuito, para no ensuciar el menú de
                    // quien solo reserva o juega fútbol. La gente descubre el
                    // circuito desde Academias / Explorar (tenis).
                    if (u != null && appState.usaCircuito)
                      _Tile(
                        icon: Icons.sports_kabaddi,
                        title: 'Mis retos',
                        subtitle: 'Rétalos, juega y sube en el ranking',
                        badge: appState.retosPendientes,
                        onTap: () => Navigator.of(context)
                            .push(MaterialPageRoute(
                                builder: (_) => const MisRetosScreen()))
                            .then((_) => appState.cargarRetosPendientes()),
                      ),
                    if (u != null && appState.usaCircuito)
                      _Tile(
                        icon: appState.proActivo
                            ? Icons.workspace_premium
                            : Icons.star_border,
                        title: appState.proActivo
                            ? 'Pichangol Pro ✓'
                            : 'Hazte Pichangol Pro',
                        subtitle: appState.proActivo
                            ? 'Tu membresía está activa'
                            : 'Tu carnet oficial y el ranking del circuito',
                        onTap: () => Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => const HazteProScreen())),
                      ),
                    if (u != null)
                      _Tile(
                        icon: Icons.account_balance_wallet,
                        title: 'Mi billetera',
                        subtitle:
                            'Tu saldo, recargas y tarjetas guardadas',
                        onTap: () => Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => const BilleteraScreen())),
                      ),

                    // --- Ajustes: apariencia + tu cuenta (identidad, invitar,
                    // compartir) viven aquí para no saturar el Perfil. ---
                    _Tile(
                      icon: Icons.tune,
                      title: 'Ajustes',
                      subtitle: 'Tu cuenta, verificación, invitar y compartir',
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
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
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
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    // En OSCURO se pintaba surface-sobre-surface y "no se notaba": ahora es una
    // tarjeta verde WhatsApp sólida (resalta como acción principal, estilo Airbnb
    // "cambiar a anfitrión"). En claro, el tinte lima suave premium.
    final fondo = oscuro ? lima : limaSuave;
    final borde = oscuro ? lima : lima.withOpacity(0.7);
    final acento = oscuro ? Colors.white : bosque; // título + chevron
    final chipBg = oscuro ? Colors.white.withOpacity(0.22) : bosque;
    final chipIcon = oscuro ? Colors.white : lima;
    final subColor =
        oscuro ? Colors.white.withOpacity(0.9) : bosque.withOpacity(0.7);
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
                    color: chipBg,
                    borderRadius: BorderRadius.circular(12)),
                child: Icon(Icons.real_estate_agent, color: chipIcon),
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
                        style: t.bodySmall?.copyWith(color: subColor)),
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
      required this.onTap,
      this.badge = 0});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  /// Contador de "requiere tu atención" (0 = sin badge). Estilo Airbnb: punto
  /// lima con el número, sobre el ícono del tile.
  final int badge;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget avatar = CircleAvatar(
      radius: 20,
      backgroundColor: limaSuave,
      child: Icon(icon, color: bosque, size: 20),
    );
    if (badge > 0) {
      avatar = Badge.count(
        count: badge,
        backgroundColor: bosque,
        textColor: Colors.white,
        child: avatar,
      );
    }
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
        leading: avatar,
        title: Text(title,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle,
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
      ),
    );
  }
}
