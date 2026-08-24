import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

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
class CuentaScreen extends StatefulWidget {
  const CuentaScreen({super.key});

  @override
  State<CuentaScreen> createState() => _CuentaScreenState();
}

class _CuentaScreenState extends State<CuentaScreen> {
  static const _saldoBajo = 15;

  @override
  void initState() {
    super.initState();
    // Empuja la contabilidad pendiente (comisiones/liquidaciones que quedaron en
    // cola) y RE-SINCRONIZA saldo/movimientos con el backend, para que un pago
    // ONLINE recién hecho ("por recibir") aparezca al abrir la billetera sin
    // reiniciar la app. Antes (StatelessWidget) no re-sincronizaba nunca.
    appState.flushContabilidad().then((_) => appState.sincronizarSaldo());
  }

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
              Row(
                children: [
                  Expanded(
                    child: Text('Movimientos',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                  ),
                  if (appState.movimientos.isNotEmpty)
                    TextButton.icon(
                      onPressed: () => _abrirEstadoCuenta(
                          context, appState.monedaSaldoSimbolo),
                      icon: const Icon(Icons.download_outlined,
                          size: 18, color: bosque),
                      label: const Text('Estado de cuenta',
                          style: TextStyle(
                              color: bosque, fontWeight: FontWeight.w700)),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              if (appState.movimientos.isEmpty)
                Text('Aún no hay movimientos.',
                    style: t.bodyMedium?.copyWith(color: textoTenueDe(context)))
              else ...[
                // 💰 Pagos de tus CLIENTES (Pichangol te los transfiere): reservas
                // online, bonos y ventas del marketplace.
                _SeccionMov(
                  titulo: 'Por recibir',
                  subtitulo:
                      'Pagos de tus clientes: reservas online, bonos y ventas. '
                      'Pichangol te transfiere el neto.',
                  icono: Icons.south_west,
                  color: teal,
                  movs: appState.movimientos
                      .where((m) => m.tipo == TipoMovimiento.liquidacion)
                      .toList(),
                ),
                // 👛 Tu MONEDERO: recargas (+) y gastos (−).
                _SeccionMov(
                  titulo: 'Mi saldo',
                  subtitulo:
                      'Tu monedero: recargas y gastos (comisiones, servicios, Pro).',
                  icono: Icons.account_balance_wallet_outlined,
                  color: lima,
                  movs: appState.movimientos
                      .where((m) =>
                          m.tipo == TipoMovimiento.recarga ||
                          m.tipo == TipoMovimiento.consumo)
                      .toList(),
                ),
              ],
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
    final sim = appState.monedaSaldoSimbolo;
    final esRecarga = m.tipo == TipoMovimiento.recarga;
    final esLiquidacion = m.tipo == TipoMovimiento.liquidacion;
    final liqPagada = esLiquidacion && m.liquidado;
    // Los pagos de clientes (liquidación) muestran un mini-recibo con desglose.
    final conRecibo = esLiquidacion && m.brutoSoles > 0;
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
    // Medio con el que pagó el jugador (yape/tarjeta/seña), si viajó del
    // backend: el dueño ve por dónde entró la plata sin abrir el recibo.
    final medioTxt = switch (m.medio) {
      'yape' => ' · Yape',
      'tarjeta' => ' · Tarjeta',
      'sena' => ' · Seña',
      _ => '',
    };
    final sub = esLiquidacion
        ? '${m.cuando}$medioTxt · ${liqPagada ? 'recibido' : 'por recibir'}'
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
                      // Mini-recibo VISIBLE (como extracto de banco): cobrado al
                      // cliente, comisión y lo que recibes. Así nadie se pregunta
                      // "¿por qué S/190 y no S/200?" sin abrir el detalle.
                      if (esLiquidacion && m.brutoSoles > 0)
                        Container(
                          margin: const EdgeInsets.only(top: 8),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 8),
                          decoration: BoxDecoration(
                            color: const Color(0x0A000000),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Column(
                            children: [
                              _lineaRecibo(context, 'Cobrado al cliente',
                                  '$sim${montoTxt(m.brutoSoles)}'),
                              const SizedBox(height: 3),
                              _lineaRecibo(context, 'Comisión Pichangol',
                                  '−$sim${montoTxt(m.comisionSoles)}',
                                  color: clayOscuro),
                              const Divider(height: 12),
                              _lineaRecibo(
                                  context,
                                  liqPagada ? 'Recibiste' : 'Recibes',
                                  '$sim${montoTxt(m.montoSoles)}',
                                  color: liqPagada ? lima : teal,
                                  fuerte: true),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    // En un pago de cliente, el número GRANDE es lo COBRADO
                    // (la transacción, ej. S/200) — como en el banco. El neto
                    // (S/190) y la comisión van en el mini-recibo de la izquierda.
                    Text(
                        conRecibo
                            ? '$sim${montoTxt(m.brutoSoles)}'
                            : '$signo $sim${m.monto}',
                        style: t.titleMedium?.copyWith(
                            color: conRecibo
                                ? Theme.of(context).colorScheme.onSurface
                                : color,
                            fontWeight: FontWeight.w800)),
                    if (conRecibo)
                      Text('cobrado',
                          style: t.bodySmall
                              ?.copyWith(color: textoTenueDe(context))),
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

// ── Estado de cuenta (PDF por periodo, como el del banco) ────────────────────
const _mesesCortoEC = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'set', 'oct', 'nov', 'dic'
];

String _fechaCortaEC(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')} ${_mesesCortoEC[d.month - 1]} ${d.year}';

/// Hoja para elegir el PERIODO del estado de cuenta (1/2/3 meses o rango) y
/// generar el PDF descargable.
void _abrirEstadoCuenta(BuildContext context, String mon) {
  final ahora = DateTime.now();
  void gen(DateTime desde, DateTime hasta, String etiqueta) {
    Navigator.pop(context);
    _descargarEstado(context, desde, hasta, mon, etiqueta);
  }

  showModalBottomSheet<void>(
    context: context,
    backgroundColor: Theme.of(context).colorScheme.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (_) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Estado de cuenta',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 2),
            Text('Descarga tus movimientos en PDF. Elige el periodo.',
                style: TextStyle(color: textoTenueDe(context), fontSize: 12.5)),
            const SizedBox(height: 14),
            _OpcionPeriodo(
                titulo: 'Último mes',
                onTap: () => gen(
                    DateTime(ahora.year, ahora.month - 1, ahora.day),
                    ahora,
                    'Último mes')),
            _OpcionPeriodo(
                titulo: 'Últimos 2 meses',
                onTap: () => gen(
                    DateTime(ahora.year, ahora.month - 2, ahora.day),
                    ahora,
                    'Últimos 2 meses')),
            _OpcionPeriodo(
                titulo: 'Últimos 3 meses',
                onTap: () => gen(
                    DateTime(ahora.year, ahora.month - 3, ahora.day),
                    ahora,
                    'Últimos 3 meses')),
            _OpcionPeriodo(
                titulo: 'Elegir rango de fechas…',
                icono: Icons.date_range,
                onTap: () async {
                  final r = await showDateRangePicker(
                    context: context,
                    firstDate: DateTime(2024, 1, 1),
                    lastDate: ahora,
                    helpText: 'Rango del estado de cuenta',
                    saveText: 'Listo',
                  );
                  if (r == null || !context.mounted) return;
                  gen(
                      r.start,
                      DateTime(r.end.year, r.end.month, r.end.day, 23, 59, 59),
                      '${_fechaCortaEC(r.start)} – ${_fechaCortaEC(r.end)}');
                }),
          ],
        ),
      ),
    ),
  );
}

Future<void> _descargarEstado(BuildContext context, DateTime desde,
    DateTime hasta, String mon, String etiqueta) async {
  final movs = appState.movimientos.where((m) {
    final d = DateTime.tryParse(m.fechaIso)?.toLocal();
    if (d == null) return false;
    return !d.isBefore(desde) && !d.isAfter(hasta);
  }).toList()
    ..sort((a, b) => (DateTime.tryParse(b.fechaIso) ?? DateTime(0))
        .compareTo(DateTime.tryParse(a.fechaIso) ?? DateTime(0)));

  if (movs.isEmpty) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('No hay movimientos en ese periodo.')));
    return;
  }

  double ingresos = 0, egresos = 0;
  for (final m in movs) {
    if (m.montoSoles >= 0) {
      ingresos += m.montoSoles;
    } else {
      egresos += -m.montoSoles;
    }
  }

  final verde = PdfColor.fromInt(0xFF14463A);
  final rojo = PdfColor.fromInt(0xFFC13515);
  final gris = PdfColor.fromInt(0xFFF2F2F2);
  final u = appState.usuario;
  final doc = pw.Document();

  pw.Widget resumen(String k, String v, {PdfColor? color}) => pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Text(k,
              style:
                  const pw.TextStyle(fontSize: 8.5, color: PdfColors.grey700)),
          pw.SizedBox(height: 2),
          pw.Text(v,
              style: pw.TextStyle(
                  fontSize: 12,
                  fontWeight: pw.FontWeight.bold,
                  color: color ?? verde)),
        ],
      );

  doc.addPage(pw.MultiPage(
    pageFormat: PdfPageFormat.a4,
    margin: const pw.EdgeInsets.all(28),
    footer: (ctx) => pw.Container(
      alignment: pw.Alignment.centerRight,
      margin: const pw.EdgeInsets.only(top: 8),
      child: pw.Text('Página ${ctx.pageNumber} de ${ctx.pagesCount}',
          style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
    ),
    build: (ctx) => [
      pw.Container(
        padding: const pw.EdgeInsets.all(16),
        decoration: pw.BoxDecoration(
            color: verde, borderRadius: pw.BorderRadius.circular(12)),
        child: pw.Row(
          mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
              pw.Text('Pichangol',
                  style: pw.TextStyle(
                      color: PdfColors.white,
                      fontSize: 22,
                      fontWeight: pw.FontWeight.bold)),
              pw.Text('Estado de cuenta',
                  style:
                      const pw.TextStyle(color: PdfColors.white, fontSize: 11)),
            ]),
            pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.end, children: [
              if (u != null)
                pw.Text(u.nombre,
                    style: const pw.TextStyle(
                        color: PdfColors.white, fontSize: 10)),
              if (u != null && u.email.isNotEmpty)
                pw.Text(u.email,
                    style: const pw.TextStyle(
                        color: PdfColors.white, fontSize: 9)),
            ]),
          ],
        ),
      ),
      pw.SizedBox(height: 12),
      pw.Text('Periodo: $etiqueta',
          style: pw.TextStyle(fontSize: 11, fontWeight: pw.FontWeight.bold)),
      pw.Text(
          'Del ${_fechaCortaEC(desde)} al ${_fechaCortaEC(hasta)} · Generado el ${_fechaCortaEC(DateTime.now())}',
          style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey700)),
      pw.SizedBox(height: 12),
      pw.Container(
        padding: const pw.EdgeInsets.all(12),
        decoration: pw.BoxDecoration(
            color: gris, borderRadius: pw.BorderRadius.circular(10)),
        child: pw.Row(
          mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
          children: [
            resumen('Ingresos', '$mon ${ingresos.toStringAsFixed(2)}'),
            resumen('Egresos', '$mon ${egresos.toStringAsFixed(2)}', color: rojo),
            resumen('Saldo actual', '$mon ${appState.saldoClub}.00'),
            resumen('Movimientos', '${movs.length}'),
          ],
        ),
      ),
      pw.SizedBox(height: 14),
      pw.Table(
        border: pw.TableBorder(
            bottom: pw.BorderSide(color: PdfColors.grey300, width: 0.5),
            horizontalInside:
                pw.BorderSide(color: PdfColors.grey200, width: 0.5)),
        columnWidths: {
          0: const pw.FixedColumnWidth(74),
          1: const pw.FlexColumnWidth(),
          2: const pw.FixedColumnWidth(62),
          3: const pw.FixedColumnWidth(82),
        },
        children: [
          pw.TableRow(
            decoration: const pw.BoxDecoration(color: PdfColors.grey100),
            children: [
              _thEC('Fecha'),
              _thEC('Concepto'),
              _thEC('Tipo'),
              _thEC('Monto', alignRight: true),
            ],
          ),
          for (final m in movs)
            pw.TableRow(children: [
              _tdEC(_fechaCortaEC(
                  DateTime.tryParse(m.fechaIso)?.toLocal() ?? DateTime.now())),
              _celdaConceptoEC(m, mon),
              // Tipo + MEDIO con el que pagó el jugador (si se conoce):
              // "Ingreso · Yape" / "Ingreso · Tarjeta" / "Ingreso · Seña".
              _tdEC((m.montoSoles >= 0 ? 'Ingreso' : 'Egreso') +
                  switch (m.medio) {
                    'yape' => ' · Yape',
                    'tarjeta' => ' · Tarjeta',
                    'sena' => ' · Seña',
                    _ => '',
                  }),
              _tdEC(
                  '${m.montoSoles >= 0 ? '+' : '-'} $mon ${m.montoSoles.abs().toStringAsFixed(2)}',
                  alignRight: true,
                  color: m.montoSoles >= 0 ? verde : rojo),
            ]),
        ],
      ),
      pw.SizedBox(height: 16),
      pw.Text(
          'Documento generado por la app Pichangol. No es un comprobante tributario.',
          style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
    ],
  ));

  final bytes = await doc.save();
  final nombre =
      'estado_pichangol_${desde.year}${desde.month.toString().padLeft(2, '0')}${desde.day.toString().padLeft(2, '0')}_'
      '${hasta.year}${hasta.month.toString().padLeft(2, '0')}${hasta.day.toString().padLeft(2, '0')}.pdf';
  await Printing.sharePdf(bytes: bytes, filename: nombre);
}

