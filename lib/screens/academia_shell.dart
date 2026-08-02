import 'package:flutter/material.dart';

import '../config/features.dart';
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
import 'planes_screen.dart';
import 'reporte_academia_screen.dart';
import 'servicios_screen.dart';

/// Panel de la ACADEMIA (profe). MISMA estructura que "Mis canchas" (HomeShell):
/// en MÓVIL barra de navegación INFERIOR con las secciones (Academia, Cobros,
/// Asistencia, Mensajes, Torneos, Reporte, Billetera); en TABLET el mismo menú
/// pero LATERAL (rail). Al elegir una sección solo cambia el cuerpo
/// (IndexedStack), nunca se tapa el menú.
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
        // Aún sin academia (cargando / crear): la pantalla resuelve todo.
        if (ac == null) return const MiAcademiaScreen();

        // MÓVIL: barra de navegación INFERIOR (igual que Mis canchas). Íconos con
        // color por sección + etiqueta; Mensajes usa el ícono de chat de marca.
        if (!tablet) {
          const azul = Color(0xFF2AA9E0);
          final paginas = <Widget>[
            const MiAcademiaScreen(), // panel (alumnos, plata, código)
            PlanesScreen(academia: ac), // plan de trabajo + evaluación
            CobrosScreen(academiaId: ac.id),
            AsistenciaScreen(academiaId: ac.id),
            ChatsAcademiaScreen(academiaId: ac.id),
            CampeonatosScreen(academiaId: ac.id),
            ReporteAcademiaScreen(academiaId: ac.id),
            const CuentaScreen(), // billetera única (saldo + movimientos)
          ];
          final iconos = <IconData>[
            Icons.sports_tennis,
            Icons.assignment_outlined,
            Icons.payments_outlined,
            Icons.fact_check_outlined,
            Icons.forum_outlined,
            Icons.emoji_events_outlined,
            Icons.insights_outlined,
            Icons.account_balance_wallet_outlined,
          ];
          final etiquetas = <String>[
            'Academia',
            'Plan',
            'Cobros',
            'Asistencia',
            'Mensajes',
            'Torneos',
            'Reporte',
            'Billetera',
          ];
          final colores = <Color>[
            teal,
            naranja,
            lima,
            azul,
            lima,
            amarillo,
            morado,
            amarillo,
          ];
          const iMensajes = 4;
          final idx = _index.clamp(0, paginas.length - 1);
          return Scaffold(
            body: IndexedStack(index: idx, children: paginas),
            // Barra inferior con SCROLL horizontal: caben las 7 secciones sin
            // apretarse ni partir las etiquetas; se desliza para verlas todas.
            bottomNavigationBar: _BarraAcademiaScroll(
              iconos: iconos,
              etiquetas: etiquetas,
              colores: colores,
              iMensajes: iMensajes,
              activo: idx,
              onTap: (i) => setState(() => _index = i),
            ),
          );
        }

        // Tablet + academia lista: menú lateral SIEMPRE visible; el cuerpo de la
        // derecha cambia según la opción elegida (IndexedStack conserva el estado
        // de cada sección al alternar).
        // Color "con vida" (Airbnb) por sección; el ícono va coloreado.
        const azul = Color(0xFF2AA9E0);
        final items = <(IconData, String, Color)>[
          (Icons.sports_tennis, 'Academia', teal),
          (Icons.assignment_outlined, 'Plan', naranja),
          (Icons.payments_outlined, 'Cobros', lima),
          (Icons.forum_outlined, 'Mensajes', lima), // ignora: va ícono WhatsApp
          (Icons.emoji_events_outlined, 'Campeonatos', amarillo),
          (Icons.fact_check_outlined, 'Asistencia', azul),
          (Icons.insights_outlined, 'Reporte', morado),
          if (kServiciosPichangolActivo)
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
                      PlanesScreen(academia: ac),
                      CobrosScreen(academiaId: ac.id),
                      ChatsAcademiaScreen(academiaId: ac.id),
                      CampeonatosScreen(academiaId: ac.id),
                      AsistenciaScreen(academiaId: ac.id),
                      ReporteAcademiaScreen(academiaId: ac.id),
                      if (kServiciosPichangolActivo)
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

/// Barra de navegación INFERIOR con SCROLL horizontal (para la academia en
/// móvil): íconos con color por sección + etiqueta en UNA línea. Como las
/// secciones son varias, la barra se desliza en vez de apretar/partir textos.
class _BarraAcademiaScroll extends StatelessWidget {
  const _BarraAcademiaScroll({
    required this.iconos,
    required this.etiquetas,
    required this.colores,
    required this.iMensajes,
    required this.activo,
    required this.onTap,
  });

  final List<IconData> iconos;
  final List<String> etiquetas;
  final List<Color> colores;
  final int iMensajes;
  final int activo;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surface,
      elevation: 8,
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 64,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: Row(
              children: [
                for (var i = 0; i < iconos.length; i++)
                  _item(context, i),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _item(BuildContext context, int i) {
    final sel = activo == i;
    final color = colores[i];
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => onTap(i),
      borderRadius: BorderRadius.circular(14),
      child: SizedBox(
        width: 76,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Ícono SIEMPRE con color (regla Airbnb "con vida"); Mensajes usa el
            // ícono de chat de marca.
            i == iMensajes
                ? IconoChatPichan(activo: sel)
                : Icon(iconos[i], color: color, size: 25),
            const SizedBox(height: 3),
            Text(
              etiquetas[i],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: sel ? FontWeight.w800 : FontWeight.w500,
                color: sel ? cs.onSurface : cs.onSurface.withOpacity(0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
