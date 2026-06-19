import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';

/// Reservas hechas por el jugador logueado (rediseño premium).
class MisReservasScreen extends StatelessWidget {
  const MisReservasScreen({super.key});

  Cancha? _cancha(String id) {
    for (final c in appState.todasLasCanchas()) {
      if (c.id == id) return c;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Mis reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final reservas = appState.misReservas;
          if (reservas.isEmpty) return const _Vacio();
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
            itemCount: reservas.length,
            separatorBuilder: (_, __) => const SizedBox(height: 14),
            itemBuilder: (context, i) {
              final r = reservas[i];
              final cancha = _cancha(r.canchaId);
              if (i == 0) return _ReservaDestacada(reserva: r, cancha: cancha);
              return _ReservaCard(reserva: r, cancha: cancha);
            },
          );
        },
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
                      '${dep.etiqueta} · ${reserva.horaInicio}–${reserva.horaFin}',
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
        color: Colors.white,
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
                  style: t.bodySmall?.copyWith(color: textoTenue),
                ),
              ],
            ),
          ),
          Text('S/${reserva.precio}',
              style:
                  t.titleMedium?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

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
            const Text('Aún no tienes reservas',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(
              'Busca una cancha en el mapa y reserva tu próximo partido.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey[600]),
            ),
          ],
        ),
      ),
    );
  }
}
