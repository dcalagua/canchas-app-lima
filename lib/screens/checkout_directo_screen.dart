import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../models/models.dart';
import '../services/club_pagos_service.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../ui/ds.dart';

/// Resultado del checkout directo: confirmada (pagó en línea), en revisión
/// (subió voucher) o cancelado.
enum ResultadoCheckout { confirmada, enRevision, cancelado }

/// CHECKOUT DIRECTO AL CLUB (plan nocturno A4/A5, jugador). Todo lo decide el
/// SERVIDOR (mismo flujo que la web: `/web/asegurar` → `/web/pagar` |
/// `/web/voucher`): precio con las reglas del club, apartado con vencimiento y
/// cobro con la cuenta Culqi DEL CLUB. El teléfono nunca calcula montos.
///
/// Pasos: 1) resumen + tus datos → aparta; 2) cómo pagas (tarjeta/Yape con el
/// Culqi del club o un medio manual con voucher) con temporizador; 3) listo.
class CheckoutDirectoScreen extends StatefulWidget {
  const CheckoutDirectoScreen({
    super.key,
    required this.cancha,
    required this.horas,
    required this.fechaTexto,
    required this.checkout,
    this.deporte = '',
  });

  final Cancha cancha;
  final List<({String fecha, String hora})> horas;
  final String fechaTexto;
  final Map<String, dynamic> checkout;
  final String deporte;

  static Future<ResultadoCheckout?> abrir(BuildContext context,
          {required Cancha cancha,
          required List<({String fecha, String hora})> horas,
          required String fechaTexto,
          required Map<String, dynamic> checkout,
          String deporte = ''}) =>
      Navigator.of(context).push<ResultadoCheckout>(MaterialPageRoute(
        builder: (_) => CheckoutDirectoScreen(
            cancha: cancha, horas: horas, fechaTexto: fechaTexto, checkout: checkout, deporte: deporte),
      ));

  @override
  State<CheckoutDirectoScreen> createState() => _CheckoutDirectoScreenState();
}

enum _Paso { datos, pago, listo }

class _CheckoutDirectoScreenState extends State<CheckoutDirectoScreen> {
  _Paso _paso = _Paso.datos;
  late final _nombre = TextEditingController(text: appState.usuario?.nombre ?? '');
  late final _celular = TextEditingController(text: appState.miCelular);
  bool _trabajando = false;
  String? _error;

  // apartado
  List<String> _ids = [];
  String _firma = '';
  int _centimos = 0;
  String _moneda = 'S/';
  DateTime? _vence;
  bool _sena = false;

  // pago
  // Medio elegido: Culqi del club ([_culqiYape] / [_culqiTarjeta]) o el TIPO de
  // un medio manual ('yape', 'plin', 'transferencia'…). Claves distintas: un
  // Yape en línea y un Yape manual NO son lo mismo.
  String _medio = '';
  static const _culqiYape = 'culqi_yape';
  static const _culqiTarjeta = 'culqi_tarjeta';
  ResultadoCheckout? _resultado;

  String get _pk => (widget.checkout['culqi_public_key'] ?? '').toString();
  List<Map<String, dynamic>> get _medios =>
      [for (final m in (widget.checkout['medios'] as List? ?? [])) Map<String, dynamic>.from(m as Map)];

  String get _horario {
    final hs = [for (final h in widget.horas) h.hora]..sort();
    return hs.length == 1 ? hs.first : '${hs.first}–${widget.cancha.horaFinDe(hs.last)}';
  }

  @override
  void dispose() {
    _nombre.dispose();
    _celular.dispose();
    super.dispose();
  }

