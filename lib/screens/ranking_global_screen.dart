import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/models.dart';
import '../models/temporada.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'perfil_global_screen.dart';

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
  String _zona = ''; // '' = todas las zonas
  String _temporadaId = ''; // '' = histórico (todas las temporadas)

  @override
  void initState() {
    super.initState();
    appState.cargarAcademiasRemotas(); // asegura tener todas las academias
    appState.cargarRetosResultados(); // retos jugados → se pliegan al ranking
    appState.cargarMiembrosPro(); // insignia PRO en la tabla
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
          final zonas = appState.zonasGlobalDe(dep);
          final zonaSel = zonas.contains(_zona) ? _zona : '';
          final temporadas = appState.temporadasConDatos(dep);
          Temporada? tempSel; // null = histórico
          for (final t in temporadas) {
            if (t.id == _temporadaId) {
              tempSel = t;
              break;
            }
          }
          final tabla = appState.rankingGlobal(
              deporte: dep,
              categoria: catSel.isEmpty ? null : catSel,
              zona: zonaSel.isEmpty ? null : zonaSel,
              temporada: tempSel);
          final ahora = DateTime.now();
          // Campeón vigente = ganador de la temporada cerrada anterior (para la
          // corona 👑 en la tabla viva).
          final campeon = appState.campeonGlobal(
              deporte: dep,
              temporada: Temporada.de(ahora).anterior,
              zona: zonaSel.isEmpty ? null : zonaSel);
          final campeonEmail = campeon?.emailIdentidad ?? '';

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
                        _zona = '';
                      }),
                    ),
                ],
              ),
              if (zonas.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ChoiceChip(
                      avatar: const Icon(Icons.place_outlined, size: 16),
                      label: const Text('Toda la ciudad'),
                      selected: zonaSel.isEmpty,
                      selectedColor: limaSuave,
                      onSelected: (_) => setState(() => _zona = ''),
                    ),
                    for (final z in zonas)
                      ChoiceChip(
                        label: Text(z),
                        selected: zonaSel == z,
                        selectedColor: limaSuave,
                        onSelected: (_) => setState(() => _zona = z),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 10),
              // Temporadas (trimestres): el ranking se reinicia cada temporada.
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  ChoiceChip(
                    avatar: const Icon(Icons.all_inclusive, size: 16),
                    label: const Text('Histórico'),
                    selected: tempSel == null,
                    selectedColor: limaSuave,
                    onSelected: (_) => setState(() => _temporadaId = ''),
                  ),
                  for (final t in temporadas)
                    ChoiceChip(
                      avatar: Icon(
                          t.esActual(ahora)
                              ? Icons.local_fire_department
                              : Icons.emoji_events_outlined,
                          size: 16),
                      label: Text(
                          t.esActual(ahora) ? '${t.corto} · en curso' : t.corto),
                      selected: tempSel?.id == t.id,
                      selectedColor: limaSuave,
                      onSelected: (_) => setState(() => _temporadaId = t.id),
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
              // Campeón (temporada cerrada) o aviso de temporada en curso.
              if (tempSel != null) ...[
                const SizedBox(height: 14),
                if (tempSel.finalizada(ahora) && tabla.isNotEmpty)
                  _CampeonBanner(temporada: tempSel, campeon: tabla.first)
                else if (tempSel.esActual(ahora))
                  _TemporadaAviso(
                    icono: Icons.local_fire_department,
                    texto:
                        'Temporada ${tempSel.nombre} en curso. Juega y reporta '
                        'resultados: el ranking se reinicia cada trimestre.',
                  )
                else if (tabla.isEmpty)
                  _TemporadaAviso(
                    icono: Icons.emoji_events_outlined,
                    texto: 'La temporada ${tempSel.nombre} no tuvo partidos.',
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
                  _FilaGlobal(
                    posicion: i + 1,
                    f: tabla[i],
                    esPro: appState.esProEmail(tabla[i].emailIdentidad),
                    // Corona al campeón vigente (de la temporada cerrada anterior)
                    // solo en las vistas "vivas" (Histórico o temporada en curso).
                    esCampeon: campeonEmail.isNotEmpty &&
                        (tempSel == null || tempSel.esActual(ahora)) &&
                        tabla[i].emailIdentidad == campeonEmail,
                  ),
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

/// Banner del CAMPEÓN de una temporada ya cerrada (el #1 de esa ventana). Es el
/// premio simbólico del circuito y el gancho para presumir/renovar Pro.
class _CampeonBanner extends StatelessWidget {
  const _CampeonBanner({required this.temporada, required this.campeon});
  final Temporada temporada;
  final RankingGlobalFila campeon;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [bosque, teal]),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          const Text('🏆', style: TextStyle(fontSize: 34)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Campeón · ${temporada.nombre}',
                    style: const TextStyle(
                        color: Colors.white70,
                        fontWeight: FontWeight.w700,
                        fontSize: 12.5)),
                const SizedBox(height: 2),
                Text(campeon.nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                        fontSize: 18)),
                Text('${campeon.puntos} pts · ${campeon.pg}G-${campeon.pp}P',
                    style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Aviso liviano de temporada (en curso / sin partidos), estilo Airbnb.
class _TemporadaAviso extends StatelessWidget {
  const _TemporadaAviso({required this.icono, required this.texto});
  final IconData icono;
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Icon(icono, color: bosque, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(texto,
                style: const TextStyle(
                    fontSize: 12.5, color: bosque, height: 1.3)),
          ),
        ],
      ),
    );
  }
}

/// Insignia PRO (Pichangol Pro) — píldora bosque compacta, estilo Airbnb.
class _ProChip extends StatelessWidget {
  const _ProChip();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: bosque,
        borderRadius: BorderRadius.circular(6),
      ),
      child: const Text('PRO',
          style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w900,
              fontSize: 9.5,
              letterSpacing: 0.5)),
    );
  }
}

class _FilaGlobal extends StatelessWidget {
  const _FilaGlobal({
    required this.posicion,
    required this.f,
    this.esPro = false,
    this.esCampeon = false,
  });
  final int posicion;
  final RankingGlobalFila f;
  final bool esPro;
  final bool esCampeon;
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
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => PerfilGlobalScreen(
                idKey: f.alumnoId, deporte: f.deporte, posicion: posicion))),
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
        title: Row(
          children: [
            Flexible(
              child: Text(f.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
            if (esCampeon) ...[
              const SizedBox(width: 4),
              const Text('👑', style: TextStyle(fontSize: 14)),
            ],
            if (esPro) ...[
              const SizedBox(width: 6),
              const _ProChip(),
            ],
          ],
        ),
        subtitle: Text(
            '${f.academiaNombre}'
            '${f.academias > 1 ? ' +${f.academias - 1}' : ''}'
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
