import 'package:flutter/material.dart';

import 'mensajes_screen.dart';
import 'mi_academia_screen.dart';

/// Panel de la ACADEMIA (profe) con menú LATERAL (rail en tablet) o barra
/// inferior (móvil), igual que el panel del dueño — el menú ya no vive en la
/// cabecera. Pestañas: Academia (resumen, alumnos, cobros) y Mensajes (chat con
/// los alumnos / apoderados).
class AcademiaShell extends StatefulWidget {
  const AcademiaShell({super.key});

  @override
  State<AcademiaShell> createState() => _AcademiaShellState();
}

class _AcademiaShellState extends State<AcademiaShell> {
  int _index = 0;

  static const _paginas = <Widget>[
    MiAcademiaScreen(), // resumen + alumnos + cobros + invitaciones
    MensajesScreen(),   // chat con alumnos / apoderados
  ];
  static const _iconos = <IconData>[Icons.sports_tennis, Icons.chat_bubble];
  static const _etiquetas = <String>['Academia', 'Mensajes'];

  @override
  Widget build(BuildContext context) {
    final body = IndexedStack(index: _index, children: _paginas);
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
