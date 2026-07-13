import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';

/// Reporte de pagos de la academia: dashboard (cobrado / por cobrar / vencido),
/// gráfico de ingresos por mes y lista de cuotas, con filtro por fecha.
class ReporteAcademiaScreen extends StatefulWidget {
  const ReporteAcademiaScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  State<ReporteAcademiaScreen> createState() => _ReporteAcademiaScreenState();
}

enum _Rango { esteMes, mesPasado, tresMeses, todo, personalizado }

class _ReporteAcademiaScreenState extends State<ReporteAcademiaScreen> {
  _Rango _sel = _Rango.esteMes;
  DateTimeRange? _custom;

  static const _mesesCorto = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  /// Fecha de referencia de una cuota: si está pagada, cuándo se cobró; si no,
  /// su vencimiento.
  DateTime _ref(Cuota c) =>
      c.pagada ? (c.fechaPago ?? c.vencimiento) : c.vencimiento;

  DateTimeRange _rangoActual() {
    final hoy = DateTime.now();
    switch (_sel) {
      case _Rango.esteMes:
        return DateTimeRange(
            start: DateTime(hoy.year, hoy.month, 1),
            end: DateTime(hoy.year, hoy.month + 1, 0, 23, 59, 59));
      case _Rango.mesPasado:
        return DateTimeRange(
            start: DateTime(hoy.year, hoy.month - 1, 1),
            end: DateTime(hoy.year, hoy.month, 0, 23, 59, 59));
      case _Rango.tresMeses:
        return DateTimeRange(
            start: DateTime(hoy.year, hoy.month - 2, 1),
            end: DateTime(hoy.year, hoy.month + 1, 0, 23, 59, 59));
      case _Rango.todo:
        return DateTimeRange(start: DateTime(2020), end: DateTime(hoy.year + 5));
      case _Rango.personalizado:
        return _custom ??
            DateTimeRange(
                start: DateTime(hoy.year, hoy.month, 1), end: hoy);
    }
  }

  bool _enRango(DateTime d, DateTimeRange r) =>
      !d.isBefore(DateTime(r.start.year, r.start.month, r.start.day)) &&
      !d.isAfter(r.end);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reporte de pagos')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final hoy = DateTime.now();
          final rango = _rangoActual();
          final todas = appState.cuotasDe(widget.academiaId);
          final enRango =
              todas.where((c) => _enRango(_ref(c), rango)).toList()
                ..sort((a, b) => _ref(b).compareTo(_ref(a)));

          double cobrado = 0, porCobrar = 0, vencido = 0;
          for (final c in enRango) {
            if (c.pagada) {
              cobrado += c.monto;
            } else {
              porCobrar += c.monto;
              if (c.vencidaAl(hoy)) vencido += c.monto;
            }
          }

          // Nombres de alumnos.
          final nombres = <String, String>{
            for (final a in appState.alumnos) a.id: a.nombre
          };

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 30),
            children: [
              _filtro(),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                      child: _Kpi('Cobrado', cobrado,
                          Theme.of(context).colorScheme.primary)),
                  const SizedBox(width: 10),
                  Expanded(child: _Kpi('Por cobrar', porCobrar, textoTenue)),
                  const SizedBox(width: 10),
                  Expanded(child: _Kpi('Vencido', vencido, clayOscuro)),
                ],
              ),
              const SizedBox(height: 20),
              const Text('Ingresos cobrados (últimos 6 meses)',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
              const SizedBox(height: 12),
              _GraficoMeses(cuotasPagadas: todas.where((c) => c.pagada).toList(),
                  ref: _ref, mesesCorto: _mesesCorto),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Movimientos (${enRango.length})',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15)),
                  Text('${enRango.where((c) => c.pagada).length} pagadas',
                      style: const TextStyle(color: textoTenue, fontSize: 12)),
                ],
              ),
              const SizedBox(height: 8),
              if (enRango.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('Sin movimientos en este rango.',
                      style: TextStyle(color: textoTenue)),
                )
              else
                for (final c in enRango)
                  _FilaPago(
                      cuota: c,
                      alumno: nombres[c.alumnoId] ?? 'Alumno',
                      ref: _ref(c),
                      hoy: hoy,
                      mesesCorto: _mesesCorto),
            ],
          );
        },
      ),
    );
  }

  Widget _filtro() {
    Widget chip(String t, _Rango r) => ChoiceChip(
          label: Text(t),
          selected: _sel == r,
          selectedColor: lima,
          onSelected: (_) => setState(() => _sel = r),
        );
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        chip('Este mes', _Rango.esteMes),
        chip('Mes pasado', _Rango.mesPasado),
        chip('3 meses', _Rango.tresMeses),
        chip('Todo', _Rango.todo),
        ActionChip(
          avatar: const Icon(Icons.event, size: 18),
          label: Text(_sel == _Rango.personalizado && _custom != null
              ? '${_custom!.start.day}/${_custom!.start.month} – ${_custom!.end.day}/${_custom!.end.month}'
              : 'Fechas…'),
          onPressed: () async {
            final hoy = DateTime.now();
            final r = await showDateRangePicker(
              context: context,
              firstDate: DateTime(2020),
              lastDate: DateTime(hoy.year + 1, 12, 31),
              initialDateRange: _custom,
              helpText: 'Rango de fechas',
            );
            if (r != null) {
              setState(() {
                _custom = r;
                _sel = _Rango.personalizado;
              });
            }
          },
        ),
      ],
    );
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi(this.titulo, this.monto, this.color);
  final String titulo;
  final double monto;
  final Color color;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 10),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        children: [
          Text('$monedaSimbolo ${monto.toStringAsFixed(0)}',
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 18, color: color)),
          const SizedBox(height: 2),
          Text(titulo,
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
        ],
      ),
    );
  }
}

