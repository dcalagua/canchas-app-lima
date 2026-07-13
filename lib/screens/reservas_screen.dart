import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/chips.dart';
import '../utils/moneda.dart';

class ReservasScreen extends StatelessWidget {
  const ReservasScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final nuevas = appState.reservas.where((r) => r.traidaPorApp).length;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                '$nuevas reservas traídas por la app. Solo estas generan comisión en Fase 2 — tus clientes de siempre nunca.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              for (final r in appState.reservas) ...[
                _ReservaCard(r),
                const SizedBox(height: 12),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _ReservaCard extends StatelessWidget {
  final Reserva reserva;
  const _ReservaCard(this.reserva);

  @override
  Widget build(BuildContext context) {
    final cancha = SampleData.canchaPorId(reserva.canchaId);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    reserva.jugador,
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 8),
                ChipEstado(reserva.estado),
              ],
            ),
            const SizedBox(height: 2),
            Text(
              '${cancha?.nombre ?? "Cancha"} · ${reserva.dia} ${reserva.horaInicio}–${reserva.horaFin}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (reserva.nivel != '—')
              Text(
                'Nivel: ${reserva.nivel}',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            const SizedBox(height: 10),
            Row(
              children: [
                if (reserva.traidaPorApp)
                  const EtiquetaChip('Reserva nueva', fondo: verdeCancha)
                else
                  const EtiquetaChip('Cliente de siempre', fondo: Color(0xFF6B7B72)),
                if (reserva.sena > 0) ...[
                  const SizedBox(width: 8),
                  const Icon(Icons.credit_card, color: arena, size: 18),
                  const SizedBox(width: 4),
                  Text(
                    'Seña $monedaSimbolo ${reserva.sena}',
                    style: const TextStyle(
                      color: arena,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ],
                const Spacer(),
                Text(
                  '$monedaSimbolo ${reserva.precio}',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: verdeCancha,
                      ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
