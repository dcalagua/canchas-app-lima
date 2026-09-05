import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/models.dart';
import '../models/temporada.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import 'buscar_usuario_screen.dart';
import 'jugadores_disponibles_screen.dart';
import 'perfil_global_screen.dart';

/// RANKING GLOBAL Pichangol: tabla cruzada de jugadores de TODAS las academias
/// por deporte (estilo circuito abierto, rankingtenis.pe). Es el motor de
/// comunidad e identidad a escala ciudad — y el gancho para la membresía Pro.
class RankingGlobalScreen extends StatefulWidget {
  const RankingGlobalScreen({super.key, this.deporteInicial});

  /// Deporte a pre-seleccionar (p. ej. abrir el ranking de FÚTBOL desde un
  /// campeonato). Null = el primero con datos (tenis por defecto).
  final Deporte? deporteInicial;

  @override
  State<RankingGlobalScreen> createState() => _RankingGlobalScreenState();
}

class _RankingGlobalScreenState extends State<RankingGlobalScreen> {
  Deporte? _deporte;
  String _categoria = ''; // '' = todas
  String _zona = ''; // '' = todas las zonas
  String _temporadaId = ''; // '' = histórico (todas las temporadas)
  bool _dobles = false; // false = singles | true = ranking de dobles (parejas)

  @override
  void initState() {
    super.initState();
    _deporte = widget.deporteInicial; // pre-selección (p. ej. fútbol)
    appState.cargarMiembrosPro(); // insignia PRO en la tabla
    appState.cargarMiPerfilCircuito(); // ¿ya me uní al circuito?
    // Cuando tenga los datos, empuja el ranking a la torre de control.
    Future.wait([
      appState.cargarAcademiasRemotas(), // todas las academias
      appState.cargarRetosResultados(), // retos jugados → ranking
    ]).then((_) {
      appState.publicarRankingSnapshot();
      appState.cargarFotosDeParticipantes(); // fotos reales en las filas
    });
  }

