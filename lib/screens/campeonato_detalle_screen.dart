import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Detalle de un campeonato: participantes, fixture (llave o tabla), carga de
/// resultados y compartir por WhatsApp. Los controles de edición se muestran
/// solo al organizador (dueño).
class CampeonatoDetalleScreen extends StatelessWidget {
  const CampeonatoDetalleScreen({super.key, required this.campeonatoId});
  final String campeonatoId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Campeonato')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final c = appState.campeonatoPorId(campeonatoId);
          if (c == null) {
            return const Center(child: Text('Campeonato no encontrado'));
          }
          final u = appState.usuario;
          final esDueno =
              u != null && c.dueno.toLowerCase() == u.email.toLowerCase();
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 30),
            children: [
              _Cabecera(campeonato: c),
              const SizedBox(height: 14),
              _Participantes(campeonato: c, esDueno: esDueno),
              const SizedBox(height: 18),
              if (c.fixtureGenerado) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                        c.formato == FormatoTorneo.liga
                            ? 'Tabla y partidos'
                            : 'Llave',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 17)),
                    TextButton.icon(
                      onPressed: () => _compartir(context, c),
                      icon: const Icon(Icons.share, size: 18),
                      label: const Text('Compartir'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                if (c.formato == FormatoTorneo.liga)
                  _Liga(campeonato: c, esDueno: esDueno)
                else
                  _Llave(campeonato: c, esDueno: esDueno),
              ],
              if (esDueno) ...[
                const SizedBox(height: 20),
                OutlinedButton.icon(
                  onPressed: () => _confirmarEliminar(context, c),
                  icon: const Icon(Icons.delete_outline,
                      color: Colors.redAccent),
                  label: const Text('Eliminar campeonato',
                      style: TextStyle(color: Colors.redAccent)),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _confirmarEliminar(BuildContext context, Campeonato c) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eliminar campeonato'),
        content: Text('¿Eliminar "${c.nombre}"? No se puede deshacer.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Eliminar')),
        ],
      ),
    );
    if (ok == true && context.mounted) {
      appState.eliminarCampeonato(c.id);
      Navigator.of(context).pop();
    }
  }

  Future<void> _compartir(BuildContext context, Campeonato c) async {
    final ok = await WhatsAppLink.compartir(_resumen(c));
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pude abrir WhatsApp.')));
    }
  }

  static String _resumen(Campeonato c) {
    final sb = StringBuffer();
    sb.writeln('🏆 ${c.nombre}');
    if (c.categoria.isNotEmpty) sb.writeln('Categoría: ${c.categoria}');
    sb.writeln('${c.deporte.etiqueta} · ${c.formato.etiqueta}');
    if (c.fechas.isNotEmpty) sb.writeln('📅 ${c.fechas}');
    if (c.sede.isNotEmpty) sb.writeln('📍 ${c.sede}');
    sb.writeln('');
    if (c.formato == FormatoTorneo.liga) {
      sb.writeln('TABLA:');
      var pos = 1;
      for (final f in TorneoFixture.tabla(c)) {
        sb.writeln('$pos. ${f.nombre} — ${f.pts} pts '
            '(${f.g}G ${f.e}E ${f.p}P, dif ${f.dif >= 0 ? '+' : ''}${f.dif})');
        pos++;
      }
    } else {
      sb.writeln('RESULTADOS:');
      final jugados = c.partidos.where((p) => p.jugado).toList();
      if (jugados.isEmpty) sb.writeln('(aún sin resultados)');
      for (final m in jugados) {
        final a = c.participante(m.aId)?.nombre ?? '—';
        final b = c.participante(m.bId)?.nombre ?? '—';
        sb.writeln('$a ${m.marcadorA}-${m.marcadorB} $b');
      }
    }
    sb.writeln('\nvía Pichangol');
    return sb.toString();
  }
}

