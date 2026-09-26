import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../models/academia.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/ilustracion_pichangol.dart';
import '../widgets/responsive.dart';
import '../widgets/logo_academia.dart';
import '../widgets/pago_tarjeta_sheet.dart';
import '../widgets/sesion_requerida.dart';

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
          if (!appState.logueado) {
            return const SesionRequerida(
              motivo: 'ver tus clases y pagos',
              icono: Icons.school_outlined,
              titulo: 'Tus clases y pagos',
            );
          }
          final matriculas = appState.misMatriculas;
          if (matriculas.isEmpty) {
            return const VacioPichangol(
              clave: 'clases_vacias',
              emoji: '🎓',
              titulo: 'Aún no tienes clases',
              mensaje: 'Entra a "Academias" en Explorar y matricúlate, o '
                  'únete con el código de tu profe.',
            );
          }
          final familia = _pendientesFamilia(matriculas);
          return ListView(
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 16, 760), 14, ladoTablet(context, 16, 760), 30),
            children: [
              // "Mi familia · un solo pago" (pedido del director, 26-sep-2026:
              // "pago la academia de mi esposa, de mis hijos y la mía, hago un
              // solo pago por ellos"): una tarjeta por moneda cuando hay
              // cuotas pendientes de 2+ personas que pago yo.
              for (final grupo in familia)
                _MiFamilia(
                  key: ValueKey('fam_${grupo.moneda}'),
                  items: grupo.items,
                  moneda: grupo.moneda,
                  onPagar: (sel) => _pagarFamilia(context, sel, grupo.moneda),
                ),
              for (final al in matriculas) _cardMatricula(context, al),
            ],
          );
        },
      ),
    );
  }

  /// Cuotas PENDIENTES de todas mis matrículas, agrupadas por moneda, solo si
  /// en esa moneda hay 2+ personas por pagar (si es una sola, basta la tarjeta
  /// de su matrícula).
  List<_GrupoFamilia> _pendientesFamilia(List<Alumno> matriculas) {
    final porMoneda = <String, List<_CuotaFamilia>>{};
    for (final al in matriculas) {
      final academia = appState.academias
          .cast<Academia?>()
          .firstWhere((a) => a?.id == al.academiaId, orElse: () => null);
      if (academia == null) continue;
      final mon = academia.monedaSimbolo;
      final pend = appState.cuotasDeAlumno(al.id).where((c) => !c.pagada).toList()
        ..sort((a, b) => a.vencimiento.compareTo(b.vencimiento));
      for (final c in pend) {
        porMoneda
            .putIfAbsent(mon, () => [])
            .add(_CuotaFamilia(cuota: c, alumno: al, academia: academia));
      }
    }
    final out = <_GrupoFamilia>[];
    for (final e in porMoneda.entries) {
      final personas = e.value.map((x) => x.alumno.id).toSet();
      if (personas.length < 2) continue;
      out.add(_GrupoFamilia(moneda: e.key, items: e.value));
    }
    return out;
  }

  /// UN SOLO cobro por las cuotas de varias personas / academias (misma
  /// moneda). Luego se registra el cobro digital POR ACADEMIA (cada una
  /// congela su comisión y recibe su neto) y se marcan pagadas con el mismo
  /// N.º de operación.
  Future<void> _pagarFamilia(
      BuildContext context, List<_CuotaFamilia> sel, String mon) async {
    if (sel.isEmpty) return;
    final total = sel.fold<double>(0, (s, x) => s + x.cuota.monto);
    if (total <= 0) return;
    final personas = sel.map((x) => x.alumno.id).toSet().length;
    String? operacionId;
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: total,
      concepto: '${sel.length} cuota${sel.length == 1 ? '' : 's'} · '
          '$personas persona${personas == 1 ? '' : 's'} · Mi familia',
      email: appState.usuario?.email ?? '',
      moneda: mon,
      onOperacion: (o) => operacionId = o,
    );
    if (!pagado) return;
    final porAcademia = <String, List<_CuotaFamilia>>{};
    for (final x in sel) {
      porAcademia.putIfAbsent(x.academia.id, () => []).add(x);
    }
    final marca = DateTime.now().microsecondsSinceEpoch;
    for (final e in porAcademia.entries) {
      final ac = e.value.first.academia;
      final sub = e.value.fold<double>(0, (s, x) => s + x.cuota.monto);
      PagosService.registrarMatricula(
        academiaId: ac.id,
        montoSoles: sub,
        matriculaId: 'cuo_${ac.id}_$marca',
        pais: ac.pais.iso,
        concepto: 'Cuotas ${ac.nombre} · pago familiar',
      );
    }
    for (final x in sel) {
      appState.marcarCuotaPagada(x.cuota.id, operacionId: operacionId ?? '');
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('${sel.length} cuotas de $personas personas pagadas '
              'en un solo pago. ¡Gracias!')));
    }
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
                LogoAcademia(logoUrl: academia?.logoUrl),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(nombreAca,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: bosque,
                              fontWeight: FontWeight.w800,
                              fontSize: 16)),
                      Text(
                          'Alumno: ${al.nombre}'
                          '${al.esFamiliar ? ' · familiar' : (al.esMenor ? ' · hijo(a)' : '')}'
                          '${al.ordenHermano > 1 ? ' · ${al.ordenHermano}.º de la familia' : ''}',
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
                if (proximas.isNotEmpty && academia != null)
                  _ProximosPagos(
                    cuotas: proximas,
                    moneda: mon,
                    onPagar: (sel) =>
                        _pagarCuotas(context, academia, sel, mon),
                  ),
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
                          _verComprobante(context, academia, al, c, mon),
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

  /// Cobra una o varias cuotas pendientes con tarjeta/Yape (Culqi). Al aprobar,
  /// las marca pagadas (se propaga al profe) y registra el neto en la academia.
  Future<void> _pagarCuotas(BuildContext context, Academia ac,
      List<Cuota> cuotas, String mon) async {
    if (cuotas.isEmpty) return;
    final total = cuotas.fold<double>(0, (s, c) => s + c.monto);
    if (total <= 0) return;
    String? operacionId;
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: total,
      concepto: cuotas.length == 1
          ? cuotas.first.concepto
          : '${cuotas.length} cuotas · ${ac.nombre}',
      email: appState.usuario?.email ?? '',
      moneda: mon,
      onOperacion: (o) => operacionId = o,
    );
    if (!pagado) return;
    // Cobro digital para la academia (congela comisión POS, neto "por recibir").
    PagosService.registrarMatricula(
      academiaId: ac.id,
      montoSoles: total,
      matriculaId: 'cuo_${ac.id}_${DateTime.now().microsecondsSinceEpoch}',
      pais: ac.pais.iso,
      concepto:
          cuotas.length == 1 ? cuotas.first.concepto : 'Cuotas ${ac.nombre}',
    );
    for (final c in cuotas) {
      appState.marcarCuotaPagada(c.id, operacionId: operacionId ?? '');
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(cuotas.length == 1
              ? 'Cuota pagada. ¡Gracias!'
              : '${cuotas.length} cuotas pagadas. ¡Gracias!')));
    }
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

  String _fechaHora(DateTime? d) {
    if (d == null) return '';
    final hh = d.hour.toString().padLeft(2, '0');
    final mm = d.minute.toString().padLeft(2, '0');
    return '${_fecha(d)} · $hh:$mm';
  }

  void _verComprobante(BuildContext context, Academia? academia, Alumno al,
      Cuota c, String mon) {
    final nombreAca = academia?.nombre ?? 'Academia';
    final logo = academia?.logoUrl;
    showDialog<void>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Comprobante de pago',
        icono: Icons.receipt_long,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (logo != null && logo.isNotEmpty) ...[
              Center(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.network(logo,
                      width: 48,
                      height: 48,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const SizedBox.shrink()),
                ),
              ),
              const SizedBox(height: 12),
            ],
            _lineaComp('Academia', nombreAca),
            _lineaComp('Alumno', al.nombre),
            _lineaComp('Concepto', c.concepto),
            _lineaComp('Fecha y hora', _fechaHora(c.fechaPago ?? c.vencimiento)),
            if (c.operacionId.isNotEmpty)
              _lineaComp('N.º operación', c.operacionId),
            const Divider(height: 20),
            _lineaComp('Monto', '$mon ${c.monto.toStringAsFixed(2)}',
                fuerte: true),
            const SizedBox(height: 10),
            const Text('Pago procesado por Pichangol.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
          ],
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              style: TextButton.styleFrom(foregroundColor: textoTenue),
              child: const Text('Cerrar')),
          FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                shape:
                    RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12)),
            icon: const Icon(Icons.ios_share, size: 18),
            label: const Text('Compartir / PDF',
                style: TextStyle(fontWeight: FontWeight.w800)),
            onPressed: () => _compartirComprobante(academia, al, c, mon),
          ),
        ],
      ),
    );
  }

  /// Genera el comprobante en PDF y abre la hoja del sistema para COMPARTIRLO o
  /// GUARDARLO (descargar). Incluye el logo de la academia si lo tiene.
  Future<void> _compartirComprobante(
      Academia? ac, Alumno al, Cuota c, String mon) async {
    final doc = pw.Document();
    pw.ImageProvider? logo;
    final url = ac?.logoUrl;
    if (url != null && url.isNotEmpty) {
      try {
        logo = await networkImage(url);
      } catch (_) {}
    }
    final nombreAca = ac?.nombre ?? 'Academia';
    doc.addPage(
      pw.Page(
        pageFormat: PdfPageFormat.a5,
        build: (context) => pw.Padding(
          padding: const pw.EdgeInsets.all(28),
          child: pw.Column(
            crossAxisAlignment: pw.CrossAxisAlignment.start,
            children: [
              pw.Row(
                crossAxisAlignment: pw.CrossAxisAlignment.center,
                children: [
                  if (logo != null) ...[
                    pw.SizedBox(width: 44, height: 44, child: pw.Image(logo)),
                    pw.SizedBox(width: 10),
                  ],
                  pw.Expanded(
                    child: pw.Text(nombreAca,
                        style: pw.TextStyle(
                            fontSize: 16, fontWeight: pw.FontWeight.bold)),
                  ),
                ],
              ),
              pw.SizedBox(height: 4),
              pw.Text('Comprobante de pago',
                  style:
                      pw.TextStyle(fontSize: 13, color: PdfColors.grey700)),
              pw.Divider(),
              _pdfLinea('Alumno', al.nombre),
              _pdfLinea('Concepto', c.concepto),
              _pdfLinea('Fecha y hora', _fechaHora(c.fechaPago ?? c.vencimiento)),
              if (c.operacionId.isNotEmpty)
                _pdfLinea('N.º operación', c.operacionId),
              pw.Divider(),
              _pdfLinea('Monto', '$mon ${c.monto.toStringAsFixed(2)}',
                  fuerte: true),
              pw.SizedBox(height: 18),
              pw.Text('Pago procesado por Pichangol.',
                  style: pw.TextStyle(fontSize: 10, color: PdfColors.grey600)),
            ],
          ),
        ),
      ),
    );
    final bytes = await doc.save();
    await Printing.sharePdf(
        bytes: bytes, filename: 'comprobante_${al.nombre}_${c.id}.pdf');
  }

  pw.Widget _pdfLinea(String k, String v, {bool fuerte = false}) => pw.Padding(
        padding: const pw.EdgeInsets.symmetric(vertical: 3),
        child: pw.Row(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.SizedBox(
                width: 92,
                child: pw.Text(k,
                    style:
                        pw.TextStyle(color: PdfColors.grey700, fontSize: 11))),
            pw.Expanded(
              child: pw.Text(v,
                  style: pw.TextStyle(
                      fontSize: fuerte ? 15 : 12,
                      fontWeight:
                          fuerte ? pw.FontWeight.bold : pw.FontWeight.normal)),
            ),
          ],
        ),
      );

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
    // Reconcilia (marca pagadas las cuotas que el cron ya cobró) y trae el estado.
    final s = await appState.reconciliarSuscripcionAlumno(widget.alumnoId);
    if (!mounted) return;
    setState(() {
      _sus = s;
      _cargando = false;
    });
  }

  Future<void> _cancelar() async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Cancelar el débito automático?',
      mensaje: 'Dejarás de pagar automático cada mes. Podrás volver a matricularte '
          'cuando quieras.',
      textoConfirmar: 'Sí, cancelar',
      textoCancelar: 'No',
      destructivo: true,
      icono: Icons.credit_card_off_outlined,
    );
    if (!ok) return;
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

