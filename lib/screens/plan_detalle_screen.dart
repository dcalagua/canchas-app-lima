import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/plan_trabajo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/dialogo_pichangol.dart';
import 'evaluar_alumno_screen.dart';

/// Detalle de un PLAN DE TRABAJO: editar sus clases y habilidades, y evaluar a
/// los alumnos de la academia sobre ese plan.
class PlanDetalleScreen extends StatelessWidget {
  const PlanDetalleScreen({super.key, required this.planId});
  final String planId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final plan = appState.planPorId(planId);
          if (plan == null) {
            return const Scaffold(
                body: Center(child: Text('Plan no encontrado')));
          }
          final alumnos = appState.alumnosDe(plan.academiaId);
          return CustomScrollView(
            slivers: [
              SliverAppBar(
                pinned: true,
                title: Text(plan.nombre,
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                actions: [
                  IconButton(
                    tooltip: 'Editar plan',
                    icon: const Icon(Icons.edit),
                    onPressed: () => _editarPlan(context, plan),
                  ),
                ],
              ),
              SliverToBoxAdapter(
                child: AnchoLectura(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (plan.nivel.isNotEmpty)
                          Text(plan.nivel,
                              style: TextStyle(
                                  color: textoTenueDe(context),
                                  fontWeight: FontWeight.w600)),
                        const SizedBox(height: 12),

                        // ── Habilidades a evaluar ──
                        _tituloConAccion(
                          context,
                          'Habilidades a evaluar',
                          onAdd: () => _agregarHabilidad(context, plan),
                        ),
                        const SizedBox(height: 6),
                        if (plan.habilidades.isEmpty)
                          Text('Agrega las habilidades que vas a evaluar.',
                              style: TextStyle(
                                  color: textoTenueDe(context), fontSize: 13)),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final h in plan.habilidades)
                              InputChip(
                                label: Text(h),
                                onDeleted: () => _quitarHabilidad(plan, h),
                                backgroundColor: limaSuave.withOpacity(0.6),
                              ),
                          ],
                        ),
                        const SizedBox(height: 20),

                        // ── Evaluar alumnos ──
                        const Text('Evaluar alumnos',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 16)),
                        const SizedBox(height: 8),
                        if (alumnos.isEmpty)
                          Text('Aún no tienes alumnos en la academia.',
                              style: TextStyle(
                                  color: textoTenueDe(context), fontSize: 13))
                        else
                          for (final al in alumnos)
                            _FilaAlumnoEval(alumnoId: al.id, plan: plan),
                        const SizedBox(height: 20),

                        // ── Clases ──
                        _tituloConAccion(
                          context,
                          'Clases (${plan.totalClases})',
                          onAdd: () => _editarSesion(context, plan, null),
                        ),
                        const SizedBox(height: 6),
                        if (plan.sesiones.isEmpty)
                          Text('Agrega las clases de tu programa.',
                              style: TextStyle(
                                  color: textoTenueDe(context), fontSize: 13)),
                        for (final s in plan.sesiones)
                          _CardSesion(
                            sesion: s,
                            onTap: () => _editarSesion(context, plan, s),
                            onEliminar: () => _eliminarSesion(plan, s),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _tituloConAccion(BuildContext context, String texto,
      {required VoidCallback onAdd}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(texto,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        TextButton.icon(
          onPressed: onAdd,
          icon: const Icon(Icons.add, size: 18),
          label: const Text('Agregar'),
        ),
      ],
    );
  }

  // ── Editar plan (nombre / nivel) ──
  Future<void> _editarPlan(BuildContext context, PlanTrabajo plan) async {
    final nombre = TextEditingController(text: plan.nombre);
    final nivel = TextEditingController(text: plan.nivel);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Editar plan',
        icono: Icons.assignment_outlined,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: nombre,
                decoration: const InputDecoration(labelText: 'Nombre del plan')),
            TextField(
                controller: nivel,
                decoration: const InputDecoration(
                    labelText: 'Nivel (ej. Iniciación)')),
          ],
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima, foregroundColor: Colors.white),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
    if (ok == true && nombre.text.trim().isNotEmpty) {
      appState.guardarPlan(
          plan.copyWith(nombre: nombre.text.trim(), nivel: nivel.text.trim()));
    }
  }

  Future<void> _agregarHabilidad(BuildContext context, PlanTrabajo plan) async {
    final c = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Nueva habilidad',
        icono: Icons.star_border,
        contenido: TextField(
          controller: c,
          autofocus: true,
          decoration:
              const InputDecoration(labelText: 'Habilidad (ej. Revés)'),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima, foregroundColor: Colors.white),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Agregar'),
          ),
        ],
      ),
    );
    final txt = c.text.trim();
    if (ok == true && txt.isNotEmpty && !plan.habilidades.contains(txt)) {
      appState.guardarPlan(
          plan.copyWith(habilidades: [...plan.habilidades, txt]));
    }
  }

  void _quitarHabilidad(PlanTrabajo plan, String h) {
    appState.guardarPlan(plan.copyWith(
        habilidades: plan.habilidades.where((x) => x != h).toList()));
  }

  // ── Editar / crear una clase ──
  Future<void> _editarSesion(
      BuildContext context, PlanTrabajo plan, SesionPlan? sesion) async {
    final esNueva = sesion == null;
    final titulo = TextEditingController(text: sesion?.titulo ?? '');
    final objetivo = TextEditingController(text: sesion?.objetivo ?? '');
    final contenidos = TextEditingController(
        text: (sesion?.contenidos ?? const []).join('\n'));
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: esNueva ? 'Nueva clase' : 'Clase ${sesion.numero}',
        icono: Icons.event_note,
        contenido: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: titulo,
                  decoration:
                      const InputDecoration(labelText: 'Título de la clase')),
              TextField(
                  controller: objetivo,
                  minLines: 1,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: 'Objetivo')),
              const SizedBox(height: 4),
              TextField(
                controller: contenidos,
                minLines: 3,
                maxLines: 8,
                decoration: const InputDecoration(
                  labelText: 'Contenidos / drills',
                  hintText: 'Uno por línea',
                  alignLabelWithHint: true,
                ),
              ),
            ],
          ),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima, foregroundColor: Colors.white),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Guardar'),
          ),
        ],
      ),
    );
    if (ok != true || titulo.text.trim().isEmpty) return;
    final drills = contenidos.text
        .split('\n')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    final lista = [...plan.sesiones];
    if (esNueva) {
      lista.add(SesionPlan(
        numero: lista.length + 1,
        titulo: titulo.text.trim(),
        objetivo: objetivo.text.trim(),
        contenidos: drills,
      ));
    } else {
      final i = lista.indexWhere((x) => x.numero == sesion.numero);
      if (i >= 0) {
        lista[i] = sesion.copyWith(
          titulo: titulo.text.trim(),
          objetivo: objetivo.text.trim(),
          contenidos: drills,
        );
      }
    }
    appState.guardarPlan(plan.copyWith(sesiones: lista));
  }

  void _eliminarSesion(PlanTrabajo plan, SesionPlan s) {
    final lista = plan.sesiones.where((x) => x.numero != s.numero).toList();
    // Renumera para que queden 1..N.
    for (var i = 0; i < lista.length; i++) {
      lista[i] = lista[i].copyWith(numero: i + 1);
    }
    appState.guardarPlan(plan.copyWith(sesiones: lista));
  }
}