class _Cabecera extends StatelessWidget {
  const _Cabecera({required this.campeonato});
  final Campeonato campeonato;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    final c = campeonato;
    final chips = <String>[
      c.deporte.etiqueta,
      c.formato.etiqueta,
      if (c.categoria.isNotEmpty) c.categoria,
      if (c.fechas.isNotEmpty) '📅 ${c.fechas}',
      if (c.sede.isNotEmpty) '📍 ${c.sede}',
      if (c.costoInscripcion > 0)
        'Inscripción S/ ${c.costoInscripcion.toStringAsFixed(2)}',
    ];
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                backgroundColor: colorDeporte(c.deporte),
                child:
                    Icon(iconoDeporte(c.deporte), color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(c.nombre,
                    style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in chips)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                      color: limaSuave,
                      borderRadius: BorderRadius.circular(999)),
                  child: Text(s,
                      style: const TextStyle(
                          color: bosque,
                          fontSize: 12,
                          fontWeight: FontWeight.w700)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Participantes extends StatelessWidget {
  const _Participantes({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;

  Future<void> _agregar(BuildContext context) async {
    final nombre = TextEditingController();
    final wa = TextEditingController();
    final esFutbol = campeonato.deporte.name == 'futbol';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(esFutbol ? 'Nuevo equipo' : 'Nuevo participante'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nombre,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(
                  labelText: esFutbol
                      ? 'Nombre del equipo'
                      : 'Nombre (jugador o pareja "A / B")'),
            ),
            TextField(
              controller: wa,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                  labelText: 'WhatsApp (opcional)', prefixText: '+51 '),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Agregar')),
        ],
      ),
    );
    if (ok == true) {
      appState.agregarParticipante(campeonato.id, nombre.text,
          contacto: wa.text);
    }
  }

  Future<void> _generar(BuildContext context) async {
    if (campeonato.participantes.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Agrega al menos 2 participantes.')));
      return;
    }
    if (campeonato.fixtureGenerado) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Regenerar fixture'),
          content: const Text(
              'Ya hay un fixture. Regenerarlo BORRA los resultados cargados. '
              '¿Continuar?'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Cancelar')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Regenerar')),
          ],
        ),
      );
      if (ok != true) return;
    }
    appState.generarFixture(campeonato.id);
  }

  @override
  Widget build(BuildContext context) {
    final c = campeonato;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Participantes (${c.participantes.length})',
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            if (esDueno)
              TextButton.icon(
                onPressed: () => _agregar(context),
                icon: const Icon(Icons.person_add_alt_1),
                label: const Text('Agregar'),
              ),
          ],
        ),
        if (c.participantes.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Aún no hay inscritos.',
                style: TextStyle(color: textoTenue)),
          ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final p in c.participantes)
              InputChip(
                label: Text(p.nombre),
                onDeleted: esDueno
                    ? () => appState.eliminarParticipante(c.id, p.id)
                    : null,
              ),
          ],
        ),
        if (esDueno) ...[
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => _generar(context),
              icon: const Icon(Icons.account_tree),
              label: Text(c.fixtureGenerado
                  ? 'Regenerar fixture'
                  : 'Generar fixture'),
            ),
          ),
        ],
      ],
    );
  }
}

/// Diálogo para cargar el marcador de un partido.
Future<void> _cargarResultado(
    BuildContext context, Campeonato c, PartidoTorneo m) async {
  if (m.aId == null || m.bId == null) return; // cruce aún no definido
  final na = c.participante(m.aId)?.nombre ?? 'A';
  final nb = c.participante(m.bId)?.nombre ?? 'B';
  final ca = TextEditingController(text: m.marcadorA?.toString() ?? '');
  final cb = TextEditingController(text: m.marcadorB?.toString() ?? '');
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Cargar resultado'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _FilaMarcador(nombre: na, controller: ca),
          const SizedBox(height: 8),
          _FilaMarcador(nombre: nb, controller: cb),
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Guardar')),
      ],
    ),
  );
  if (ok == true) {
    final a = int.tryParse(ca.text.trim());
    final b = int.tryParse(cb.text.trim());
    if (a != null && b != null) {
      appState.setResultado(c.id, m.id, a, b);
    }
  }
}

class _FilaMarcador extends StatelessWidget {
  const _FilaMarcador({required this.nombre, required this.controller});
  final String nombre;
  final TextEditingController controller;
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
            child: Text(nombre,
                maxLines: 1, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 10),
        SizedBox(
          width: 60,
          child: TextField(
            controller: controller,
            textAlign: TextAlign.center,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(hintText: '0'),
          ),
        ),
      ],
    );
  }
}