pw.Widget _thEC(String s, {bool alignRight = false}) => pw.Padding(
      padding: const pw.EdgeInsets.symmetric(vertical: 6, horizontal: 4),
      child: pw.Text(s,
          textAlign: alignRight ? pw.TextAlign.right : pw.TextAlign.left,
          style: pw.TextStyle(
              fontSize: 9,
              fontWeight: pw.FontWeight.bold,
              color: PdfColors.grey800)),
    );

pw.Widget _tdEC(String s, {bool alignRight = false, PdfColor? color}) =>
    pw.Padding(
      padding: const pw.EdgeInsets.symmetric(vertical: 5, horizontal: 4),
      child: pw.Text(s,
          textAlign: alignRight ? pw.TextAlign.right : pw.TextAlign.left,
          style: pw.TextStyle(fontSize: 9, color: color ?? PdfColors.grey900)),
    );

/// Celda "Concepto" del PDF: para un pago de cliente (liquidación) añade el
/// mini-recibo cobrado/comisión/recibes, igual que en la app.
pw.Widget _celdaConceptoEC(MovimientoSaldo m, String mon) {
  final esLiq = m.tipo == TipoMovimiento.liquidacion && m.brutoSoles > 0;
  if (!esLiq) return _tdEC(m.concepto);
  return pw.Padding(
    padding: const pw.EdgeInsets.symmetric(vertical: 5, horizontal: 4),
    child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
      pw.Text(m.concepto,
          style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey900)),
      pw.SizedBox(height: 1),
      pw.Text(
          'Cobrado $mon${m.brutoSoles.toStringAsFixed(2)} · '
          'comisión $mon${m.comisionSoles.toStringAsFixed(2)} · '
          'recibes $mon${m.montoSoles.toStringAsFixed(2)}',
          style: const pw.TextStyle(fontSize: 7.5, color: PdfColors.grey600)),
    ]),
  );
}

