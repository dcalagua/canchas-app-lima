import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/court_lines.dart';
import '../utils/moneda.dart';
import '../widgets/sesion_requerida.dart';
import 'chat_screen.dart';

/// Reservas hechas por el jugador logueado (rediseño premium, handoff v2):
/// tabs Próximas/Historial + card destacada bosque de la próxima reserva.
class MisReservasScreen extends StatefulWidget {
  const MisReservasScreen({super.key});

  @override
  State<MisReservasScreen> createState() => _MisReservasScreenState();
}

class _MisReservasScreenState extends State<MisReservasScreen> {
  int _tab = 0; // 0 = Próximas, 1 = Historial

  Cancha? _cancha(String id) {
    for (final c in appState.todasLasCanchas()) {
      if (c.id == id) return c;
    }
    return null;
  }

  DateTime? _fechaHora(String fechaIso, String hora) {
    try {
      final p = hora.split(':');
      final d = DateTime.parse(fechaIso);
      return DateTime(d.year, d.month, d.day, int.parse(p[0]), int.parse(p[1]));
    } catch (_) {
      return null;
    }
  }

  /// Una reserva es "próxima" si aún no terminó y no está jugada/no-show.
  bool _esProxima(Reserva r) {
    if (r.estado == EstadoReserva.completada ||
        r.estado == EstadoReserva.noShow) {
      return false;
    }
    final fin = _fechaHora(r.fecha, r.horaFin);
    if (fin == null) return true;
    return fin.isAfter(DateTime.now());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (!appState.logueado) {
            return const SesionRequerida(
              motivo: 'ver tus reservas',
              icono: Icons.sports_soccer,
              titulo: 'Tus reservas te esperan',
            );
          }
          final todas = appState.misReservas;
          final proximas = todas.where(_esProxima).toList()
            ..sort((a, b) => (_fechaHora(a.fecha, a.horaInicio) ?? DateTime.now())
                .compareTo(_fechaHora(b.fecha, b.horaInicio) ?? DateTime.now()));
          final historial = todas.where((r) => !_esProxima(r)).toList()
            ..sort((a, b) => (_fechaHora(b.fecha, b.horaInicio) ?? DateTime(2000))
                .compareTo(_fechaHora(a.fecha, a.horaInicio) ?? DateTime(2000)));
          final lista = _tab == 0 ? proximas : historial;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 4, 18, 12),
                child: _SegTabs(
                  seleccion: _tab,
                  etiquetas: const ['Próximas', 'Historial'],
                  onTap: (i) => setState(() => _tab = i),
                ),
              ),
              Expanded(
                child: lista.isEmpty
                    ? _Vacio(historial: _tab == 1)
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(18, 4, 18, 28),
                        itemCount: lista.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 14),
                        itemBuilder: (context, i) {
                          final r = lista[i];
                          final cancha = _cancha(r.canchaId);
                          // La primera PRÓXIMA va destacada (card bosque).
                          if (_tab == 0 && i == 0) {
                            return _ReservaDestacada(reserva: r, cancha: cancha);
                          }
                          return _ReservaCard(reserva: r, cancha: cancha);
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Control segmentado (píldoras) estilo handoff: Próximas / Historial.
class _SegTabs extends StatelessWidget {
  const _SegTabs(
      {required this.seleccion, required this.etiquetas, required this.onTap});
  final int seleccion;
  final List<String> etiquetas;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var i = 0; i < etiquetas.length; i++) ...[
          if (i > 0) const SizedBox(width: 10),
          _SegChip(
            texto: etiquetas[i],
            activo: seleccion == i,
            onTap: () => onTap(i),
          ),
        ],
      ],
    );
  }
}

class _SegChip extends StatelessWidget {
  const _SegChip(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        decoration: BoxDecoration(
          // Activo = verde WhatsApp (marca), no negro. Congruente con la app.
          color: activo ? lima : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: activo ? lima : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? Colors.white : textoTenueDe(context),
                fontWeight: FontWeight.w700,
                fontSize: 14)),
      ),
    );
  }
}

