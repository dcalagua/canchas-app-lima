import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Reporte de cobros del DUEÑO de canchas (panel SaaS): facturación por rango de
/// fechas, reservas, ticket promedio, ingresos por mes y desglose por cancha.
/// Reusa `appState.reservas` (las de las canchas del dueño); no hay tabla nueva.
class ReporteCanchasScreen extends StatefulWidget {
  const ReporteCanchasScreen({super.key, this.embedded = false});

  /// true cuando se muestra DENTRO del hub de Reportes (pestaña "Cobros"): oculta
  /// su propia AppBar para no duplicar la barra del hub.
  final bool embedded;

  @override
  State<ReporteCanchasScreen> createState() => _ReporteCanchasScreenState();
}

enum _Rango { esteMes, mesPasado, tresMeses, todo, personalizado }

class _ReporteCanchasScreenState extends State<ReporteCanchasScreen> {
  _Rango _sel = _Rango.esteMes;
  DateTimeRange? _custom;

  static const _mesesCorto = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  DateTime? _fechaDe(Reserva r) => DateTime.tryParse(r.fecha);

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
            DateTimeRange(start: DateTime(hoy.year, hoy.month, 1), end: hoy);
    }
  }

  bool _enRango(DateTime d, DateTimeRange r) =>
      !d.isBefore(DateTime(r.start.year, r.start.month, r.start.day)) &&
      !d.isAfter(r.end);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: widget.embedded
          ? null
          : AppBar(title: const Text('Reporte de cobros')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final misCanchas = appState.misCanchas;
          final nombres = {for (final c in misCanchas) c.id: c.nombre};
          final mon =
              misCanchas.isNotEmpty ? misCanchas.first.monedaSimbolo : 'S/';
          final rango = _rangoActual();

          // Resuelve cada reserva a la cancha del dueño (tolerante a ids
          // duplicados del mismo local) para no perder cobros en el reporte.
          final canchaDe = <String, Cancha>{}; // reservaId → cancha del dueño
          final delRango = appState.reservas.where((r) {
            final c = appState.miCanchaDeReserva(r.canchaId);
            if (c == null) return false;
            final f = _fechaDe(r);
            if (f == null || !_enRango(f, rango)) return false;
            canchaDe[r.id] = c;
            return true;
          }).toList()
            ..sort((a, b) => (_fechaDe(b) ?? DateTime(2000))
                .compareTo(_fechaDe(a) ?? DateTime(2000)));

          double facturado = 0, porCobrar = 0;
          var nReservas = 0;
          double comisionTotal = 0; // comisión Pichangol estimada del período
          final porCancha = <String, double>{};
          for (final r in delRango) {
            if (r.estado == EstadoReserva.noShow) continue; // no-show ≠ venta
            nReservas++;
            // Reserva canjeada con BONO: su dinero (y comisión) ya se contó al
            // VENDER el bono. Aquí no suma facturado/comisión (evita doble
            // conteo); solo cuenta como reserva/ocupación.
            if (r.esBono) continue;
            final t = r.totalConExtras;
            if (r.pagado) {
              facturado += t;
            } else {
              porCobrar += t;
            }
            // Comisión Pichangol: 5% del precio de la cancha, mínimo S/2 (igual
            // que el backend). Se cobra en toda reserva que trae la app.
            if (r.traidaPorApp) {
              final c = r.precio * 0.05;
              comisionTotal += c < 2 ? 2 : c;
            }
            final cid = canchaDe[r.id]?.id ?? r.canchaId;
            porCancha[cid] = (porCancha[cid] ?? 0) + t;
          }
          final ticket = nReservas > 0 ? (facturado + porCobrar) / nReservas : 0;
          final ranking = porCancha.entries.toList()
            ..sort((a, b) => b.value.compareTo(a.value));
          final maxCancha =
              ranking.isEmpty ? 0.0 : ranking.first.value;

          // Agrupa el ranking por LOCAL (club) — y por país (moneda) si el dueño
          // tiene canchas en más de uno.
          final clubDe = {
            for (final c in misCanchas)
              c.id: (c.club.trim().isEmpty ? 'Mi local' : c.club.trim())
          };
          final monedaDe = {for (final c in misCanchas) c.id: c.monedaSimbolo};
          final porLocal = <String, List<MapEntry<String, double>>>{};
          final monedaLocal = <String, String>{};
          for (final e in ranking) {
            final club = clubDe[e.key] ?? 'Mi local';
            porLocal.putIfAbsent(club, () => []).add(e);
            monedaLocal[club] = monedaDe[e.key] ?? mon;
          }
          final subtotalLocal = {
            for (final k in porLocal.keys)
              k: porLocal[k]!.fold<double>(0, (s, x) => s + x.value)
          };
          final localesOrden = porLocal.keys.toList()
            ..sort((a, b) => subtotalLocal[b]!.compareTo(subtotalLocal[a]!));
          final variosLocales = porLocal.length > 1;
          final variosPaisesR = monedaLocal.values.toSet().length > 1;

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 30),
            children: [
              _filtro(),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                      child: _Kpi('Cobrado', '$mon ${facturado.toStringAsFixed(0)}',
                          Theme.of(context).colorScheme.primary)),
                  const SizedBox(width: 10),
                  Expanded(
                      child: _Kpi('Por cobrar',
                          '$mon ${porCobrar.toStringAsFixed(0)}', textoTenue)),
                  const SizedBox(width: 10),
                  Expanded(child: _Kpi('Reservas', '$nReservas', bosque)),
                ],
              ),
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
                decoration: BoxDecoration(
                    color: limaSuave, borderRadius: BorderRadius.circular(14)),
                child: Row(
                  children: [
                    const Icon(Icons.confirmation_number_outlined,
                        color: bosque, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text('Ticket promedio por reserva',
                          style: TextStyle(color: bosque, fontSize: 13)),
                    ),
                    Text('$mon ${ticket.toStringAsFixed(2)}',
                        style: const TextStyle(
                            color: bosque, fontWeight: FontWeight.w800)),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              _ResumenComision(moneda: mon),
              const SizedBox(height: 20),
              const Text('Ingresos cobrados (últimos 6 meses)',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
              const SizedBox(height: 12),
              _GraficoMeses(
                pagadas: appState.reservas
                    .where((r) =>
                        r.pagado &&
                        r.estado != EstadoReserva.noShow &&
                        appState.miCanchaDeReserva(r.canchaId) != null)
                    .toList(),
                fechaDe: _fechaDe,
                mesesCorto: _mesesCorto,
              ),
              const SizedBox(height: 20),
              if (ranking.isNotEmpty) ...[
                const Text('Por cancha',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 10),
                // Un solo local → lista plana. Varios → agrupado por local, con
                // su subtotal (y país si el dueño está en más de uno).
                if (!variosLocales)
                  for (final e in ranking)
                    _BarraCancha(
                      nombre: nombres[e.key] ?? 'Cancha',
                      monto: e.value,
                      max: maxCancha,
                      moneda: mon,
                    )
                else
                  for (final club in localesOrden) ...[
                    _LocalHeaderRep(
                      club: club,
                      pais: variosPaisesR
                          ? _paisDeMonedaRep(monedaLocal[club]!)
                          : '',
                      subtotal: subtotalLocal[club]!,
                      moneda: monedaLocal[club]!,
                    ),
                    const SizedBox(height: 8),
                    for (final e in porLocal[club]!)
                      _BarraCancha(
                        nombre: nombres[e.key] ?? 'Cancha',
                        monto: e.value,
                        max: maxCancha,
                        moneda: monedaLocal[club]!,
                      ),
                    const SizedBox(height: 16),
                  ],
                const SizedBox(height: 20),
              ],
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Reservas (${delRango.where((r) => r.estado != EstadoReserva.noShow).length})',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15)),
                  Text('${delRango.where((r) => r.pagado).length} pagadas',
                      style: const TextStyle(color: textoTenue, fontSize: 12)),
                ],
              ),
              const SizedBox(height: 8),
              if (delRango.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('Sin reservas en este rango.',
                      style: TextStyle(color: textoTenue)),
                )
              else
                for (final r in delRango)
                  _FilaReserva(
                      reserva: r,
                      cancha: canchaDe[r.id]?.nombre ??
                          nombres[r.canchaId] ??
                          'Cancha',
                      moneda: mon,
                      mesesCorto: _mesesCorto),
              const SizedBox(height: 20),
              // Descargar/compartir el reporte (hoja del sistema: WhatsApp, PDF,
              // correo, Drive…). Comparte el resumen del período.
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: bosque,
                    side: const BorderSide(color: trazo),
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  onPressed: () => _compartirReporte(
                    moneda: mon,
                    cobrado: facturado,
                    porCobrar: porCobrar,
                    comision: comisionTotal,
                    nReservas: nReservas,
                    porLocal: {
                      for (final club in localesOrden)
                        club: subtotalLocal[club]!
                    },
                  ),
                  icon: const Icon(Icons.ios_share, color: teal),
                  label: const Text('Compartir / descargar reporte',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _compartirReporte({
    required String moneda,
    required double cobrado,
    required double porCobrar,
    required double comision,
    required int nReservas,
    required Map<String, double> porLocal,
  }) {
    final bruto = cobrado + porCobrar;
    // Desglose de "Por recibir" por fuente (mismos movimientos que la billetera).
    final liqs = appState.movimientos.where((m) =>
        m.tipo == TipoMovimiento.liquidacion && !m.liquidado);
    var recOnline = 0, recSaldo = 0, nOnline = 0, nSaldo = 0;
    var comOnline = 0.0, comSaldo = 0.0;
    for (final m in liqs) {
      if (m.fuente == 'saldo') {
        recSaldo += m.monto;
        comSaldo += m.comisionSoles;
        nSaldo++;
      } else {
        recOnline += m.monto;
        comOnline += m.comisionSoles;
        nOnline++;
      }
    }
    final b = StringBuffer()
      ..writeln('📊 Reporte de cobros · Pichangol')
      ..writeln('')
      ..writeln('Generado: $moneda ${bruto.toStringAsFixed(2)}')
      ..writeln('  • Cobrado: $moneda ${cobrado.toStringAsFixed(2)}')
      ..writeln('  • Por cobrar: $moneda ${porCobrar.toStringAsFixed(2)}')
      ..writeln('Reservas: $nReservas');
    if (recOnline + recSaldo > 0) {
      b
        ..writeln('')
        ..writeln('Por recibir de Pichangol: $moneda ${recOnline + recSaldo}')
        ..writeln('  • Online ($nOnline): $moneda $recOnline '
            '(comisión $moneda ${comOnline.round()} del pago)')
        ..writeln('  • Con tu saldo ($nSaldo): $moneda $recSaldo al 100% '
            '(comisión $moneda ${comSaldo.round()} de tu saldo)')
        ..writeln('Cuadra con "Por recibir" de tu billetera.');
    }
    if (porLocal.length > 1) {
      b.writeln('');
      b.writeln('Por local:');
      porLocal.forEach((club, monto) =>
          b.writeln('  • $club: $moneda ${monto.toStringAsFixed(2)}'));
    }
    Share.share(b.toString());
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
  const _Kpi(this.titulo, this.valor, this.color);
  final String titulo;
  final String valor;
  final Color color;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        children: [
          Text(valor,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 17, color: color)),
          const SizedBox(height: 2),
          Text(titulo,
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
        ],
      ),
    );
  }
}