/// Fila de opción de periodo en la hoja de "Estado de cuenta".
class _OpcionPeriodo extends StatelessWidget {
  const _OpcionPeriodo({required this.titulo, required this.onTap, this.icono});
  final String titulo;
  final VoidCallback onTap;
  final IconData? icono;
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        leading: CircleAvatar(
          radius: 18,
          backgroundColor: bosque.withOpacity(0.10),
          child: Icon(icono ?? Icons.picture_as_pdf_outlined,
              size: 18, color: bosque),
        ),
        title:
            Text(titulo, style: const TextStyle(fontWeight: FontWeight.w700)),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
      ),
    );
  }
}

/// Etiqueta de día para agrupar movimientos: "Hoy" / "Ayer" / "12 ago".
String _diaLabelMov(String iso, String cuando) {
  final d = DateTime.tryParse(iso);
  if (d == null) return cuando.isEmpty ? 'Anteriores' : cuando;
  final now = DateTime.now();
  final dd = DateTime(d.year, d.month, d.day);
  final hoy = DateTime(now.year, now.month, now.day);
  final diff = hoy.difference(dd).inDays;
  if (diff == 0) return 'Hoy';
  if (diff == 1) return 'Ayer';
  const meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  final anio = d.year != now.year ? ' ${d.year}' : '';
  return '${d.day} ${meses[d.month - 1]}$anio';
}