class _ReservaDestacada extends StatelessWidget {
  const _ReservaDestacada({required this.reserva, required this.cancha});
  final Reserva reserva;
  final Cancha? cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final dep = cancha?.deporte ?? Deporte.futbol;
    // Card claro con acento verde (nunca fondo negro): se distingue como "la
    // próxima" por el borde lima y la pastilla, no por un fondo oscuro.
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: lima, width: 2),
        boxShadow: const [
          BoxShadow(
              color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                    color: lima, borderRadius: BorderRadius.circular(999)),
                child: Text('PRÓXIMA · ${reserva.dia.toUpperCase()}',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.w800)),
              ),
              const Spacer(),
              Text(_estadoLabel(reserva.estado),
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              _MenuReserva(reserva: reserva),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Container(
                width: 58,
                height: 58,
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  gradient: gradienteDeporte(dep),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const CourtLines(opacity: 0.5),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cancha?.nombre ?? 'Cancha',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    Text(
                      '${cancha?.club ?? dep.etiqueta} · ${reserva.horaInicio}–${reserva.horaFin}',
                      style: t.bodyMedium
                          ?.copyWith(color: textoTenueDe(context)),
                    ),
                    if (reserva.sena > 0)
                      Text('Seña pagada ${reserva.monedaSimbolo}${reserva.sena}',
                          style: t.bodySmall?.copyWith(
                              color: lima, fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 13)),
                  onPressed: cancha == null
                      ? null
                      : () => UbicacionShare.abrirMapa(cancha!.ubicacion),
                  icon: const Icon(Icons.directions, size: 18),
                  label: const Text('Cómo llegar'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: lima,
                    side: const BorderSide(color: lima, width: 1.5),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  onPressed: () => _mostrarPase(context, reserva, cancha),
                  child: const Text('Ver pase'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReservaCard extends StatelessWidget {
  const _ReservaCard({required this.reserva, required this.cancha});
  final Reserva reserva;
  final Cancha? cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final dep = cancha?.deporte ?? Deporte.futbol;
    return GestureDetector(
      onTap: () => _mostrarPase(context, reserva, cancha),
      child: Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              gradient: gradienteDeporte(dep),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const CourtLines(opacity: 0.5),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(cancha?.nombre ?? 'Cancha',
                    style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(
                  '${cancha?.club ?? ''} · ${reserva.dia} ${reserva.horaInicio}–${reserva.horaFin}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                ),
                const SizedBox(height: 6),
                _EstadoChip(estado: reserva.estado),
              ],
            ),
          ),
          Text('${reserva.monedaSimbolo}${reserva.precio}',
              style: t.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.onSurface)),
          if (_puedeChatear(context))
            IconButton(
              icon: const Icon(Icons.chat_bubble_outline, size: 20),
              tooltip: 'Mensaje al dueño',
              visualDensity: VisualDensity.compact,
              onPressed: () => _chatearConDueno(context),
            ),
          _MenuReserva(reserva: reserva),
        ],
      ),
      ),
    );
  }

  bool _puedeChatear(BuildContext context) {
    final owner = (cancha?.dueno ?? '').toLowerCase();
    final me = (appState.usuario?.email ?? '').toLowerCase();
    return owner.isNotEmpty && me.isNotEmpty && owner != me;
  }

  /// Abre el chat con el dueño de la cancha (conversación de cancha).
  void _chatearConDueno(BuildContext context) {
    final owner = cancha?.dueno ?? '';
    final me = appState.usuario?.email ?? '';
    if (owner.isEmpty || me.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: me,
        titulo: (cancha?.club.isNotEmpty ?? false)
            ? cancha!.club
            : (cancha?.nombre ?? 'Dueño'),
        soyProfe: false,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }
}

/// ¿La reserva ya terminó su ciclo (historial)? Cambia el texto del menú.
bool _esHistorial(Reserva r) =>
    r.estado == EstadoReserva.completada || r.estado == EstadoReserva.noShow;

/// Menú "⋮" de una reserva: permite al jugador CANCELAR (si es próxima) o
/// QUITAR del historial. Libera el slot y borra la reserva.
class _MenuReserva extends StatelessWidget {
  const _MenuReserva({required this.reserva, this.color});
  final Reserva reserva;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final historial = _esHistorial(reserva);
    return PopupMenuButton<String>(
      icon: Icon(Icons.more_vert, size: 20, color: color),
      tooltip: 'Opciones',
      onSelected: (v) {
        if (v == 'cancelar') _confirmarCancelar(context, reserva);
      },
      itemBuilder: (_) => [
        PopupMenuItem(
          value: 'cancelar',
          child: Row(
            children: [
              Icon(historial ? Icons.delete_outline : Icons.cancel_outlined,
                  size: 18, color: clayOscuro),
              const SizedBox(width: 10),
              Text(historial ? 'Quitar del historial' : 'Cancelar reserva'),
            ],
          ),
        ),
      ],
    );
  }
}

