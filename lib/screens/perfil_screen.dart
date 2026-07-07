import 'package:flutter/material.dart';

import '../brand.dart';
import '../services/growth_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'home_shell.dart';
import 'login_google_sheet.dart';
import 'registrar_cancha_screen.dart';
import 'verificador_screen.dart';

/// Pestaña PERFIL del jugador: sesión (login/logout), acceso al panel del dueño,
/// registrar cancha y verificador. Mismo estilo (header sage) que Mis canchas.
class PerfilScreen extends StatelessWidget {
  const PerfilScreen({super.key});

  Future<void> _abrirPanel(BuildContext context) async {
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !context.mounted) return;
    }
    if (!context.mounted) return;
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const HomeShell()));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: papel,
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final u = appState.usuario;
          return ListView(
            padding: EdgeInsets.zero,
            children: [
              // Header sage (igual a Mis canchas) con la ficha del usuario.
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
                      const SizedBox(height: 8),
                    ],
                    _Tile(
                      icon: Icons.storefront,
                      title: 'Mis canchas',
                      subtitle: 'Panel del dueño: canchas, agenda, reservas',
                      onTap: () => _abrirPanel(context),
                    ),
                    _Tile(
                      icon: Icons.add_a_photo,
                      title: 'Registrar mi cancha',
                      subtitle: 'Súmala al mapa (la IA detecta el deporte)',
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => const RegistrarCanchaScreen())),
                    ),
                    if (GrowthService.disponible)
                      _Tile(
                        icon: Icons.verified_user,
                        title: 'Verificador',
                        subtitle: 'Visitas: foto, GPS y firma',
                        onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                                builder: (_) => const VerificadorScreen())),
                      ),
                    if (u != null) ...[
                      const SizedBox(height: 8),
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
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        leading: Icon(icon, color: bosque),
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
