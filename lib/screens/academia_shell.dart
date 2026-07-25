import 'package:flutter/material.dart';

import '../state/app_state.dart';
import 'asistencia_screen.dart';
import 'campeonatos_screen.dart';
import 'chats_academia_screen.dart';
import 'crear_academia_screen.dart';
import 'mi_academia_screen.dart';
import 'reporte_academia_screen.dart';
import 'servicios_screen.dart';

/// Panel de la ACADEMIA (profe). En TABLET usa un menú LATERAL (rail) a la
/// izquierda con TODAS las acciones (Mensajes, Campeonatos, Asistencia, Reporte,
/// Publicidad, Editar) — así la cabecera queda limpia y se gana el espacio del
/// medio. La sección "Academia" (resumen) es el cuerpo; las demás abren su
/// pantalla. En MÓVIL no hay rail: se usa `MiAcademiaScreen` con sus accesos en
/// la cabecera (ahí sí caben).
class AcademiaShell extends StatelessWidget {
  const AcademiaShell({super.key});

  static const _bp = 720.0; // ancho a partir del cual mostramos el rail

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final ac = appState.miAcademia;
        final tablet = MediaQuery.of(context).size.width >= _bp;
        // Móvil, o aún sin academia (cargando / crear): la pantalla resuelve todo
        // y muestra sus accesos en la cabecera.
        if (!tablet || ac == null) return const MiAcademiaScreen();

        // Tablet + academia lista: menú lateral con todas las acciones.
        final items = <(IconData, String, VoidCallback?)>[
          (Icons.sports_tennis, 'Academia', null), // sección activa (cuerpo)
          (Icons.forum_outlined, 'Mensajes', () => _push(context,
              ChatsAcademiaScreen(academiaId: ac.id))),
          (Icons.emoji_events_outlined, 'Campeonatos', () => _push(context,
              CampeonatosScreen(academiaId: ac.id))),
          (Icons.fact_check_outlined, 'Asistencia', () => _push(context,
              AsistenciaScreen(academiaId: ac.id))),
          (Icons.insights_outlined, 'Reporte', () => _push(context,
              ReporteAcademiaScreen(academiaId: ac.id))),
          (Icons.campaign_outlined, 'Publicidad', () => _push(context,
              ServiciosScreen(
                  negocio: appState.negocioServiciosDeAcademia(ac)))),
          (Icons.edit_outlined, 'Editar', () => _push(context,
              CrearAcademiaScreen(academia: ac))),
        ];
        return Scaffold(
          body: SafeArea(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: 0, // "Academia" es el cuerpo; el resto abre pantalla
                  onDestinationSelected: (i) {
                    if (i == 0) return; // ya estamos en el resumen
                    items[i].$3?.call();
                  },
                  labelType: NavigationRailLabelType.all,
                  groupAlignment: -0.9,
                  destinations: [
                    for (final it in items)
                      NavigationRailDestination(
                        icon: Icon(it.$1),
                        label: Text(it.$2),
                      ),
                  ],
                ),
                const VerticalDivider(width: 1),
                const Expanded(child: MiAcademiaScreen()),
              ],
            ),
          ),
        );
      },
    );
  }

  void _push(BuildContext context, Widget pantalla) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => pantalla));
  }
}