/// Sección "Próximos pagos" con CHECKBOXES: el alumno marca las cuotas que va a
/// pagar y un solo botón "Pagar S/X" cobra las seleccionadas. Por defecto vienen
/// todas marcadas (pagar todo con un tap; puede desmarcar las que no).
class _ProximosPagos extends StatefulWidget {
  const _ProximosPagos(
      {required this.cuotas, required this.moneda, required this.onPagar});
  final List<Cuota> cuotas; // pendientes, orden cronológico
  final String moneda;
  final Future<void> Function(List<Cuota>) onPagar;

  @override
  State<_ProximosPagos> createState() => _ProximosPagosState();
}

class _ProximosPagosState extends State<_ProximosPagos> {
  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  late Set<String> _sel;
  bool _pagando = false;

  @override
  void initState() {
    super.initState();
    _sel = widget.cuotas.map((c) => c.id).toSet(); // todas marcadas por defecto
  }

  @override
  void didUpdateWidget(_ProximosPagos old) {
    super.didUpdateWidget(old);
    // Si cambió la lista (tras pagar), suma las nuevas y limpia las que ya no están.
    final ids = widget.cuotas.map((c) => c.id).toSet();
    final nuevas = ids.difference(old.cuotas.map((c) => c.id).toSet());
    _sel
      ..retainWhere(ids.contains)
      ..addAll(nuevas);
  }