/// Sección de movimientos de la billetera (una por "mundo": Por recibir / Mi
/// saldo), agrupada por día. Se oculta si no tiene movimientos.
class _SeccionMov extends StatelessWidget {
  const _SeccionMov({
    required this.titulo,
    required this.subtitulo,
    required this.icono,
    required this.color,
    required this.movs,
  });
  final String titulo;
  final String subtitulo;
  final IconData icono;
  final Color color;
  final List<MovimientoSaldo> movs;

  @override
  Widget build(BuildContext context) {
    if (movs.isEmpty) return const SizedBox.shrink();
    final t = Theme.of(context).textTheme;
    // `movs` ya viene del más reciente al más antiguo. Insertamos un encabezado
    // de día cuando cambia la fecha.
    final filas = <Widget>[];
    String? dia;
    for (final m in movs) {
      final d = _diaLabelMov(m.fechaIso, m.cuando);
      if (d != dia) {
        dia = d;
        filas.add(Padding(
          padding: const EdgeInsets.only(top: 12, bottom: 2),
          child: Text(d,
              style: t.bodySmall?.copyWith(
                  color: textoTenueDe(context), fontWeight: FontWeight.w700)),
        ));
      }
      filas.add(_FilaMovimiento(m));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 18),
        Row(
          children: [
            Icon(icono, size: 18, color: color),
            const SizedBox(width: 6),
            Text(titulo,
                style: t.titleSmall
                    ?.copyWith(fontWeight: FontWeight.w800, color: color)),
          ],
        ),
        const SizedBox(height: 2),
        Text(subtitulo,
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ...filas,
      ],
    );
  }
}

/// Una línea del mini-recibo dentro de un movimiento (etiqueta a la izquierda,
/// monto a la derecha). `fuerte` resalta el total (lo que recibe el dueño).
Widget _lineaRecibo(BuildContext context, String etiqueta, String valor,
    {Color? color, bool fuerte = false}) {
  final t = Theme.of(context).textTheme;
  final estilo = (fuerte ? t.bodyMedium : t.bodySmall)?.copyWith(
      color: color ?? textoTenueDe(context),
      fontWeight: fuerte ? FontWeight.w800 : FontWeight.w600);
  return Row(
    mainAxisAlignment: MainAxisAlignment.spaceBetween,
    children: [
      Text(etiqueta,
          style: t.bodySmall?.copyWith(
              color: color ?? textoTenueDe(context),
              fontWeight: fuerte ? FontWeight.w800 : FontWeight.w500)),
      Text(valor, style: estilo),
    ],
  );
}
