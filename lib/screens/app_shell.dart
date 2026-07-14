import 'package:flutter/material.dart';

import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'convocatorias_screen.dart';
import 'explorar_home_screen.dart';
import 'mensajes_screen.dart';
import 'mis_reservas_screen.dart';
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
    final club = appState.nombreClub;
    _paginas = [
      const ExplorarHomeScreen(),
      ConvocatoriasScreen(
          clubId: ConvocatoriasService.slugClub(club), clubNombre: club),
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
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
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
                  icon: Icon(Icons.chat_bubble_outline),
                  selectedIcon: Icon(Icons.chat_bubble),
                  label: 'Mensajes'),
              NavigationDestination(
                icon: _PerfilIcono(fotoUrl: foto, seleccionado: false),
                selectedIcon: _PerfilIcono(fotoUrl: foto, seleccionado: true),
                label: 'Perfil',
              ),
            ],
          );
        },
      ),
    );
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
          color: seleccionado ? bosque : Colors.transparent,
          width: 2,
        ),
      ),
      child: CircleAvatar(radius: 11, backgroundImage: NetworkImage(fotoUrl!)),
    );
  }
}
