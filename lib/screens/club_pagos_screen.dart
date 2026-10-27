import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../brand.dart';
import '../services/club_pagos_service.dart';
import '../state/app_state.dart';
import '../ui/ds.dart';
import 'pagos_por_confirmar_screen.dart';
import 'recargar_saldo_screen.dart';
import 'reglas_reserva_screen.dart';

const _simbolo = {'PEN': 'S/', 'USD': r'$', 'BOB': 'Bs'};

/// COBROS DEL CLUB (plan nocturno A4/A5/A6): el dinero de las reservas va
/// DIRECTO a la cuenta del club. Aquí el dueño conecta su Culqi (Perú), carga
/// sus medios manuales (Yape, Plin, transferencia / QR), ve su deuda de
/// comisión y entra a la bandeja de pagos por confirmar y a las reglas de
/// reserva de cada cancha.
class ClubPagosScreen extends StatefulWidget {
  const ClubPagosScreen({super.key});

  @override
  State<ClubPagosScreen> createState() => _ClubPagosScreenState();
}

class _ClubPagosScreenState extends State<ClubPagosScreen> {
  RespuestaClub? _cfg;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final r = await ClubPagosService.miConfig();
    if (!mounted) return;
    setState(() {
      _cfg = r;
      _cargando = false;
    });
  }

  Map<String, dynamic> get _d => _cfg?.datos ?? const {};
  String get _moneda => _simbolo[_d['moneda']] ?? 'S/';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Cobros de tu club')),
      body: RefreshIndicator(
        onRefresh: _cargar,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Esp.x4, Esp.x2, Esp.x4, Esp.x10),
          children: _cargando
              ? [const SizedBox(height: Esp.x4), CLSkeleton.lista(n: 4, alto: 96)]
              : (_cfg == null || !_cfg!.ok)
                  ? [CLError(mensaje: _cfg?.mensaje ?? '', onReintentar: _cargar)]
                  : _contenido(context),
        ),
      ),
    );
  }

  List<Widget> _contenido(BuildContext context) {
    final culqi = Map<String, dynamic>.from(_d['culqi'] as Map? ?? {});
    final medios = [for (final m in (_d['medios'] as List? ?? [])) Map<String, dynamic>.from(m as Map)];
    final com = Map<String, dynamic>.from(_d['comision'] as Map? ?? {});
    final pendientes = (_d['pendientes'] as num?)?.toInt() ?? 0;
    final deuda = ((com['deuda_centimos'] as num?) ?? 0) / 100;
    final suspendido = com['suspendido'] == true;
    return [
      Text('El pago de cada reserva llega directo a tu cuenta. $kBrandName cobra solo su comisión por reserva.',
          style: Tipo.detalle(context)),
      const SizedBox(height: Esp.x4),
      if (suspendido)
        Padding(
          padding: const EdgeInsets.only(bottom: Esp.x3),
          child: CLAviso(
            tono: CLTono.error,
            titulo: 'Cobros en línea pausados',
            texto: 'Tienes $_moneda ${deuda.toStringAsFixed(2)} de comisiones por pagar. '
                'Recarga tu saldo para volver a recibir pagos en línea (el pago en la cancha sigue).',
          ),
        ),
      CLTarjeta(
        onTap: () => _abrir(const PagosPorConfirmarScreen()),
        semantica: 'Pagos por confirmar: $pendientes',
        destacada: pendientes > 0,
        child: Row(children: [
          Icon(Icons.receipt_long_rounded, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: Esp.x3),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Pagos por confirmar', style: Tipo.subtitulo(context)),
              Text(pendientes == 0 ? 'No tienes vouchers pendientes' : '$pendientes por revisar',
                  style: Tipo.detalle(context)),
            ]),
          ),
          if (pendientes > 0) CLInsignia(texto: '$pendientes', tono: CLTono.aviso),
          const Icon(Icons.chevron_right_rounded),
        ]),
      ),
      if (culqi['no_aplica'] != true) ...[
        const CLSeccion(titulo: 'Tarjeta y Yape con tu Culqi', bajada: 'Cobra en línea con tu propia cuenta Culqi.'),
        _TarjetaCulqi(culqi: culqi, alCambiar: _cargar),
      ],
      CLSeccion(
        titulo: 'Pagos manuales',
        bajada: 'El jugador te paga y sube su comprobante; tú lo confirmas.',
        accion: TextButton.icon(
          onPressed: () => _editarMedio(medios, null),
          icon: const Icon(Icons.add_rounded),
          label: const Text('Agregar'),
        ),
      ),
      if (medios.isEmpty)
        const CLAviso(texto: 'Aún no agregas medios manuales. Agrega tu Yape, Plin o cuenta bancaria.')
      else
        for (var i = 0; i < medios.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: Esp.x3),
            child: CLTarjeta(
              onTap: () => _editarMedio(medios, i),
              semantica: 'Editar ${medios[i]['etiqueta']}',
              child: _FilaMedio(m: medios[i]),
            ),
          ),
      const CLSeccion(titulo: 'Comisión', bajada: 'Se descuenta de tu saldo prepago al confirmarse cada reserva.'),
      CLTarjeta(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          CLFila(etiqueta: 'Comisiones por pagar', valor: '$_moneda ${deuda.toStringAsFixed(2)}', fuerte: true),
          CLFila(
              etiqueta: 'Tope antes de pausar cobros',
              valor: '$_moneda ${(((com['tope_centimos'] as num?) ?? 0) / 100).toStringAsFixed(2)}'),
          const SizedBox(height: Esp.x3),
          CLBoton(
            texto: 'Recargar saldo',
            icono: Icons.account_balance_wallet_rounded,
            tipo: deuda > 0 ? CLBotonTipo.primario : CLBotonTipo.secundario,
            onPressed: () => _abrir(const RecargarSaldoScreen()),
          ),
        ]),
      ),
      const CLSeccion(titulo: 'Reglas de reserva', bajada: 'Horarios por día, precios por franja y tu política.'),
      for (final c in appState.misCanchas.where((c) => c.verificada))
        Padding(
          padding: const EdgeInsets.only(bottom: Esp.x3),
          child: CLTarjeta(
            onTap: () => _abrir(ReglasReservaScreen(cancha: c)),
            semantica: 'Reglas de ${c.nombre}',
            child: Row(children: [
              const Icon(Icons.tune_rounded),
              const SizedBox(width: Esp.x3),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(c.nombre, style: Tipo.subtitulo(context)),
                  Text(c.club, style: Tipo.detalle(context)),
                ]),
              ),
              const Icon(Icons.chevron_right_rounded),
            ]),
          ),
        ),
    ];
  }

  Future<void> _abrir(Widget w) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));
    if (mounted) _cargar();
  }

  Future<void> _editarMedio(List<Map<String, dynamic>> medios, int? i) async {
    final permitidos = [for (final t in (_d['medios_permitidos'] as List? ?? ['yape', 'plin', 'transferencia'])) t.toString()];
    final res = await mostrarHojaCL<_EdicionMedio>(
      context,
      titulo: i == null ? 'Nuevo medio de pago' : 'Editar medio de pago',
      contenido: (ctx) => _FormMedio(inicial: i == null ? null : medios[i], permitidos: permitidos, puedeBorrar: i != null),
    );
    if (res == null || !mounted) return;
    final lista = [
      for (final m in medios) {for (final k in _FormMedio.campos) k: m[k] ?? ''},
    ];
    if (res.borrar && i != null) {
      lista.removeAt(i);
    } else if (i != null) {
      lista[i] = res.medio;
    } else {
      lista.add(res.medio);
    }
    final r = await ClubPagosService.guardarMedios(lista);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r.ok ? 'Guardado' : r.mensaje)));
    if (r.ok) _cargar();
  }
}

