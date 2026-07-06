import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Reportes REALES del dueño: ingresos del mes (cobrado), reservas, por cobrar
/// y ocupación de hoy, calculados sobre sus canchas y reservas reales. Sin
/// números demo: si no hay datos, muestra ceros y un aviso honesto.
class ReportesScreen extends StatelessWidget {
  const ReportesScreen({super.key});

  static const _meses = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre',
  ];

  static String _iso(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final ahora = DateTime.now();
    final mes = _meses[ahora.month - 1];
    final claveMes = _iso(ahora).substring(0, 7); // 'YYYY-MM'

    return Scaffold(
      backgroundColor: papelCalido,
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final ids = canchas.map((c) => c.id).toSet();
          final mias =
              appState.reservas.where((r) => ids.contains(r.canchaId)).toList();

          // --- Mes en curso (excluye no-shows) ---
          final delMes = mias
              .where((r) =>
                  r.fecha.startsWith(claveMes) &&
                  r.estado != EstadoReserva.noShow)
              .toList();
          final ingresoMes = delMes
              .where((r) => r.pagado)
              .fold<int>(0, (a, r) => a + r.precio);
          final porCobrarMes = delMes
              .where((r) => !r.pagado)
              .fold<int>(0, (a, r) => a + r.precio);

          // --- Ingresos cobrados por día, últimos 7 días (gráfico real) ---
          final serie = <int>[];
          for (var i = 6; i >= 0; i--) {
            final dia = _iso(ahora.subtract(Duration(days: i)));
            final s = mias
                .where((r) => r.fecha == dia && r.pagado)
                .fold<int>(0, (a, r) => a + r.precio);
            serie.add(s);
          }

          // --- Ocupación de HOY sobre todas mis canchas ---
          final hoy = _iso(ahora);
          final reservasHoy = mias
              .where((r) => r.fecha == hoy && r.estado != EstadoReserva.noShow)
              .length;
          final slotsHoy =
              canchas.fold<int>(0, (s, c) => s + c.horariosSlots().length);
          final pctOcupacion =
              slotsHoy == 0 ? 0 : (reservasHoy * 100) ~/ slotsHoy;

          final sinDatos = mias.isEmpty;

          return ListView(
            padding: EdgeInsets.fromLTRB(
                18, 18 + MediaQuery.of(context).padding.top, 18, 28),
            children: [
              Text('Reportes · $mes', style: t.headlineSmall),
              const SizedBox(height: 4),
              Text('Tu cuaderno, en tiempo real: lo que cobras en tus canchas.',
                  style: t.bodySmall?.copyWith(color: textoTenue)),
              const SizedBox(height: 16),

              // Ingresos del mes (cobrado) + gráfico real de 7 días
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: pino,
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Ingresos del mes (cobrado)',
                        style: t.bodyMedium?.copyWith(color: Colors.white70)),
                    const SizedBox(height: 6),
                    Text('S/ $ingresoMes',
                        style: t.displaySmall?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('Últimos 7 días',
                        style: t.bodySmall?.copyWith(color: Colors.white60)),
                    const SizedBox(height: 12),
                    _MiniBarChart(valores: serie),
                  ],
                ),
              ),
              const SizedBox(height: 14),

              Row(
                children: [
                  Expanded(
                    child: _MetricCard(
                        valor: '${delMes.length}',
                        label: 'reservas este mes'),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _MetricCard(
                        valor: 'S/ $porCobrarMes',
                        label: 'por cobrar este mes'),
                  ),
                ],
              ),
              const SizedBox(height: 14),

              // Ocupación de hoy (real)
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
                        const Icon(Icons.today, color: verde),
                        const SizedBox(width: 8),
                        Text('Ocupación de hoy',
                            style: t.titleSmall
                                ?.copyWith(fontWeight: FontWeight.w700)),
                        const Spacer(),
                        Text('$pctOcupacion%',
                            style: t.bodyMedium?.copyWith(
                                color: verde, fontWeight: FontWeight.w700)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(999),
                      child: LinearProgressIndicator(
                        value: pctOcupacion / 100,
                        minHeight: 8,
                        backgroundColor: const Color(0xFFECEFE8),
                        valueColor: const AlwaysStoppedAnimation(sage),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '$reservasHoy de $slotsHoy franjas reservadas hoy en tus '
                      'canchas.',
                      style:
                          t.bodySmall?.copyWith(color: textoTenue, height: 1.4),
                    ),
                  ],
                ),
              ),

              if (sinDatos) ...[
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.insights, color: bosque),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Aún no hay reservas registradas. Cuando entren '
                          'reservas por la app, aquí verás tus ingresos y '
                          'ocupación en tiempo real.',
                          style: t.bodySmall
                              ?.copyWith(color: bosque, height: 1.4),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

/// Mini gráfico de barras REAL (ingresos por día). Normaliza a la barra máxima;
/// la última (hoy) se resalta en lima.
class _MiniBarChart extends StatelessWidget {
  const _MiniBarChart({required this.valores});
  final List<int> valores;

  @override
  Widget build(BuildContext context) {
    final maxv = valores.fold<int>(0, (m, v) => v > m ? v : m);
    return SizedBox(
      height: 54,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (var i = 0; i < valores.length; i++) ...[
            Expanded(
              child: FractionallySizedBox(
                heightFactor:
                    maxv == 0 ? 0.04 : (valores[i] / maxv).clamp(0.04, 1.0),
                child: Container(
                  decoration: BoxDecoration(
                    color: i == valores.length - 1
                        ? lima
                        : Colors.white.withOpacity(0.25),
                    borderRadius: BorderRadius.circular(5),
                  ),
                ),
              ),
            ),
            if (i != valores.length - 1) const SizedBox(width: 7),
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
