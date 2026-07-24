import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// CIRCUITO / RANKING interno de una academia (Fase 0 de Pichangol Circuito).
/// Tabla de posiciones de los alumnos + carnet del jugador. El dueño (profe)
/// registra resultados de partidos entre sus alumnos; los puntos actualizan la
/// tabla al instante. Es la capa de comunidad/identidad sobre la academia.
class RankingAcademiaScreen extends StatefulWidget {
  const RankingAcademiaScreen(
      {super.key, required this.academiaId, this.esDueno = false});
  final String academiaId;
  final bool esDueno;

  @override
  State<RankingAcademiaScreen> createState() => _RankingAcademiaScreenState();
}

class _RankingAcademiaScreenState extends State<RankingAcademiaScreen> {
  String _categoriaSel = ''; // '' = todas
  String _sedeSel = ''; // '' = todas

  Academia? _academia() {
    for (final a in appState.academias) {
      if (a.id == widget.academiaId) return a;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Ranking del circuito')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final ac = _academia();
          if (ac == null) {
            return const Center(child: Text('Academia no encontrada.'));
          }
          final alumnos = appState.alumnosDe(ac.id);
          final sedes = ac.sedesEfectivas;
          final multiSede = ac.sedes.length > 1;
          // Categorías presentes (para el filtro).
          final categorias = <String>{
            for (final a in alumnos)
              if (ac.categoriaDe(a.id).isNotEmpty) ac.categoriaDe(a.id)
          }.toList()
            ..sort();
          final tabla = ac.ranking(alumnos,
              sedeId: _sedeSel.isEmpty ? null : _sedeSel,
              categoria: _categoriaSel.isEmpty ? null : _categoriaSel);

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
            children: [
              _Explicacion(),
              if (multiSede) ...[
                const SizedBox(height: 12),
                _filtro('Sede', [
                  ('', 'Todas'),
                  for (final s in sedes) (s.id, s.nombre),
                ], _sedeSel, (v) => setState(() => _sedeSel = v)),
              ],
              if (categorias.isNotEmpty) ...[
                const SizedBox(height: 10),
                _filtro('Categoría', [
                  ('', 'Todas'),
                  for (final c in categorias) (c, c),
                ], _categoriaSel, (v) => setState(() => _categoriaSel = v)),
              ],
              const SizedBox(height: 14),
              if (alumnos.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text(
                      'Aún no tienes alumnos. Cuando se unan aparecerán en el '
                      'ranking.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: textoTenue)),
                )
              else
                for (var i = 0; i < tabla.length; i++)
                  _FilaRanking(
                    posicion: i + 1,
                    p: tabla[i],
                    moneda: ac.monedaSimbolo,
                    onTap: () => _abrirCarnet(context, ac, tabla[i], i + 1),
                  ),
            ],
          );
        },
      ),
      floatingActionButton: widget.esDueno
          ? FloatingActionButton.extended(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.sports_tennis),
              label: const Text('Registrar resultado'),
              onPressed: () => _registrarResultado(context),
            )
          : null,
    );
  }

  Widget _filtro(String titulo, List<(String, String)> ops, String sel,
      ValueChanged<String> onSel) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(titulo,
            style: const TextStyle(
                fontSize: 12.5, color: textoTenue, fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (val, label) in ops)
              ChoiceChip(
                label: Text(label),
                selected: sel == val,
                selectedColor: limaSuave,
                onSelected: (_) => onSel(val),
              ),
          ],
        ),
      ],
    );
  }

  // ── Carnet del jugador ─────────────────────────────────────────────────────
  void _abrirCarnet(
      BuildContext context, Academia ac, PosicionRanking p, int posicion) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _Carnet(
        academiaId: ac.id,
        esDueno: widget.esDueno,
        alumnoId: p.alumnoId,
      ),
    );
  }

  // ── Registrar resultado (solo dueño) ───────────────────────────────────────
  Future<void> _registrarResultado(BuildContext context) async {
    final ac = _academia();
    if (ac == null) return;
    final alumnos = appState.alumnosDe(ac.id);
    if (alumnos.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Necesitas al menos 2 alumnos para registrar un '
              'partido.')));
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => _RegistrarResultadoSheet(academiaId: ac.id),
    );
  }
}