  String _fecha(DateTime d) => '${d.day} ${_meses[d.month - 1]} ${d.year}';

  double get _totalSel =>
      widget.cuotas.where((c) => _sel.contains(c.id)).fold(0, (s, c) => s + c.monto);

  Future<void> _pagar() async {
    final sel = widget.cuotas.where((c) => _sel.contains(c.id)).toList();
    if (sel.isEmpty || _pagando) return;
    setState(() => _pagando = true);
    await widget.onPagar(sel);
    if (mounted) setState(() => _pagando = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 12),
        const Text('Próximos pagos',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
        const SizedBox(height: 2),
        const Text('Marca las que quieres pagar.',
            style: TextStyle(color: textoTenue, fontSize: 12)),
        for (final c in widget.cuotas)
          InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => setState(() {
              if (!_sel.remove(c.id)) _sel.add(c.id);
            }),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                children: [
                  Checkbox(
                    value: _sel.contains(c.id),
                    activeColor: lima,
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    visualDensity: VisualDensity.compact,
                    onChanged: (v) => setState(() {
                      if (v == true) {
                        _sel.add(c.id);
                      } else {
                        _sel.remove(c.id);
                      }
                    }),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(c.concepto,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 13.5, fontWeight: FontWeight.w600)),
                        Text('Vence ${_fecha(c.vencimiento)}',
                            style: const TextStyle(
                                color: textoTenue, fontSize: 12)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('${widget.moneda} ${c.monto.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontSize: 13.5,
                          fontWeight: FontWeight.w800,
                          color: clayOscuro)),
                ],
              ),
            ),
          ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12)),
            onPressed: (_sel.isEmpty || _pagando) ? null : _pagar,
            child: Text('Pagar ${widget.moneda} ${_totalSel.toStringAsFixed(2)}',
                style: const TextStyle(fontWeight: FontWeight.w800)),
          ),
        ),
      ],
    );
  }
}


