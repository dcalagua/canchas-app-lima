import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/pais.dart';
import '../screens/login_google_sheet.dart';
import '../screens/pago_sheet.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'cargando_pichangol.dart';
import '../utils/input_formatos.dart';
import 'marcas_pago.dart';
import 'pago_libelula.dart';
import 'pago_procesando.dart';
import '../utils/moneda.dart';

/// Flujo de cobro reutilizable al jugador (reservas, matrículas). Deja elegir
/// una **tarjeta guardada** (Culqi One Click) o **una nueva**, tokeniza, cobra
/// contra el backend y muestra la caja "cobrándose". Devuelve true si el pago
/// fue exitoso.
///
/// Si Culqi no está configurado (o no hay backend), cae a la pasarela SIMULADA
/// para no romper la demo.
class PagoTarjeta {
  static Future<bool> cobrar(
    BuildContext context, {
    required int monto,
    required String concepto,
    required String email,
    String moneda = '',
    ValueChanged<String>? onToken, // recibe el token (tkn_/crd_) usado si el pago fue OK
    ValueChanged<String>? onOperacion, // recibe el N.º de operación (charge_id)
  }) async {
    // BOLIVIA: la pasarela es Libélula (no Culqi). Se detecta por el país actual
    // (GPS/selección). El pago se hace en la página hospedada de Libélula dentro
    // de un WebView (QR · tarjeta · Tigo Money).
    if (paisActual.pasarela == 'libelula') {
      return PagoLibelula.cobrar(context,
          monto: monto, concepto: concepto, email: email,
          moneda: moneda.isNotEmpty ? moneda : 'Bs');
    }

    final cfg = await PagosService.config();
    final disponible = cfg != null && cfg['disponible'] == true;
    if (!context.mounted) return false;

    if (!disponible) {
      // Demo: pasarela simulada.
      final r = await PagoSheet.mostrar(context,
          monto: monto, concepto: concepto, moneda: moneda);
      return r != null && r.exito;
    }

    final pk = (cfg['public_key'] ?? '').toString();
    final esTest = (cfg['modo'] ?? '') == 'test';
    // Culqi EXIGE un email válido. Resuélvelo (sesión > el pasado) y, si falta,
    // pide login AQUÍ antes de cobrar (evita el error "invalid_email").
    var correo = (appState.usuario?.email ?? '').trim();
    if (!_emailValido(correo)) correo = email.trim();
    if (!_emailValido(correo)) {
      final entro = await LoginGoogleSheet.mostrar(context, motivo: 'pagar');
      if (!context.mounted) return false;
      if (!entro) return false;
      correo = (appState.usuario?.email ?? '').trim();
      if (!_emailValido(correo)) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content:
                Text('Necesitas una cuenta con correo válido para pagar.')));
        return false;
      }
    }
    final userId = correo;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _PagoTarjetaSheet(
        monto: monto,
        concepto: concepto,
        email: correo,
        userId: userId,
        pk: pk,
        esTest: esTest,
        moneda: moneda,
        onToken: onToken,
        onOperacion: onOperacion,
      ),
    );
    return ok == true;
  }

  /// Email con formato mínimo válido (Culqi lo rechaza si no lo tiene).
  static bool _emailValido(String e) =>
      RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(e.trim());
}

class _PagoTarjetaSheet extends StatefulWidget {
  const _PagoTarjetaSheet({
    required this.monto,
    required this.concepto,
    required this.email,
    required this.userId,
    required this.pk,
    required this.esTest,
    this.moneda = '',
    this.onToken,
    this.onOperacion,
  });
  final int monto;
  final String concepto;
  final String email;
  final String userId;
  final String pk;
  final bool esTest;
  final String moneda;
  final ValueChanged<String>? onToken;
  final ValueChanged<String>? onOperacion;

  @override
  State<_PagoTarjetaSheet> createState() => _PagoTarjetaSheetState();
}