class _Explicacion extends StatelessWidget {
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
          const Icon(Icons.emoji_events, color: bosque, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
                'Cada partido suma: ganar +${Academia.puntosVictoria}, jugar '
                '+${Academia.puntosDerrota}. Compite, sube en la tabla y arma '
                'tu carnet.',
                style: const TextStyle(
                    fontSize: 13, color: bosque, height: 1.3)),
          ),
        ],
      ),
    );
  }
}

class _FilaRanking extends StatelessWidget {
  const _FilaRanking(
      {required this.posicion,
      required this.p,
      required this.moneda,
      required this.onTap});
  final int posicion;
  final PosicionRanking p;
  final String moneda;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Medalla para el podio.
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
        onTap: onTap,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        leading: SizedBox(
          width: 60,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 22,
                child: Text(
                    medalla.isNotEmpty ? medalla : '$posicion',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: medalla.isNotEmpty ? 18 : 15,
                        color: textoTenue)),
              ),
              const SizedBox(width: 4),
              CircleAvatar(
                radius: 16,
                backgroundColor: limaSuave,
                backgroundImage: (p.fotoUrl != null && p.fotoUrl!.isNotEmpty)
                    ? NetworkImage(p.fotoUrl!)
                    : null,
                child: (p.fotoUrl == null || p.fotoUrl!.isEmpty)
                    ? Text(
                        p.nombre.isNotEmpty ? p.nombre[0].toUpperCase() : '?',
                        style: const TextStyle(
                            color: bosque, fontWeight: FontWeight.w800))
                    : null,
              ),
            ],
          ),
        ),
        title: Text(p.nombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(
            '${p.pj} PJ · ${p.pg} G · ${p.pp} P'
            '${p.categoria.isNotEmpty ? ' · ${p.categoria}' : ''}',
            style: const TextStyle(color: textoTenue, fontSize: 12)),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('${p.puntos}',
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

/// Carnet digital del jugador: identidad + estadísticas + últimos partidos.
class _Carnet extends StatelessWidget {
  const _Carnet(
      {required this.academiaId, required this.esDueno, required this.alumnoId});
  final String academiaId;
  final bool esDueno;
  final String alumnoId;

  Academia? _ac() {
    for (final a in appState.academias) {
      if (a.id == academiaId) return a;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    // Recomputamos en vivo (el ranking puede cambiar si se registran partidos).
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final ac = _ac();
        if (ac == null) return const SizedBox.shrink();
        final alumnos = appState.alumnosDe(ac.id);
        final tabla = ac.ranking(alumnos);
        final idx = tabla.indexWhere((e) => e.alumnoId == alumnoId);
        if (idx < 0) return const SizedBox.shrink();
        final posicion = idx + 1;
        final p = tabla[idx];
        final partidos = ac.partidosDe(p.alumnoId);
        final cs = Theme.of(context).colorScheme;
        return Padding(
          padding: EdgeInsets.fromLTRB(
              20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Encabezado tipo "carnet".
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [bosque, Color(0xFF1E5C4C)],
                    ),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 30,
                        backgroundColor: lima,
                        backgroundImage:
                            (p.fotoUrl != null && p.fotoUrl!.isNotEmpty)
                                ? NetworkImage(p.fotoUrl!)
                                : null,
                        child: (p.fotoUrl == null || p.fotoUrl!.isEmpty)
                            ? Text(
                                p.nombre.isNotEmpty
                                    ? p.nombre[0].toUpperCase()
                                    : '?',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 24))
                            : null,
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(p.nombre,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 19)),
                            const SizedBox(height: 2),
                            Text(
                                'Puesto #$posicion'
                                '${p.categoria.isNotEmpty ? ' · ${p.categoria}' : ''}',
                                style: TextStyle(
                                    color: Colors.white.withOpacity(0.85),
                                    fontWeight: FontWeight.w700)),
                            Text(ac.nombre,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    color: Colors.white.withOpacity(0.7),
                                    fontSize: 12.5)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                // Estadísticas.
                Row(
                  children: [
                    _StatBox('Puntos', '${p.puntos}', cs.primary),
                    const SizedBox(width: 10),
                    _StatBox('Jugados', '${p.pj}', cs.onSurface),
                    const SizedBox(width: 10),
                    _StatBox('Ganados', '${p.pg}', lima),
                    const SizedBox(width: 10),
                    _StatBox('Efectividad', '${p.pct.toStringAsFixed(0)}%',
                        bosque),
                  ],
                ),
                if (esDueno) ...[
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: () => _editarCategoria(context, ac, p),
                    style: OutlinedButton.styleFrom(
                        foregroundColor: bosque,
                        side: const BorderSide(color: bosque)),
                    icon: const Icon(Icons.badge_outlined, size: 18),
                    label: Text(p.categoria.isEmpty
                        ? 'Asignar categoría'
                        : 'Editar categoría (${p.categoria})'),
                  ),
                ],
                const SizedBox(height: 18),
                const Text('Últimos partidos',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 8),
                if (partidos.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 10),
                    child: Text('Sin partidos aún.',
                        style: TextStyle(color: textoTenue)),
                  )
                else
                  for (final partido in partidos.take(10))
                    _FilaPartidoCarnet(p: partido, alumnoId: p.alumnoId),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _editarCategoria(
      BuildContext context, Academia ac, PosicionRanking p) async {
    final ctrl = TextEditingController(text: p.categoria);
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Categoría del jugador'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
              labelText: 'Categoría',
              hintText: 'ej. 7ma, Intermedio, Sub-10'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(dctx, true),
              child: const Text('Guardar')),
        ],
      ),
    );
    if (ok == true) {
      await appState.setCategoriaAlumno(ac.id, p.alumnoId, ctrl.text.trim());
    }
  }
}

