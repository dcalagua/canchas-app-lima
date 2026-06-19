import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/chips.dart';

/// Reservas hechas por el jugador logueado.
class MisReservasScreen extends StatelessWidget {
  const MisReservasScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final reservas = appState.misReservas;
          if (reservas.isEmpty) {
            return _Vacio();
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: reservas.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (context, i) => _ReservaCard(reservas[i]),
          );
        },
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.sports_tennis, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            const Text(
              'Aún no tienes reservas',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
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

class _ReservaCard extends StatelessWidget {
  final Reserva reserva;
  const _ReservaCard(this.reserva);

  @override
  Widget build(BuildContext context) {
    final cancha = SampleData.canchaPorId(reserva.canchaId);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 54,
              height: 54,
              decoration: BoxDecoration(
                color: verdeCancha,
                borderRadius: BorderRadius.circular(12),
              ),
              alignment: Alignment.center,
              child: Text(
                reserva.horaInicio,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    cancha?.nombre ?? 'Cancha',
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${cancha?.club ?? ''} · ${reserva.dia} ${reserva.horaInicio}–${reserva.horaFin}',
                    style: TextStyle(color: Colors.grey[600], fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      ChipEstado(reserva.estado),
                      const SizedBox(width: 8),
                      if (reserva.sena > 0)
                        Text(
                          'Seña S/ ${reserva.sena}',
                          style: const TextStyle(
                              color: arena,
                              fontWeight: FontWeight.w600,
                              fontSize: 12),
                        ),
                    ],
                  ),
                ],
              ),
            ),
            Text(
              'S/ ${reserva.precio}',
              style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  color: verdeCancha,
                  fontSize: 16),
            ),
          ],
        ),
      ),
    );
  }
}
