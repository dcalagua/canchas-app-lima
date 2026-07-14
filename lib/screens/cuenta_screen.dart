import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/pagos_service.dart';
import '../services/payments_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'pago_sheet.dart';
import 'recargar_saldo_screen.dart';
import '../utils/moneda.dart';

/// Cuenta del club: saldo prepago (modelo inDrive), recargas y movimientos.
class CuentaScreen extends StatelessWidget {
  const CuentaScreen({super.key});

  static const _saldoBajo = 15;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? Theme.of(context).scaffoldBackgroundColor
          : papelCalido,
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: EdgeInsets.fromLTRB(
                18, 18 + MediaQuery.of(context).padding.top, 18, 28),
            children: [
              Row(
                children: [
                  GestureDetector(
                    onTap: () => Navigator.of(context).maybePop(),
                    child: Padding(
                      padding: const EdgeInsets.only(right: 10),
                      child: Icon(Icons.arrow_back_ios_new,
                          color: Theme.of(context).colorScheme.onSurface,
                          size: 20),
                    ),
                  ),
                  Text('Mi cuenta', style: t.headlineSmall),
                ],
              ),
              const SizedBox(height: 16),
              _TarjetaSaldo(
                saldo: appState.saldoClub,
                destacado: appState.destacadoActivo,
                onRecargar: () => _abrirRecarga(context),
              ),
              if (appState.saldoClub <= _saldoBajo) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF1EC),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: clay.withOpacity(0.5)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.warning_amber_rounded, color: clayOscuro),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Saldo bajo: si llega a 0 dejas de aparecer destacado. '
                          'Recarga para seguir recibiendo reservas.',
                          style: t.bodySmall
                              ?.copyWith(color: clayOscuro, height: 1.3),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 22),
              Text('Movimientos',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              if (appState.movimientos.isEmpty)
                Text('Aún no hay movimientos.',
                    style: t.bodyMedium?.copyWith(color: textoTenueDe(context)))
              else
                ...appState.movimientos.map((m) => _FilaMovimiento(m)),
            ],
          );
        },
      ),
    );
  }

  Future<void> _abrirRecarga(BuildContext context) async {
    // Con backend de pagos disponible → flujo REAL con Culqi (tarjeta/Yape).
    if (PagosService.disponible) {
      final monto = await Navigator.of(context).push<int>(
          MaterialPageRoute(builder: (_) => const RecargarSaldoScreen()));
      if (monto != null && monto > 0) {
        appState.recargar(monto); // refleja el saldo en la UI (autoritativo: backend)
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: pino,
          content: Text('✅ Recargaste ${appState.monedaSaldoSimbolo}$monto. ¡Ya apareces destacado!'),
        ));
      }
      return;
    }
    // Fallback (demo sin backend): pasarela simulada.
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _RecargaSheet(
        onRecargar: (monto) async {
          Navigator.of(sheetContext).pop();
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
                backgroundColor: pino,
                content: Text(
                    '✅ Recargaste ${appState.monedaSaldoSimbolo}$monto. ¡Ya apareces destacado! (${res.referencia})'),
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
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        // Degradado verde WhatsApp (antes era negro): look más cálido y de marca.
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF128C7E), Color(0xFF075E54)],
        ),
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
              color: const Color(0xFF075E54).withOpacity(0.35),
              blurRadius: 18,
              offset: const Offset(0, 8)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Saldo Pichangol',
                  style: t.bodyMedium?.copyWith(color: Colors.white70)),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(destacado ? 0.20 : 0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(destacado ? Icons.star : Icons.pause_circle_filled,
                        color: Colors.white, size: 14),
                    const SizedBox(width: 5),
                    Text(destacado ? 'Destacado' : 'Pausado',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 11,
                            fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text('${appState.monedaSaldoSimbolo} $saldo.00',
              style: t.displaySmall?.copyWith(
                  color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text('Las comisiones de cada reserva nueva se descuentan de aquí.',
              style: t.bodySmall?.copyWith(color: Colors.white60)),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: lima,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
              onPressed: onRecargar,
              icon: const Icon(Icons.add),
              label: const Text('Recargar saldo'),
            ),
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
    final t = Theme.of(context).textTheme;
    final esRecarga = m.tipo == TipoMovimiento.recarga;
    // Congruencia con el acento de la app: ingresos en verde WhatsApp (lima),
    // egresos en rojo. Antes usaba un lima brillante (#C4F542) que desentonaba.
    final color = esRecarga ? lima : clayOscuro;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: color.withOpacity(0.12),
            child: Icon(esRecarga ? Icons.arrow_downward : Icons.arrow_upward,
                color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(m.concepto,
                    style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
                Text(m.cuando,
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ],
            ),
          ),
          Text('${esRecarga ? '+' : '−'} ${appState.monedaSaldoSimbolo}${m.monto}',
              style: t.titleMedium
                  ?.copyWith(color: color, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _RecargaSheet extends StatelessWidget {
  final ValueChanged<int> onRecargar;
  const _RecargaSheet({required this.onRecargar});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    const montos = [20, 50, 100, 200];
    return Container(
      decoration: const BoxDecoration(
        color: papel,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: const EdgeInsets.fromLTRB(22, 14, 22, 30),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 5,
              decoration: BoxDecoration(
                color: const Color(0xFFD8D3C6),
                borderRadius: BorderRadius.circular(3),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Text('Elige cuánto recargar', style: t.titleLarge),
          const SizedBox(height: 4),
          Text('Mientras tengas saldo, tu club aparece destacado en el mapa.',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
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
            style: t.bodySmall?.copyWith(color: const Color(0xFFA39D91)),
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
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: trazo),
          ),
          alignment: Alignment.center,
          child: Text('${appState.monedaSaldoSimbolo} $monto',
              style: const TextStyle(
                  color: pino, fontWeight: FontWeight.w800, fontSize: 20)),
        ),
      ),
    );
  }
}