enum _Metodo { yape, tarjeta }

class _PagoTarjetaSheetState extends State<_PagoTarjetaSheet> {
  String get _mon => widget.moneda.isNotEmpty ? widget.moneda : monedaSimbolo;
  bool _cargando = true;
  _Metodo _metodo = _Metodo.tarjeta;
  List<Map<String, dynamic>> _guardadas = [];
  String? _cardSel; // id de la tarjeta guardada elegida; null = nueva
  bool _nueva = false; // mostrando el formulario de tarjeta nueva
  String? _error;

  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();
  final _cel = TextEditingController(); // Yape
  final _otp = TextEditingController(); // Yape

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final lista = await PagosService.metodos(widget.userId);
    if (!mounted) return;
    setState(() {
      _guardadas = lista;
      _cargando = false;
      if (lista.isNotEmpty) {
        _cardSel = lista.first['id'].toString();
      } else {
        _nueva = true;
      }
    });
  }

  @override
  void dispose() {
    _num.dispose();
    _exp.dispose();
    _cvv.dispose();
    _cel.dispose();
    _otp.dispose();
    super.dispose();
  }

  Future<void> _pagar() async {
    setState(() => _error = null);
    final centimos = widget.monto * 100;

    // --- YAPE ---
    if (_metodo == _Metodo.yape) {
      final cel = _cel.text.replaceAll(RegExp(r'[^0-9]'), '');
      final otp = _otp.text.replaceAll(RegExp(r'[^0-9]'), '');
      if (cel.length != 9) {
        return setState(() => _error = 'Pon tu celular Yape (9 dígitos).');
      }
      if (otp.length < 6) {
        return setState(() => _error = 'Ingresa el código de aprobación de Yape (6 dígitos).');
      }
      Future<Map<String, dynamic>> accionYape() async {
        final t = await PagosService.tokenizarYape(
            publicKey: widget.pk, celular: cel, otp: otp, montoCentimos: centimos);
        if (t['ok'] != true) {
          return {'ok': false, 'error': t['error']?.toString() ?? 'No se pudo validar el Yape.'};
        }
        final res = await PagosService.cobrar(
            token: t['token'].toString(), email: widget.email,
            montoSoles: widget.monto.toDouble(), concepto: widget.concepto);
        if (res['ok'] == true && res['chargeId'] != null) {
          widget.onOperacion?.call(res['chargeId'].toString());
        }
        return res['ok'] == true
            ? {'ok': true, 'detalle': 'Pago de $_mon ${widget.monto} aprobado.'}
            : {'ok': false, 'error': res['error']?.toString() ?? 'No se pudo cobrar.'};
      }
      final ok = await PagoProcesando.mostrar(context,
          titulo: 'Cobrando $_mon ${widget.monto}', exitoTitulo: '¡Pago aprobado!',
          accion: accionYape);
      if (ok == true && mounted) Navigator.of(context).pop(true);
      return;
    }

    // --- TARJETA ---
    String? token = (!_nueva && _cardSel != null) ? _cardSel : null;
    final numero = _num.text.replaceAll(' ', '');
    int mes = 0;
    int anio = 0;
    if (token == null) {
      if (numero.length < 15) return setState(() => _error = 'Número de tarjeta inválido.');
      final partes = _exp.text.split('/');
      mes = partes.isNotEmpty ? (int.tryParse(partes[0].trim()) ?? 0) : 0;
      if (partes.length != 2 || mes < 1 || mes > 12) {
        return setState(() => _error = 'Fecha inválida. MES/AÑO, ej. 09/28.');
      }
      anio = int.tryParse(partes[1].trim()) ?? 0;
      if (anio < 100) anio += 2000;
      if (_cvv.text.length < 3) return setState(() => _error = 'CVV inválido.');
    }

    Future<Map<String, dynamic>> accion() async {
      var tk = token;
      if (tk == null) {
        final t = await PagosService.tokenizarTarjeta(
            publicKey: widget.pk, numero: numero, cvv: _cvv.text.trim(),
            mesExp: mes, anioExp: anio, email: widget.email);
        if (t['ok'] != true) {
          return {'ok': false, 'error': t['error']?.toString() ?? 'Tarjeta rechazada.'};
        }
        tk = t['token'].toString();
      }
      final res = await PagosService.cobrar(
        token: tk, email: widget.email,
        montoSoles: widget.monto.toDouble(), concepto: widget.concepto);
      if (res['ok'] == true) {
        widget.onToken?.call(tk!);
        if (res['chargeId'] != null) {
          widget.onOperacion?.call(res['chargeId'].toString());
        }
      }
      return res['ok'] == true
          ? {'ok': true, 'detalle': 'Pago de $_mon ${widget.monto} aprobado.'}
          : {'ok': false, 'error': res['error']?.toString() ?? 'No se pudo cobrar.'};
    }

    final ok = await PagoProcesando.mostrar(
      context,
      titulo: 'Cobrando $_mon ${widget.monto}',
      exitoTitulo: '¡Pago aprobado!',
      accion: accion,
    );
    if (ok == true && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 16, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: _cargando
          ? const Padding(
              padding: EdgeInsets.all(30),
              child: CargandoPichangol())
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40, height: 4,
                    decoration: BoxDecoration(
                        color: trazo, borderRadius: BorderRadius.circular(99)),
                  ),
                ),
                const SizedBox(height: 16),
                Text('Pagar $_mon ${widget.monto}',
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 20,
                        color: Theme.of(context).colorScheme.onSurface)),
                const SizedBox(height: 2),
                Text(widget.concepto,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: textoTenue, fontSize: 13)),
                const SizedBox(height: 16),

                // Selector de método: Yape o Tarjeta.
                Row(
                  children: [
                    _MetodoMini(
                      marca: const YapeBadge(alto: 26),
                      sel: _metodo == _Metodo.yape,
                      onTap: () => setState(() => _metodo = _Metodo.yape),
                    ),
                    const SizedBox(width: 10),
                    _MetodoMini(
                      marca: const MarcasTarjeta(),
                      etiqueta: 'Tarjeta',
                      sel: _metodo == _Metodo.tarjeta,
                      onTap: () => setState(() => _metodo = _Metodo.tarjeta),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                // --- YAPE ---
                if (_metodo == _Metodo.yape) ...[
                  if (widget.esTest)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                          color: const Color(0xFFFFF4E5),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0xFFF2C94C))),
                      child: const Text(
                          'En modo prueba, Yape no valida (limitación de Culqi). '
                          'Para probar usa Tarjeta.',
                          style: TextStyle(fontSize: 13, color: Color(0xFF7A5B00))),
                    ),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                        color: limaSuave, borderRadius: BorderRadius.circular(12)),
                    child: const Text(
                        'Abre Yape → "Código de aprobación", genera el código de '
                        '6 dígitos y ponlo aquí con tu celular.',
                        style: TextStyle(fontSize: 13, color: bosque)),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _cel,
                    keyboardType: TextInputType.phone,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(9)
                    ],
                    decoration: const InputDecoration(
                        labelText: 'Celular Yape', prefixText: '+51 ',
                        prefixIcon: Icon(Icons.phone_android)),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _otp,
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(6)
                    ],
                    decoration: const InputDecoration(
                        labelText: 'Código de aprobación (6 dígitos)',
                        prefixIcon: Icon(Icons.password)),
                  ),
                ],

                // --- TARJETA (guardadas + nueva) ---
                if (_metodo == _Metodo.tarjeta) ...[
                for (final m in _guardadas)
                  _FilaCard(
                    marca: (m['marca'] ?? 'Tarjeta').toString(),
                    ultimos4: (m['ultimos4'] ?? '').toString(),
                    sel: !_nueva && _cardSel == m['id'].toString(),
                    onTap: () => setState(() {
                      _nueva = false;
                      _cardSel = m['id'].toString();
                    }),
                  ),
                _FilaNueva(
                  sel: _nueva,
                  onTap: () => setState(() => _nueva = true),
                ),
                if (_nueva) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _num,
                    keyboardType: TextInputType.number,
                    inputFormatters: [TarjetaNumeroFormatter()],
                    decoration: const InputDecoration(
                        labelText: 'Número de tarjeta',
                        hintText: '1234 5678 9012 3456',
                        prefixIcon: Icon(Icons.credit_card)),
                  ),
                  const SizedBox(height: 10),
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
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                            LengthLimitingTextInputFormatter(4)
                          ],
                          decoration: const InputDecoration(labelText: 'CVV'),
                        ),
                      ),
                    ],
                  ),
                  if (widget.esTest)
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

                if (_error != null) ...[
                  const SizedBox(height: 10),
                  Text(_error!,
                      style: const TextStyle(
                          color: Color(0xFFC0392B), fontWeight: FontWeight.w600)),
                ],
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _pagar,
                    child: Text('Pagar $_mon ${widget.monto}'),
                  ),
                ),
                const SizedBox(height: 8),
                const Center(
                  child: Text('Pago seguro procesado por Culqi',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ),
              ],
            ),
    );
  }
}

