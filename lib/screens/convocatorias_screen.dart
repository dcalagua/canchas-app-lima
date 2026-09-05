import 'package:flutter/material.dart';

import '../models/convocatoria.dart';
import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import '../widgets/cargando_pichangol.dart';
import 'convocatoria_detalle_screen.dart';
import 'crear_convocatoria_screen.dart';
import 'ranking_socios_screen.dart';

/// Lista de "pichangas" (convocatorias) de un club. Es la puerta de entrada del
/// módulo: el jugador ve las convocatorias y se anota; el dueño (admin del club)
/// crea nuevas y entra al ranking de recurrencia.
class ConvocatoriasScreen extends StatefulWidget {
  final String clubId;
  final String clubNombre;
  const ConvocatoriasScreen({
    super.key,
    required this.clubId,
    required this.clubNombre,
  });

  @override
  State<ConvocatoriasScreen> createState() => _ConvocatoriasScreenState();
}

class _ConvocatoriasScreenState extends State<ConvocatoriasScreen> {
  late Future<List<Convocatoria>> _futuro;

  bool get _esAdmin => appState.sesionIniciada;

  @override
  void initState() {
    super.initState();
    _futuro = ConvocatoriasService.listar(widget.clubId);
  }

  Future<void> _recargar() async {
    setState(() {
      _futuro = ConvocatoriasService.listar(widget.clubId);
    });
    await _futuro;
  }

  Future<void> _crear() async {
    final creada = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => CrearConvocatoriaScreen(
          clubId: widget.clubId, clubNombre: widget.clubNombre),
    ));
    if (creada == true) _recargar();
  }

  void _abrir(Convocatoria c) {
    Navigator.of(context)
        .push(MaterialPageRoute(
          builder: (_) => ConvocatoriaDetalleScreen(convId: c.id),
        ))
        .then((_) => _recargar());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pichangas'),
        actions: [
          if (_esAdmin)
            IconButton(
              tooltip: 'Ranking de socios',
              icon: const Icon(Icons.leaderboard_outlined),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => RankingSociosScreen(
                    clubId: widget.clubId, clubNombre: widget.clubNombre),
              )),
            ),
        ],
      ),
      floatingActionButton: _esAdmin
          ? FloatingActionButton.extended(
              onPressed: _crear,
              icon: const Icon(Icons.add),
              label: const Text('Nueva pichanga'),
            )
          : null,
      body: !ConvocatoriasService.disponible
          ? const _AvisoSinBackend()
          : RefreshIndicator(
              onRefresh: _recargar,
              child: FutureBuilder<List<Convocatoria>>(
                future: _futuro,
                builder: (context, snap) {
                  if (snap.connectionState == ConnectionState.waiting) {
                    return const CargandoPichangol();
                  }
                  final lista = snap.data ?? const [];
                  if (lista.isEmpty) {
                    return _VacioLista(esAdmin: _esAdmin, onCrear: _crear);
                  }
                  return ListView.separated(
                    // Regla app: contenido centrado en pantallas anchas.
                    padding: EdgeInsets.fromLTRB(
                        ladoTablet(context, 16, 760), 16,
                        ladoTablet(context, 16, 760), 96),
                    itemCount: lista.length + 1,
                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                    itemBuilder: (context, i) {
                      if (i == 0) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Text(widget.clubNombre,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700, fontSize: 18)),
                        );
                      }
                      return _ConvocatoriaCard(
                          conv: lista[i - 1], onTap: () => _abrir(lista[i - 1]));
                    },
                  );
                },
              ),
            ),
    );
  }
}

class _ConvocatoriaCard extends StatelessWidget {
  final Convocatoria conv;
  final VoidCallback onTap;
  const _ConvocatoriaCard({required this.conv, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(conv.titulo,
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 16)),
                  ),
                  EstadoChip(
                    texto: conv.cerrada ? 'Cerrada' : 'Abierta',
                    bg: conv.cerrada ? estadoNeutroBg : estadoOkBg,
                    fg: conv.cerrada ? estadoNeutroFg : estadoOkFg,
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  if (conv.categoria != null && conv.categoria!.isNotEmpty)
                    EstadoChip(
                        texto: conv.categoria!,
                        bg: estadoInfoBg,
                        fg: estadoInfoFg),
                  ModoChip(modo: conv.modo),
                  if (conv.fechaPartido != null && conv.fechaPartido!.isNotEmpty)
                    EstadoChip(
                        texto: conv.fechaPartido!,
                        bg: estadoNeutroBg,
                        fg: estadoNeutroFg,
                        icono: Icons.event),
                ],
              ),
              const SizedBox(height: 12),
              _BarraCupos(conv: conv),
            ],
          ),
        ),
      ),
    );
  }
}

