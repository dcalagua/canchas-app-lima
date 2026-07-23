import 'package:flutter/material.dart';

import '../services/payments_service.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import '../widgets/marcas_pago.dart';

/// Hoja de pago estilo checkout (Yape o tarjeta). Demo: usa [PasarelaSimulada].
/// Devuelve el [PagoResult] por Navigator.pop (o null si se cancela).
///
/// Multi-país (piloto): los métodos dependen del país (por la moneda). Perú =
/// Yape + tarjeta (Culqi). Otros países (Ecuador/Bolivia con Libélula, etc.) =
/// tarjeta por ahora; sus métodos locales (QR, Tigo Money…) se agregan por país
/// en la fase de pasarela real. Los logos son de marca, no íconos genéricos.
class PagoSheet extends StatefulWidget {
  final int monto;
  final String concepto;
  final bool esRecarga;
  final String moneda;
  const PagoSheet({
    super.key,
    required this.monto,
    required this.concepto,
    this.esRecarga = false,
    this.moneda = '',
  });

  static Future<PagoResult?> mostrar(
    BuildContext context, {
    required int monto,
    required String concepto,
    bool esRecarga = false,
    String moneda = '',
  }) {
    return showModalBottomSheet<PagoResult>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => PagoSheet(
          monto: monto,
          concepto: concepto,
          esRecarga: esRecarga,
          moneda: moneda),
    );
  }

  @override
  State<PagoSheet> createState() => _PagoSheetState();
}

class _PagoSheetState extends State<PagoSheet> {
  String get _mon => widget.moneda.isNotEmpty ? widget.moneda : monedaSimbolo;

  /// País del pago por la moneda. Yape solo aplica en Perú; los demás países
  /// (Libélula, etc.) van con tarjeta por ahora.
  bool get _esPeru => widget.moneda.isEmpty || widget.moneda == 'S/';

  late MetodoPago _metodo =
      _esPeru ? MetodoPago.yape : MetodoPago.tarjeta;
  bool _procesando = false;

  final _cel = TextEditingController(); // Yape
  final _num = TextEditingController();
  final _exp = TextEditingController();
  final _cvv = TextEditingController();

  @override
  void dispose() {
    _cel.dispose();
    _num.dispose();
    _exp.dispose();
    _cvv.dispose();
    super.dispose();
  }

  /// Rellena datos FICTICIOS para simular el pago sin tipear (modo demo).
  void _autocompletar() {
    setState(() {
      _cel.text = '987 654 321';
      _num.text = '4111 1111 1111 1111';
      _exp.text = '09/28';
      _cvv.text = '123';
    });
  }

  Future<void> _pagar() async {
    setState(() => _procesando = true);
    final result = widget.esRecarga
        ? await pasarela.recargarSaldo(montoSoles: widget.monto, metodo: _metodo)
        : await pasarela.cobrar(
            montoSoles: widget.monto,
            metodo: _metodo,
            concepto: widget.concepto);
    if (!mounted) return;
    Navigator.of(context).pop(result);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.fromLTRB(
          20, 14, 20, 24 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 44,
              height: 5,
              decoration: BoxDecoration(
                  color: Colors.black12, borderRadius: BorderRadius.circular(10)),
            ),
          ),
          const SizedBox(height: 18),
          Text(widget.concepto,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text('$_mon ${widget.monto}',
              style: TextStyle(
                  fontSize: 32, fontWeight: FontWeight.bold, color: cs.primary)),
          const SizedBox(height: 18),
          Row(
            children: [
              // Yape: solo Perú (por país). En otros países se ocultará hasta
              // integrar su método local (Libélula/QR/…).
              if (_esPeru) ...[
                Expanded(
                  child: _OpcionMetodo(
                    activo: _metodo == MetodoPago.yape,
                    color: const Color(0xFF742284),
                    marca: const YapeBadge(alto: 26),
                    onTap: () => setState(() => _metodo = MetodoPago.yape),
                  ),
                ),
                const SizedBox(width: 12),
              ],
              Expanded(
                child: _OpcionMetodo(
                  activo: _metodo == MetodoPago.tarjeta,
                  color: azulPadel,
                  marca: const MarcasTarjeta(),
                  texto: 'Tarjeta',
                  onTap: () => setState(() => _metodo = MetodoPago.tarjeta),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_metodo == MetodoPago.yape)
            TextField(
              controller: _cel,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Número de celular Yape',
                hintText: '9XX XXX XXX',
                prefixIcon: Icon(Icons.phone_iphone),
              ),
            )
          else ...[
            TextField(
              controller: _num,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Número de tarjeta',
                hintText: '4111 1111 1111 1111',
                prefixIcon: Icon(Icons.credit_card),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _exp,
                    decoration: const InputDecoration(labelText: 'MM/AA'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _cvv,
                    keyboardType: TextInputType.number,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'CVV'),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 10),
          // DEMO: autocompletar datos ficticios para simular sin tipear.
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: _autocompletar,
              icon: const Icon(Icons.auto_fix_high, size: 18),
              label: const Text('Autocompletar datos de prueba'),
            ),
          ),
          const SizedBox(height: 6),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: coral,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
              onPressed: _procesando ? null : _pagar,
              child: _procesando
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : Text('Pagar $_mon ${widget.monto}'),
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Pago de demostración. La pasarela real (Culqi en Perú, Libélula en '
            'Ecuador/Bolivia) se conecta con el backend en la siguiente fase.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _OpcionMetodo extends StatelessWidget {
  final bool activo;
  final Color color;
  final Widget marca; // logo de marca (YapeBadge / MarcasTarjeta)
  final String? texto; // etiqueta opcional bajo la marca
  final VoidCallback onTap;
  const _OpcionMetodo({
    required this.activo,
    required this.color,
    required this.marca,
    required this.onTap,
    this.texto,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 62,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: activo ? color.withOpacity(0.10) : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: activo ? color : const Color(0xFFDADCE0),
              width: activo ? 2 : 1),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            marca,
            if (texto != null) ...[
              const SizedBox(height: 4),
              Text(texto!,
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: activo ? color : Colors.black87)),
            ],
          ],
        ),
      ),
    );
  }
}
