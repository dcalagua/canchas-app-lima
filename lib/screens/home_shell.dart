import 'package:flutter/material.dart';

import 'agenda_screen.dart';
import 'clientes_screen.dart';
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

  // Cuenta/Saldo (modelo inDrive): recarga real con Culqi (Yape/tarjeta).
  static const _paginas = <Widget>[
    MisCanchasScreen(),     // tus canchas reales (editar precio/horarios/servicios)
    AgendaScreen(),         // agenda de hoy (real)
    ReservasDuenoScreen(),  // reservas reales de tus canchas + caja
    ClientesScreen(),       // base de clientes (CRM ligero, derivado de reservas)
    ReportesScreen(),       // reportes / KPIs (reales)
    CuentaScreen(),         // saldo prepago + recargar (Culqi)
  ];

  // Íconos/etiquetas de las secciones (compartidos por barra inferior y rail).
  static const _iconos = <IconData>[
    Icons.sports_soccer,
    Icons.calendar_month,
    Icons.event_note,
    Icons.groups,
    Icons.bar_chart,
    Icons.account_balance_wallet,
  ];
  static const _etiquetas = <String>[
    'Canchas',
    'Agenda',
    'Reservas',
    'Clientes',
    'Reportes',
    'Cuenta',
  ];

  @override
  Widget build(BuildContext context) {
    final body = IndexedStack(index: _index, children: _paginas);
    // Tablet / horizontal: navegación LATERAL (NavigationRail), como un panel de
    // control cómodo en pantalla ancha. Móvil / vertical: barra inferior.
    final tablet = MediaQuery.of(context).size.width >= 720;
    if (tablet) {
      return Scaffold(
        body: SafeArea(
          child: Row(
            children: [
              NavigationRail(
                selectedIndex: _index,
                onDestinationSelected: (i) => setState(() => _index = i),
                labelType: NavigationRailLabelType.all,
                groupAlignment: -0.85,
                destinations: [
                  for (var i = 0; i < _iconos.length; i++)
                    NavigationRailDestination(
                      icon: Icon(_iconos[i]),
                      label: Text(_etiquetas[i]),
                    ),
                ],
              ),
              const VerticalDivider(width: 1),
              Expanded(child: body),
            ],
          ),
        ),
      );
    }
    return Scaffold(
      body: body,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          for (var i = 0; i < _iconos.length; i++)
            NavigationDestination(icon: Icon(_iconos[i]), label: _etiquetas[i]),
        ],
      ),
    );
  }
}
