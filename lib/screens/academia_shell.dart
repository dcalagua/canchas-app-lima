import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/icono_chat_pichan.dart';
import '../widgets/menu_lateral_scroll.dart';
import 'asistencia_screen.dart';
import 'campeonatos_screen.dart';
import 'chats_academia_screen.dart';
import 'cobros_screen.dart';
import 'crear_academia_screen.dart';
import 'cuenta_screen.dart';
import 'mi_academia_screen.dart';
import 'reporte_academia_screen.dart';
import 'servicios_screen.dart';

/// Panel de la ACADEMIA (profe). En TABLET usa un menú LATERAL (rail) a la
/// izquierda con TODAS las acciones (Academia, Mensajes, Campeonatos, Asistencia,
/// Reporte, Publicidad, Editar). Al elegir cualquiera, el rail SIGUE visible y
/// solo cambia el contenido de la derecha (IndexedStack) — nunca se tapa el
/// menú. En MÓVIL no hay rail: se usa `MiAcademiaScreen` con sus accesos en la
/// cabecera (ahí sí caben).
class AcademiaShell extends StatefulWidget {
  const AcademiaShell({super.key});

  @override
  State<AcademiaShell> createState() => _AcademiaShellState();
}

class _AcademiaShellState extends State<AcademiaShell> {
  static const _bp = 720.0; // ancho a partir del cual mostramos el rail
  int _index = 0; // sección activa dentro del rail

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

        // Tablet + academia lista: menú lateral SIEMPRE visible; el cuerpo de la
        // derecha cambia según la opción elegida (IndexedStack conserva el estado
        // de cada sección al alternar).
        // Color "con vida" (Airbnb) por sección; el ícono va coloreado.
        const azul = Color(0xFF2AA9E0);
        final items = <(IconData, String, Color)>[
          (Icons.sports_tennis, 'Academia', teal),
          (Icons.payments_outlined, 'Cobros', lima),
          (Icons.forum_outlined, 'Mensajes', lima), // ignora: va ícono WhatsApp
          (Icons.emoji_events_outlined, 'Campeonatos', amarillo),
          (Icons.fact_check_outlined, 'Asistencia', azul),
          (Icons.insights_outlined, 'Reporte', morado),
          (Icons.campaign_outlined, 'Publicidad', naranja),
          (Icons.edit_outlined, 'Editar', teal),
          (Icons.account_balance_wallet_outlined, 'Billetera', amarillo),
        ];
        // El índice no puede quedar fuera de rango (p. ej. si cambia la lista).
        final idx = _index.clamp(0, items.length - 1);
        return Scaffold(
          body: SafeArea(
            child: Row(
              children: [
                MenuLateralScroll(
                  rail: NavigationRail(
                    selectedIndex: idx,
                    onDestinationSelected: (i) => setState(() => _index = i),
                    labelType: NavigationRailLabelType.all,
                    groupAlignment: -0.9,
                    destinations: [
                      for (final it in items)
                        NavigationRailDestination(
                          icon: it.$2 == 'Mensajes'
                              ? const IconoChatPichan()
                              : Icon(it.$1, color: it.$3),
                          label: Text(it.$2),
                        ),
                    ],
                  ),
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  child: IndexedStack(
                    index: idx,
                    children: [
                      const MiAcademiaScreen(),
                      CobrosScreen(academiaId: ac.id),
                      ChatsAcademiaScreen(academiaId: ac.id),
                      CampeonatosScreen(academiaId: ac.id),
                      AsistenciaScreen(academiaId: ac.id),
                      ReporteAcademiaScreen(academiaId: ac.id),
                      ServiciosScreen(
                          negocio: appState.negocioServiciosDeAcademia(ac),
                          mostrarBilleteraEnAppBar: false),
                      CrearAcademiaScreen(academia: ac),
                      const CuentaScreen(), // billetera única (saldo + movimientos)
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
