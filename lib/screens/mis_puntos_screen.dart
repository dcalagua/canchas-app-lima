import 'package:flutter/material.dart';

import '../config/pais.dart';
import '../services/puntos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/cargando_pichangol.dart';

/// MIS PUNTOS (fidelidad del jugador): saldo, cuánto valen, qué está por
/// vencer y el historial de cómo los ganó. Reglas: 1 punto por S/ 1 (o Bs 1;
/// $1 = 3 puntos) efectivamente PAGADO — online al pagar, efectivo cuando el
/// dueño marca el cobro (por eso al jugador le conviene exigir que marquen).
class MisPuntosScreen extends StatefulWidget {
  const MisPuntosScreen({super.key});

  @override
  State<MisPuntosScreen> createState() => _MisPuntosScreenState();
}

class _MisPuntosScreenState extends State<MisPuntosScreen> {
  bool _cargando = true;
  List<Map<String, dynamic>> _movs = [];

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final email = (appState.usuario?.email ?? '').trim().toLowerCase();
    await appState.flushPuntos(); // sube acreditaciones pendientes primero
    await appState.sincronizarPuntos();
    final movs =
        email.isEmpty ? const <Map<String, dynamic>>[] : await PuntosService.movimientos(email);
    if (!mounted) return;
    setState(() {
      _movs = movs;
      _cargando = false;
    });
  }

  String _fechaCorta(String? iso) {
    final d = DateTime.tryParse(iso ?? '')?.toLocal();
    if (d == null) return '';
    const meses = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'set', 'oct', 'nov', 'dic'
    ];
    return '${d.day} ${meses[d.month - 1]}';
  }

  (String, String) _etiquetaMov(Map<String, dynamic> m) {
    final accion = (m['accion'] ?? '').toString();
    return switch (accion) {
      'reserva_pagada' => ('🎾', 'Reserva pagada'),
      'traer_cancha' => ('🏟️', 'Trajiste una cancha'),
      'invitar_jugador' => ('🤝', 'Invitaste a un jugador'),
      'pedir_cancha' => ('📍', 'Pediste una cancha'),
      _ => ('⭐', 'Puntos Pichangol'),
    };
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final info = appState.puntosInfo;
    final disponible = appState.puntosSaldo;
    final valor100 =
        (info?['valor_100_puntos'] as num?)?.toDouble() ?? 3.0;
    final valor = disponible * valor100 / 100;
    final porVencer = (info?['por_vencer_30d'] as num?)?.toInt() ?? 0;
    final mon = paisActual.moneda;
    return Scaffold(
      appBar: AppBar(title: const Text('Mis puntos')),
      body: AnchoLectura(
        child: _cargando
            ? const Center(child: CargandoPichangol())
            : RefreshIndicator(
                onRefresh: _cargar,
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
                          Text('$disponible',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                  fontSize: 42)),
                          Text(
                              'Valen $mon ${valor.toStringAsFixed(2)} en descuentos',
                              style: const TextStyle(
                                  color: Colors.white, fontSize: 13.5)),
                          if (porVencer > 0) ...[
                            const SizedBox(height: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 5),
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.14),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(
                                  '⏳ $porVencer vencen en los próximos 30 días',
                                  style: const TextStyle(
                                      color: Colors.white, fontSize: 12)),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    // Cómo se ganan (reglas claras = confianza).
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: limaSuave,
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Cómo se ganan',
                              style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 14)),
                          const SizedBox(height: 6),
                          Text(
                            '• 1 punto por cada $mon 1 que pagas en tus '
                            'reservas.\n'
                            '• Pago online: puntos al instante.\n'
                            '• Pago en efectivo: cuando el local confirma tu '
                            'pago — si no te los acreditan, pídele al local '
                            'que marque tu pago en la app.\n'
                            '• Duran 6 meses. 100 puntos = '
                            '$mon ${valor100.toStringAsFixed(0)} de descuento '
                            'en tu próxima reserva.',
                            style: const TextStyle(
                                fontSize: 12.5, height: 1.5),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    const Text('Historial',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 8),
                    if (_movs.isEmpty)
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
                    for (final m in _movs)
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
                            Text(_etiquetaMov(m).$1,
                                style: const TextStyle(fontSize: 20)),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(_etiquetaMov(m).$2,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                          fontSize: 13.5)),
                                  Text(
                                      '${_fechaCorta(m['creado_en']?.toString())}'
                                      '${(m['estado'] ?? '') == 'pendiente' ? ' · pendiente' : ''}',
                                      style: const TextStyle(
                                          color: textoTenue,
                                          fontSize: 11.5)),
                                ],
                              ),
                            ),
                            Text('+${(m['puntos'] as num?)?.toInt() ?? 0}',
                                style: TextStyle(
                                    fontWeight: FontWeight.w900,
                                    fontSize: 15,
                                    color: (m['estado'] ?? '') == 'liberado'
                                        ? bosque
                                        : textoTenue)),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
      ),
    );
  }
}
