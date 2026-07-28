import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/icono_chat_pichan.dart';
import 'explorar_home_screen.dart';
import 'mensajes_screen.dart';
import 'mis_reservas_screen.dart';
import 'novedades_screen.dart';
import 'partidos_screen.dart';
import 'perfil_screen.dart';

/// Shell del JUGADOR con barra inferior (estilo Airbnb): Explorar · Partidos ·
/// Reservas · Mensajes · Perfil. "Novedades" (historias) es una sección
/// CONTEXTUAL: solo aparece en la barra cuando estás usando Mensajes (como el
/// WhatsApp actual, pero sin ocupar espacio fijo en el resto de la app).
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  // Clave de la sección activa (evita índices frágiles al insertar/quitar
  // "Novedades" dinámicamente).
  String _sel = 'explorar';

  // Todas las páginas (IndexedStack conserva su estado aunque no estén en la
  // barra). El orden acá es fijo; la barra decide qué se ve.
  static const _claves = <String>[
    'explorar',
    'partidos',
    'reservas',
    'mensajes',
    'novedades',
    'perfil',
  ];
  late final List<Widget> _paginas = const [
    ExplorarHomeScreen(),
    PartidosScreen(),
    MisReservasScreen(),
    MensajesScreen(),
    NovedadesScreen(),
    PerfilScreen(),
  ];

  bool get _enMensajes => _sel == 'mensajes' || _sel == 'novedades';

  void _ir(String clave) {
    setState(() => _sel = clave);
    if (clave == 'perfil') appState.cargarRetosPendientes();
    if (clave == 'novedades') appState.cargarEstados();
  }

  @override
  Widget build(BuildContext context) {
    final stackIndex = _claves.indexOf(_sel).clamp(0, _claves.length - 1);
    return Scaffold(
      body: IndexedStack(index: stackIndex, children: _paginas),
      bottomNavigationBar: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final foto = appState.usuario?.fotoUrl;
          final retos = appState.retosPendientes;

          // Destinos visibles: los 5 fijos + "Novedades" insertado tras Mensajes
          // SOLO cuando estás en ese contexto.
          final items = <_NavItem>[
            const _NavItem('explorar', 'Explorar',
                icon: Icon(Icons.explore_outlined),
                selectedIcon: Icon(Icons.explore)),
            const _NavItem('partidos', 'Partidos',
                icon: Icon(Icons.groups_outlined),
                selectedIcon: Icon(Icons.groups)),
            const _NavItem('reservas', 'Reservas',
                icon: Icon(Icons.event_note_outlined),
                selectedIcon: Icon(Icons.event_note)),
            const _NavItem('mensajes', 'Mensajes',
                icon: IconoChatPichan(activo: false),
                selectedIcon: IconoChatPichan(activo: true)),
            if (_enMensajes)
              const _NavItem('novedades', 'Novedades',
                  icon: Icon(Icons.donut_large_outlined, color: lima),
                  selectedIcon: Icon(Icons.donut_large, color: lima)),
            _NavItem('perfil', 'Perfil',
                icon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: false)),
                selectedIcon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: true))),
          ];

          final sel = items.indexWhere((it) => it.clave == _sel);
          return NavigationBar(
            selectedIndex: sel < 0 ? 0 : sel,
            onDestinationSelected: (i) => _ir(items[i].clave),
            destinations: [
              for (final it in items)
                NavigationDestination(
                    icon: it.icon,
                    selectedIcon: it.selectedIcon,
                    label: it.label),
            ],
          );
        },
      ),
    );
  }
}

/// Descriptor de un destino de la barra (para armarla dinámicamente).
class _NavItem {
  const _NavItem(this.clave, this.label,
      {required this.icon, required this.selectedIcon});
  final String clave;
  final String label;
  final Widget icon;
  final Widget selectedIcon;
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
