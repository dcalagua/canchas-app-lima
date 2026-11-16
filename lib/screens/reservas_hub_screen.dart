import 'package:flutter/material.dart';

import '../theme.dart';
import 'agenda_screen.dart';
import 'reservas_dueno_screen.dart';

/// Módulo unificado de RESERVAS del dueño con conmutador de vista, igual que
/// Playtomic / Calendly / Google Calendar: los MISMOS datos (las reservas de
/// sus canchas) vistos de dos formas complementarias, en una sola entrada del
/// menú (antes eran dos pestañas separadas, "Agenda" y "Reservas", que leían
/// lo mismo y confundían).
///
/// - **Lista** (`ReservasDuenoScreen`): bandeja operativa de cobros — quién
///   reservó, si pagó, próximas/pasadas, efectivo, no-show, chat, caja.
/// - **Calendario** (`AgendaScreen`): grilla día × hora de una cancha —
///   disponibilidad visual (qué horas están libres/ocupadas) y "llenar cancha".
///
/// Ambas vistas viven en un `IndexedStack`, así cada una CONSERVA su estado
/// (día/cancha/filtro seleccionados) al alternar; cada una aporta su propio FAB
/// contextual ("Reserva manual" en Lista, "Llenar cancha" en Calendario).
class ReservasHubScreen extends StatefulWidget {
  const ReservasHubScreen({super.key, this.inicial = 0});

  /// Vista inicial: 0 = Lista, 1 = Calendario.
  final int inicial;

  @override
  State<ReservasHubScreen> createState() => _ReservasHubScreenState();
}

class _ReservasHubScreenState extends State<ReservasHubScreen> {
  late int _vista = widget.inicial;

  @override
  Widget build(BuildContext context) {
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final fondo =
        oscuro ? Theme.of(context).scaffoldBackgroundColor : papelCalido;
    // TABLET (≥900 dp): las DOS vistas a la vez, lado a lado — Calendario
    // (disponibilidad día × hora) a la izquierda y Lista (cobros) a la
    // derecha, como la recepción de un local con tablet. Sin conmutador:
    // no hay que alternar nada. Cada mitad conserva su propio FAB
    // ("Llenar cancha" / "Reserva manual"; heroTags ya distintos).
    if (MediaQuery.sizeOf(context).width >= 900) {
      return Scaffold(
        backgroundColor: fondo,
        appBar: AppBar(
          title: const Text('Reservas'),
          actions: accionesReservas(context),
        ),
        body: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Expanded(flex: 11, child: AgendaScreen(embedded: true)),
            Container(width: 1, color: trazo),
            const Expanded(
                flex: 9, child: ReservasDuenoScreen(embedded: true)),
          ],
        ),
      );
    }
    return Scaffold(
      backgroundColor: fondo,
      appBar: AppBar(
        title: const Text('Reservas'),
        // Herramientas del dominio de reservas (valen para ambas vistas):
        // recordatorios anti no-show, clientes fijos y reportes.
        actions: accionesReservas(context),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: _ConmutadorVista(
            vista: _vista,
            onCambio: (v) => setState(() => _vista = v),
          ),
        ),
      ),
      // Cada vista conserva su estado (día/cancha/filtro) y aporta su propio FAB.
      body: IndexedStack(
        index: _vista,
        children: const [
          ReservasDuenoScreen(embedded: true),
          AgendaScreen(embedded: true),
        ],
      ),
    );
  }
}

/// Conmutador Lista ↔ Calendario (estilo Airbnb: pastillas blancas sobre riel
/// suave; la activa se rellena de lima con texto blanco, nunca borde negro).
class _ConmutadorVista extends StatelessWidget {
  const _ConmutadorVista({required this.vista, required this.onCambio});
  final int vista;
  final ValueChanged<int> onCambio;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 2, 18, 12),
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: trazo),
          boxShadow: const [
            BoxShadow(color: Color(0x0F000000), blurRadius: 6, offset: Offset(0, 2)),
          ],
        ),
        child: Row(
          children: [
            _seg(context, 'Lista', Icons.receipt_long_outlined, 0),
            _seg(context, 'Calendario', Icons.calendar_month_outlined, 1),
          ],
        ),
      ),
    );
  }

  Widget _seg(BuildContext context, String texto, IconData icono, int i) {
    final activo = vista == i;
    return Expanded(
      child: GestureDetector(
        onTap: () => onCambio(i),
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: BoxDecoration(
            color: activo ? lima : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icono,
                  size: 18, color: activo ? Colors.white : textoTenue),
              const SizedBox(width: 7),
              Text(texto,
                  style: TextStyle(
                      color: activo ? Colors.white : textoTenue,
                      fontWeight: FontWeight.w700)),
            ],
          ),
        ),
      ),
    );
  }
}
