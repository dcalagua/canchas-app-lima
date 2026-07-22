import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Vista del ALUMNO: sus matrículas, los pagos que hizo (comprobante/boleta) y
/// los próximos pagos. Es el "¿dónde veo mis pagos?" del jugador.
class MisClasesScreen extends StatelessWidget {
  const MisClasesScreen({super.key});

  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  String _fecha(DateTime? d) =>
      d == null ? '' : '${d.day} ${_meses[d.month - 1]} ${d.year}';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis clases y pagos')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final matriculas = appState.misMatriculas;
          if (matriculas.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Text(
                    'Aún no estás matriculado en ninguna academia.\n'
                    'Entra a "Academias" y matricúlate, o únete con el código de '
                    'tu profe.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue, height: 1.4)),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
            children: [
              for (final al in matriculas) _cardMatricula(context, al),
            ],
          );
        },
      ),
    );
  }

  Widget _cardMatricula(BuildContext context, Alumno al) {
    final academia = appState.academias
        .cast<Academia?>()
        .firstWhere((a) => a?.id == al.academiaId, orElse: () => null);
    final nombreAca = academia?.nombre ?? 'Academia';
    final mon = academia?.monedaSimbolo ?? 'S/';
    final cuotas = appState.cuotasDeAlumno(al.id)
      ..sort((a, b) => b.vencimiento.compareTo(a.vencimiento));
    final pagadas = cuotas.where((c) => c.pagada).toList();
    final proximas = cuotas.where((c) => !c.pagada).toList()
      ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));
    final totalPagado =
        pagadas.fold<double>(0, (s, c) => s + c.monto);

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Cabecera.
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              color: limaSuave,
              borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
            ),
            child: Row(
              children: [
                const Icon(Icons.sports_tennis, color: lima),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(nombreAca,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 16)),
                      Text('Alumno: ${al.nombre}',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Total pagado: $mon ${totalPagado.toStringAsFixed(2)}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 14, color: lima)),
                _SuscripcionMesAMes(alumnoId: al.id, moneda: mon),
                if (proximas.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Text('Próximos pagos',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 13)),
                  const SizedBox(height: 6),
                  for (final c in proximas)
                    _fila(c.concepto,
                        'Vence ${_fecha(c.vencimiento)}',
                        '$mon ${c.monto.toStringAsFixed(2)}',
                        color: clayOscuro),
                ],
                const SizedBox(height: 12),
                const Text('Comprobantes de pago',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                const SizedBox(height: 6),
                if (pagadas.isEmpty)
                  const Text('Aún no hay pagos registrados.',
                      style: TextStyle(color: textoTenue, fontSize: 13))
                else
                  for (final c in pagadas)
                    InkWell(
                      borderRadius: BorderRadius.circular(10),
                      onTap: () =>
                          _verComprobante(context, nombreAca, al, c, mon),
                      child: _fila(
                          c.concepto,
                          'Pagado ${_fecha(c.fechaPago ?? c.vencimiento)}',
                          '$mon ${c.monto.toStringAsFixed(2)}',
                          trailingIcon: Icons.receipt_long,
                          color: lima),
                    ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _fila(String titulo, String sub, String monto,
      {Color? color, IconData? trailingIcon}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w600)),
                Text(sub,
                    style:
                        const TextStyle(color: textoTenue, fontSize: 12)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(monto,
              style: TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w800,
                  color: color ?? Colors.black)),
          if (trailingIcon != null) ...[
            const SizedBox(width: 6),
            Icon(trailingIcon, size: 18, color: textoTenue),
          ],
        ],
      ),
    );
  }

  void _verComprobante(BuildContext context, String academia, Alumno al,
      Cuota c, String mon) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.receipt_long, color: lima, size: 36),
        title: const Text('Comprobante de pago'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _lineaComp('Academia', academia),
            _lineaComp('Alumno', al.nombre),
            _lineaComp('Concepto', c.concepto),
            _lineaComp('Fecha', _fecha(c.fechaPago ?? c.vencimiento)),
            const Divider(height: 20),
            _lineaComp('Monto', '$mon ${c.monto.toStringAsFixed(2)}',
                fuerte: true),
            const SizedBox(height: 10),
            const Text('Pago procesado por Pichangol.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cerrar')),
        ],
      ),
    );
  }

  Widget _lineaComp(String k, String v, {bool fuerte = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 84,
            child: Text(k,
                style: const TextStyle(color: textoTenue, fontSize: 13)),
          ),
          Expanded(
            child: Text(v,
                style: TextStyle(
                    fontSize: fuerte ? 16 : 13.5,
                    fontWeight: fuerte ? FontWeight.w900 : FontWeight.w600,
                    color: fuerte ? lima : null)),
          ),
        ],
      ),
    );
  }
}

/// Estado de la suscripción "mes a mes" del alumno (débito automático) con opción
/// a cancelar. Solo aparece si el alumno activó el pago mensual automático.
class _SuscripcionMesAMes extends StatefulWidget {
  const _SuscripcionMesAMes({required this.alumnoId, required this.moneda});
  final String alumnoId;
  final String moneda;
  @override
  State<_SuscripcionMesAMes> createState() => _SuscripcionMesAMesState();
}

class _SuscripcionMesAMesState extends State<_SuscripcionMesAMes> {
  Map<String, dynamic>? _sus;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final s = await PagosService.estadoSuscripcionAlumno(widget.alumnoId);
    if (!mounted) return;
    setState(() {
      _sus = s;
      _cargando = false;
    });
  }

  Future<void> _cancelar() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('¿Cancelar el débito automático?'),
        content: const Text(
            'Dejarás de pagar automático cada mes. Podrás volver a matricularte '
            'cuando quieras.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('No')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Sí, cancelar')),
        ],
      ),
    );
    if (ok != true) return;
    await PagosService.cancelarSuscripcionAlumno(widget.alumnoId);
    if (mounted) _cargar();
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const SizedBox.shrink();
    final s = _sus;
    if (s == null || s['activa'] != true) return const SizedBox.shrink();
    final monto = (s['monto_soles'] as num?)?.toDouble() ?? 0;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          const Icon(Icons.autorenew, color: lima, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
                'Mes a mes activo: ${widget.moneda} ${monto.toStringAsFixed(2)} '
                'automático cada mes.',
                style: const TextStyle(fontSize: 12.5, color: bosque)),
          ),
          TextButton(
            onPressed: _cancelar,
            child: const Text('Cancelar',
                style: TextStyle(color: clayOscuro, fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}