class _FilaMedio extends StatelessWidget {
  const _FilaMedio({required this.m});
  final Map<String, dynamic> m;

  @override
  Widget build(BuildContext context) {
    final tipo = m['tipo'];
    final detalle = switch (tipo) {
      'transferencia' => '${m['banco']} · ${(m['cci'] ?? '').toString().isNotEmpty ? 'CCI ${m['cci']}' : m['cuenta']}',
      _ => (m['numero'] ?? '').toString().isNotEmpty ? m['numero'].toString() : 'Código QR',
    };
    return Row(children: [
      Icon(tipo == 'transferencia' ? Icons.account_balance_rounded : Icons.qr_code_2_rounded),
      const SizedBox(width: Esp.x3),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${m['etiqueta']} · ${m['titular']}', style: Tipo.subtitulo(context)),
          Text(detalle, style: Tipo.detalle(context)),
        ]),
      ),
      const Icon(Icons.edit_rounded, size: 20),
    ]);
  }
}

class _EdicionMedio {
  final Map<String, dynamic> medio;
  final bool borrar;
  const _EdicionMedio(this.medio, {this.borrar = false});
}

class _FormMedio extends StatefulWidget {
  const _FormMedio({required this.inicial, required this.permitidos, required this.puedeBorrar});

  static const campos = ['tipo', 'titular', 'numero', 'banco', 'cuenta', 'cci', 'qr_url', 'nota'];
  final Map<String, dynamic>? inicial;
  final List<String> permitidos;
  final bool puedeBorrar;

