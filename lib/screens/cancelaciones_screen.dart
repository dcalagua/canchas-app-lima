import 'package:flutter/material.dart';

import '../data/cancelaciones_repo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import '../widgets/vacio_airbnb.dart';

/// Reporte de CANCELACIONES del dueño: qué reservas de sus canchas fueron
/// canceladas, por quién, cuándo y si había pago de por medio (para hacer
/// seguimiento). Pestaña de Reportes. Fuente:
/// `pichangol_reservas_canceladas` (se registra al cancelar; la reserva
/// original se borra para liberar el horario al instante).
class CancelacionesScreen extends StatefulWidget {
  const CancelacionesScreen({super.key});

  @override
  State<CancelacionesScreen> createState() => _CancelacionesScreenState();
}

class _CancelacionesScreenState extends State<CancelacionesScreen> {
  List<Map<String, dynamic>> _items = [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final rows =
        await CancelacionesRepo.deDueno(appState.usuario?.email ?? '');
    if (!mounted) return;
    setState(() {
      _items = rows;
      _cargando = false;
    });
  }

  /// "hace 2 h" / "ayer" / "12 ago" para el momento de la cancelación.
  String _cuando(String iso) {
    final d = DateTime.tryParse(iso)?.toLocal();
    if (d == null) return '';
    final dif = DateTime.now().difference(d);
    if (dif.inMinutes < 60) return 'hace ${dif.inMinutes} min';
    if (dif.inHours < 24) return 'hace ${dif.inHours} h';
    if (dif.inDays == 1) return 'ayer';
    return AppState.fechaBonita(
        '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}');
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const CargandoPichangol();
    if (_items.isEmpty) {
      return const VacioAirbnb(
        icono: Icons.event_busy_outlined,
        colorIcono: clayOscuro,
        titulo: 'Sin reservas\ncanceladas',
        mensaje: 'Cuando un jugador cancele una reserva de tus canchas la '
            'verás aquí, con quién canceló, cuándo y si había pago.',
      );
    }
    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView.separated(
        padding: EdgeInsets.fromLTRB(
            ladoTablet(context, 16, 760), 14, ladoTablet(context, 16, 760), 24),
        itemCount: _items.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (_, i) => _Card(c: _items[i], cuando: _cuando),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.c, required this.cuando});
  final Map<String, dynamic> c;
  final String Function(String) cuando;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final local = (c['local'] ?? '').toString().trim();
    final canchaNombre = (c['cancha_nombre'] ?? '').toString().trim();
    final lugar = (local.isNotEmpty && local != canchaNombre)
        ? '$local · $canchaNombre'
        : (canchaNombre.isNotEmpty ? canchaNombre : local);
    final jugador = (c['jugador'] ?? '').toString().trim();
    final pagado = c['pagado'] == true;
    final mon = (c['moneda'] ?? 'S/').toString();
    final precio = ((c['precio'] ?? 0) as num);
    final sena = ((c['sena'] ?? 0) as num);
    // Al cancelar, el jugador YA NO debe nada (regla del director): si adelantó
    // seña, esa queda a favor del dueño y el resto simplemente no se cobra.
    final String estadoPago;
    final bool aFavor;
    if (pagado) {
      estadoPago = 'Estaba PAGADA (revisar reembolso)';
      aFavor = true;
    } else if (sena > 0) {
      estadoPago =
          'Seña $mon ${sena.toStringAsFixed(0)} a tu favor · resto ya no se debe';
      aFavor = true;
    } else {
      estadoPago = 'Sin pago de por medio · nadie debe nada';
      aFavor = false;
    }
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.event_busy_outlined,
                  size: 18, color: clayOscuro),
              const SizedBox(width: 8),
              Expanded(
                child: Text(jugador.isEmpty ? 'Jugador' : jugador,
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              Text(cuando((c['cancelada_en'] ?? '').toString()),
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '$lugar · ${AppState.fechaBonita((c['fecha'] ?? '').toString())} · '
            '${c['hora_inicio'] ?? ''}–${c['hora_fin'] ?? ''}',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Text('$mon ${precio.toStringAsFixed(0)}',
                  style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(width: 8),
              Flexible(
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: aFavor ? limaSuave : const Color(0xFFF3F3F3),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    estadoPago,
                    maxLines: 2,
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: aFavor ? bosque : textoTenueDe(context)),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