  Future<void> _apartar() async {
    final cel = _celular.text.replaceAll(RegExp(r'\D'), '');
    if (_nombre.text.trim().length < 3 || cel.length < 8) {
      setState(() => _error = 'Completa tu nombre y un celular válido.');
      return;
    }
    setState(() {
      _trabajando = true;
      _error = null;
    });
    final r = await ClubPagosService.apartar(
      canchaId: widget.cancha.id,
      nombre: _nombre.text.trim(),
      email: appState.usuario?.email ?? '',
      celular: cel,
      horas: widget.horas,
      deporte: widget.deporte,
      sena: _sena,
    );
    if (!mounted) return;
    if (!r.ok) {
      setState(() {
        _trabajando = false;
        _error = r.mensaje;
      });
      return;
    }
    final d = r.datos;
    setState(() {
      _trabajando = false;
      _ids = [for (final i in d['ids'] as List) i.toString()];
      _firma = d['firma'].toString();
      _centimos = (d['total_centimos'] as num?)?.toInt() ?? 0;
      _moneda = (d['moneda'] ?? widget.cancha.monedaSimbolo).toString();
      _vence = DateTime.now().add(Duration(seconds: (d['hold_segundos'] as num?)?.toInt() ?? 600));
      _medio = _pk.isNotEmpty ? _culqiYape : (_medios.isNotEmpty ? _medios.first['tipo'].toString() : '');
      _paso = _Paso.pago;
    });
  }

  Future<void> _soltar() async {
    if (_ids.isNotEmpty && _resultado == null) {
      unawaited(ClubPagosService.liberar(_ids, _firma));
    }
  }

  void _terminar(ResultadoCheckout r) {
    setState(() {
      _resultado = r;
      _paso = _Paso.listo;
    });
    unawaited(appState.cargarReservasRemotas());
  }