/// Fila de un alumno con su % de avance en el plan → abre su evaluación.
class _FilaAlumnoEval extends StatelessWidget {
  const _FilaAlumnoEval({required this.alumnoId, required this.plan});
  final String alumnoId;
  final PlanTrabajo plan;

  @override
  Widget build(BuildContext context) {
    Alumno? al;
    for (final a in appState.alumnos) {
      if (a.id == alumnoId) al = a;
    }
    if (al == null) return const SizedBox.shrink();
    final prog = appState.progresoAlumno(alumnoId, plan);
    final tieneFoto = al.fotoUrl != null && al.fotoUrl!.isNotEmpty;
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: verdeClaro,
          backgroundImage: tieneFoto ? NetworkImage(al.fotoUrl!) : null,
          child: tieneFoto
              ? null
              : Text(al.nombre.isNotEmpty ? al.nombre[0].toUpperCase() : '?',
                  style: const TextStyle(color: Colors.white)),
        ),
        title: Text(al.nombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: prog.total == 0 ? 0 : prog.pct / 100,
                    minHeight: 7,
                    backgroundColor: Colors.black.withOpacity(0.07),
                    valueColor: const AlwaysStoppedAnimation(lima),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text('${prog.pct.round()}%',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 12.5)),
            ],
          ),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) =>
                EvaluarAlumnoScreen(alumnoId: alumnoId, planId: plan.id))),
      ),
    );
  }
}

class _CardSesion extends StatelessWidget {
  const _CardSesion({
    required this.sesion,
    required this.onTap,
    required this.onEliminar,
  });
  final SesionPlan sesion;
  final VoidCallback onTap;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(10)),
              child: Text('${sesion.numero}',
                  style: const TextStyle(
                      color: bosque, fontWeight: FontWeight.w900)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: InkWell(
                onTap: onTap,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(sesion.titulo,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    if (sesion.objetivo.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(sesion.objetivo,
                          style: TextStyle(
                              color: textoTenueDe(context), fontSize: 12.8)),
                    ],
                    if (sesion.contenidos.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      for (final d in sesion.contenidos)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 2),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('•  ',
                                  style: TextStyle(color: lima)),
                              Expanded(
                                child: Text(d,
                                    style: const TextStyle(fontSize: 12.8)),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            ),
            PopupMenuButton<String>(
              onSelected: (v) {
                if (v == 'edit') onTap();
                if (v == 'del') onEliminar();
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'edit', child: Text('Editar')),
                PopupMenuItem(value: 'del', child: Text('Eliminar')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