class _StatBox extends StatelessWidget {
  const _StatBox(this.titulo, this.valor, this.color);
  final String titulo;
  final String valor;
  final Color color;
  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: trazo),
        ),
        child: Column(
          children: [
            Text(valor,
                style: TextStyle(
                    fontWeight: FontWeight.w900, fontSize: 17, color: color)),
            const SizedBox(height: 2),
            Text(titulo,
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue, fontSize: 10.5)),
          ],
        ),
      ),
    );
  }
}

class _FilaPartidoCarnet extends StatelessWidget {
  const _FilaPartidoCarnet({required this.p, required this.alumnoId});
  final PartidoRanking p;
  final String alumnoId;
  @override
  Widget build(BuildContext context) {
    final gano = p.ganadorId == alumnoId;
    final rivalId = p.jugadorAId == alumnoId ? p.jugadorBId : p.jugadorAId;
    final rival = p.nombreDe(rivalId);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: gano ? limaSuave : const Color(0xFFF3E4E4),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(gano ? 'Ganó' : 'Perdió',
                style: TextStyle(
                    color: gano ? bosque : clayOscuro,
                    fontWeight: FontWeight.w800,
                    fontSize: 12)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text('vs $rival',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          if (p.marcador.isNotEmpty)
            Text(p.marcador,
                style: const TextStyle(color: textoTenue, fontSize: 12.5)),
        ],
      ),
    );
  }
}

/// Hoja para registrar un resultado (solo el dueño/profe).
class _RegistrarResultadoSheet extends StatefulWidget {
  const _RegistrarResultadoSheet({required this.academiaId});
  final String academiaId;
  @override
  State<_RegistrarResultadoSheet> createState() =>
      _RegistrarResultadoSheetState();
}

class _RegistrarResultadoSheetState extends State<_RegistrarResultadoSheet> {
  String? _aId;
  String? _bId;
  String? _ganadorId;
  String _sedeId = '';
  final _marcador = TextEditingController();
  String? _error;
  bool _guardando = false;

  @override
  void dispose() {
    _marcador.dispose();
    super.dispose();
  }

  Academia? _ac() {
    for (final a in appState.academias) {
      if (a.id == widget.academiaId) return a;
    }
    return null;
  }