class _Liga extends StatelessWidget {
  const _Liga({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tabla = TorneoFixture.tabla(campeonato);
    // Partidos agrupados por jornada.
    final porJornada = <int, List<PartidoTorneo>>{};
    for (final m in campeonato.partidos) {
      (porJornada[m.ronda] ??= []).add(m);
    }
    final jornadas = porJornada.keys.toList()..sort();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Tabla.
        Container(
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: trazo),
          ),
          child: Column(
            children: [
              const _TablaHeader(),
              for (var i = 0; i < tabla.length; i++)
                _TablaFila(pos: i + 1, fila: tabla[i]),
            ],
          ),
        ),
        const SizedBox(height: 16),
        for (final j in jornadas) ...[
          Text('Jornada ${j + 1}',
              style:
                  const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          const SizedBox(height: 6),
          for (final m in porJornada[j]!)
            _PartidoTile(
                campeonato: campeonato, partido: m, esDueno: esDueno),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _TablaHeader extends StatelessWidget {
  const _TablaHeader();
  @override
  Widget build(BuildContext context) {
    const st = TextStyle(
        fontWeight: FontWeight.w800, fontSize: 12, color: textoTenue);
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      child: Row(
        children: [
          const SizedBox(width: 22, child: Text('#', style: st)),
          const Expanded(child: Text('Equipo', style: st)),
          _celda('PJ', st),
          _celda('G', st),
          _celda('E', st),
          _celda('P', st),
          _celda('Dif', st),
          _celda('Pts', st),
        ],
      ),
    );
  }

  static Widget _celda(String t, TextStyle st) =>
      SizedBox(width: 30, child: Text(t, textAlign: TextAlign.center, style: st));
}

class _TablaFila extends StatelessWidget {
  const _TablaFila({required this.pos, required this.fila});
  final int pos;
  final FilaTabla fila;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final n = TextStyle(fontSize: 13, color: cs.onSurface);
    final b = TextStyle(
        fontSize: 13, fontWeight: FontWeight.w800, color: cs.onSurface);
    return Container(
      decoration: BoxDecoration(
          border: Border(top: BorderSide(color: trazo.withOpacity(0.6)))),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      child: Row(
        children: [
          SizedBox(width: 22, child: Text('$pos', style: b)),
          Expanded(
              child: Text(fila.nombre,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: n)),
          _celda('${fila.pj}', n),
          _celda('${fila.g}', n),
          _celda('${fila.e}', n),
          _celda('${fila.p}', n),
          _celda('${fila.dif >= 0 ? '+' : ''}${fila.dif}', n),
          _celda('${fila.pts}', b),
        ],
      ),
    );
  }

  static Widget _celda(String t, TextStyle st) =>
      SizedBox(width: 30, child: Text(t, textAlign: TextAlign.center, style: st));
}

class _Llave extends StatelessWidget {
  const _Llave({required this.campeonato, required this.esDueno});
  final Campeonato campeonato;
  final bool esDueno;

  static String _nombreRonda(int total, int r) {
    final desdeFinal = total - 1 - r;
    return switch (desdeFinal) {
      0 => 'Final',
      1 => 'Semifinal',
      2 => 'Cuartos de final',
      3 => 'Octavos de final',
      _ => 'Ronda ${r + 1}',
    };
  }

  @override
  Widget build(BuildContext context) {
    final porRonda = <int, List<PartidoTorneo>>{};
    for (final m in campeonato.partidos) {
      (porRonda[m.ronda] ??= []).add(m);
    }
    final rondas = porRonda.keys.toList()..sort();
    final total = rondas.isEmpty ? 0 : rondas.last + 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final r in rondas) ...[
          Text(_nombreRonda(total, r),
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          const SizedBox(height: 6),
          for (final m in porRonda[r]!)
            _PartidoTile(
                campeonato: campeonato, partido: m, esDueno: esDueno),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _PartidoTile extends StatelessWidget {
  const _PartidoTile(
      {required this.campeonato, required this.partido, required this.esDueno});
  final Campeonato campeonato;
  final PartidoTorneo partido;
  final bool esDueno;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final m = partido;
    final na = campeonato.participante(m.aId)?.nombre;
    final nb = campeonato.participante(m.bId)?.nombre;
    final ganador = m.ganadorId;
    final defBye =
        m.ronda == 0 && ((m.aId == null) != (m.bId == null)) && !m.jugado;
    final habilitado = esDueno && m.aId != null && m.bId != null;
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        dense: true,
        onTap: habilitado ? () => _cargarResultado(context, campeonato, m) : null,
        title: Row(
          children: [
            Expanded(
              child: _Lado(
                  nombre: na ?? (defBye ? '(bye)' : 'Por definir'),
                  gana: ganador != null && ganador == m.aId),
            ),
            _Marcador(m.marcadorA),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 4),
              child: Text('-', style: TextStyle(color: textoTenue)),
            ),
            _Marcador(m.marcadorB),
            Expanded(
              child: _Lado(
                  nombre: nb ?? (defBye ? '(bye)' : 'Por definir'),
                  gana: ganador != null && ganador == m.bId,
                  alinearDerecha: true),
            ),
          ],
        ),
        trailing: habilitado
            ? Icon(Icons.edit, size: 16, color: cs.primary)
            : null,
      ),
    );
  }
}

class _Lado extends StatelessWidget {
  const _Lado(
      {required this.nombre, required this.gana, this.alinearDerecha = false});
  final String nombre;
  final bool gana;
  final bool alinearDerecha;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Text(
      nombre,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      textAlign: alinearDerecha ? TextAlign.right : TextAlign.left,
      style: TextStyle(
        fontSize: 13,
        color: cs.onSurface,
        fontWeight: gana ? FontWeight.w800 : FontWeight.w500,
      ),
    );
  }
}

class _Marcador extends StatelessWidget {
  const _Marcador(this.valor);
  final int? valor;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SizedBox(
      width: 20,
      child: Text(valor?.toString() ?? '–',
          textAlign: TextAlign.center,
          style: TextStyle(fontWeight: FontWeight.w800, color: cs.onSurface)),
    );
  }
}