class _FilaCard extends StatelessWidget {
  const _FilaCard(
      {required this.marca,
      required this.ultimos4,
      required this.sel,
      required this.onTap});
  final String marca;
  final String ultimos4;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final esVisa = marca.toLowerCase().contains('visa');
    final esMaster = marca.toLowerCase().contains('master');
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: sel ? limaSuave : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: sel ? lima : const Color(0xFFE4E4E4), width: sel ? 2 : 1),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 42,
              child: esVisa
                  ? const VisaMark(alto: 15)
                  : esMaster
                      ? const MastercardMark(alto: 22)
                      : Icon(Icons.credit_card,
                          color: Theme.of(context).colorScheme.primary),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text('$marca ···· $ultimos4',
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: sel
                          ? bosque
                          : Theme.of(context).colorScheme.onSurface)),
            ),
            if (sel) const Icon(Icons.check_circle, color: bosque, size: 20),
          ],
        ),
      ),
    );
  }
}

/// Botón mini de método (Yape / Tarjeta) con la marca real y check al elegir.
class _MetodoMini extends StatelessWidget {
  const _MetodoMini(
      {required this.marca, required this.sel, required this.onTap, this.etiqueta});
  final Widget marca;
  final String? etiqueta;
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            color: sel ? limaSuave : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: sel ? lima : const Color(0xFFE4E4E4), width: sel ? 2 : 1),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  marca,
                  if (etiqueta != null) ...[
                    const SizedBox(width: 8),
                    Text(etiqueta!,
                        style: TextStyle(
                            color: sel
                                ? bosque
                                : Theme.of(context).colorScheme.onSurface,
                            fontWeight: FontWeight.w700)),
                  ],
                ],
              ),
              if (sel)
                const Positioned(
                    top: 4,
                    right: 6,
                    child: Icon(Icons.check_circle, color: bosque, size: 16)),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilaNueva extends StatelessWidget {
  const _FilaNueva({required this.sel, required this.onTap});
  final bool sel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: sel ? limaSuave : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: sel ? lima : const Color(0xFFE4E4E4), width: sel ? 2 : 1),
        ),
        child: Row(
          children: [
            Icon(Icons.add_card, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Text('Usar otra tarjeta',
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: sel
                          ? bosque
                          : Theme.of(context).colorScheme.onSurface)),
            ),
            if (sel) const Icon(Icons.check_circle, color: bosque, size: 20),
          ],
        ),
      ),
    );
  }
}
