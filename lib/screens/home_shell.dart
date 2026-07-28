import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/icono_chat_pichan.dart';
import '../widgets/menu_lateral_scroll.dart';
import 'agenda_screen.dart';
import 'clientes_screen.dart';
import 'cuenta_screen.dart';
import 'mensajes_screen.dart';
import 'mis_canchas_screen.dart';
import 'novedades_screen.dart';
import 'reportes_screen.dart';
import 'reservas_dueno_screen.dart';

/// Panel del DUEÑO unificado: un solo lugar con TODO lo del dueño en pestañas,
/// con el mismo estilo premium. "Mis canchas" (reales) es la pestaña principal.
/// "Novedades" (historias) es CONTEXTUAL: solo aparece junto a Mensajes cuando
/// estás usando esa sección (igual que en la app del jugador).
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, this.initialIndex = 0});

  /// Pestaña inicial (0 = Mis canchas).
  final int initialIndex;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  late String _sel = _claves[widget.initialIndex.clamp(0, _claves.length - 1)];

  // Todas las secciones (IndexedStack conserva su estado aunque no estén en la
  // barra). Orden fijo; la barra decide qué se ve.
  static const _claves = <String>[
    'canchas',
    'agenda',
    'reservas',
    'clientes',
    'mensajes',
    'novedades',
    'reportes',
    'billetera',
  ];
  static const _paginas = <Widget>[
    MisCanchasScreen(),
    AgendaScreen(),
    ReservasDuenoScreen(),
    ClientesScreen(),
    MensajesScreen(),
    NovedadesScreen(),
    ReportesScreen(),
    CuentaScreen(),
  ];

  bool get _enMensajes => _sel == 'mensajes' || _sel == 'novedades';

  void _ir(String clave) {
    setState(() => _sel = clave);
    if (clave == 'novedades') appState.cargarEstados();
  }

  // Destinos visibles (dinámicos): las 7 secciones + "Novedades" insertado tras
  // Mensajes SOLO en ese contexto.
  List<_Nav> _items() {
    return <_Nav>[
      const _Nav('canchas', 'Canchas', Icons.sports_soccer, lima),
      const _Nav('agenda', 'Agenda', Icons.calendar_month, Color(0xFF2AA9E0)),
      const _Nav('reservas', 'Reservas', Icons.event_note, naranja),
      const _Nav('clientes', 'Clientes', Icons.groups, morado),
      const _Nav('mensajes', 'Mensajes', Icons.chat_bubble, lima,
          esChat: true),
      if (_enMensajes)
        const _Nav('novedades', 'Novedades', Icons.donut_large, lima),
      const _Nav('reportes', 'Reportes', Icons.bar_chart, teal),
      const _Nav('billetera', 'Billetera', Icons.account_balance_wallet,
          amarillo),
    ];
  }

  Widget _icono(_Nav n) => n.esChat
      ? IconoChatPichan(activo: _sel == n.clave)
      : Icon(n.icono, color: n.color);

  @override
  Widget build(BuildContext context) {
    final stackIndex = _claves.indexOf(_sel).clamp(0, _claves.length - 1);
    final body = IndexedStack(index: stackIndex, children: _paginas);
    final items = _items();
    final sel = items.indexWhere((it) => it.clave == _sel);
    final selIndex = sel < 0 ? 0 : sel;

    final tablet = MediaQuery.of(context).size.width >= 720;
    if (tablet) {
      return Scaffold(
        body: SafeArea(
          child: Row(
            children: [
              MenuLateralScroll(
                rail: NavigationRail(
                  selectedIndex: selIndex,
                  onDestinationSelected: (i) => _ir(items[i].clave),
                  labelType: NavigationRailLabelType.all,
                  groupAlignment: -0.85,
                  destinations: [
                    for (final n in items)
                      NavigationRailDestination(
                        icon: _icono(n),
                        label: Text(n.label),
                      ),
                  ],
                ),
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
        selectedIndex: selIndex,
        onDestinationSelected: (i) => _ir(items[i].clave),
        destinations: [
          for (final n in items)
            NavigationDestination(icon: _icono(n), label: n.label),
        ],
      ),
    );
  }
}

/// Descriptor de una sección de navegación del dueño.
class _Nav {
  const _Nav(this.clave, this.label, this.icono, this.color,
      {this.esChat = false});
  final String clave;
  final String label;
  final IconData icono;
  final Color color;
  final bool esChat; // usa el ícono de chat "Pichan" en vez de [icono]
}
