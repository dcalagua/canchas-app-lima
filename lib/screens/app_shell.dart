import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/icono_chat_pichan.dart';
import 'explorar_home_screen.dart';
import 'mensajes_screen.dart';
import 'mis_reservas_screen.dart';
import 'partidos_screen.dart';
import 'perfil_screen.dart';

/// Shell del JUGADOR con barra inferior (estilo Airbnb): Explorar · Partidos ·
/// Reservas · Mensajes · Perfil. Es la raíz de la app del jugador.
/// (Las "Novedades"/historias se abren desde el ícono de aro en la cabecera de
/// Mensajes, para no recargar la barra inferior.)
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;
  late final List<Widget> _paginas;
  late bool _ultimoLogueado;
  // Recuerda la última pestaña para RETOMARLA al reabrir (si Android mató la app
  // en segundo plano, vuelves donde estabas en vez de a Explorar).
  static const _kUltimaTab = 'jugador_ultima_tab';

  @override
  void initState() {
    super.initState();
    _paginas = [
      const ExplorarHomeScreen(),
      const PartidosScreen(), // "Match": partidos abiertos (+ pichangas de club)
      const MisReservasScreen(),
      const MensajesScreen(),
      const PerfilScreen(),
    ];
    _ultimoLogueado = appState.logueado;
    appState.addListener(_alCambiarSesion);
    _restaurarTab();
  }

  Future<void> _restaurarTab() async {
    // Solo si hay sesión (si no, Explorar es el inicio natural).
    if (!appState.logueado) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      final t = prefs.getInt(_kUltimaTab);
      if (t != null && t >= 0 && t < _paginas.length && mounted && _index == 0) {
        setState(() => _index = t);
        if (t == 4) appState.cargarRetosPendientes();
      }
    } catch (_) {}
  }

  void _irTab(int i) {
    setState(() => _index = i);
    if (i == 4) appState.cargarRetosPendientes();
    try {
      SharedPreferences.getInstance()
          .then((p) => p.setInt(_kUltimaTab, i));
    } catch (_) {}
  }

  @override
  void dispose() {
    appState.removeListener(_alCambiarSesion);
    super.dispose();
  }

  /// Al iniciar o cerrar sesión, siempre volver a Explorar (inicio) y olvidar la
  /// pestaña recordada (para no aterrizar en un chat de la cuenta anterior).
  void _alCambiarSesion() {
    if (appState.logueado == _ultimoLogueado) return;
    _ultimoLogueado = appState.logueado;
    if (_index != 0 && mounted) setState(() => _index = 0);
    try {
      SharedPreferences.getInstance().then((p) => p.setInt(_kUltimaTab, 0));
    } catch (_) {}
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
          final retos = appState.retosPendientes;
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: _irTab,
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
              // Mensajes: ícono de chat normal, como las demás pestañas
              // (decisión del director, sep-2026; ni logo ni burbuja de marca).
              const NavigationDestination(
                  icon: IconoMensajesLogo(activo: false),
                  selectedIcon: IconoMensajesLogo(activo: true),
                  label: 'Mensajes'),
              NavigationDestination(
                icon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: false)),
                selectedIcon: _ConBadge(
                    count: retos,
                    child: _PerfilIcono(fotoUrl: foto, seleccionado: true)),
                label: 'Perfil',
              ),
            ],
          );
        },
      ),
    );
  }
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
