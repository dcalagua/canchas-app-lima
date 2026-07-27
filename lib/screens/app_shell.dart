import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/icono_chat_pichan.dart';
import 'explorar_home_screen.dart';
import 'mensajes_screen.dart';
import 'mis_reservas_screen.dart';
import 'partidos_screen.dart';
import 'perfil_screen.dart';

/// Shell del JUGADOR con barra inferior (estilo Airbnb): Explorar · Partidos ·
/// Reservas · Perfil. Es la raíz de la app del jugador.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;
  late final List<Widget> _paginas;

  @override
  void initState() {
    super.initState();
    _paginas = [
      const ExplorarHomeScreen(),
      const PartidosScreen(), // "Match": partidos abiertos (+ pichangas de club)
      const MisReservasScreen(),
      const MensajesScreen(),
      const PerfilScreen(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _paginas),
      // La pestaña Perfil muestra la FOTO del usuario logueado (estilo Airbnb).
      // ListenableBuilder para que reaccione al iniciar/cerrar sesión.
      bottomNavigationBar: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final foto = appState.usuario?.fotoUrl;
          final retos = appState.retosPendientes;
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) {
              setState(() => _index = i);
              // Al entrar a Perfil, refresca el contador de retos (badge).
              if (i == 4) appState.cargarRetosPendientes();
            },
            destinations: [
              const NavigationDestination(
                  icon: Icon(Icons.explore_outlined),
                  selectedIcon: Icon(Icons.explore),
                  label: 'Explorar'),
              const NavigationDestination(
                  icon: Icon(Icons.groups_outlined),
                  selectedIcon: Icon(Icons.groups),
                  label: 'Partidos'),
              const NavigationDestination(
                  icon: Icon(Icons.event_note_outlined),
                  selectedIcon: Icon(Icons.event_note),
                  label: 'Reservas'),
              const NavigationDestination(
                  icon: IconoChatPichan(activo: false),
                  selectedIcon: IconoChatPichan(activo: true),
                  label: 'Mensajes'),
              NavigationDestination(
                icon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: false)),
                selectedIcon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: true)),
                label: 'Perfil',
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Envuelve un ícono de la barra con un badge (punto verde con número) cuando
/// hay retos pendientes de atención. count<=0 = sin badge.
class _ConBadge extends StatelessWidget {
  const _ConBadge({required this.count, required this.child});
  final int count;
  final Widget child;
  @override
  Widget build(BuildContext context) {
    if (count <= 0) return child;
    return Badge.count(
        count: count,
        backgroundColor: bosque,
        textColor: Colors.white,
        child: child);
  }
}

/// Ícono de la pestaña Perfil: foto del usuario (círculo) si hay sesión, con
/// aro verde cuando está seleccionada; si no, el ícono de persona por defecto.
class _PerfilIcono extends StatelessWidget {
  const _PerfilIcono({required this.fotoUrl, required this.seleccionado});
  final String? fotoUrl;
  final bool seleccionado;

  @override
  Widget build(BuildContext context) {
    if (fotoUrl == null) {
      return Icon(seleccionado ? Icons.person : Icons.person_outline);
    }
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: seleccionado ? lima : Colors.transparent,
          width: 2,
        ),
      ),
      child: CircleAvatar(radius: 11, backgroundImage: NetworkImage(fotoUrl!)),
    );
  }
}
