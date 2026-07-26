import 'package:flutter/material.dart';

import '../services/convocatorias_service.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import 'convocatorias_screen.dart' show EstadoChip;

/// Ranking de recurrencia por socio (la trazabilidad pedida): quién se inscribe
/// más, cuántas veces jugó, cuántas quedó en espera y no-shows. Vista del dueño.
class RankingSociosScreen extends StatefulWidget {
  final String clubId;
  final String clubNombre;
  const RankingSociosScreen({
    super.key,
    required this.clubId,
    required this.clubNombre,
  });

  @override
  State<RankingSociosScreen> createState() => _RankingSociosScreenState();
}

class _RankingSociosScreenState extends State<RankingSociosScreen> {
  late Future<List<Map<String, dynamic>>> _futuro;

  @override
  void initState() {
    super.initState();
    _futuro = ConvocatoriasService.ranking(widget.clubId);
  }

  Future<void> _recargar() async {
    setState(() => _futuro = ConvocatoriasService.ranking(widget.clubId));
    await _futuro;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ranking de socios')),
      body: RefreshIndicator(
        onRefresh: _recargar,
        child: FutureBuilder<List<Map<String, dynamic>>>(
          future: _futuro,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const CargandoPichangol();
            }
            final filas = snap.data ?? const [];
            if (filas.isEmpty) {
              return ListView(
                children: [
                  const SizedBox(height: 100),
                  Icon(Icons.leaderboard_outlined,
                      size: 52, color: sage.withOpacity(0.6)),
                  const SizedBox(height: 14),
                  const Center(
                    child: Text('Sin datos todavía',
                        style: TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 17)),
                  ),
                  const SizedBox(height: 6),
                  Center(
                    child: Text(
                      'El ranking se llena a medida que hay convocatorias y asistencia.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: textoTenue),
                    ),
                  ),
                ],
              );
            }
            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
              itemCount: filas.length + 1,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                if (i == 0) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.clubNombre,
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 18)),
                        const SizedBox(height: 2),
                        Text('Ordenado por partidos jugados',
                            style:
                                TextStyle(color: textoTenue, fontSize: 13)),
                      ],
                    ),
                  );
                }
                return _FilaSocio(orden: i, fila: filas[i - 1]);
              },
            );
          },
        ),
      ),
    );
  }
}

class _FilaSocio extends StatelessWidget {
  final int orden;
  final Map<String, dynamic> fila;
  const _FilaSocio({required this.orden, required this.fila});

  int _n(String k) => (fila[k] as num?)?.toInt() ?? 0;

  @override
  Widget build(BuildContext context) {
    final nombre = fila['socio_nombre'] as String? ?? fila['socio_id'] as String? ?? '';
    final medalla = switch (orden) {
      1 => amarillo,
      2 => const Color(0xFFB8C0C2),
      3 => const Color(0xFFCD9A6A),
      _ => limaSuave,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: medalla,
              child: Text('$orden',
                  style: TextStyle(
                      color: orden <= 3 ? bosque : bosque,
                      fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(nombre,
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15),
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      EstadoChip(
                          texto: '${_n('jugo')} jugó',
                          bg: estadoOkBg,
                          fg: estadoOkFg,
                          icono: Icons.sports_soccer),
                      EstadoChip(
                          texto: '${_n('inscripciones')} inscrito',
                          bg: estadoInfoBg,
                          fg: estadoInfoFg,
                          icono: Icons.how_to_reg),
                      if (_n('lista_espera') > 0)
                        EstadoChip(
                            texto: '${_n('lista_espera')} en espera',
                            bg: estadoWarnBg,
                            fg: estadoWarnFg,
                            icono: Icons.hourglass_bottom),
                      if (_n('no_show') > 0)
                        EstadoChip(
                            texto: '${_n('no_show')} no-show',
                            bg: estadoBadBg,
                            fg: estadoBadFg,
                            icono: Icons.person_off),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