  Future<void> _guardar() async {
    final ac = _ac();
    if (ac == null) return;
    if (_aId == null || _bId == null) {
      setState(() => _error = 'Elige los dos jugadores.');
      return;
    }
    if (_aId == _bId) {
      setState(() => _error = 'Deben ser jugadores distintos.');
      return;
    }
    if (_ganadorId == null) {
      setState(() => _error = 'Marca quién ganó.');
      return;
    }
    final alumnos = appState.alumnosDe(ac.id);
    String nombre(String id) =>
        alumnos.firstWhere((a) => a.id == id, orElse: () => alumnos.first).nombre;
    setState(() {
      _guardando = true;
      _error = null;
    });
    final partido = PartidoRanking(
      id: 'pr_${DateTime.now().microsecondsSinceEpoch}',
      fecha: DateTime.now(),
      jugadorAId: _aId!,
      jugadorANombre: nombre(_aId!),
      jugadorBId: _bId!,
      jugadorBNombre: nombre(_bId!),
      ganadorId: _ganadorId!,
      marcador: _marcador.text.trim(),
      sedeId: _sedeId,
    );
    await appState.registrarPartido(ac.id, partido);
    if (!mounted) return;
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Resultado registrado. Ranking actualizado.')));
  }

  @override
  Widget build(BuildContext context) {
    final ac = _ac();
    if (ac == null) return const SizedBox.shrink();
    final alumnos = appState.alumnosDe(ac.id);
    final multiSede = ac.sedes.length > 1;

    DropdownButtonFormField<String> selector(
        String label, String? valor, ValueChanged<String?> onChanged) {
      return DropdownButtonFormField<String>(
        value: valor,
        isExpanded: true,
        decoration: InputDecoration(labelText: label, isDense: true),
        items: [
          for (final a in alumnos)
            DropdownMenuItem(value: a.id, child: Text(a.nombre)),
        ],
        onChanged: onChanged,
      );
    }

    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Registrar resultado',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 14),
            selector('Jugador A', _aId, (v) => setState(() {
                  _aId = v;
                  if (_ganadorId != null &&
                      _ganadorId != _aId &&
                      _ganadorId != _bId) _ganadorId = null;
                })),
            const SizedBox(height: 12),
            selector('Jugador B', _bId, (v) => setState(() {
                  _bId = v;
                  if (_ganadorId != null &&
                      _ganadorId != _aId &&
                      _ganadorId != _bId) _ganadorId = null;
                })),
            const SizedBox(height: 12),
            TextField(
              controller: _marcador,
              decoration: const InputDecoration(
                  labelText: 'Marcador (opcional)', hintText: 'ej. 6-3 6-4'),
            ),
            if (multiSede) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _sedeId.isEmpty ? null : _sedeId,
                isExpanded: true,
                decoration:
                    const InputDecoration(labelText: 'Sede (opcional)', isDense: true),
                items: [
                  for (final s in ac.sedesEfectivas)
                    DropdownMenuItem(value: s.id, child: Text(s.nombre)),
                ],
                onChanged: (v) => setState(() => _sedeId = v ?? ''),
              ),
            ],
            const SizedBox(height: 16),
            const Text('¿Quién ganó?',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: _botonGanador(alumnos, _aId, 'Jugador A')),
                const SizedBox(width: 10),
                Expanded(child: _botonGanador(alumnos, _bId, 'Jugador B')),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  style: const TextStyle(
                      color: Color(0xFFC0392B), fontWeight: FontWeight.w600)),
            ],
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                onPressed: _guardando ? null : _guardar,
                child: _guardando
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2.4, color: Colors.white))
                    : const Text('Guardar resultado'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _botonGanador(List<Alumno> alumnos, String? id, String fallback) {
    final habilitado = id != null;
    final sel = _ganadorId != null && _ganadorId == id;
    String nombre() {
      if (id == null) return fallback;
      for (final a in alumnos) {
        if (a.id == id) return a.nombre;
      }
      return fallback;
    }

    return InkWell(
      onTap: habilitado ? () => setState(() => _ganadorId = id) : null,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
        decoration: BoxDecoration(
          color: sel ? limaSuave : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: sel ? lima : trazo, width: sel ? 1.6 : 1),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(sel ? Icons.emoji_events : Icons.emoji_events_outlined,
                size: 18, color: sel ? bosque : textoTenue),
            const SizedBox(width: 6),
            Flexible(
              child: Text(nombre(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: sel ? bosque : textoTenue)),
            ),
          ],
        ),
      ),
    );
  }
}