  void _abrirDisponibles() => Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => const JugadoresDisponiblesScreen()));

  /// Buscar un jugador por nombre para RETARLO o CHATEAR y coordinar.
  void _buscarJugador() => Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => BuscarUsuarioScreen(
          deporteReto: _deporte ?? deportesCircuito.first)));

  /// Abre la hoja "Unirme al circuito" directo (sin pasar por Jugadores
  /// disponibles) y avisa al unirse.
  Future<void> _unirme() async {
    final ok = await mostrarUnirseCircuito(context);
    if (ok && mounted) {
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: bosque,
          content: Text('¡Estás en el circuito! Ya pueden retarte.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ranking Global'),
        actions: [
          IconButton(
            tooltip: 'Buscar jugador',
            icon: const Icon(Icons.search),
            onPressed: _buscarJugador,
          ),
          IconButton(
            tooltip: 'Jugadores disponibles',
            icon: const Icon(Icons.person_add_alt_1),
            onPressed: _abrirDisponibles,
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final deportes = appState.deportesConRanking;
          if (deportes.isEmpty) {
            return _Vacio(
              enCircuito: appState.estoyEnCircuito,
              onUnirme: _unirme,
              onVerDisponibles: _abrirDisponibles,
            );
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
          final hayDobles = appState.hayRankingDobles(dep);
          final dobles = _dobles && hayDobles;
          final tabla = dobles
              ? appState.rankingDobles(
                  deporte: dep,
                  zona: zonaSel.isEmpty ? null : zonaSel,
                  temporada: tempSel)
              : appState.rankingGlobal(
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
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 16, 700), 12, ladoTablet(context, 16, 700), 30),
            children: [
              Container(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    const CircleAvatar(
                        radius: 18,
                        backgroundColor: teal,
                        child: Icon(Icons.public,
                            color: Colors.white, size: 20)),
                    const SizedBox(width: 12),
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
              const SizedBox(height: 10),
              // CTA: si NO estoy en el circuito → abre "Unirme" directo; si ya
              // estoy → ver jugadores disponibles para retar.
              InkWell(
                onTap: appState.estoyEnCircuito ? _abrirDisponibles : _unirme,
                borderRadius: BorderRadius.circular(14),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                  decoration: BoxDecoration(
                    color: appState.estoyEnCircuito
                        ? Theme.of(context).colorScheme.surface
                        : lima,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                        color: appState.estoyEnCircuito ? trazo : lima),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.person_add_alt_1,
                          color: appState.estoyEnCircuito
                              ? bosque
                              : Colors.white,
                          size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                            appState.estoyEnCircuito
                                ? 'Estás en el circuito · ver jugadores para retar'
                                : 'Únete al circuito y deja que te reten',
                            style: TextStyle(
                                color: appState.estoyEnCircuito
                                    ? null
                                    : Colors.white,
                                fontWeight: FontWeight.w700,
                                fontSize: 13)),
                      ),
                      Icon(Icons.chevron_right,
                          color: appState.estoyEnCircuito
                              ? textoTenue
                              : Colors.white),
                    ],
                  ),
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
              // Modalidad Singles / Dobles (solo si hay dobles en este deporte).
              if (hayDobles) ...[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final m in const [('Singles', false), ('Dobles', true)])
                      ChoiceChip(
                        label: Text(m.$1),
                        selected: dobles == m.$2,
                        selectedColor: lima,
                        labelStyle: TextStyle(
                            color: dobles == m.$2 ? Colors.white : null,
                            fontWeight: FontWeight.w700),
                        onSelected: (_) => setState(() => _dobles = m.$2),
                      ),
                  ],
                ),
              ],
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
                      onSelected: (_) => setState(() => _zona = ''),
                    ),
                    for (final z in zonas)
                      ChoiceChip(
                        label: Text(z),
                        selected: zonaSel == z,
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
                      onSelected: (_) => setState(() => _temporadaId = t.id),
                    ),
                ],
              ),
              if (!dobles && cats.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ChoiceChip(
                      label: const Text('Todas'),
                      selected: catSel.isEmpty,
                      onSelected: (_) => setState(() => _categoria = ''),
                    ),
                    for (final c in cats)
                      ChoiceChip(
                        label: Text(c),
                        selected: catSel == c,
                        onSelected: (_) => setState(() => _categoria = c),
                      ),
                  ],
                ),
              ],
              // Campeón (temporada cerrada) o aviso de temporada en curso.
              if (!dobles && tempSel != null) ...[
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
                    esPareja: dobles,
                    esPro: !dobles &&
                        appState.esProEmail(tabla[i].emailIdentidad),
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
  const _Vacio({
    required this.enCircuito,
    required this.onUnirme,
    required this.onVerDisponibles,
  });

  /// Si el usuario YA está en el circuito no se le vuelve a pedir unirse: el
  /// ranking está vacío porque aún nadie jugó, así que lo empujamos a retar.
  final bool enCircuito;
  final VoidCallback onUnirme;
  final VoidCallback onVerDisponibles;

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
            Text(
                enCircuito
                    ? 'Ya estás en el circuito. Reta a otros jugadores para ser '
                        'de los primeros en aparecer en la tabla de tu ciudad.'
                    : 'Únete al circuito, reta a otros jugadores y sé de los '
                        'primeros en aparecer en la tabla de tu ciudad.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue)),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima, foregroundColor: Colors.white),
              onPressed: enCircuito ? onVerDisponibles : onUnirme,
              icon: Icon(
                  enCircuito ? Icons.sports_tennis : Icons.person_add_alt_1,
                  size: 18),
              label: Text(
                  enCircuito ? 'Ver jugadores para retar' : 'Unirme al circuito'),
            ),
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
          CircleAvatar(
              radius: 18,
              backgroundColor: amarillo,
              child: Icon(icono, color: Colors.white, size: 20)),
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
    this.esPareja = false,
  });
  final int posicion;
  final RankingGlobalFila f;
  final bool esPro;
  final bool esCampeon;

  /// Fila de PAREJA (ranking de dobles): no navega al carnet individual.
  final bool esPareja;
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
        onTap: esPareja
            ? null
            : () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => PerfilGlobalScreen(
                    idKey: f.alumnoId,
                    deporte: f.deporte,
                    posicion: posicion))),
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
              Builder(builder: (_) {
                // Foto real del jugador (singles). En parejas no hay una sola
                // foto → inicial. La foto se resuelve del perfil cacheado.
                final foto = esPareja ? null : appState.fotoDe(f.emailIdentidad);
                return CircleAvatar(
                  radius: 15,
                  backgroundColor: teal,
                  backgroundImage: (foto != null && foto.isNotEmpty)
                      ? NetworkImage(foto)
                      : null,
                  child: (foto == null || foto.isEmpty)
                      ? Text(
                          f.nombre.isNotEmpty ? f.nombre[0].toUpperCase() : '?',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              fontSize: 13))
                      : null,
                );
              }),
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
            '${f.categoria.isNotEmpty ? ' · ${f.categoria}' : ''}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: textoTenue, fontSize: 12)),
        // Tabla: columnas alineadas PJ · G · P · Pts (cada una con su etiqueta).
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _Stat('${f.pj}', 'PJ'),
            _Stat('${f.pg}', 'G', color: pino),
            _Stat('${f.pp}', 'P', color: coral),
            _Stat('${f.puntos}', 'Pts', color: cs.primary, grande: true),
          ],
        ),
      ),
    );
  }
}

/// Columna de estadística de la tabla del ranking: número arriba + etiqueta
/// abajo, ancho fijo para que queden alineadas entre filas.
class _Stat extends StatelessWidget {
  const _Stat(this.valor, this.label, {this.color, this.grande = false});
  final String valor;
  final String label;
  final Color? color;
  final bool grande;
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: grande ? 40 : 26,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(valor,
              style: TextStyle(
                  fontWeight: grande ? FontWeight.w900 : FontWeight.w700,
                  fontSize: grande ? 18 : 14,
                  color: color)),
          Text(label,
              style: const TextStyle(
                  color: textoTenue, fontSize: 9.5, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