  @override
  Widget build(BuildContext context) {
    final mon = widget.cancha.monedaSimbolo;
    return PopScope(
      canPop: _paso != _Paso.pago,
      onPopInvokedWithResult: (pop, _) async {
        if (pop) return;
        final salir = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('¿Dejar el pago?'),
            content: const Text('Tu horario quedará libre para otros jugadores.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Seguir pagando')),
              FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Salir')),
            ],
          ),
        );
        if (salir == true && context.mounted) {
          await _soltar();
          if (context.mounted) Navigator.of(context).pop(ResultadoCheckout.cancelado);
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(switch (_paso) {
            _Paso.datos => 'Confirma tu reserva',
            _Paso.pago => 'Paga al club',
            _Paso.listo => 'Listo',
          }),
          automaticallyImplyLeading: _paso != _Paso.listo,
        ),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(Esp.x4, Esp.x2, Esp.x4, Esp.x10),
            children: [
              _Encabezado(cancha: widget.cancha, fecha: widget.fechaTexto, horario: _horario),
              const SizedBox(height: Esp.x4),
              ...switch (_paso) {
                _Paso.datos => _pasoDatos(context, mon),
                _Paso.pago => _pasoPago(context),
                _Paso.listo => _pasoListo(context),
              },
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _pasoDatos(BuildContext context, String mon) => [
        const CLSeccion(titulo: 'Tus datos', bajada: 'El club los usa para contactarte si hace falta.'),
        CLCampo(etiqueta: 'Nombre', controller: _nombre),
        CLCampo(etiqueta: 'Celular', controller: _celular, teclado: TextInputType.phone, maxLength: 15),
        if (widget.cancha.senaPct > 0)
          CLTarjeta(
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _sena,
              onChanged: (v) => setState(() => _sena = v),
              title: Text('Pagar solo la seña (${widget.cancha.senaPct} %)'),
              subtitle: const Text('El resto lo pagas en la cancha.'),
            ),
          ),
        const SizedBox(height: Esp.x3),
        const CLAviso(
          texto: 'El precio final lo calcula el club según sus tarifas del día. Lo verás antes de pagar.',
        ),
        if (_error != null) ...[
          const SizedBox(height: Esp.x3),
          CLAviso(tono: CLTono.error, texto: _error!),
        ],
        const SizedBox(height: Esp.x5),
        CLBoton(texto: 'Apartar horario', cargando: _trabajando, onPressed: _apartar),
      ];

  List<Widget> _pasoPago(BuildContext context) {
    final opciones = <({String clave, String titulo, String bajada, IconData icono})>[
      if (_pk.isNotEmpty) (clave: _culqiYape, titulo: 'Yape en línea', bajada: 'Se confirma al instante', icono: Icons.bolt_rounded),
      if (_pk.isNotEmpty) (clave: _culqiTarjeta, titulo: 'Tarjeta', bajada: 'Débito o crédito · se confirma al instante', icono: Icons.credit_card_rounded),
      for (final m in _medios)
        (
          clave: m['tipo'].toString(),
          titulo: m['tipo'] == 'transferencia' ? m['etiqueta'].toString() : '${m['etiqueta']} al número del club',
          bajada: 'Subes tu comprobante y el club lo confirma',
          icono: m['tipo'] == 'transferencia' ? Icons.account_balance_rounded : Icons.qr_code_2_rounded,
        ),
    ];
    return [
      CLTarjeta(
        destacada: true,
        child: Row(children: [
          Expanded(child: Text('Total a pagar', style: Tipo.subtitulo(context))),
          CLPrecio(monto: _centimos / 100, moneda: _moneda, grande: true),
        ]),
      ),
      const SizedBox(height: Esp.x3),
      if (_vence != null)
        CLTemporizador(
          vence: _vence!,
          alVencer: () {
            if (!mounted || _resultado != null) return;
            setState(() => _error = RespuestaClub.mensajeDeError('hold_vencido'));
          },
        ),
      const CLSeccion(titulo: '¿Cómo pagas?'),
      for (final o in opciones)
        Padding(
          padding: const EdgeInsets.only(bottom: Esp.x2),
          child: CLTarjeta(
            destacada: _medio == o.clave,
            onTap: () => setState(() {
              _medio = o.clave;
              _error = null;
            }),
            semantica: '${o.titulo}${_medio == o.clave ? ', elegido' : ''}',
            child: Row(children: [
              Icon(o.icono),
              const SizedBox(width: Esp.x3),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(o.titulo, style: Tipo.subtitulo(context)),
                  Text(o.bajada, style: Tipo.detalle(context)),
                ]),
              ),
              Icon(_medio == o.clave ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
                  color: _medio == o.clave ? Theme.of(context).colorScheme.primary : null),
            ]),
          ),
        ),
      const SizedBox(height: Esp.x3),
      if (_medio == _culqiYape || _medio == _culqiTarjeta)
        _FormCulqi(
          key: ValueKey(_medio),
          yape: _medio == _culqiYape,
          pk: _pk,
          centimos: _centimos,
          email: appState.usuario?.email ?? '',
          alPagar: (token) async {
            final r = await ClubPagosService.pagar(
                ids: _ids, firma: _firma, token: token, medio: _medio == _culqiYape ? 'yape' : 'tarjeta');
            if (!mounted) return r;
            if (r.ok) _terminar(ResultadoCheckout.confirmada);
            return r;
          },
        )
      else if (_medio.isNotEmpty)
        _FormVoucher(
          key: ValueKey(_medio),
          medio: _medios.firstWhere((m) => m['tipo'] == _medio),
          monto: '$_moneda ${(_centimos / 100).toStringAsFixed(2)}',
          alEnviar: (operacion, imagen) async {
            final r = await ClubPagosService.subirVoucher(
                ids: _ids, firma: _firma, medio: _medio, operacion: operacion, imagenBase64: imagen);
            if (!mounted) return r;
            if (r.ok) _terminar(ResultadoCheckout.enRevision);
            return r;
          },
        ),
      if (_error != null) ...[
        const SizedBox(height: Esp.x3),
        CLAviso(tono: CLTono.error, texto: _error!),
      ],
    ];
  }

  List<Widget> _pasoListo(BuildContext context) {
    final ok = _resultado == ResultadoCheckout.confirmada;
    return [
      const SizedBox(height: Esp.x6),
      CLVacio(
        icono: ok ? Icons.check_circle_rounded : Icons.hourglass_top_rounded,
        titulo: ok ? '¡Reserva confirmada!' : 'Comprobante enviado',
        mensaje: ok
            ? 'Te esperamos en ${widget.cancha.nombre}. La verás en Mis reservas.'
            : 'El club revisará tu pago y te avisaremos apenas lo confirme. Tu horario queda apartado mientras tanto.',
      ),
      CLBoton(texto: 'Listo', onPressed: () => Navigator.of(context).pop(_resultado)),
    ];
  }
}

class _Encabezado extends StatelessWidget {
  const _Encabezado({required this.cancha, required this.fecha, required this.horario});
  final Cancha cancha;
  final String fecha;
  final String horario;

