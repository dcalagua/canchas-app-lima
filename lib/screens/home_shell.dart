import 'package:flutter/material.dart';

import 'agenda_screen.dart';
import 'cuenta_screen.dart';
import 'mis_canchas_screen.dart';
import 'reportes_screen.dart';
import 'reservas_dueno_screen.dart';

/// Panel del DUEÑO unificado: un solo lugar con TODO lo del dueño en pestañas,
/// con el mismo estilo premium. "Mis canchas" (reales) es la pestaña principal.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, this.initialIndex = 0});

  /// Pestaña inicial (0 = Mis canchas).
  final int initialIndex;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  late int _index = widget.initialIndex;

  static const _paginas = <Widget>[
    MisCanchasScreen(),     // tus canchas reales (editar precio/horarios/servicios)
    AgendaScreen(),         // agenda de hoy
    ReservasDuenoScreen(),  // reservas reales de tus canchas + caja
    ReportesScreen(),       // reportes / KPIs
    CuentaScreen(),         // saldo prepago
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _paginas),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.sports_soccer), label: 'Mis canchas'),
          NavigationDestination(
              icon: Icon(Icons.calendar_month), label: 'Agenda'),
          NavigationDestination(
              icon: Icon(Icons.event_note), label: 'Reservas'),
          NavigationDestination(
              icon: Icon(Icons.bar_chart), label: 'Reportes'),
          NavigationDestination(
              icon: Icon(Icons.account_balance_wallet), label: 'Cuenta'),
        ],
      ),
    );
  }
}
