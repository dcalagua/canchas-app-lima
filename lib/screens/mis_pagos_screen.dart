import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';

/// Un renglón del estado de cuenta del JUGADOR (un pago que hizo o una reserva).
class _Pago {
  final DateTime fecha;
  final String titulo;
  final String sub;
  final String moneda;
  final double monto;
  final bool cubiertoConBono; // reserva pagada con bono → S/0 fresco
  final bool pendiente; // efectivo por pagar en la cancha
  const _Pago({
    required this.fecha,
    required this.titulo,
    required this.sub,
    required this.moneda,
    required this.monto,
    this.cubiertoConBono = false,
    this.pendiente = false,
  });
}

/// "Mis pagos" (estado de cuenta del JUGADOR): todo lo que pagó en Pichangol —
/// compras de bonos y reservas (online / con bono / efectivo por pagar). Le da
/// claridad y confianza: ve cada movimiento como en el banco. Device-first
/// (arma la lista desde sus reservas y bonos locales/sincronizados).
class MisPagosScreen extends StatefulWidget {
  const MisPagosScreen({super.key});

  @override
  State<MisPagosScreen> createState() => _MisPagosScreenState();
}

class _MisPagosScreenState extends State<MisPagosScreen> {
  @override
  void initState() {
    super.initState();
    appState.cargarMisBonos();
  }

  Cancha? _cancha(String id) {
    for (final c in appState.todasLasCanchas()) {
      if (c.id == id) return c;
    }
    return null;
  }

  List<_Pago> _armar() {
    final pagos = <_Pago>[];
    // 1) Compras de bonos (pago real, una vez).
    for (final b in appState.misBonos) {
      pagos.add(_Pago(
        fecha: b.creado,
        titulo: 'Bono de ${b.horasTotal} horas',
        sub: b.club,
        moneda: appState.monedaDeClub(b.club),
        monto: b.precio,
      ));
    }
    // 2) Reservas del jugador.
    for (final r in appState.misReservas) {
      if (r.estado == EstadoReserva.noShow) continue;
      final cancha = _cancha(r.canchaId);
      final lugar = cancha?.club.isNotEmpty == true
          ? cancha!.club
          : (cancha?.nombre ?? 'Cancha');
      final cuando = '${r.dia} ${r.horaInicio}–${r.horaFin}';
      pagos.add(_Pago(
        fecha: DateTime.tryParse(r.fecha) ?? DateTime.now(),
        titulo: 'Reserva · $lugar',
        sub: cuando,
        moneda: r.monedaSimbolo,
        monto: r.esBono ? 0 : r.totalConExtras,
        cubiertoConBono: r.esBono,
        pendiente: !r.esBono && !r.pagado,
      ));
    }
    pagos.sort((a, b) => b.fecha.compareTo(a.fecha)); // más reciente primero
    return pagos;
  }

  String _diaLabel(DateTime d) {
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis pagos')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final pagos = _armar();
          final t = Theme.of(context).textTheme;
          return RefreshIndicator(
            onRefresh: () async {
              await appState.cargarMisBonos();
              await appState.cargarReservasRemotas();
            },
            child: AnchoLectura(
              child: pagos.isEmpty
                  ? ListView(children: const [SizedBox(height: 90), _Vacio()])
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(18, 12, 18, 24),
                      children: [
                        Text(
                            'Tu estado de cuenta: bonos que compraste y reservas '
                            '(pagadas online, con bono, o por pagar en la cancha).',
                            style: t.bodySmall
                                ?.copyWith(color: textoTenueDe(context))),
                        const SizedBox(height: 8),
                        ..._conFechas(pagos),
                      ],
                    ),
            ),
          );
        },
      ),
    );
  }

  List<Widget> _conFechas(List<_Pago> pagos) {
    final out = <Widget>[];
    String? dia;
    for (final p in pagos) {
      final d = _diaLabel(p.fecha);
      if (d != dia) {
        dia = d;
        out.add(Padding(
          padding: const EdgeInsets.only(top: 14, bottom: 4),
          child: Text(d,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: textoTenueDe(context), fontWeight: FontWeight.w700)),
        ));
      }
      out.add(_PagoCard(pago: p));
    }
    return out;
  }
}

class _PagoCard extends StatelessWidget {
  const _PagoCard({required this.pago});
  final _Pago pago;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final Color color;
    final IconData icono;
    final String montoTxtStr;
    if (pago.cubiertoConBono) {
      color = teal;
      icono = Icons.confirmation_number;
      montoTxtStr = 'Con bono';
    } else if (pago.pendiente) {
      color = clayOscuro;
      icono = Icons.schedule;
      montoTxtStr = '${pago.moneda} ${montoTxt(pago.monto)}';
    } else {
      color = lima;
      icono = Icons.check_circle_outline;
      montoTxtStr = '− ${pago.moneda} ${montoTxt(pago.monto)}';
    }
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
            child: Icon(icono, color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(pago.titulo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
                Text(
                    pago.pendiente
                        ? '${pago.sub} · por pagar en la cancha'
                        : pago.cubiertoConBono
                            ? '${pago.sub} · descontado de tu bono'
                            : pago.sub,
                    style:
                        t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(montoTxtStr,
              style: t.titleSmall
                  ?.copyWith(color: color, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Column(
      children: [
        Icon(Icons.receipt_long_outlined,
            size: 56, color: textoTenueDe(context)),
        const SizedBox(height: 12),
        Text('Aún no tienes pagos',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
              'Aquí verás tus compras de bonos y tus reservas, con lo que '
              'pagaste en cada una.',
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        ),
      ],
    );
  }
}
