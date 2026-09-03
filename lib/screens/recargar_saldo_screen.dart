import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/pais.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../utils/input_formatos.dart';
import '../widgets/marcas_pago.dart';
import '../widgets/pago_libelula.dart';
import '../widgets/pago_payphone.dart';
import '../widgets/pago_procesando.dart';
import '../widgets/responsive.dart';
import '../widgets/sesion_requerida.dart';
import '../utils/moneda.dart';
import 'recarga_qr_screen.dart';

/// Recarga de saldo del dueño con Culqi (tarjeta o Yape). Tokeniza con la llave
/// pública en el celular y confirma el cobro contra el backend. Devuelve el monto
/// recargado (int soles) por Navigator.pop, o null si se canceló/falló.
class RecargarSaldoScreen extends StatefulWidget {
  /// Por defecto recarga el saldo del DUEÑO logueado (su correo). Para destacar
  /// una ACADEMIA se pasa [duenoId] = id de la academia (su saldo va aparte del
  /// de las canchas). El cobro Culqi siempre usa el correo del pagador.
  const RecargarSaldoScreen(
      {super.key, this.duenoId, this.titulo, this.pais});

  final String? duenoId;
  final String? titulo;

  /// País del saldo que se recarga. Define la MONEDA mostrada y la PASARELA
  /// (Perú → Culqi con Yape/tarjeta; Bolivia → Libélula; Ecuador → PayPhone).
  /// Si es null se usa el país de la BILLETERA del usuario
  /// (`appState.paisBilletera`), nunca el del GPS: antes, con null, caía a
  /// Culqi mientras la moneda salía del GPS, y un dueño en Guayaquil veía
  /// "$ 50" con Yape.
  final PaisConfig? pais;

  @override
  State<RecargarSaldoScreen> createState() => _RecargarSaldoScreenState();
}

enum _Metodo { yape, tarjeta }

class _RecargarSaldoScreenState extends State<RecargarSaldoScreen> {
  static const _montos = [20, 50, 100, 200];
  int _monto = 50;
  _Metodo _metodo = _Metodo.yape;
  bool _cargando = true;
  String? _pk;
  String _modo = 'off'; // test | live | off (de /pagos/config)
  String? _error;
  // ¿La recarga por QR (Yape directo) está configurada en el backend? Solo
  // aplica al flujo Perú (Yape no existe fuera).
  bool _qrDisponible = false;
  // Promo del bono de recarga (banner que empuja a recargar más). null = sin.
  Map<String, dynamic>? _promoBono;

