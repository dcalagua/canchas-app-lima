import 'package:flutter/material.dart';

import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import 'convocatorias_screen.dart';
import 'explorar_home_screen.dart';
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
      const PerfilScreen(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _paginas),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.explore_outlined),
              selectedIcon: Icon(Icons.explore),
              label: 'Explorar'),
          NavigationDestination(
              icon: Icon(Icons.groups_outlined),
              selectedIcon: Icon(Icons.groups),
              label: 'Partidos'),
          NavigationDestination(
              icon: Icon(Icons.event_note_outlined),
              selectedIcon: Icon(Icons.event_note),
              label: 'Reservas'),
          NavigationDestination(
              icon: Icon(Icons.person_outline),
              selectedIcon: Icon(Icons.person),
              label: 'Perfil'),
        ],
      ),
    );
  }
}