  @override
  State<_FormMedio> createState() => _FormMedioState();
}

class _FormMedioState extends State<_FormMedio> {
  late String _tipo = (widget.inicial?['tipo'] ?? widget.permitidos.first).toString();
  late final Map<String, TextEditingController> _c = {
    for (final k in _FormMedio.campos.skip(1)) k: TextEditingController(text: (widget.inicial?[k] ?? '').toString()),
  };

  static const _etiquetas = {
    'yape': 'Yape',
    'plin': 'Plin',
    'transferencia': 'Transferencia',
    'billetera': 'Billetera',
    'qr': 'QR',
  };

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final esCel = _tipo == 'yape' || _tipo == 'plin';
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Wrap(spacing: Esp.x2, runSpacing: Esp.x2, children: [
        for (final t in widget.permitidos)
          ChoiceChip(
            label: Text(_etiquetas[t] ?? t),
            selected: _tipo == t,
            onSelected: (_) => setState(() => _tipo = t),
          ),
      ]),
      const SizedBox(height: Esp.x4),
      CLCampo(etiqueta: 'Titular', controller: _c['titular'], ayuda: 'Como aparece en el comprobante'),
      if (esCel || _tipo == 'billetera' || _tipo == 'qr')
        CLCampo(
          etiqueta: esCel ? 'Celular' : 'Número (opcional)',
          controller: _c['numero'],
          teclado: TextInputType.phone,
          maxLength: 15,
        ),
      if (_tipo == 'transferencia') ...[
        CLCampo(etiqueta: 'Banco', controller: _c['banco']),
        CLCampo(etiqueta: 'Número de cuenta', controller: _c['cuenta'], teclado: TextInputType.number),
        CLCampo(etiqueta: 'CCI (opcional)', controller: _c['cci'], teclado: TextInputType.number, maxLength: 20),
      ],
      if (_tipo == 'qr' || _tipo == 'billetera')
        CLCampo(etiqueta: 'Enlace de la imagen del QR (opcional)', controller: _c['qr_url'], teclado: TextInputType.url),
      CLCampo(etiqueta: 'Nota para el jugador (opcional)', controller: _c['nota'], maxLength: 140),
      CLBoton(
        texto: 'Guardar',
        onPressed: () => Navigator.of(context).pop(_EdicionMedio({
          'tipo': _tipo,
          for (final e in _c.entries) e.key: e.value.text.trim(),
        })),
      ),
      if (widget.puedeBorrar) ...[
        const SizedBox(height: Esp.x2),
        CLBoton(
          texto: 'Quitar este medio',
          tipo: CLBotonTipo.texto,
          onPressed: () => Navigator.of(context).pop(const _EdicionMedio({}, borrar: true)),
        ),
      ],
    ]);
  }
}

class _TarjetaCulqi extends StatefulWidget {
  const _TarjetaCulqi({required this.culqi, required this.alCambiar});
  final Map<String, dynamic> culqi;
  final VoidCallback alCambiar;

  @override
  State<_TarjetaCulqi> createState() => _TarjetaCulqiState();
}