/// Una cuota pendiente con su alumno y academia (para el pago familiar).
class _CuotaFamilia {
  const _CuotaFamilia(
      {required this.cuota, required this.alumno, required this.academia});
  final Cuota cuota;
  final Alumno alumno;
  final Academia academia;
}

class _GrupoFamilia {
  const _GrupoFamilia({required this.moneda, required this.items});
  final String moneda;
  final List<_CuotaFamilia> items;
}

/// Tarjeta "Mi familia · un solo pago": cuotas pendientes de TODAS las personas
/// que pago (yo, mi pareja, mis hijos) en TODAS las academias, agrupadas por
/// persona, con casillas y un solo botón de pago. Estilo Airbnb.
class _MiFamilia extends StatefulWidget {
  const _MiFamilia(
      {super.key,
      required this.items,
      required this.moneda,
      required this.onPagar});
  final List<_CuotaFamilia> items;
  final String moneda;
  final Future<void> Function(List<_CuotaFamilia>) onPagar;

  @override
  State<_MiFamilia> createState() => _MiFamiliaState();
}

class _MiFamiliaState extends State<_MiFamilia> {
  static const _meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  late Set<String> _sel;
  bool _pagando = false;

  @override
  void initState() {
    super.initState();
    _sel = widget.items.map((x) => x.cuota.id).toSet();
  }