class _BarraCupos extends StatelessWidget {
  final Convocatoria conv;
  const _BarraCupos({required this.conv});

  @override
  Widget build(BuildContext context) {
    final cupos = conv.cupos == 0 ? 1 : conv.cupos;
    final ratio = (conv.confirmadosN / cupos).clamp(0.0, 1.0);
    final lleno = conv.cuposLibres == 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: ratio,
            minHeight: 8,
            backgroundColor: estadoNeutroBg,
            valueColor: AlwaysStoppedAnimation(lleno ? amarillo : sage),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Icon(Icons.groups, size: 16, color: textoTenue),
            const SizedBox(width: 6),
            Text('${conv.confirmadosN}/${conv.cupos} confirmados',
                style: const TextStyle(fontWeight: FontWeight.w600)),
            if (conv.esperaN > 0) ...[
              const SizedBox(width: 12),
              Icon(Icons.hourglass_bottom, size: 16, color: textoTenue),
              const SizedBox(width: 4),
              Text('${conv.esperaN} en espera',
                  style: TextStyle(color: textoTenue)),
            ],
            const Spacer(),
            if (!conv.cerrada)
              Text(lleno ? 'Lista llena' : '${conv.cuposLibres} libres',
                  style: TextStyle(
                      color: lleno ? estadoWarnFg : estadoOkFg,
                      fontWeight: FontWeight.w700)),
          ],
        ),
      ],
    );
  }
}

class _VacioLista extends StatelessWidget {
  final bool esAdmin;
  final VoidCallback onCrear;
  const _VacioLista({required this.esAdmin, required this.onCrear});

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 80),
        Icon(Icons.sports_soccer, size: 56, color: sage.withOpacity(0.6)),
        const SizedBox(height: 16),
        const Center(
          child: Text('Aún no hay pichangas',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
        ),
        const SizedBox(height: 6),
        Center(
          child: Text(
            esAdmin
                ? 'Crea la primera convocatoria del club.'
                : 'Cuando el club abra una convocatoria, aparecerá acá.',
            style: TextStyle(color: textoTenue),
          ),
        ),
        const SizedBox(height: 20),
        if (esAdmin)
          Center(
            child: FilledButton.icon(
              onPressed: onCrear,
              icon: const Icon(Icons.add),
              label: const Text('Nueva pichanga'),
            ),
          ),
      ],
    );
  }
}

class _AvisoSinBackend extends StatelessWidget {
  const _AvisoSinBackend();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 48, color: textoTenue),
            const SizedBox(height: 16),
            const Text('Convocatorias no disponibles',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 6),
            Text(
              'El servidor de pichangas no está configurado en este build '
              '(GROWTH_API_URL).',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Chips reutilizables ───────────────────────────────────────────────────
class EstadoChip extends StatelessWidget {
  final String texto;
  final Color bg;
  final Color fg;
  final IconData? icono;
  const EstadoChip(
      {super.key,
      required this.texto,
      required this.bg,
      required this.fg,
      this.icono});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icono != null) ...[
            Icon(icono, size: 13, color: fg),
            const SizedBox(width: 4),
          ],
          Text(texto,
              style: TextStyle(
                  color: fg, fontWeight: FontWeight.w700, fontSize: 12)),
        ],
      ),
    );
  }
}

class ModoChip extends StatelessWidget {
  final ModoAsignacion modo;
  const ModoChip({super.key, required this.modo});

  @override
  Widget build(BuildContext context) {
    final icono = switch (modo) {
      ModoAsignacion.ordenLlegada => Icons.timer_outlined,
      ModoAsignacion.sorteo => Icons.casino_outlined,
      ModoAsignacion.equidad => Icons.balance_outlined,
    };
    return EstadoChip(
        texto: modo.etiqueta, bg: limaSuave, fg: estadoOkFg, icono: icono);
  }
}
