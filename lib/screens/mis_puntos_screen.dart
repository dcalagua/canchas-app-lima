import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';

/// MIS PUNTOS (fidelidad del jugador). Los puntos se DERIVAN de sus reservas
/// pagadas por la app (últimos 12 meses): 1 punto por S/ 1 pagado — online al
/// instante, efectivo cuando el local marca el cobro (por eso conviene exigir
/// que lo marquen). Canje: 100 puntos = S/ 3 al reservar online (lo absorbe
/// la comisión de Pichangol, no el dueño). Lo canjeado vive en Supabase.
class MisPuntosScreen extends StatefulWidget {
  const MisPuntosScreen({super.key});

  @override
  State<MisPuntosScreen> createState() => _MisPuntosScreenState();
}

class _MisPuntosScreenState extends State<MisPuntosScreen> {
  @override
  void initState() {
    super.initState();
    _refrescar();
  }

  Future<void> _refrescar() async {
    await appState.cargarReservasRemotas();
    await appState.cargarPuntosCanjeados();
  }

  String _nombreCancha(String id) {
    for (final c in appState.todasLasCanchas()) {
      if (c.id == id) return c.club.trim().isNotEmpty ? c.club : c.nombre;
    }
    return 'Reserva';
  }

  String _fechaCorta(String iso) {
    final d = DateTime.tryParse(iso);
    if (d == null) return iso;
    const meses = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'set', 'oct', 'nov', 'dic'
    ];
    return '${d.day} ${meses[d.month - 1]}';
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Mis puntos')),
      body: AnchoLectura(
        child: ListenableBuilder(
          listenable: appState,
          builder: (context, _) {
            final disponibles = appState.misPuntosDisponibles;
            final pendientes = appState.misPuntosPendientes;
            final canjeados = appState.misPuntosCanjeados;
            final valor = disponibles * 3 / 100;
            // Historial: reservas por la app de los últimos 12 meses (las
            // pagadas suman; las no pagadas son la palanca "que lo marquen").
            final desde =
                DateTime.now().subtract(const Duration(days: 365));
            final movs = [
              for (final r in appState.misReservas)
                if (r.traidaPorApp &&
                    r.estado != EstadoReserva.noShow &&
                    (DateTime.tryParse(r.fecha)?.isAfter(desde) ?? false))
                  r,
            ]..sort((a, b) => b.fecha.compareTo(a.fecha));
            return RefreshIndicator(
              onRefresh: _refrescar,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 40),
                children: [
                  // Saldo grande estilo billetera.
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: bosque,
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Column(
                      children: [
                        const Text('⭐ Puntos Pichangol',
                            style: TextStyle(
                                color: Colors.white70,
                                fontWeight: FontWeight.w700,
                                fontSize: 13)),
                        const SizedBox(height: 6),
                        Text('$disponibles',
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 42)),
                        Text(
                            'Valen S/ ${valor.toStringAsFixed(2)} en '
                            'descuentos al reservar online',
                            style: const TextStyle(
                                color: Colors.white, fontSize: 13.5)),
                        if (canjeados > 0)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text('Ya canjeaste $canjeados puntos 🎉',
                                style: const TextStyle(
                                    color: Colors.white70, fontSize: 12)),
                          ),
                      ],
                    ),
                  ),
                  // La palanca del jugador: efectivo sin marcar = puntos en
                  // el aire → que le exija al local.
                  if (pendientes > 0) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFBEAD2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                          '⏳ +$pendientes por confirmar: pídele al local que '
                          'marque tu pago en efectivo para acreditarlos.',
                          style: const TextStyle(
                              color: Color(0xFF8A5A00),
                              fontWeight: FontWeight.w700,
                              fontSize: 12.5,
                              height: 1.3)),
                    ),
                  ],
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Cómo funcionan',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 14)),
                        SizedBox(height: 6),
                        Text(
                          '• Ganas 1 punto por cada S/ 1 que pagas por la '
                          'app (últimos 12 meses).\n'
                          '• Pago online: puntos al instante. Efectivo: '
                          'cuando el local confirma tu pago.\n'
                          '• Cada 100 puntos = S/ 3 de descuento al pagar '
                          'online tu próxima reserva (el descuento lo pone '
                          'Pichangol, no el local).',
                          style: TextStyle(fontSize: 12.5, height: 1.5),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Text('Historial (últimos 12 meses)',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15)),
                  const SizedBox(height: 8),
                  if (movs.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 26),
                      child: Center(
                        child: Text(
                            'Aún no tienes puntos. Reserva y paga por la '
                            'app para empezar a acumular ⭐',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: textoTenue)),
                      ),
                    ),
                  for (final r in movs)
                    Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: cs.surface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: trazo),
                      ),
                      child: Row(
                        children: [
                          Text(r.pagado ? '🎾' : '⏳',
                              style: const TextStyle(fontSize: 20)),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(_nombreCancha(r.canchaId),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13.5)),
                                Text(
                                    '${_fechaCorta(r.fecha)} · ${r.horaInicio}'
                                    '${r.pagado ? '' : ' · por confirmar'}',
                                    style: const TextStyle(
                                        color: textoTenue, fontSize: 11.5)),
                              ],
                            ),
                          ),
                          Text('+${r.totalConExtras.round()}',
                              style: TextStyle(
                                  fontWeight: FontWeight.w900,
                                  fontSize: 15,
                                  color: r.pagado ? bosque : textoTenue)),
                        ],
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
