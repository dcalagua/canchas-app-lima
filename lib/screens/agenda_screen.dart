import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class AgendaScreen extends StatelessWidget {
  const AgendaScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final canchas = SampleData.canchasDelClubActivo();
    return Scaffold(
      appBar: AppBar(title: const Text('Agenda de hoy')),
      floatingActionButton: Builder(
        builder: (context) => FloatingActionButton.extended(
          onPressed: () {
            final res = appState.simularReservaEntrante();
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(res != null
                    ? '🎾 ¡Entró una reserva! $res'
                    : 'No quedan horas libres abiertas'),
              ),
            );
          },
          backgroundColor: arena,
          foregroundColor: Colors.white,
          icon: const Icon(Icons.bolt),
          label: const Text('Simular reserva'),
        ),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                appState.nombreClub,
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              Text(
                'Toca “Simular reserva” en la demo para que el dueño la vea entrar.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              const _Leyenda(),
              const SizedBox(height: 12),
              for (final cancha in canchas) ...[
                _CanchaCard(
                  nombre: cancha.nombre,
                  bloques: appState.bloquesDe(cancha.id),
                ),
                const SizedBox(height: 16),
              ],
              const SizedBox(height: 72),
            ],
          );
        },
      ),
    );
  }
}

class _Leyenda extends StatelessWidget {
  const _Leyenda();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 16,
      runSpacing: 6,
      children: const [
        _Punto(verdeCancha, 'Reservada'),
        _Punto(arena, 'Hora valle libre'),
        _Punto(Color(0xFFD7E3DB), 'Libre'),
      ],
    );
  }
}

class _Punto extends StatelessWidget {
  final Color color;
  final String texto;
  const _Punto(this.color, this.texto);

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(texto, style: Theme.of(context).textTheme.labelSmall),
      ],
    );
  }
}

class _CanchaCard extends StatelessWidget {
  final String nombre;
  final List<BloqueHorario> bloques;
  const _CanchaCard({required this.nombre, required this.bloques});

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
            const SizedBox(height: 10),
            for (final b in bloques) ...[
              _BloqueFila(b),
              const SizedBox(height: 8),
            ],
          ],
        ),
      ),
    );
  }
}

class _BloqueFila extends StatelessWidget {
  final BloqueHorario bloque;
  const _BloqueFila(this.bloque);

  @override
  Widget build(BuildContext context) {
    final ocupada = bloque.reservaId != null;
    final reserva =
        bloque.reservaId != null ? appState.reservaPorId(bloque.reservaId!) : null;
    final fondo = ocupada
        ? verdeCancha
        : (bloque.esHoraValle ? arena : const Color(0xFFD7E3DB));
    final contenido =
        (ocupada || bloque.esHoraValle) ? Colors.white : const Color(0xFF20302A);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          width: 64,
          height: 36,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: fondo,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            bloque.hora,
            style: TextStyle(color: contenido, fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                ocupada
                    ? (reserva?.jugador ?? 'Reservada')
                    : (bloque.esHoraValle
                        ? 'Hora valle libre — ¡llénala!'
                        : 'Libre'),
                style: TextStyle(
                  fontWeight: ocupada ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
              if (ocupada && reserva != null)
                Text(
                  '${reserva.traidaPorApp ? "Por la app" : "Cliente de siempre"} · ${reserva.horaInicio}–${reserva.horaFin}',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
            ],
          ),
        ),
      ],
    );
  }
}
