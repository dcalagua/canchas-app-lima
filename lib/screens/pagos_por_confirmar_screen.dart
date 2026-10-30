import 'package:flutter/material.dart';

import '../services/club_pagos_service.dart';
import '../ui/ds.dart';

const _simbolo = {'PEN': 'S/', 'USD': r'$', 'BOB': 'Bs'};
const _medio = {'yape': 'Yape', 'plin': 'Plin', 'transferencia': 'Transferencia', 'billetera': 'Billetera', 'qr': 'QR'};

/// BANDEJA de pagos manuales (plan A5): el dueño compara el voucher con lo que
/// llegó a su cuenta y confirma o rechaza. Lo que no revisa a tiempo vence solo
/// y el horario se libera (backend `cobro_directo_web.vencer`).
class PagosPorConfirmarScreen extends StatefulWidget {
  const PagosPorConfirmarScreen({super.key});

  @override
  State<PagosPorConfirmarScreen> createState() => _PagosPorConfirmarScreenState();
}

class _PagosPorConfirmarScreenState extends State<PagosPorConfirmarScreen> {
  bool _pendientes = true;
  RespuestaClub? _r;
  Map<String, String> _cab = const {};

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _r = null);
    final cab = await ClubPagosService.cabecerasImagen();
    final r = await ClubPagosService.vouchers(pendientes: _pendientes);
    if (!mounted) return;
    setState(() {
      _cab = cab;
      _r = r;
    });
  }

  @override
  Widget build(BuildContext context) {
    final pagos = [for (final p in (_r?.datos['pagos'] as List? ?? [])) Map<String, dynamic>.from(p as Map)];
    return Scaffold(
      appBar: AppBar(title: const Text('Pagos por confirmar')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Esp.x4, Esp.x2, Esp.x4, Esp.x2),
          child: SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: true, label: Text('Pendientes'), icon: Icon(Icons.schedule_rounded)),
              ButtonSegment(value: false, label: Text('Revisados'), icon: Icon(Icons.done_all_rounded)),
            ],
            selected: {_pendientes},
            onSelectionChanged: (s) {
              setState(() => _pendientes = s.first);
              _cargar();
            },
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _cargar,
            child: _r == null
                ? ListView(padding: Esp.pantalla, children: [CLSkeleton.lista(n: 3, alto: 140)])
                : !_r!.ok
                    ? ListView(children: [CLError(mensaje: _r!.mensaje, onReintentar: _cargar)])
                    : pagos.isEmpty
                        ? ListView(children: [
                            CLVacio(
                              icono: Icons.inbox_rounded,
                              titulo: _pendientes ? 'Todo al día' : 'Sin pagos revisados',
                              mensaje: _pendientes
                                  ? 'Cuando un jugador suba su comprobante, aparecerá aquí para que lo confirmes.'
                                  : 'Aquí verás el historial de vouchers aprobados, rechazados o vencidos.',
                            )
                          ])
                        : ListView.separated(
                            padding: const EdgeInsets.fromLTRB(Esp.x4, Esp.x2, Esp.x4, Esp.x10),
                            itemCount: pagos.length,
                            separatorBuilder: (_, __) => const SizedBox(height: Esp.x3),
                            itemBuilder: (ctx, i) => _TarjetaPago(
                              p: pagos[i],
                              cabeceras: _cab,
                              alResolver: _cargar,
                            ),
                          ),
          ),
        ),
      ]),
    );
  }
}

class _TarjetaPago extends StatefulWidget {
  const _TarjetaPago({required this.p, required this.cabeceras, required this.alResolver});
  final Map<String, dynamic> p;
  final Map<String, String> cabeceras;
  final VoidCallback alResolver;

  @override
  State<_TarjetaPago> createState() => _TarjetaPagoState();
}

class _TarjetaPagoState extends State<_TarjetaPago> {
  bool _trabajando = false;

  Map<String, dynamic> get p => widget.p;