/// Confirma y ejecuta la cancelación/eliminación de una reserva del jugador.
Future<void> _confirmarCancelar(BuildContext context, Reserva r) async {
  final historial = _esHistorial(r);
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(historial ? '¿Quitar del historial?' : '¿Cancelar esta reserva?'),
      content: Text(historial
          ? 'Se eliminará esta reserva de tu historial. No se puede deshacer.'
          : 'Se liberará el horario ${r.dia} ${r.horaInicio}–${r.horaFin} y '
              'dejará de aparecer en tus reservas.'),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('No')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: coral),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(historial ? 'Sí, quitar' : 'Sí, cancelar'),
        ),
      ],
    ),
  );
  if (ok != true) return;
  await appState.cancelarReserva(r);
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: bosque,
      content: Text(historial
          ? 'Reserva eliminada del historial.'
          : 'Reserva cancelada. El horario quedó libre.'),
    ));
  }
}

/// Hoja "pase de reserva": el DETALLE que ve el jugador al tocar una reserva o
/// pulsar "Ver pase". Muestra los datos y permite "Cómo llegar".
void _mostrarPase(BuildContext context, Reserva reserva, Cancha? cancha) {
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: Theme.of(context).colorScheme.surface,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) {
      final t = Theme.of(ctx).textTheme;
      final dep = cancha?.deporte ?? Deporte.futbol;
      final id = reserva.id;
      final codigo = (id.length > 6 ? id.substring(id.length - 6) : id)
          .toUpperCase();
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                        color: trazo,
                        borderRadius: BorderRadius.circular(999))),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Container(
                    width: 54,
                    height: 54,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                        gradient: gradienteDeporte(dep),
                        borderRadius: BorderRadius.circular(14)),
                    child: const CourtLines(opacity: 0.5),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(cancha?.nombre ?? 'Cancha',
                            style: t.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        Text(cancha?.club ?? dep.etiqueta,
                            style:
                                t.bodySmall?.copyWith(color: textoTenue)),
                      ],
                    ),
                  ),
                  _EstadoChip(estado: reserva.estado),
                ],
              ),
              const SizedBox(height: 18),
              _PaseFila(Icons.event_outlined, 'Día', reserva.dia),
              _PaseFila(Icons.schedule, 'Hora',
                  '${reserva.horaInicio}–${reserva.horaFin}'),
              _PaseFila(Icons.sports_soccer, 'Deporte', dep.etiqueta),
              _PaseFila(Icons.payments_outlined, 'Precio',
                  '${reserva.monedaSimbolo}${reserva.precio} · pagas en la cancha'),
              _PaseFila(Icons.confirmation_number_outlined, 'Código', codigo),
              const SizedBox(height: 18),
              if (cancha != null)
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: () {
                      Navigator.pop(ctx);
                      UbicacionShare.abrirMapa(cancha.ubicacion);
                    },
                    icon: const Icon(Icons.directions, size: 18),
                    label: const Text('Cómo llegar'),
                  ),
                ),
            ],
          ),
        ),
      );
    },
  );
}

/// Una fila del pase: ícono + etiqueta + valor.
class _PaseFila extends StatelessWidget {
  const _PaseFila(this.icono, this.label, this.valor);
  final IconData icono;
  final String label;
  final String valor;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          Icon(icono, size: 18, color: lima),
          const SizedBox(width: 12),
          Text(label,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(width: 16),
          Expanded(
            child: Text(valor,
                textAlign: TextAlign.right,
                style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

/// Chip de estado de la reserva (Confirmada/Jugada/No-show).
class _EstadoChip extends StatelessWidget {
  const _EstadoChip({required this.estado});
  final EstadoReserva estado;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (estado) {
      EstadoReserva.confirmada || EstadoReserva.nueva => (estadoOkBg, estadoOkFg),
      EstadoReserva.noShow => (estadoBadBg, estadoBadFg),
      _ => (estadoNeutroBg, estadoNeutroFg),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(_estadoLabel(estado),
          style:
              TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}

String _estadoLabel(EstadoReserva e) => switch (e) {
      EstadoReserva.confirmada || EstadoReserva.nueva => 'Confirmada',
      EstadoReserva.completada => 'Jugada',
      EstadoReserva.noShow => 'No-show',
    };

class _Vacio extends StatelessWidget {
  const _Vacio({this.historial = false});
  final bool historial;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.sports_soccer, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            Text(
                historial ? 'Sin reservas anteriores' : 'Aún no tienes reservas',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(
              historial
                  ? 'Aquí verás tus partidos ya jugados.'
                  : 'Busca una cancha en el mapa y reserva tu próximo partido.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue),
            ),
          ],
        ),
      ),
    );
  }
}