/// Nombre de país desde el símbolo de moneda de la cancha (proxy de país).
String _paisDeMonedaRep(String m) => switch (m.trim()) {
      'S/' => 'Perú',
      'Bs' => 'Bolivia',
      r'$' => 'Ecuador',
      _ => m,
    };

/// Resumen de COMISIÓN del período: lo generado, cuánto se lleva Pichangol y el
/// NETO del dueño. Transparencia total (nada escondido).
/// Desglose de "Cuánto vas a recibir de Pichangol", SEPARADO por fuente de la
/// comisión, para que cuadre EXACTO con "Por recibir" de la billetera. Usa los
/// MISMOS movimientos del backend que la billetera (no una estimación local):
///  - Reservas online → la comisión salió del PAGO, recibes el NETO.
///  - Reservas pagadas con tu SALDO → recibes el 100%, la comisión salió de tu
///    billetera (aparece como un egreso "Comisión" en tu saldo).
class _ResumenComision extends StatelessWidget {
  const _ResumenComision({required this.moneda});
  final String moneda;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Fuente ÚNICA de verdad = los movimientos del backend (los mismos que suma
    // la billetera en "Por recibir"), para que ambos números cuadren SIEMPRE.
    final liqs = appState.movimientos.where((m) =>
        m.tipo == TipoMovimiento.liquidacion && !m.liquidado);
    var recOnline = 0, recSaldo = 0, nOnline = 0, nSaldo = 0;
    var comOnline = 0.0, comSaldo = 0.0;
    for (final m in liqs) {
      if (m.fuente == 'saldo') {
        recSaldo += m.monto; // recibes el 100% (bruto)
        comSaldo += m.comisionSoles;
        nSaldo++;
      } else {
        recOnline += m.monto; // recibes el neto
        comOnline += m.comisionSoles;
        nOnline++;
      }
    }
    final totalRecibir = recOnline + recSaldo; // == "Por recibir" de la billetera
    final comTotal = comOnline + comSaldo;
    // Nada por recibir → no mostramos el card (evita "0" confusos).
    if (totalRecibir <= 0) return const SizedBox.shrink();

    Widget bloque(String titulo, String sub, int recibe) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titulo,
                        style: TextStyle(
                            color: cs.onSurface,
                            fontSize: 13.5,
                            fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(sub,
                        style: TextStyle(
                            color: textoTenueDe(context),
                            fontSize: 11.5,
                            height: 1.3)),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text('$moneda $recibe',
                  style: TextStyle(
                      color: cs.primary,
                      fontSize: 15,
                      fontWeight: FontWeight.w800)),
            ],
          ),
        );

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Cuánto vas a recibir de Pichangol',
              style: TextStyle(
                  color: cs.onSurface,
                  fontWeight: FontWeight.w800,
                  fontSize: 13.5)),
          const SizedBox(height: 4),
          if (nOnline > 0)
            bloque(
                'Reservas online ($nOnline)',
                'La comisión ($moneda ${comOnline.round()}) se descontó del pago '
                    '· recibes el neto',
                recOnline),
          if (nSaldo > 0)
            bloque(
                'Reservas pagadas con tu saldo ($nSaldo)',
                'Recibes el 100% · la comisión ($moneda ${comSaldo.round()}) '
                    'salió de tu billetera',
                recSaldo),
          const Divider(height: 16, color: trazo),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Total por recibir',
                  style: TextStyle(
                      color: cs.onSurface,
                      fontWeight: FontWeight.w800,
                      fontSize: 14)),
              Text('$moneda $totalRecibir',
                  style: TextStyle(
                      color: cs.primary,
                      fontWeight: FontWeight.w800,
                      fontSize: 17)),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.check_circle_outline, size: 15, color: teal),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Este total es EXACTO el "Por recibir" de tu billetera. '
                  'Comisión total: $moneda ${comTotal.round()} '
                  '($moneda ${comOnline.round()} del pago + '
                  '$moneda ${comSaldo.round()} de tu saldo).',
                  style: TextStyle(
                      color: textoTenueDe(context),
                      fontSize: 11.5,
                      height: 1.35),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Cabecera de sección por LOCAL en el reporte: nombre del local (+ país si el
/// dueño tiene canchas en más de uno) y el subtotal facturado del local.
class _LocalHeaderRep extends StatelessWidget {
  const _LocalHeaderRep({
    required this.club,
    required this.pais,
    required this.subtotal,
    required this.moneda,
  });
  final String club;
  final String pais;
  final double subtotal;
  final String moneda;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 2),
      child: Row(
        children: [
          const Icon(Icons.stadium_outlined, size: 17, color: bosque),
          const SizedBox(width: 8),
          Expanded(
            child: Text(pais.isEmpty ? club : '$club · $pais',
                style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 13.5),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ),
          Text('$moneda ${subtotal.toStringAsFixed(0)}',
              style: const TextStyle(
                  fontWeight: FontWeight.w800, color: bosque, fontSize: 13.5)),
        ],
      ),
    );
  }
}

