import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Reportes del club (rediseño): tarjeta de ingresos pino con mini-gráfico,
/// métricas clave y un insight de horas valle.
class ReportesScreen extends StatelessWidget {
  const ReportesScreen({super.key});

  static const _meses = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre',
  ];

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final mes = _meses[DateTime.now().month - 1];

    return Scaffold(
      backgroundColor: papelCalido,
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final reservasApp =
              appState.reservas.where((r) => r.traidaPorApp).toList();
          final ingresoApp = reservasApp
              .where((r) => r.estado != EstadoReserva.noShow)
              .fold<int>(0, (a, r) => a + r.precio);
          final pctApp = appState.reservas.isEmpty
              ? 0
              : (reservasApp.length * 100) ~/ appState.reservas.length;
          final senasCobradas = reservasApp.fold<int>(0, (a, r) => a + r.sena);

          final bloquesValle =
              appState.agenda.where((b) => b.esHoraValle).toList();
          final valleLlenas =
              bloquesValle.where((b) => b.reservaId != null).length;
          final pctValle = bloquesValle.isEmpty
              ? 0
              : (valleLlenas * 100) ~/ bloquesValle.length;

          return ListView(
            padding: EdgeInsets.fromLTRB(
                18, 18 + MediaQuery.of(context).padding.top, 18, 28),
            children: [
              Row(
                children: [
                  GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    child: const Padding(
                      padding: EdgeInsets.only(right: 10),
                      child: Icon(Icons.arrow_back_ios_new,
                          color: tinta, size: 20),
                    ),
                  ),
                  Expanded(
                    child: Text('Reportes · $mes', style: t.headlineSmall),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text('Tu cuaderno, en tiempo real. Lo que importa es lo que la '
                  'app te suma.',
                  style: t.bodySmall?.copyWith(color: textoTenue)),
              const SizedBox(height: 16),

              // Tarjeta de ingresos (pino) con mini-gráfico
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: pino,
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Ingreso vía app',
                            style: t.bodyMedium
                                ?.copyWith(color: Colors.white70)),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 9, vertical: 4),
                          decoration: BoxDecoration(
                              color: lima.withOpacity(0.18),
                              borderRadius: BorderRadius.circular(999)),
                          child: Text('↑ 23% vs. mes pasado',
                              style: t.labelSmall?.copyWith(
                                  color: lima, fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text('S/ $ingresoApp',
                        style: t.displaySmall?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 16),
                    const _MiniBarChart(),
                  ],
                ),
              ),
              const SizedBox(height: 14),

              Row(
                children: [
                  Expanded(
                    child: _MetricCard(
                        valor: '$pctApp%',
                        label: 'reservas traídas por la app'),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _MetricCard(
                        valor: 'S/ $senasCobradas',
                        label: 'en señas (anti no-show)'),
                  ),
                ],
              ),
              const SizedBox(height: 14),

              // Insight horas valle
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: trazo),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.wb_twilight, color: clayOscuro),
                        const SizedBox(width: 8),
                        Text('Horas valle',
                            style: t.titleSmall
                                ?.copyWith(fontWeight: FontWeight.w700)),
                        const Spacer(),
                        Text('$pctValle% llenas',
                            style: t.bodyMedium?.copyWith(
                                color: clayOscuro,
                                fontWeight: FontWeight.w700)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(999),
                      child: LinearProgressIndicator(
                        value: pctValle / 100,
                        minHeight: 8,
                        backgroundColor: const Color(0xFFF0ECE2),
                        valueColor: const AlwaysStoppedAnimation(clay),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Activa una promo de -20% de 7 a 11 a.m. para llenar las '
                      'mañanas (tu oro de Fase 1).',
                      style: t.bodySmall?.copyWith(color: textoTenue, height: 1.4),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),

              if (SampleData.canchasDelClubActivo().any((c) => c.clubFundador))
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: pinoOscuro,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(
                    children: [
                      const _BadgeChip('★ CLUB FUNDADOR'),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Posición preferente en la app y condiciones que no '
                          'se repiten. Cupos limitados por distrito.',
                          style: t.bodySmall
                              ?.copyWith(color: Colors.white70, height: 1.4),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Mini gráfico de barras ilustrativo (sparkline) para la tarjeta de ingresos.
class _MiniBarChart extends StatelessWidget {
  const _MiniBarChart();

  @override
  Widget build(BuildContext context) {
    const alturas = [0.35, 0.5, 0.42, 0.6, 0.55, 0.78, 1.0];
    return SizedBox(
      height: 54,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var i = 0; i < alturas.length; i++) ...[
            Expanded(
              child: FractionallySizedBox(
                heightFactor: alturas[i],
                child: Container(
                  decoration: BoxDecoration(
                    color: i >= alturas.length - 2
                        ? lima
                        : Colors.white.withOpacity(0.25),
                    borderRadius: BorderRadius.circular(5),
                  ),
                ),
              ),
            ),
            if (i != alturas.length - 1) const SizedBox(width: 7),
          ],
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.valor, required this.label});
  final String valor;
  final String label;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(valor,
              style: t.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
          const SizedBox(height: 4),
          Text(label, style: t.bodySmall?.copyWith(color: textoTenue)),
        ],
      ),
    );
  }
}

class _BadgeChip extends StatelessWidget {
  const _BadgeChip(this.texto);
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration:
          BoxDecoration(color: lima, borderRadius: BorderRadius.circular(999)),
      child: Text(texto,
          style: const TextStyle(
              color: pinoOscuro, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}