class _TarjetaCulqiState extends State<_TarjetaCulqi> {
  final _pk = TextEditingController();
  final _sk = TextEditingController();
  bool _editando = false;
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _pk.dispose();
    _sk.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    setState(() {
      _guardando = true;
      _error = null;
    });
    final r = await ClubPagosService.guardarCulqi(_pk.text.trim(), _sk.text.trim());
    if (!mounted) return;
    setState(() {
      _guardando = false;
      _error = r.ok ? null : r.mensaje;
      if (r.ok) {
        _editando = false;
        _sk.clear();
      }
    });
    if (r.ok) widget.alCambiar();
  }

  Future<void> _desconectar() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('¿Desconectar tu Culqi?'),
        content: const Text('Los jugadores ya no podrán pagarte con tarjeta o Yape en línea.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Desconectar')),
        ],
      ),
    );
    if (ok != true) return;
    await ClubPagosService.borrarCulqi();
    widget.alCambiar();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.culqi;
    final conectada = c['configurada'] == true && !_editando;
    if (conectada) {
      final live = c['modo'] == 'live';
      return CLTarjeta(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Text('Culqi conectado', style: Tipo.subtitulo(context)),
            const Spacer(),
            CLInsignia(texto: live ? 'En vivo' : 'Prueba', tono: live ? CLTono.ok : CLTono.aviso),
          ]),
          const SizedBox(height: Esp.x2),
          CLFila(etiqueta: 'Llave pública', valor: _corta(c['public_key']?.toString() ?? '')),
          CLFila(etiqueta: 'Llave secreta', valor: c['secret_key']?.toString() ?? ''),
          if (c['verificada'] != true)
            const Padding(
              padding: EdgeInsets.only(top: Esp.x2),
              child: CLAviso(tono: CLTono.aviso, texto: 'No pudimos comprobar la llave con Culqi; se reintentará al cobrar.'),
            ),
          const SizedBox(height: Esp.x3),
          Text('Webhook (pégalo en tu panel de Culqi → Eventos):', style: Tipo.micro(context)),
          const SizedBox(height: Esp.x1),
          Row(children: [
            Expanded(child: SelectableText(c['webhook_url']?.toString() ?? '', style: Tipo.detalle(context))),
            IconButton(
              tooltip: 'Copiar webhook',
              icon: const Icon(Icons.copy_rounded),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: c['webhook_url']?.toString() ?? ''));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Webhook copiado')));
              },
            ),
          ]),
          const SizedBox(height: Esp.x2),
          Row(children: [
            Expanded(
              child: CLBoton(
                  texto: 'Cambiar', tipo: CLBotonTipo.secundario, grande: false,
                  onPressed: () => setState(() => _editando = true)),
            ),
            const SizedBox(width: Esp.x3),
            Expanded(
              child: CLBoton(texto: 'Desconectar', tipo: CLBotonTipo.texto, grande: false, onPressed: _desconectar),
            ),
          ]),
        ]),
      );
    }
    return CLTarjeta(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Copia tus llaves de Culqi → Desarrollo → API Keys. La secreta se guarda cifrada y nunca se vuelve a mostrar.',
            style: Tipo.detalle(context)),
        const SizedBox(height: Esp.x4),
        CLCampo(etiqueta: 'Llave pública', controller: _pk, ayuda: 'Empieza con pk_live_ o pk_test_'),
        CLCampo(etiqueta: 'Llave secreta', controller: _sk, oculto: true, ayuda: 'Empieza con sk_live_ o sk_test_'),
        if (_error != null) Padding(
          padding: const EdgeInsets.only(bottom: Esp.x3),
          child: CLAviso(tono: CLTono.error, texto: _error!),
        ),
        CLBoton(texto: 'Conectar Culqi', icono: Icons.link_rounded, cargando: _guardando, onPressed: _guardar),
        if (_editando)
          CLBoton(texto: 'Cancelar', tipo: CLBotonTipo.texto, onPressed: () => setState(() => _editando = false)),
      ]),
    );
  }

  static String _corta(String k) => k.length <= 16 ? k : '${k.substring(0, 12)}…${k.substring(k.length - 4)}';
}