/// Gráfico de barras simple (sin dependencias): cobrado por mes, últimos 6.
class _GraficoMeses extends StatelessWidget {
  const _GraficoMeses(
      {required this.cuotasPagadas,
      required this.ref,
      required this.mesesCorto});
  final List<Cuota> cuotasPagadas;
  final DateTime Function(Cuota) ref;
  final List<String> mesesCorto;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hoy = DateTime.now();
    // Últimos 6 meses (más antiguo → actual).
    final meses = <DateTime>[
      for (var i = 5; i >= 0; i--) DateTime(hoy.year, hoy.month - i, 1)
    ];
    final totales = <double>[];
    for (final m in meses) {
      double s = 0;
      for (final c in cuotasPagadas) {
        final r = ref(c);
        if (r.year == m.year && r.month == m.month) s += c.monto;
      }
      totales.add(s);
    }
    final maxV = totales.fold<double>(0, (a, b) => b > a ? b : a);
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: SizedBox(
        height: 140,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < meses.length; i++)
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Text(totales[i] == 0 ? '' : totales[i].toStringAsFixed(0),
                        style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: textoTenue)),
                    const SizedBox(height: 4),
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      height: maxV <= 0 ? 3 : (totales[i] / maxV * 90) + 3,
                      decoration: BoxDecoration(
                        color: totales[i] == 0
                            ? trazo
                            : cs.primary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(mesesCorto[meses[i].month - 1],
                        style: const TextStyle(
                            fontSize: 11, color: textoTenue)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _FilaPago extends StatelessWidget {
  const _FilaPago(
      {required this.cuota,
      required this.alumno,
      required this.ref,
      required this.hoy,
      required this.mesesCorto});
  final Cuota cuota;
  final String alumno;
  final DateTime ref;
  final DateTime hoy;
  final List<String> mesesCorto;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final vencida = cuota.vencidaAl(hoy);
    final color = cuota.pagada
        ? cs.primary
        : vencida
            ? clayOscuro
            : textoTenue;
    final estado = cuota.pagada ? 'Pagada' : (vencida ? 'Vencida' : 'Pendiente');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: color.withOpacity(0.14),
            child: Icon(
                cuota.pagada
                    ? Icons.check
                    : (vencida ? Icons.warning_amber_rounded : Icons.schedule),
                size: 18,
                color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(alumno,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontWeight: FontWeight.w700, color: cs.onSurface)),
                Text('${cuota.concepto} · $estado',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: textoTenue, fontSize: 12)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('$monedaSimbolo ${cuota.monto.toStringAsFixed(2)}',
                  style: TextStyle(
                      fontWeight: FontWeight.w800, color: cs.onSurface)),
              Text('${ref.day} ${mesesCorto[ref.month - 1]}',
                  style: const TextStyle(color: textoTenue, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}