  @override
  Widget build(BuildContext context) => CLTarjeta(
        child: Row(children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary.withOpacity(0.08), borderRadius: Rad.rMd),
            child: Icon(iconoDeporte(cancha.deporte), color: Theme.of(context).colorScheme.primary),
          ),
          const SizedBox(width: Esp.x3),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(cancha.nombre, style: Tipo.subtitulo(context)),
              Text(cancha.club, style: Tipo.detalle(context)),
              const SizedBox(height: Esp.x1),
              Text('$fecha · $horario', style: Tipo.etiqueta(context)),
            ]),
          ),
        ]),
      );
}

class _FormCulqi extends StatefulWidget {
  const _FormCulqi({
    super.key,
    required this.yape,
    required this.pk,
    required this.centimos,
    required this.email,
    required this.alPagar,
  });

  final bool yape;
  final String pk;
  final int centimos;
  final String email;
  final Future<RespuestaClub> Function(String token) alPagar;

  @override
  State<_FormCulqi> createState() => _FormCulqiState();
}

class _FormCulqiState extends State<_FormCulqi> {
  final _a = TextEditingController(); // celular Yape | número de tarjeta
  final _b = TextEditingController(); // código Yape | MM/AA
  final _c = TextEditingController(); // CVV
  bool _pagando = false;
  String? _error;

  @override
  void dispose() {
    _a.dispose();
    _b.dispose();
    _c.dispose();
    super.dispose();
  }

  Future<void> _pagar() async {
    setState(() {
      _pagando = true;
      _error = null;
    });
    Map<String, dynamic> t;
    if (widget.yape) {
      t = await PagosService.tokenizarYape(
          publicKey: widget.pk,
          celular: _a.text.replaceAll(RegExp(r'\D'), ''),
          otp: _b.text.replaceAll(RegExp(r'\D'), ''),
          montoCentimos: widget.centimos);
    } else {
      final p = _b.text.split('/');
      var anio = p.length == 2 ? int.tryParse(p[1].trim()) ?? 0 : 0;
      if (anio < 100) anio += 2000;
      t = await PagosService.tokenizarTarjeta(
          publicKey: widget.pk,
          numero: _a.text.replaceAll(' ', ''),
          cvv: _c.text.trim(),
          mesExp: int.tryParse(p.first.trim()) ?? 0,
          anioExp: anio,
          email: widget.email);
    }
    if (t['ok'] != true) {
      if (!mounted) return;
      setState(() {
        _pagando = false;
        _error = (t['error'] ?? 'No se pudo validar el medio de pago.').toString();
      });
      return;
    }
    final r = await widget.alPagar(t['token'].toString());
    if (!mounted) return;
    setState(() {
      _pagando = false;
      _error = r.ok ? null : r.mensaje;
    });
  }

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (widget.yape) ...[
          CLCampo(etiqueta: 'Celular Yape', controller: _a, teclado: TextInputType.phone, maxLength: 9),
          CLCampo(
              etiqueta: 'Código de aprobación',
              controller: _b,
              teclado: TextInputType.number,
              maxLength: 6,
              ayuda: 'Yape → Menú → Código de aprobación'),
        ] else ...[
          CLCampo(etiqueta: 'Número de tarjeta', controller: _a, teclado: TextInputType.number, maxLength: 19),
          Row(children: [
            Expanded(child: CLCampo(etiqueta: 'Vence (MM/AA)', controller: _b, teclado: TextInputType.datetime, maxLength: 5)),
            const SizedBox(width: Esp.x3),
            Expanded(child: CLCampo(etiqueta: 'CVV', controller: _c, teclado: TextInputType.number, oculto: true, maxLength: 4)),
          ]),
        ],
        if (_error != null)
          Padding(padding: const EdgeInsets.only(bottom: Esp.x3), child: CLAviso(tono: CLTono.error, texto: _error!)),
        CLBoton(texto: 'Pagar', icono: Icons.lock_rounded, cargando: _pagando, onPressed: _pagar),
        const SizedBox(height: Esp.x2),
        Text('El pago va directo a la cuenta del club, procesado por Culqi.',
            textAlign: TextAlign.center, style: Tipo.micro(context)),
      ]);
}

