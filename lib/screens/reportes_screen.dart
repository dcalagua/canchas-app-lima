import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class ReportesScreen extends StatelessWidget {
  const ReportesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reportes')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchasActivas = SampleData.canchasDelClubActivo().length;
          final reservasApp =
              appState.reservas.where((r) => r.traidaPorApp).toList();
          final ingresoApp = reservasApp
              .where((r) => r.estado != EstadoReserva.noShow)
              .fold<int>(0, (a, r) => a + r.precio);
          final noShows = appState.reservas
              .where((r) => r.estado == EstadoReserva.noShow)
              .length;
          final totalConResultado = appState.reservas
              .where((r) =>
                  r.estado == EstadoReserva.completada ||
                  r.estado == EstadoReserva.noShow)
              .length;
          final denom = totalConResultado == 0 ? 1 : totalConResultado;
          final pctSinNoShow = ((denom - noShows) * 100) ~/ denom;

          final bloquesValle =
              appState.agenda.where((b) => b.esHoraValle).toList();
          final valleLlenas =
              bloquesValle.where((b) => b.reservaId != null).length;
          final pctValle = bloquesValle.isEmpty
              ? 0
              : (valleLlenas * 100) ~/ bloquesValle.length;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Resumen del mes',
                style: Theme.of(context)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              Text(
                'Tu cuaderno, pero en tiempo real. Lo importante es lo que la app te suma.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: _KpiCard('Canchas activas', '$canchasActivas',
                        'publicadas en la app', verdeCancha),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _KpiCard('Reservas por la app',
                        '${reservasApp.length}', 'este mes', arena),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: _KpiCard('Ingreso vía app', 'S/ $ingresoApp',
                        'reservas nuevas', verdeCancha),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _KpiCard('Horas valle llenas', '$pctValle%',
                        '$valleLlenas de ${bloquesValle.length} hoy', arena),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _InfoCard(
                titulo: 'Anti no-show',
                texto:
                    '$pctSinNoShow% de las reservas con seña llegaron a jugar. La seña con tarjeta reduce los plantones.',
              ),
              const SizedBox(height: 14),
              _InfoCard(
                titulo: 'Club Fundador',
                texto:
                    'Eres Club Fundador de San Borja: posición preferente en la app y condiciones que no se repiten. Cupos limitados por distrito.',
              ),
            ],
          );
        },
      ),
    );
  }
}

class _KpiCard extends StatelessWidget {
  final String titulo;
  final String valor;
  final String sub;
  final Color acento;
  const _KpiCard(this.titulo, this.valor, this.sub, this.acento);

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo, style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: 6),
            Text(
              valor,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: acento,
                  ),
            ),
            const SizedBox(height: 2),
            Text(sub, style: Theme.of(context).textTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final String titulo;
  final String texto;
  const _InfoCard({required this.titulo, required this.texto});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              titulo,
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            Text(texto, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}
