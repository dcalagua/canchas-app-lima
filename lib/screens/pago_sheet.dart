import 'package:flutter/material.dart';

import '../services/payments_service.dart';
import '../theme.dart';

const Color _yape = Color(0xFF6E2A8C);

/// Hoja de pago estilo checkout (Yape o tarjeta). Demo: usa [PasarelaSimulada].
/// Devuelve el [PagoResult] por Navigator.pop (o null si se cancela).
class PagoSheet extends StatefulWidget {
  final int monto;
  final String concepto;
  final bool esRecarga;
  const PagoSheet({
    super.key,
    required this.monto,
    required this.concepto,
    this.esRecarga = false,
  });

  static Future<PagoResult?> mostrar(
    BuildContext context, {
    required int monto,
    required String concepto,
    bool esRecarga = false,
  }) {
    return showModalBottomSheet<PagoResult>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) =>
          PagoSheet(monto: monto, concepto: concepto, esRecarga: esRecarga),
    );
  }

  @override
  State<PagoSheet> createState() => _PagoSheetState();
}

class _PagoSheetState extends State<PagoSheet> {
  MetodoPago _metodo = MetodoPago.yape;
  bool _procesando = false;

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
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
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
          Text('S/ ${widget.monto}',
              style: const TextStyle(
                  fontSize: 32, fontWeight: FontWeight.bold, color: verdeCancha)),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: _OpcionMetodo(
                  activo: _metodo == MetodoPago.yape,
                  color: _yape,
                  icono: Icons.account_balance_wallet,
                  texto: 'Yape',
                  onTap: () => setState(() => _metodo = MetodoPago.yape),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _OpcionMetodo(
                  activo: _metodo == MetodoPago.tarjeta,
                  color: azulPadel,
                  icono: Icons.credit_card,
                  texto: 'Tarjeta',
                  onTap: () => setState(() => _metodo = MetodoPago.tarjeta),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_metodo == MetodoPago.yape) const _FormYape() else const _FormTarjeta(),
          const SizedBox(height: 18),
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
                  : Text('Pagar S/ ${widget.monto}'),
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Pago de demostración. La pasarela real (Culqi/Yape) se conecta con el backend en la siguiente fase.',
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
  final IconData icono;
  final String texto;
  final VoidCallback onTap;
  const _OpcionMetodo({
    required this.activo,
    required this.color,
    required this.icono,
    required this.texto,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: activo ? color.withOpacity(0.10) : Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: activo ? color : const Color(0xFFDADCE0),
              width: activo ? 2 : 1),
        ),
        child: Column(
          children: [
            Icon(icono, color: color),
            const SizedBox(height: 6),
            Text(texto,
                style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: activo ? color : Colors.black87)),
          ],
        ),
      ),
    );
  }
}

class _FormYape extends StatelessWidget {
  const _FormYape();

  @override
  Widget build(BuildContext context) {
    return const TextField(
      keyboardType: TextInputType.phone,
      decoration: InputDecoration(
        labelText: 'Número de celular Yape',
        hintText: '9XX XXX XXX',
        prefixIcon: Icon(Icons.phone_iphone),
      ),
    );
  }
}

class _FormTarjeta extends StatelessWidget {
  const _FormTarjeta();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: const [
        TextField(
          keyboardType: TextInputType.number,
          decoration: InputDecoration(
            labelText: 'Número de tarjeta',
            hintText: '4111 1111 1111 1111',
            prefixIcon: Icon(Icons.credit_card),
          ),
        ),
        SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                decoration: InputDecoration(labelText: 'MM/AA'),
              ),
            ),
            SizedBox(width: 12),
            Expanded(
              child: TextField(
                keyboardType: TextInputType.number,
                obscureText: true,
                decoration: InputDecoration(labelText: 'CVV'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