  Future<void> _aprobar() async {
    setState(() => _trabajando = true);
    final r = await ClubPagosService.aprobarVoucher(p['id'].toString());
    if (!mounted) return;
    setState(() => _trabajando = false);
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(r.ok ? 'Reserva confirmada. Le avisamos al jugador.' : r.mensaje)));
    widget.alResolver();
  }

  Future<void> _rechazar() async {
    final ctl = TextEditingController();
    final motivo = await mostrarHojaCL<String>(
      context,
      titulo: '¿Por qué lo rechazas?',
      contenido: (ctx) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Wrap(spacing: Esp.x2, runSpacing: Esp.x2, children: [
          for (final m in const ['No llegó el pago', 'El monto no coincide', 'Comprobante ilegible'])
            ActionChip(label: Text(m), onPressed: () => Navigator.pop(ctx, m)),
        ]),
        const SizedBox(height: Esp.x4),
        CLCampo(etiqueta: 'Otro motivo', controller: ctl, maxLength: 140),
        CLBoton(
            texto: 'Rechazar y liberar el horario',
            tipo: CLBotonTipo.peligro,
            onPressed: () => Navigator.pop(ctx, ctl.text.trim().isEmpty ? 'Pago no confirmado' : ctl.text.trim())),
      ]),
    );
    ctl.dispose();
    if (motivo == null || !mounted) return;
    setState(() => _trabajando = true);
    final r = await ClubPagosService.rechazarVoucher(p['id'].toString(), motivo);
    if (!mounted) return;
    setState(() => _trabajando = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r.ok ? 'Rechazado. El horario quedó libre.' : r.mensaje)));
    widget.alResolver();
  }

  void _verImagen() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => Scaffold(
        appBar: AppBar(title: const Text('Comprobante')),
        backgroundColor: Colors.black,
        body: InteractiveViewer(
          maxScale: 5,
          child: Center(
            child: Image.network(ClubPagosService.urlImagenVoucher(p['id'].toString()), headers: widget.cabeceras,
                errorBuilder: (_, __, ___) =>
                    const Text('No se pudo cargar la imagen', style: TextStyle(color: Colors.white))),
          ),
        ),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final monto = ((p['monto_centimos'] as num?) ?? 0) / 100;
    final moneda = _simbolo[p['moneda']] ?? 'S/';
    final estado = p['estado'].toString();
    final vence = DateTime.tryParse(p['vence_en']?.toString() ?? '')?.toLocal();
    final (tono, etiqueta) = switch (estado) {
      'aprobado' => (CLTono.ok, 'Aprobado'),
      'rechazado' => (CLTono.error, 'Rechazado'),
      'vencido' => (CLTono.neutro, 'Vencido'),
      _ => (CLTono.aviso, 'Por revisar'),
    };
    return CLTarjeta(
      padding: EdgeInsets.zero,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Semantics(
          button: true,
          label: 'Ver comprobante en grande',
          child: InkWell(
            onTap: _verImagen,
            child: SizedBox(
              height: 160,
              child: Image.network(
                ClubPagosService.urlImagenVoucher(p['id'].toString()),
                headers: widget.cabeceras,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.image_not_supported_outlined)),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(Esp.x4),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Expanded(child: CLPrecio(monto: monto, moneda: moneda, grande: true)),
              CLInsignia(texto: etiqueta, tono: tono),
            ]),
            const SizedBox(height: Esp.x2),
            CLFila(etiqueta: 'Jugador', valor: (p['jugador_nombre'] ?? p['jugador_email']).toString()),
            CLFila(etiqueta: 'Medio', valor: _medio[p['medio']] ?? p['medio'].toString()),
            CLFila(etiqueta: 'N.º de operación', valor: p['operacion'].toString()),
            if (estado == 'rechazado' && (p['motivo_rechazo'] ?? '').toString().isNotEmpty)
              CLFila(etiqueta: 'Motivo', valor: p['motivo_rechazo'].toString()),
            if (estado == 'en_revision' && vence != null) ...[
              const SizedBox(height: Esp.x2),
              CLTemporizador(vence: vence, prefijo: 'Revisa antes de que se libere el horario:'),
              const SizedBox(height: Esp.x3),
              Text('Confirma solo si el monto ya está en tu cuenta.', style: Tipo.detalle(context)),
              const SizedBox(height: Esp.x3),
              Row(children: [
                Expanded(
                  child: CLBoton(
                      texto: 'Rechazar', tipo: CLBotonTipo.secundario, cargando: _trabajando, onPressed: _rechazar),
                ),
                const SizedBox(width: Esp.x3),
                Expanded(
                  child: CLBoton(
                      texto: 'Confirmar', cargando: _trabajando, onPressed: _aprobar),
                ),
              ]),
            ],
          ]),
        ),
      ]),
    );
  }
}
