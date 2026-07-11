import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../screens/pago_sheet.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/input_formatos.dart';
import 'marcas_pago.dart';
import 'pago_procesando.dart';

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
  }) async {
    final cfg = await PagosService.config();
    final disponible = cfg != null && cfg['disponible'] == true;
    if (!context.mounted) return false;

    if (!disponible) {
      // Demo: pasarela simulada.
      final r = await PagoSheet.mostrar(context, monto: monto, concepto: concepto);
      return r != null && r.exito;
    }

    final pk = (cfg['public_key'] ?? '').toString();
    final esTest = (cfg['modo'] ?? '') == 'test';
    final userId = appState.usuario?.email ?? email;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _PagoTarjetaSheet(
        monto: monto,
        concepto: concepto,
        email: email,
        userId: userId,
        pk: pk,
        esTest: esTest,
      ),
    );
    return ok == true;
  }
}

class _PagoTarjetaSheet extends StatefulWidget {
  const _PagoTarjetaSheet({
    required this.monto,
    required this.concepto,
    required this.email,
    required this.userId,
    required this.pk,
    required this.esTest,
  });
  final int monto;
  final String concepto;
  final String email;
  final String userId;
  final String pk;
  final bool esTest;

  @override
  State<_PagoTarjetaSheet> createState() => _PagoTarjetaSheetState();
}

class _PagoTarjetaSheetState extends State<_PagoTarjetaSheet> {
  bool _cargando = true;
  List<Map<String, dynamic>> _guardadas = [];
  String? _cardSel; // id de la tarjeta guardada elegida; null = nueva
  bool _nueva = false; // mostrando el formulario de tarjeta nueva
  String? _error;

  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();

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
    super.dispose();
  }

  Future<void> _pagar() async {
    setState(() => _error = null);
    String? token = (!_nueva && _cardSel != null) ? _cardSel : null;

    // Tarjeta nueva: validar campos antes.
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
      return res['ok'] == true
          ? {'ok': true, 'detalle': 'Pago de S/ ${widget.monto} aprobado.'}
          : {'ok': false, 'error': res['error']?.toString() ?? 'No se pudo cobrar.'};
    }

    final ok = await PagoProcesando.mostrar(
      context,
      titulo: 'Cobrando S/ ${widget.monto}',
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
              child: Center(child: CircularProgressIndicator()))
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
                Text('Pagar S/ ${widget.monto}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 20, color: tinta)),
                const SizedBox(height: 2),
                Text(widget.concepto,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: textoTenue, fontSize: 13)),
                const SizedBox(height: 16),

                // Tarjetas guardadas.
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

                // Opción tarjeta nueva.
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
                        backgroundColor: pino,
                        foregroundColor: lima,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _pagar,
                    child: Text('Pagar S/ ${widget.monto}'),
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
          color: sel ? limaSuave : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: sel ? bosque : const Color(0xFFE4E4E4), width: sel ? 2 : 1),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 42,
              child: esVisa
                  ? const VisaMark(alto: 15)
                  : esMaster
                      ? const MastercardMark(alto: 22)
                      : const Icon(Icons.credit_card, color: bosque),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text('$marca ···· $ultimos4',
                  style: const TextStyle(fontWeight: FontWeight.w700, color: tinta)),
            ),
            if (sel) const Icon(Icons.check_circle, color: bosque, size: 20),
          ],
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
          color: sel ? limaSuave : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: sel ? bosque : const Color(0xFFE4E4E4), width: sel ? 2 : 1),
        ),
        child: Row(
          children: [
            const Icon(Icons.add_card, color: bosque),
            const SizedBox(width: 12),
            const Expanded(
              child: Text('Usar otra tarjeta',
                  style: TextStyle(fontWeight: FontWeight.w700, color: tinta)),
            ),
            if (sel) const Icon(Icons.check_circle, color: bosque, size: 20),
          ],
        ),
      ),
    );
  }
}