class _FormVoucher extends StatefulWidget {
  const _FormVoucher({super.key, required this.medio, required this.monto, required this.alEnviar});
  final Map<String, dynamic> medio;
  final String monto;
  final Future<RespuestaClub> Function(String operacion, String imagenBase64) alEnviar;

  @override
  State<_FormVoucher> createState() => _FormVoucherState();
}

class _FormVoucherState extends State<_FormVoucher> {
  final _op = TextEditingController();
  XFile? _foto;
  bool _enviando = false;
  String? _error;

  @override
  void dispose() {
    _op.dispose();
    super.dispose();
  }

  Future<void> _elegir(ImageSource src) async {
    final f = await ImagePicker().pickImage(source: src, maxWidth: 1600, imageQuality: 80);
    if (f != null && mounted) setState(() => _foto = f);
  }

  Future<void> _enviar() async {
    if (_foto == null) {
      setState(() => _error = 'Adjunta la captura de tu comprobante.');
      return;
    }
    if (_op.text.trim().length < 3) {
      setState(() => _error = 'Escribe el número de operación.');
      return;
    }
    setState(() {
      _enviando = true;
      _error = null;
    });
    final b64 = base64Encode(await _foto!.readAsBytes());
    final r = await widget.alEnviar(_op.text.trim(), b64);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      _error = r.ok ? null : r.mensaje;
    });
  }

  Widget _copiable(BuildContext context, String etiqueta, String valor) => valor.isEmpty
      ? const SizedBox.shrink()
      : Row(children: [
          Expanded(child: CLFila(etiqueta: etiqueta, valor: valor)),
          IconButton(
            tooltip: 'Copiar $etiqueta',
            icon: const Icon(Icons.copy_rounded, size: 20),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: valor));
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$etiqueta copiado')));
            },
          ),
        ]);

  @override
  Widget build(BuildContext context) {
    final m = widget.medio;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      CLTarjeta(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('1. Paga ${widget.monto} a', style: Tipo.etiqueta(context)),
          const SizedBox(height: Esp.x2),
          CLFila(etiqueta: 'Titular', valor: m['titular'].toString()),
          _copiable(context, 'Número', (m['numero'] ?? '').toString()),
          if ((m['banco'] ?? '').toString().isNotEmpty) CLFila(etiqueta: 'Banco', valor: m['banco'].toString()),
          _copiable(context, 'Cuenta', (m['cuenta'] ?? '').toString()),
          _copiable(context, 'CCI', (m['cci'] ?? '').toString()),
          if ((m['nota'] ?? '').toString().isNotEmpty) ...[
            const SizedBox(height: Esp.x2),
            Text(m['nota'].toString(), style: Tipo.detalle(context)),
          ],
        ]),
      ),
      const SizedBox(height: Esp.x3),
      Text('2. Sube tu comprobante', style: Tipo.etiqueta(context)),
      const SizedBox(height: Esp.x2),
      Row(children: [
        Expanded(
          child: CLBoton(
              texto: _foto == null ? 'Galería' : 'Cambiar',
              icono: Icons.photo_library_rounded,
              tipo: CLBotonTipo.secundario,
              grande: false,
              onPressed: () => _elegir(ImageSource.gallery)),
        ),
        const SizedBox(width: Esp.x3),
        Expanded(
          child: CLBoton(
              texto: 'Cámara',
              icono: Icons.photo_camera_rounded,
              tipo: CLBotonTipo.secundario,
              grande: false,
              onPressed: () => _elegir(ImageSource.camera)),
        ),
      ]),
      if (_foto != null)
        Padding(
          padding: const EdgeInsets.only(top: Esp.x2),
          child: CLAviso(tono: CLTono.ok, texto: 'Comprobante adjunto: ${_foto!.name}'),
        ),
      const SizedBox(height: Esp.x4),
      CLCampo(
          etiqueta: 'N.º de operación',
          controller: _op,
          ayuda: 'Está en tu comprobante (en Yape: "Nro. de operación").',
          maxLength: 30),
      if (_error != null)
        Padding(padding: const EdgeInsets.only(bottom: Esp.x3), child: CLAviso(tono: CLTono.error, texto: _error!)),
      CLBoton(texto: 'Enviar comprobante', cargando: _enviando, onPressed: _enviar),
    ]);
  }
}