  /// Banner de la promo de bono de recarga (si está activa en la torre).
  Widget _bannerPromo() {
    final b = _promoBono;
    if (b == null) return const SizedBox.shrink();
    return Container(
      margin: const EdgeInsets.only(top: 14),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
            colors: [Color(0xFFFFF6D8), Color(0xFFFFEFC2)]),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8D9A0)),
      ),
      child: Row(
        children: [
          const Text('🎁', style: TextStyle(fontSize: 22)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Recarga $_mon ${((b['min'] as num?) ?? 0).toStringAsFixed(0)} '
              'o más y te regalamos '
              '${((b['pct'] as num?) ?? 0).toStringAsFixed(0)}% extra '
              '(hasta $_mon ${((b['tope'] as num?) ?? 0).toStringAsFixed(0)}).',
              style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF7A5C00),
                  height: 1.3),
            ),
          ),
        ],
      ),
    );
  }

  bool get _esTest => _modo == 'test';

  // Yape
  final _celular = TextEditingController();
  final _otp = TextEditingController();
  // Tarjeta
  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();

  String get _email => appState.usuario?.email ?? '';

  /// País de la billetera que se recarga: el que pasó el llamador o, si no,
  /// el de la billetera del usuario. Moneda y pasarela salen SIEMPRE de aquí.
  PaisConfig get _pais => widget.pais ?? appState.paisBilletera;

  /// Moneda a mostrar: la de la billetera.
  String get _mon => _pais.moneda;

  /// ¿La pasarela del país está integrada? Perú (Culqi), Bolivia (Libélula) y
  /// Ecuador (PayPhone). Los demás muestran el aviso "próximamente" en vez del
  /// formulario de cobro.
  bool get _pasarelaLista =>
      _pais.pasarela == 'culqi' ||
      _pais.pasarela == 'libelula' ||
      _pais.pasarela == 'payphone';

  /// Bolivia y Ecuador: el cobro es HOSPEDADO (Libélula / PayPhone abren su
  /// propia página en un WebView), no tokenización de tarjeta en la app.
  bool get _esLibelula =>
      _pais.pasarela == 'libelula' || _pais.pasarela == 'payphone';

  @override
  void initState() {
    super.initState();
    _cargarConfig();
  }

  Future<void> _cargarConfig() async {
    final cfg = await PagosService.config();
    if (!mounted) return;
    setState(() {
      _cargando = false;
      if (cfg != null && cfg['disponible'] == true) {
        _pk = (cfg['public_key'] ?? '') as String;
        _modo = (cfg['modo'] ?? 'off').toString();
        // En modo prueba Yape no valida (Culqi sandbox); arranca en Tarjeta.
        if (_esTest) _metodo = _Metodo.tarjeta;
      }
    });
    // ¿Recarga por QR (Yape directo) activa? Solo en el flujo Perú.
    if (_pais.iso == 'PE') {
      final qr = await PagosService.recargaQrConfig();
      if (mounted && (qr?['activo'] ?? false) == true) {
        setState(() => _qrDisponible = true);
      }
    }
    // ¿Bono de recarga vigente? (banner que empuja a recargar).
    final promos = await PagosService.promos();
    final b = promos?['bono_recarga'];
    if (mounted && b is Map && (b['activo'] ?? false) == true) {
      setState(() => _promoBono = Map<String, dynamic>.from(b));
    }
  }

  @override
  void dispose() {
    _celular.dispose();
    _otp.dispose();
    _num.dispose();
    _exp.dispose();
    _cvv.dispose();
    super.dispose();
  }

  /// Recarga por LIBÉLULA (Bolivia): pago hospedado en WebView. Al confirmarse,
  /// el backend acredita el saldo (tipo 'recarga'); aquí re-sincronizamos.
  Future<void> _pagarLibelula() async {
    setState(() => _error = null);
    if (_email.isEmpty) {
      setState(() => _error = 'Inicia sesión para recargar.');
      return;
    }
    final esPayPhone = _pais.pasarela == 'payphone';
    final ok = esPayPhone
        ? await PagoPayPhone.cobrar(
            context,
            monto: _monto,
            concepto: 'Recarga de saldo Pichangol',
            email: _email,
            moneda: _mon,
            tipo: 'recarga',
            duenoId: widget.duenoId ?? _email,
          )
        : await PagoLibelula.cobrar(
            context,
            monto: _monto,
            concepto: 'Recarga de saldo Pichangol',
            email: _email,
            moneda: _mon,
            tipo: 'recarga',
            duenoId: widget.duenoId ?? _email, // billetera única: el correo
          );
    if (!mounted) return;
    if (ok) {
      await appState.sincronizarSaldo(); // el backend ya acreditó; refresca
      if (mounted) Navigator.of(context).pop(_monto);
    }
  }

  Future<void> _pagar() async {
    setState(() => _error = null);
    if (_email.isEmpty) {
      setState(() => _error = 'Inicia sesión para recargar.');
      return;
    }
    if (_pk == null || _pk!.isEmpty) {
      setState(() => _error = 'Pagos no configurados en el servidor.');
      return;
    }
    // Validación de campos ANTES de mostrar la caja de cobro.
    final centimos = PagosService.solesACentimos(_monto.toDouble());
    final cel = _celular.text.replaceAll(RegExp(r'[^0-9]'), '');
    final otp = _otp.text.replaceAll(RegExp(r'[^0-9]'), '');
    final numero = _num.text.replaceAll(' ', '');
    if (_metodo == _Metodo.yape) {
      if (cel.length != 9) {
        return setState(() => _error = 'Pon tu número de celular Yape (9 dígitos).');
      }
      if (otp.length < 6) {
        return setState(() => _error = 'Ingresa el código de aprobación de Yape (6 dígitos).');
      }
    } else {
      if (numero.length < 15) {
        return setState(() => _error = 'Número de tarjeta inválido.');
      }
      final partes = _exp.text.split('/');
      final mesN = partes.isNotEmpty ? (int.tryParse(partes[0].trim()) ?? 0) : 0;
      if (partes.length != 2 || mesN < 1 || mesN > 12) {
        return setState(() =>
            _error = 'Fecha inválida. Escribe MES/AÑO (el mes va primero), ej. 09/28.');
      }
      if (_cvv.text.length < 3) {
        return setState(() => _error = 'CVV inválido.');
      }
    }

    // Acción de pago: tokeniza (Yape/tarjeta) y cobra en el backend.
    Future<Map<String, dynamic>> accion() async {
      Map<String, dynamic> tok;
      if (_metodo == _Metodo.yape) {
        tok = await PagosService.tokenizarYape(
            publicKey: _pk!, celular: cel, otp: otp, montoCentimos: centimos);
      } else {
        final exp = _exp.text.split('/');
        final mes = int.tryParse(exp[0].trim()) ?? 0;
        var anio = int.tryParse(exp[1].trim()) ?? 0;
        if (anio < 100) anio += 2000;
        tok = await PagosService.tokenizarTarjeta(
            publicKey: _pk!, numero: numero, cvv: _cvv.text.trim(),
            mesExp: mes, anioExp: anio, email: _email);
      }
      if (tok['ok'] != true) {
        return {'ok': false, 'error': tok['error']?.toString() ?? 'No se pudo validar el pago.'};
      }
      final res = await PagosService.recargar(
        token: tok['token'].toString(),
        duenoId: widget.duenoId ?? _email, // billetera única: siempre el correo del dueño
        email: _email,
        montoSoles: _monto.toDouble(),
      );
      if (res['ok'] != true) {
        return {'ok': false, 'error': res['error']?.toString() ?? 'No se pudo acreditar.'};
      }
      return {
        'ok': true,
        'detalle': 'Se acreditaron $_mon $_monto a tu saldo.',
      };
    }

    final ok = await PagoProcesando.mostrar(
      context,
      titulo: 'Cobrando $_mon $_monto',
      exitoTitulo: '¡Recarga exitosa!',
      exitoDetalle: 'Se acreditaron $_mon $_monto a tu saldo.',
      accion: accion,
    );
    if (ok == true && mounted) Navigator.of(context).pop(_monto);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(widget.titulo ?? 'Recargar saldo')),
      body: _email.isEmpty
          ? SesionRequerida(
              motivo: 'recargar tu saldo',
              icono: Icons.account_balance_wallet_outlined,
              titulo: 'Inicia sesión para recargar',
              onLogueado: () => setState(() {}),
            )
          : !_pasarelaLista
              ? _pasarelaProximamente()
              : _esLibelula
              ? _formLibelula()
              : _cargando
          ? const CargandoPichangol()
          : ListView(
              // Regla app: contenido centrado (ancho máx) en pantallas anchas.
              padding: EdgeInsets.symmetric(
                  horizontal: ladoTablet(context, 18, 600), vertical: 18),
              children: [
                Text('¿Cuánto quieres recargar?',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    for (final m in _montos)
                      ChoiceChip(
                        label: Text('$_mon $m'),
                        selected: _monto == m,
                        selectedColor: lima,
                        labelStyle: TextStyle(
                            fontWeight: FontWeight.w800,
                            color: _monto == m ? Colors.white : cs.onSurface),
                        onSelected: (_) => setState(() => _monto = m),
                      ),
                  ],
                ),
                _bannerPromo(),
                const SizedBox(height: 22),
                Text('Método de pago',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 10),
                Row(
                  children: [
                    _MetodoBoton(
                      marca: const YapeBadge(alto: 30),
                      sel: _metodo == _Metodo.yape,
                      onTap: () => setState(() => _metodo = _Metodo.yape),
                    ),
                    const SizedBox(width: 12),
                    _MetodoBoton(
                      marca: const MarcasTarjeta(),
                      etiqueta: 'Tarjeta',
                      sel: _metodo == _Metodo.tarjeta,
                      onTap: () => setState(() => _metodo = _Metodo.tarjeta),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                if (_metodo == _Metodo.yape) _formYape() else _formTarjeta(),
                if (_pk == null || _pk!.isEmpty) ...[
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                        color: const Color(0xFFFFF1EC),
                        borderRadius: BorderRadius.circular(12)),
                    child: const Text(
                        'Las recargas con Yape y tarjeta todavía no están '
                        'activas. Estamos terminando de habilitarlas; mientras '
                        'tanto puedes seguir usando Pichangol con normalidad.',
                        style: TextStyle(fontSize: 13)),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 14),
                  Text(_error!,
                      style: const TextStyle(
                          color: Color(0xFFC0392B), fontWeight: FontWeight.w600)),
                ],
                const SizedBox(height: 22),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _pagar,
                    child: Text('Pagar $_mon $_monto'),
                  ),
                ),
                const SizedBox(height: 10),
                const Center(
                  child: Text('Pago seguro procesado por Culqi',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ),
                // RECARGA POR QR (Yape directo, sin comisión): camino
                // alternativo aprobado por el operador en la torre. Solo se
                // ofrece si el backend tiene el QR configurado (Perú).
                if (_qrDisponible) ...[
                  const SizedBox(height: 18),
                  const Row(children: [
                    Expanded(child: Divider()),
                    Padding(
                      padding: EdgeInsets.symmetric(horizontal: 10),
                      child: Text('o', style: TextStyle(color: textoTenue)),
                    ),
                    Expanded(child: Divider()),
                  ]),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                          padding:
                              const EdgeInsets.symmetric(vertical: 14)),
                      onPressed: () async {
                        final enviado = await Navigator.of(context)
                            .push<bool>(MaterialPageRoute(
                                builder: (_) => const RecargaQrScreen()));
                        // Enviada la constancia no hay monto acreditado aún
                        // (queda en revisión): se cierra sin acreditar.
                        if (enviado == true && context.mounted) {
                          Navigator.of(context).pop();
                        }
                      },
                      icon: const Icon(Icons.qr_code_2, color: bosque),
                      label: const Text(
                          'Yapear al QR de Pichangol (sin tarjeta)',
                          style: TextStyle(
                              color: bosque, fontWeight: FontWeight.w700)),
                    ),
                  ),
                ],
              ],
            ),
    );
  }

  /// Formulario de recarga para BOLIVIA (Libélula): elegir monto y pagar en la
  /// pasarela hospedada (QR · tarjeta · Tigo Money) dentro de un WebView.
  Widget _formLibelula() {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        Text('¿Cuánto quieres recargar?',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final m in _montos)
              ChoiceChip(
                label: Text('$_mon $m'),
                selected: _monto == m,
                selectedColor: lima,
                labelStyle: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: _monto == m ? Colors.white : cs.onSurface),
                onSelected: (_) => setState(() => _monto = m),
              ),
          ],
        ),
        const SizedBox(height: 22),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
              color: limaSuave, borderRadius: BorderRadius.circular(14)),
          child: Row(
            children: [
              const Icon(Icons.lock_outline, color: bosque, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                    'Pagas de forma segura con ${_pais.pasarelaNombre}. '
                    'Se abre la pasarela y, al confirmarse, se acredita tu saldo.',
                    style: const TextStyle(color: bosque, fontSize: 13)),
              ),
            ],
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 14),
          Text(_error!,
              style: const TextStyle(
                  color: Color(0xFFC0392B), fontWeight: FontWeight.w600)),
        ],
        const SizedBox(height: 22),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15)),
            onPressed: _pagarLibelula,
            icon: const Icon(Icons.lock, size: 18),
            label: Text('Pagar $_mon $_monto',
                style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 15)),
          ),
        ),
      ],
    );
  }

  /// Estado "pasarela próximamente" para países cuya integración de cobro aún no
  /// está lista (hoy: Bolivia → Libélula, #35). Muestra la moneda y la pasarela
  /// que corresponderá, para que el dueño sepa que su país está contemplado.
  Widget _pasarelaProximamente() {
    final p = _pais;
    final t = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(22),
      children: [
        const SizedBox(height: 10),
        Center(
          child: Container(
            width: 84,
            height: 84,
            decoration: BoxDecoration(
                color: limaSuave, shape: BoxShape.circle),
            child: const Icon(Icons.schedule, size: 40, color: bosque),
          ),
        ),
        const SizedBox(height: 18),
        Text('${p.bandera}  ${p.nombre}',
            textAlign: TextAlign.center,
            style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Text(
          'Estamos integrando la pasarela de pago de ${p.nombre} '
          '(${p.pasarelaNombre}) para que puedas recargar y destacar tus '
          'canchas en $_mon. Muy pronto quedará habilitada aquí mismo.',
          textAlign: TextAlign.center,
          style: t.bodyMedium?.copyWith(color: textoTenueDe(context), height: 1.35),
        ),
        const SizedBox(height: 22),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
              color: limaSuave, borderRadius: BorderRadius.circular(14)),
          child: Row(
            children: [
              const CircleAvatar(radius: 16, backgroundColor: teal, child: Icon(Icons.info_outline, size: 17, color: Colors.white)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                    'Mientras tanto, tus canchas de ${p.nombre} ya aparecen en '
                    'el mapa y reciben reservas con normalidad.',
                    style: t.bodySmall?.copyWith(color: bosque, height: 1.3)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 22),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton(
            onPressed: () => Navigator.of(context).maybePop(),
            child: const Text('Entendido'),
          ),
        ),
      ],
    );
  }

  Widget _formYape() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_esTest)
          Container(
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
                color: const Color(0xFFFFF4E5),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFD9B45A))),
            child: const Row(
              children: [
                CircleAvatar(radius: 16, backgroundColor: amarillo, child: Icon(Icons.info_outline, size: 17, color: Colors.white)),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                      'En modo prueba, Yape no valida (limitación de Culqi). '
                      'Para probar usa la pestaña Tarjeta con una tarjeta de test.',
                      style: TextStyle(fontSize: 13, color: Color(0xFF7A5B00))),
                ),
              ],
            ),
          ),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
              color: limaSuave, borderRadius: BorderRadius.circular(12)),
          child: const Text(
              'Abre tu app Yape → menú → "Código de aprobación", genera el '
              'código de 6 dígitos y ponlo aquí junto a tu celular.',
              style: TextStyle(fontSize: 13, color: bosque)),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _celular,
          keyboardType: TextInputType.phone,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(9)],
          decoration: const InputDecoration(
              labelText: 'Celular Yape', prefixText: '+51 ',
              prefixIcon: Icon(Icons.phone_android)),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _otp,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
          decoration: const InputDecoration(
              labelText: 'Código de aprobación (6 dígitos)',
              prefixIcon: Icon(Icons.password)),
        ),
      ],
    );
  }

  Widget _formTarjeta() {
    return Column(
      children: [
        TextField(
          controller: _num,
          keyboardType: TextInputType.number,
          inputFormatters: [TarjetaNumeroFormatter()],
          decoration: const InputDecoration(
              labelText: 'Número de tarjeta',
              hintText: '1234 5678 9012 3456',
              prefixIcon: Icon(Icons.credit_card)),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _exp,
                keyboardType: TextInputType.number,
                inputFormatters: [VencimientoFormatter()],
                decoration: const InputDecoration(
                    labelText: 'Vence (MM/AA)', hintText: '09/28'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _cvv,
                keyboardType: TextInputType.number,
                obscureText: true,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(4)],
                decoration: const InputDecoration(labelText: 'CVV'),
              ),
            ),
          ],
        ),
        if (_esTest) ...[
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => setState(() {
                _num.text = '4111 1111 1111 1111';
                _exp.text = '09/28';
                _cvv.text = '123';
              }),
              icon: const Icon(Icons.auto_fix_high, size: 18),
              label: const Text('Usar tarjeta de prueba (Culqi)'),
            ),
          ),
        ],
      ],
    );
  }
}

/// Botón de método de pago: muestra la MARCA real (logo Yape / Visa-Mastercard)
/// siempre a color; al seleccionar resalta con borde verde + tinte lima + check.
class _MetodoBoton extends StatelessWidget {
  const _MetodoBoton({
    required this.marca,
    required this.sel,
    required this.onTap,
    this.etiqueta,
  });
  final Widget marca;
  final String? etiqueta;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          height: 62,
          decoration: BoxDecoration(
            color: sel ? limaSuave : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: sel ? lima : const Color(0xFFE4E4E4),
                width: sel ? 2 : 1),
            boxShadow: const [
              BoxShadow(
                  color: Color(0x0F000000), blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  marca,
                  if (etiqueta != null) ...[
                    const SizedBox(width: 10),
                    Text(etiqueta!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.onSurface,
                            fontWeight: FontWeight.w700,
                            fontSize: 15)),
                  ],
                ],
              ),
              if (sel)
                const Positioned(
                  top: 6,
                  right: 8,
                  child: Icon(Icons.check_circle, color: bosque, size: 18),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