/// Barra horizontal simple: cuánto generó cada cancha (relativo al máximo).
class _BarraCancha extends StatelessWidget {
  const _BarraCancha(
      {required this.nombre,
      required this.monto,
      required this.max,
      required this.moneda});
  final String nombre;
  final double monto;
  final double max;
  final String moneda;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final frac = max <= 0 ? 0.0 : (monto / max).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              Text('$moneda ${monto.toStringAsFixed(0)}',
                  style: TextStyle(
                      fontWeight: FontWeight.w800, color: cs.primary)),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: frac,
              minHeight: 8,
              backgroundColor: trazo,
              valueColor: AlwaysStoppedAnimation(cs.primary),
            ),
          ),
        ],
      ),
    );
  }
}

/// Gráfico de barras (sin dependencias): cobrado por mes, últimos 6.
class _GraficoMeses extends StatelessWidget {
  const _GraficoMeses(
      {required this.pagadas, required this.fechaDe, required this.mesesCorto});
  final List<Reserva> pagadas;
  final DateTime? Function(Reserva) fechaDe;
  final List<String> mesesCorto;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hoy = DateTime.now();
    final meses = <DateTime>[
      for (var i = 5; i >= 0; i--) DateTime(hoy.year, hoy.month - i, 1)
    ];
    final totales = <double>[];
    for (final m in meses) {
      double s = 0;
      for (final r in pagadas) {
        final f = fechaDe(r);
        if (f != null && f.year == m.year && f.month == m.month) {
          s += r.totalConExtras;
        }
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
                        color: totales[i] == 0 ? trazo : cs.primary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(mesesCorto[meses[i].month - 1],
                        style:
                            const TextStyle(fontSize: 11, color: textoTenue)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _FilaReserva extends StatelessWidget {
  const _FilaReserva(
      {required this.reserva,
      required this.cancha,
      required this.moneda,
      required this.mesesCorto});
  final Reserva reserva;
  final String cancha;
  final String moneda;
  final List<String> mesesCorto;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final noShow = reserva.estado == EstadoReserva.noShow;
    final color = noShow
        ? clayOscuro
        : (reserva.pagado ? cs.primary : textoTenue);
    final estado = noShow ? 'No-show' : (reserva.pagado ? 'Pagado' : 'Por cobrar');
    final f = DateTime.tryParse(reserva.fecha);
    final fechaTxt =
        f != null ? '${f.day} ${mesesCorto[f.month - 1]}' : reserva.dia;
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
                noShow
                    ? Icons.person_off_outlined
                    : (reserva.pagado ? Icons.check : Icons.schedule),
                size: 18,
                color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(reserva.jugador,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontWeight: FontWeight.w700, color: cs.onSurface)),
                Text('$cancha · ${reserva.horaInicio} · $estado',
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
              Text('$moneda ${reserva.totalConExtras.toStringAsFixed(2)}',
                  style: TextStyle(
                      fontWeight: FontWeight.w800,
                      color: noShow ? textoTenue : cs.onSurface,
                      decoration:
                          noShow ? TextDecoration.lineThrough : null)),
              Text(fechaTxt,
                  style: const TextStyle(color: textoTenue, fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }
}
