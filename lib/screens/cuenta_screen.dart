import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/payments_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'pago_sheet.dart';

/// Cuenta del club: saldo prepago (modelo inDrive), recargas y movimientos.
class CuentaScreen extends StatelessWidget {
  const CuentaScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mi cuenta')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _TarjetaSaldo(
                saldo: appState.saldoClub,
                destacado: appState.destacadoActivo,
                onRecargar: () => _abrirRecarga(context),
              ),
              const SizedBox(height: 18),
              Text('Movimientos',
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              if (appState.movimientos.isEmpty)
                Text('Aún no hay movimientos.',
                    style: TextStyle(color: Colors.grey[600]))
              else
                ...appState.movimientos.map((m) => _FilaMovimiento(m)),
            ],
          );
        },
      ),
    );
  }

  void _abrirRecarga(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _RecargaSheet(
        onRecargar: (monto) async {
          Navigator.of(sheetContext).pop(); // cierra la selección de monto
          final res = await PagoSheet.mostrar(
            context,
            monto: monto,
            concepto: 'Recarga de saldo',
            esRecarga: true,
          );
          if (res != null && res.exito) {
            appState.recargar(monto);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                backgroundColor: verdeCancha,
                content: Text(
                    '✅ Recargaste S/ $monto. ¡Ya apareces destacado! (${res.referencia})'),
              ),
            );
          }
        },
      ),
    );
  }
}

class _TarjetaSaldo extends StatelessWidget {
  final int saldo;
  final bool destacado;
  final VoidCallback onRecargar;
  const _TarjetaSaldo(
      {required this.saldo, required this.destacado, required this.onRecargar});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [verdeClaro, verdeOscuro],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Saldo disponible',
              style: TextStyle(color: Colors.white70, fontSize: 14)),
          const SizedBox(height: 4),
          Text('S/ $saldo',
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 40,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.18),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(destacado ? Icons.star : Icons.pause_circle_filled,
                    color: destacado ? lima : Colors.white, size: 16),
                const SizedBox(width: 6),
                Text(
                  destacado
                      ? 'Destacado activo · apareces primero'
                      : 'Pausado · recarga para aparecer',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: coral,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              onPressed: onRecargar,
              icon: const Icon(Icons.add),
              label: const Text('Recargar saldo'),
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Cada reserva nueva descuenta una pequeña comisión de tu saldo. '
            'Solo pagas por las reservas que la app te trae.',
            style: TextStyle(color: Colors.white70, fontSize: 12, height: 1.4),
          ),
        ],
      ),
    );
  }
}

class _FilaMovimiento extends StatelessWidget {
  final MovimientoSaldo m;
  const _FilaMovimiento(this.m);

  @override
  Widget build(BuildContext context) {
    final esRecarga = m.tipo == TipoMovimiento.recarga;
    final color = esRecarga ? verdeCancha : coral;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: color.withOpacity(0.14),
          child: Icon(esRecarga ? Icons.arrow_downward : Icons.arrow_upward,
              color: color, size: 20),
        ),
        title: Text(m.concepto,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        subtitle: Text(m.cuando),
        trailing: Text(
          '${esRecarga ? '+' : '−'} S/ ${m.monto}',
          style: TextStyle(
              color: color, fontWeight: FontWeight.bold, fontSize: 15),
        ),
      ),
    );
  }
}

class _RecargaSheet extends StatelessWidget {
  final ValueChanged<int> onRecargar;
  const _RecargaSheet({required this.onRecargar});

  @override
  Widget build(BuildContext context) {
    const montos = [20, 50, 100, 200];
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 44,
              height: 5,
              decoration: BoxDecoration(
                color: Colors.black12,
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text('Elige cuánto recargar',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text('Mientras tengas saldo, tu club aparece destacado en el mapa.',
              style: TextStyle(color: Colors.grey[600], fontSize: 13)),
          const SizedBox(height: 16),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 2.4,
            children: [
              for (final m in montos)
                _BotonMonto(monto: m, onTap: () => onRecargar(m)),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Pago con tarjeta o Yape (se conectará la pasarela en la siguiente fase).',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey[500], fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _BotonMonto extends StatelessWidget {
  final int monto;
  final VoidCallback onTap;
  const _BotonMonto({required this.monto, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFFEAF6EF),
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Center(
          child: Text(
            'S/ $monto',
            style: const TextStyle(
                color: verdeOscuro, fontWeight: FontWeight.bold, fontSize: 20),
          ),
        ),
      ),
    );
  }
}
