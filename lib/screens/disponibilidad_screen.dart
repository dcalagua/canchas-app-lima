import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class DisponibilidadScreen extends StatelessWidget {
  const DisponibilidadScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final canchas = SampleData.canchasDelClubActivo();
    return Scaffold(
      appBar: AppBar(title: const Text('Disponibilidad')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Abre las horas que quieres publicar en la app. Las mañanas (horas valle) son las que más conviene llenar.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              for (final cancha in canchas) ...[
                _CanchaDisponibilidad(
                  nombre: cancha.nombre,
                  bloques: appState.bloquesDe(cancha.id),
                ),
                const SizedBox(height: 16),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _CanchaDisponibilidad extends StatelessWidget {
  final String nombre;
  final List<BloqueHorario> bloques;
  const _CanchaDisponibilidad({required this.nombre, required this.bloques});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              nombre,
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
            for (int i = 0; i < bloques.length; i++) ...[
              if (i > 0) const Divider(height: 1),
              _FilaDisponibilidad(bloques[i]),
            ],
          ],
        ),
      ),
    );
  }
}

class _FilaDisponibilidad extends StatelessWidget {
  final BloqueHorario bloque;
  const _FilaDisponibilidad(this.bloque);

  @override
  Widget build(BuildContext context) {
    final ocupada = bloque.reservaId != null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          SizedBox(
            width: 64,
            child: Text(
              bloque.hora,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ocupada
                      ? 'Reservada'
                      : (bloque.esHoraValle ? 'Hora valle' : 'Horario regular'),
                ),
                if (bloque.esHoraValle && !ocupada)
                  const Text(
                    'Prioriza abrirla',
                    style: TextStyle(
                      color: arena,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
                    ),
                  ),
              ],
            ),
          ),
          if (ocupada)
            const Icon(Icons.lock, color: verdeCancha)
          else
            Switch(
              value: bloque.disponible,
              onChanged: (_) => appState.alternarDisponibilidad(bloque),
            ),
        ],
      ),
    );
  }
}