  @override
  void didUpdateWidget(_MiFamilia old) {
    super.didUpdateWidget(old);
    final ids = widget.items.map((x) => x.cuota.id).toSet();
    final nuevas = ids.difference(old.items.map((x) => x.cuota.id).toSet());
    _sel
      ..retainWhere(ids.contains)
      ..addAll(nuevas);
  }

  String _fecha(DateTime d) => '${d.day} ${_meses[d.month - 1]} ${d.year}';

  List<_CuotaFamilia> get _seleccion =>
      widget.items.where((x) => _sel.contains(x.cuota.id)).toList();

  double get _totalSel =>
      _seleccion.fold(0, (s, x) => s + x.cuota.monto);

  Future<void> _pagar() async {
    final sel = _seleccion;
    if (sel.isEmpty || _pagando) return;
    setState(() => _pagando = true);
    await widget.onPagar(sel);
    if (mounted) setState(() => _pagando = false);
  }

  @override
  Widget build(BuildContext context) {
    // Agrupado por persona (en el orden en que llegan).
    final porPersona = <String, List<_CuotaFamilia>>{};
    for (final x in widget.items) {
      porPersona.putIfAbsent(x.alumno.id, () => []).add(x);
    }
    final personasSel = _seleccion.map((x) => x.alumno.id).toSet().length;
    final mon = widget.moneda;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 3)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(
              color: limaSuave,
              borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
            ),
            child: Row(
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12)),
                  alignment: Alignment.center,
                  child: const Text('👨‍👩‍👧', style: TextStyle(fontSize: 22)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Mi familia · un solo pago',
                          style: TextStyle(
                              color: bosque,
                              fontWeight: FontWeight.w800,
                              fontSize: 16)),
                      Text(
                          '${porPersona.length} personas · ${widget.items.length} '
                          'cuotas pendientes. Paga todo junto con una sola tarjeta.',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final e in porPersona.entries) ...[
                  const SizedBox(height: 8),
                  Text(
                      '${e.value.first.alumno.nombre}'
                      '${e.value.first.alumno.esFamiliar ? ' · familiar' : (e.value.first.alumno.esMenor ? ' · hijo(a)' : '')}'
                      ' · ${e.value.first.academia.nombre}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 13)),
                  for (final x in e.value)
                    InkWell(
                      borderRadius: BorderRadius.circular(10),
                      onTap: () => setState(() {
                        if (!_sel.remove(x.cuota.id)) _sel.add(x.cuota.id);
                      }),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          children: [
                            Checkbox(
                              value: _sel.contains(x.cuota.id),
                              activeColor: lima,
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                              onChanged: (v) => setState(() {
                                if (v == true) {
                                  _sel.add(x.cuota.id);
                                } else {
                                  _sel.remove(x.cuota.id);
                                }
                              }),
                            ),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(x.cuota.concepto,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontSize: 13.5,
                                          fontWeight: FontWeight.w600)),
                                  Text('Vence ${_fecha(x.cuota.vencimiento)}',
                                      style: const TextStyle(
                                          color: textoTenue, fontSize: 12)),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text('$mon ${x.cuota.monto.toStringAsFixed(2)}',
                                style: const TextStyle(
                                    fontSize: 13.5,
                                    fontWeight: FontWeight.w800,
                                    color: clayOscuro)),
                          ],
                        ),
                      ),
                    ),
                ],
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 12)),
                    onPressed: (_sel.isEmpty || _pagando) ? null : _pagar,
                    child: Text(
                        _pagando
                            ? 'Procesando…'
                            : 'Pagar todo · $mon ${_totalSel.toStringAsFixed(2)}'
                                '${personasSel > 1 ? ' ($personasSel personas)' : ''}',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                    'Un solo cargo a tu tarjeta o Yape; cada academia recibe lo '
                    'suyo y todas las cuotas quedan con el mismo N.º de operación.',
                    style: TextStyle(color: textoTenue, fontSize: 11.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
