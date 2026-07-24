import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// RANKING GLOBAL Pichangol: tabla cruzada de jugadores de TODAS las academias
/// por deporte (estilo circuito abierto, rankingtenis.pe). Es el motor de
/// comunidad e identidad a escala ciudad — y el gancho para la membresía Pro.
class RankingGlobalScreen extends StatefulWidget {
  const RankingGlobalScreen({super.key});
  @override
  State<RankingGlobalScreen> createState() => _RankingGlobalScreenState();
}

class _RankingGlobalScreenState extends State<RankingGlobalScreen> {
  Deporte? _deporte;
  String _categoria = ''; // '' = todas

  @override
  void initState() {
    super.initState();
    appState.cargarAcademiasRemotas(); // asegura tener todas las academias
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ranking Global')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final deportes = appState.deportesConRanking;
          if (deportes.isEmpty) {
            return const _Vacio();
          }
          // Deporte por defecto: el primero con datos.
          final dep = (_deporte != null && deportes.contains(_deporte))
              ? _deporte!
              : deportes.first;
          final cats = appState.categoriasGlobalDe(dep);
          final catSel = cats.contains(_categoria) ? _categoria : '';
          final tabla = appState.rankingGlobal(
              deporte: dep, categoria: catSel.isEmpty ? null : catSel);

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 30),
            children: [
              Container(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.public, color: bosque, size: 22),
                    const SizedBox(width: 10),
                    const Expanded(
                      child: Text(
                          'Ranking cruzado de todas las academias. Juega, sube en '
                          'tu ciudad y presume tu carnet.',
                          style: TextStyle(
                              fontSize: 13, color: bosque, height: 1.3)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              // Deportes.
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final d in deportes)
                    ChoiceChip(
                      label: Text(d.etiqueta),
                      selected: dep == d,
                      selectedColor: lima,
                      labelStyle: TextStyle(
                          color: dep == d ? Colors.white : null,
                          fontWeight: FontWeight.w700),
                      onSelected: (_) => setState(() {
                        _deporte = d;
                        _categoria = '';
                      }),
                    ),
                ],
              ),
              if (cats.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ChoiceChip(
                      label: const Text('Todas'),
                      selected: catSel.isEmpty,
                      selectedColor: limaSuave,
                      onSelected: (_) => setState(() => _categoria = ''),
                    ),
                    for (final c in cats)
                      ChoiceChip(
                        label: Text(c),
                        selected: catSel == c,
                        selectedColor: limaSuave,
                        onSelected: (_) => setState(() => _categoria = c),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 14),
              if (tabla.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text('Aún no hay partidos en este filtro.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: textoTenue)),
                )
              else
                for (var i = 0; i < tabla.length; i++)
                  _FilaGlobal(posicion: i + 1, f: tabla[i]),
            ],
          );
        },
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.emoji_events_outlined,
                size: 64, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 14),
            const Text('El ranking global está por arrancar',
                textAlign: TextAlign.center,
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 6),
            const Text(
                'Cuando las academias registren resultados en su circuito, '
                'aquí aparecerá la tabla cruzada por deporte.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
          ],
        ),
      ),
    );
  }
}

class _FilaGlobal extends StatelessWidget {
  const _FilaGlobal({required this.posicion, required this.f});
  final int posicion;
  final RankingGlobalFila f;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final medalla = switch (posicion) {
      1 => '🥇',
      2 => '🥈',
      3 => '🥉',
      _ => '',
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        leading: SizedBox(
          width: 54,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 22,
                child: Text(medalla.isNotEmpty ? medalla : '$posicion',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: medalla.isNotEmpty ? 18 : 15,
                        color: textoTenue)),
              ),
              const SizedBox(width: 6),
              CircleAvatar(
                radius: 15,
                backgroundColor: limaSuave,
                child: Text(
                    f.nombre.isNotEmpty ? f.nombre[0].toUpperCase() : '?',
                    style: const TextStyle(
                        color: bosque, fontWeight: FontWeight.w800, fontSize: 13)),
              ),
            ],
          ),
        ),
        title: Text(f.nombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(
            '${f.academiaNombre}'
            '${f.categoria.isNotEmpty ? ' · ${f.categoria}' : ''} · ${f.pg}G-${f.pp}P',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: textoTenue, fontSize: 12)),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('${f.puntos}',
                style: TextStyle(
                    fontWeight: FontWeight.w900,
                    fontSize: 18,
                    color: cs.primary)),
            const Text('pts', style: TextStyle(color: textoTenue, fontSize: 11)),
          ],
        ),
      ),
    );
  }
}
