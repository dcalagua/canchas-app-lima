import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'recargar_saldo_screen.dart';

/// MI BILLETERA: saldo único del usuario + historial COMPLETO de movimientos
/// (recargas por Yape/tarjeta que entran, y lo que consume: Pichangol Pro,
/// inscripciones a torneos, servicios, comisiones). Cada movimiento tiene su
/// recibo compartible.
class BilleteraScreen extends StatefulWidget {
  const BilleteraScreen({super.key});
  @override
  State<BilleteraScreen> createState() => _BilleteraScreenState();
}

class _BilleteraScreenState extends State<BilleteraScreen> {
  static const _mesesCorto = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  @override
  void initState() {
    super.initState();
    appState.sincronizarSaldo();
  }

  String _fechaLarga(String iso) {
    final d = DateTime.tryParse(iso)?.toLocal();
    if (d == null) return '';
    return '${d.day} ${_mesesCorto[d.month - 1]} ${d.year}, '
        '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final mon = appState.monedaSaldoSimbolo;
    return Scaffold(
      appBar: AppBar(title: const Text('Mi billetera')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final movs = appState.movimientos;
          return RefreshIndicator(
            color: lima,
            onRefresh: () => appState.sincronizarSaldo(),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
              children: [
                // Saldo.
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [bosque, Color(0xFF1E5C4C)],
                    ),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Saldo Pichangol',
                          style: TextStyle(color: Colors.white70, fontSize: 13)),
                      const SizedBox(height: 6),
                      Text('$mon ${appState.saldoClub}.00',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 34,
                              fontWeight: FontWeight.w900)),
                      const SizedBox(height: 4),
                      const Text(
                          'Es tu saldo único: recargas por Yape/tarjeta y de aquí '
                          'salen Pro, torneos y servicios.',
                          style: TextStyle(color: Colors.white60, fontSize: 12)),
                      const SizedBox(height: 14),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(
                              backgroundColor: Colors.white,
                              foregroundColor: bosque,
                              padding: const EdgeInsets.symmetric(vertical: 13)),
                          icon: const Icon(Icons.add),
                          label: const Text('Recargar saldo',
                              style: TextStyle(fontWeight: FontWeight.w800)),
                          onPressed: () async {
                            await Navigator.of(context).push(MaterialPageRoute(
                                builder: (_) => RecargarSaldoScreen(
                                    duenoId: appState.usuario?.email,
                                    titulo: 'Recargar saldo')));
                            await appState.sincronizarSaldo();
                          },
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                const Text('Movimientos',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                const SizedBox(height: 8),
                if (movs.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Text(
                        'Aún no tienes movimientos. Recarga tu saldo para empezar.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: textoTenue)),
                  )
                else
                  for (final m in movs) _FilaMovimiento(m: m, moneda: mon, onTap: () => _recibo(m, mon)),
              ],
            ),
          );
        },
      ),
    );
  }

  // ── Recibo ─────────────────────────────────────────────────────────────────
  void _recibo(MovimientoSaldo m, String mon) {
    final ingreso = m.montoSoles >= 0;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 26),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('Recibo',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
                const Spacer(),
                if (m.comprobante > 0)
                  Text('N.º ${m.comprobante.toString().padLeft(4, '0')}',
                      style: const TextStyle(color: textoTenue)),
              ],
            ),
            const SizedBox(height: 16),
            Center(
              child: Text(
                  '${ingreso ? '+' : '−'} $mon ${m.montoSoles.abs().toStringAsFixed(2)}',
                  style: TextStyle(
                      fontWeight: FontWeight.w900,
                      fontSize: 30,
                      color: ingreso ? bosque : clayOscuro)),
            ),
            const SizedBox(height: 16),
            _filaRecibo('Concepto', m.concepto),
            _filaRecibo('Tipo', ingreso ? 'Ingreso' : 'Egreso'),
            if (m.fechaIso.isNotEmpty)
              _filaRecibo('Fecha', _fechaLarga(m.fechaIso)),
            if (m.tipo == TipoMovimiento.liquidacion)
              _filaRecibo('Estado', m.liquidado ? 'Recibido' : 'Por recibir'),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                    foregroundColor: bosque,
                    side: const BorderSide(color: bosque),
                    padding: const EdgeInsets.symmetric(vertical: 12)),
                icon: const Icon(Icons.ios_share, size: 18),
                label: const Text('Compartir recibo',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                onPressed: () => _compartirRecibo(m, mon),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _filaRecibo(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
                width: 88,
                child: Text(k,
                    style: const TextStyle(color: textoTenue, fontSize: 13))),
            Expanded(
                child: Text(v,
                    style: const TextStyle(fontWeight: FontWeight.w600))),
          ],
        ),
      );

  Future<void> _compartirRecibo(MovimientoSaldo m, String mon) async {
    final ingreso = m.montoSoles >= 0;
    final verde = PdfColor.fromInt(0xFF14463A);
    final doc = pw.Document();
    doc.addPage(pw.Page(
      pageFormat: PdfPageFormat(320, 460, marginAll: 24),
      build: (context) => pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.stretch,
        children: [
          pw.Container(
            padding: const pw.EdgeInsets.all(14),
            decoration: pw.BoxDecoration(
                color: verde, borderRadius: pw.BorderRadius.circular(12)),
            child: pw.Column(children: [
              pw.Text('Pichangol',
                  style: pw.TextStyle(
                      color: PdfColors.white,
                      fontSize: 20,
                      fontWeight: pw.FontWeight.bold)),
              pw.Text('Recibo de billetera',
                  style: const pw.TextStyle(
                      color: PdfColors.white, fontSize: 11)),
            ]),
          ),
          pw.SizedBox(height: 18),
          pw.Center(
            child: pw.Text(
                '${ingreso ? '+' : '-'} $mon ${m.montoSoles.abs().toStringAsFixed(2)}',
                style: pw.TextStyle(
                    fontSize: 28, fontWeight: pw.FontWeight.bold, color: verde)),
          ),
          pw.SizedBox(height: 20),
          _pdfFila('N.º comprobante',
              m.comprobante > 0 ? m.comprobante.toString().padLeft(4, '0') : '—'),
          _pdfFila('Concepto', m.concepto),
          _pdfFila('Tipo', ingreso ? 'Ingreso' : 'Egreso'),
          if (m.fechaIso.isNotEmpty) _pdfFila('Fecha', _fechaLarga(m.fechaIso)),
          pw.Spacer(),
          pw.Divider(),
          pw.Text('Gracias por usar Pichangol.',
              style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey600)),
        ],
      ),
    ));
    final bytes = await doc.save();
    await Printing.sharePdf(
        bytes: bytes,
        filename: 'recibo_pichangol_${m.comprobante}.pdf');
  }

  pw.Widget _pdfFila(String k, String v) => pw.Padding(
        padding: const pw.EdgeInsets.symmetric(vertical: 5),
        child: pw.Row(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.SizedBox(
                width: 96,
                child: pw.Text(k,
                    style: const pw.TextStyle(
                        fontSize: 10, color: PdfColors.grey700))),
            pw.Expanded(
                child: pw.Text(v,
                    style: pw.TextStyle(
                        fontSize: 11, fontWeight: pw.FontWeight.bold))),
          ],
        ),
      );
}

class _FilaMovimiento extends StatelessWidget {
  const _FilaMovimiento(
      {required this.m, required this.moneda, required this.onTap});
  final MovimientoSaldo m;
  final String moneda;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final ingreso = m.montoSoles >= 0;
    final color = ingreso ? bosque : clayOscuro;
    final icono = switch (m.tipo) {
      TipoMovimiento.recarga => Icons.add,
      TipoMovimiento.liquidacion => Icons.account_balance_wallet_outlined,
      TipoMovimiento.consumo => Icons.remove,
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        onTap: onTap,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        leading: CircleAvatar(
          radius: 18,
          backgroundColor: color.withOpacity(0.12),
          child: Icon(icono, size: 18, color: color),
        ),
        title: Text(m.concepto,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(
            m.cuando +
                (m.comprobante > 0
                    ? ' · N.º ${m.comprobante.toString().padLeft(4, '0')}'
                    : ''),
            style: const TextStyle(color: textoTenue, fontSize: 12)),
        trailing: Text(
            '${ingreso ? '+' : '−'} $moneda ${m.montoSoles.abs().toStringAsFixed(2)}',
            style: TextStyle(fontWeight: FontWeight.w800, color: color)),
      ),
    );
  }
}
