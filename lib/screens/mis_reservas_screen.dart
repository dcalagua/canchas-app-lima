import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';

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
          color: activo ? bosque : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: activo ? bosque : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? lima : textoTenue,
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
    final dep = cancha?.deporte ?? Deporte.futbol;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: pino,
        borderRadius: BorderRadius.circular(22),
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
                        color: pinoOscuro,
                        fontSize: 11,
                        fontWeight: FontWeight.w800)),
              ),
              const Spacer(),
              Text(_estadoLabel(reserva.estado),
                  style: t.bodySmall
                      ?.copyWith(color: Colors.white.withOpacity(0.7))),
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
                        style: t.titleMedium?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w700)),
                    Text(
                      '${cancha?.club ?? dep.etiqueta} · ${reserva.horaInicio}–${reserva.horaFin}',
                      style: t.bodyMedium
                          ?.copyWith(color: Colors.white.withOpacity(0.8)),
                    ),
                    if (reserva.sena > 0)
                      Text('Seña pagada S/${reserva.sena}',
                          style: t.bodySmall?.copyWith(color: lima)),
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
                      backgroundColor: lima, foregroundColor: pinoOscuro),
                  onPressed: () {},
                  icon: const Icon(Icons.directions, size: 18),
                  label: const Text('Cómo llegar'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: BorderSide(color: Colors.white.withOpacity(0.4)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  onPressed: () {},
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
    return Container(
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
          Text('S/${reserva.precio}',
              style: t.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.onSurface)),
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
