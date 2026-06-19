import 'package:flutter/material.dart';

import 'agenda_screen.dart';
import 'cuenta_screen.dart';
import 'disponibilidad_screen.dart';
import 'reportes_screen.dart';
import 'reservas_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _paginas = <Widget>[
    AgendaScreen(),
    DisponibilidadScreen(),
    ReservasScreen(),
    ReportesScreen(),
    CuentaScreen(),
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
              icon: Icon(Icons.calendar_month), label: 'Agenda'),
          NavigationDestination(
              icon: Icon(Icons.schedule), label: 'Horarios'),
          NavigationDestination(
              icon: Icon(Icons.list_alt), label: 'Reservas'),
          NavigationDestination(
              icon: Icon(Icons.bar_chart), label: 'Reportes'),
          NavigationDestination(
              icon: Icon(Icons.account_balance_wallet), label: 'Cuenta'),
        ],
      ),
    );
  }
}
