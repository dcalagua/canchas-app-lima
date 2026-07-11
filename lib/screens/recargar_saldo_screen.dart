import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/input_formatos.dart';
import '../widgets/marcas_pago.dart';
import '../widgets/pago_procesando.dart';

/// Recarga de saldo del dueño con Culqi (tarjeta o Yape). Tokeniza con la llave
/// pública en el celular y confirma el cobro contra el backend. Devuelve el monto
/// recargado (int soles) por Navigator.pop, o null si se canceló/falló.
class RecargarSaldoScreen extends StatefulWidget {
  const RecargarSaldoScreen({super.key});

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
  String? _error;

  // Yape
  final _celular = TextEditingController();
  final _otp = TextEditingController();
  // Tarjeta
  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();

  String get _email => appState.usuario?.email ?? '';

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
      }
    });
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
      if (_exp.text.split('/').length != 2) {
        return setState(() => _error = 'Vencimiento inválido (MM/AA).');
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
        duenoId: _email,
        email: _email,
        montoSoles: _monto.toDouble(),
      );
      if (res['ok'] != true) {
        return {'ok': false, 'error': res['error']?.toString() ?? 'No se pudo acreditar.'};
      }
      return {
        'ok': true,
        'detalle': 'Se acreditaron S/ $_monto a tu saldo.',
      };
    }

    final ok = await PagoProcesando.mostrar(
      context,
      titulo: 'Cobrando S/ $_monto',
      exitoTitulo: '¡Recarga exitosa!',
      exitoDetalle: 'Se acreditaron S/ $_monto a tu saldo.',
      accion: accion,
    );
    if (ok == true && mounted) Navigator.of(context).pop(_monto);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Recargar saldo')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : ListView(
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
                        label: Text('S/ $m'),
                        selected: _monto == m,
                        selectedColor: lima,
                        labelStyle: TextStyle(
                            fontWeight: FontWeight.w800,
                            color: _monto == m ? pinoOscuro : tinta),
                        onSelected: (_) => setState(() => _monto = m),
                      ),
                  ],
                ),
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
                        'Los pagos aún no están habilitados en el servidor. '
                        'Vuelve a intentar cuando estén activas las llaves de Culqi.',
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
                        backgroundColor: pino,
                        foregroundColor: lima,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _pagar,
                    child: Text('Pagar S/ $_monto'),
                  ),
                ),
                const SizedBox(height: 10),
                const Center(
                  child: Text('Pago seguro procesado por Culqi',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ),
              ],
            ),
    );
  }

  Widget _formYape() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
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
            color: sel ? limaSuave : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: sel ? bosque : const Color(0xFFE4E4E4),
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
                        style: const TextStyle(
                            color: tinta,
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
