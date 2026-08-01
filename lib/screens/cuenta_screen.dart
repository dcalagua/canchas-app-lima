import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/pagos_service.dart';
import '../services/payments_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'metodos_pago_screen.dart';
import 'pago_sheet.dart';
import 'recargar_saldo_screen.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';

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
      body: AnchoLectura(child: ListenableBuilder(
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
                  Text('Mi billetera', style: t.headlineSmall),
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
              // "Por recibir": neto de reservas online que Pichangol aún no te
              // transfiere (Fase 2). Distinto del saldo prepago.
              Builder(builder: (context) {
                final porRecibir = appState.movimientos
                    .where((m) =>
                        m.tipo == TipoMovimiento.liquidacion && !m.liquidado)
                    .fold<int>(0, (a, m) => a + m.monto);
                if (porRecibir <= 0) return const SizedBox.shrink();
                return Container(
                  margin: const EdgeInsets.only(top: 12),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: teal.withOpacity(0.10),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: teal.withOpacity(0.4)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.account_balance_wallet_outlined,
                          color: teal),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          'Por recibir de reservas online (Pichangol te transfiere aparte).',
                          style: t.bodySmall?.copyWith(height: 1.3),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text('${appState.monedaSaldoSimbolo}$porRecibir',
                          style: t.titleMedium?.copyWith(
                              color: teal, fontWeight: FontWeight.w800)),
                    ],
                  ),
                );
              }),
              const SizedBox(height: 16),
              // Tarjetas guardadas (Culqi One-Click): parte de la billetera única.
              Material(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(16),
                child: ListTile(
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                      side: BorderSide(color: trazo)),
                  leading: const CircleAvatar(
                      backgroundColor: limaSuave,
                      child: Icon(Icons.credit_card, color: bosque)),
                  title: const Text('Tarjetas guardadas',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: const Text('Para pagar y recargar rápido'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const MetodosPagoScreen())),
                ),
              ),
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
      )),
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
          Text('Es tu saldo único: el mismo para tus canchas y academias. '
              'Las comisiones de cada reserva se descuentan de aquí.',
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
    final esLiquidacion = m.tipo == TipoMovimiento.liquidacion;
    final liqPagada = esLiquidacion && m.liquidado;
    // Recarga en verde; comisión que sale del saldo en rojo; liquidación online
    // en teal si está PENDIENTE (por recibir) y en verde si ya te la pagaron.
    final color = esRecarga
        ? lima
        : (esLiquidacion ? (liqPagada ? lima : teal) : clayOscuro);
    final signo = (esRecarga || esLiquidacion) ? '+' : '−';
    final icono = esRecarga
        ? Icons.arrow_downward
        : (esLiquidacion
            ? (liqPagada
                ? Icons.check_circle_outline
                : Icons.account_balance_wallet_outlined)
            : Icons.arrow_upward);
    // Subtítulo con la FUENTE (para que se entienda de dónde salió/entró):
    //  - comisión que sale del saldo → "de tu saldo"
    //  - reserva online → "por recibir / recibido" (Pichangol te lo transfiere)
    final esComisionSaldo = !esRecarga && !esLiquidacion && m.fuente == 'saldo';
    final sub = esLiquidacion
        ? '${m.cuando} · ${liqPagada ? 'recibido' : 'por recibir'}'
        : (esComisionSaldo ? '${m.cuando} · de tu saldo' : m.cuando);
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => _mostrarRecibo(context, m),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 20,
                  backgroundColor: color.withOpacity(0.12),
                  child: Icon(icono, color: color, size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(m.concepto,
                          style:
                              t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
                      Text(sub,
                          style: t.bodySmall
                              ?.copyWith(color: textoTenueDe(context))),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('$signo ${appState.monedaSaldoSimbolo}${m.monto}',
                        style: t.titleMedium?.copyWith(
                            color: color, fontWeight: FontWeight.w700)),
                    Icon(Icons.chevron_right,
                        size: 16, color: textoTenueDe(context)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Recibo detallado de un movimiento (se abre al tocarlo): explica de dónde
/// salió/entró la plata, con el desglose bruto/comisión/neto y el comprobante.
void _mostrarRecibo(BuildContext context, MovimientoSaldo m) {
  final sim = appState.monedaSaldoSimbolo;
  final esRecarga = m.tipo == TipoMovimiento.recarga;
  final esLiquidacion = m.tipo == TipoMovimiento.liquidacion;
  final liqPagada = esLiquidacion && m.liquidado;

  String dinero(double v) => '$sim${v.toStringAsFixed(2)}';
  // Fecha larga desde el ISO (cae a la etiqueta "cuando" si no se puede).
  String fechaLarga() {
    final d = DateTime.tryParse(m.fechaIso);
    if (d == null) return m.cuando;
    final l = d.toLocal();
    final dd = l.day.toString().padLeft(2, '0');
    final mm = l.month.toString().padLeft(2, '0');
    final hh = l.hour.toString().padLeft(2, '0');
    final mi = l.minute.toString().padLeft(2, '0');
    return '$dd/$mm/${l.year} · $hh:$mi';
  }

  // Explicación de la FUENTE (lo que el usuario pedía: "de dónde salió").
  String explicacion() {
    if (esRecarga) return 'Entró a tu saldo Pichangol.';
    if (m.tipo == TipoMovimiento.consumo) {
      return m.fuente == 'saldo'
          ? 'Se descontó de tu saldo Pichangol.'
          : 'Salió de tu billetera.';
    }
    // Liquidación (reserva online):
    final transferido = liqPagada
        ? 'Ya te lo transferimos.'
        : 'Pichangol te lo transferirá (va en "Por recibir").';
    if (m.fuente == 'saldo') {
      return 'Recibes el 100% de la reserva. La comisión de Pichangol se '
          'descontó de tu SALDO (aparece como un movimiento "Comisión" aparte). '
          '$transferido';
    }
    return 'La comisión de Pichangol se descontó del PAGO del jugador; recibes '
        'el neto. $transferido';
  }

  showModalBottomSheet<void>(
    context: context,
    backgroundColor: papel,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    builder: (ctx) {
      final t = Theme.of(ctx).textTheme;
      Widget fila(String k, String v, {bool fuerte = false}) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(k, style: t.bodyMedium?.copyWith(color: textoTenueDe(ctx))),
                Text(v,
                    style: t.bodyMedium?.copyWith(
                        fontWeight: fuerte ? FontWeight.w800 : FontWeight.w600)),
              ],
            ),
          );
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 14, 22, 24),
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
                      borderRadius: BorderRadius.circular(3)),
                ),
              ),
              const SizedBox(height: 16),
              Text('Detalle del movimiento', style: t.titleLarge),
              const SizedBox(height: 2),
              Text(m.concepto,
                  style: t.bodyMedium?.copyWith(color: textoTenueDe(ctx))),
              const SizedBox(height: 16),
              fila('Fecha', fechaLarga()),
              if (esLiquidacion) ...[
                fila('Estado', liqPagada ? 'Recibido' : 'Por recibir'),
                if (m.brutoSoles > 0) fila('Reserva (bruto)', dinero(m.brutoSoles)),
                if (m.comisionSoles > 0)
                  fila('Comisión Pichangol', '− ${dinero(m.comisionSoles)}'),
                fila(m.fuente == 'saldo' ? 'Recibes (100%)' : 'Recibes (neto)',
                    dinero(m.montoSoles.abs()),
                    fuerte: true),
              ] else ...[
                if (m.comisionSoles > 0 && m.tipo == TipoMovimiento.consumo)
                  fila('Comisión', dinero(m.comisionSoles)),
                fila(esRecarga ? 'Monto' : 'Descontado',
                    dinero(m.montoSoles.abs()),
                    fuerte: true),
              ],
              if (m.comprobante > 0) fila('Comprobante', 'N.º ${m.comprobante}'),
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                    color: const Color(0xFFF1F4EE),
                    borderRadius: BorderRadius.circular(14)),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.info_outline, size: 18, color: textoTenueDe(ctx)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(explicacion(),
                          style: t.bodySmall
                              ?.copyWith(color: textoTenueDe(ctx), height: 1.35)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
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
