import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/plan_trabajo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';

/// Evaluación de un ALUMNO sobre un PLAN: rúbrica simple por habilidad
/// (Inicial · En proceso · Logrado). Cada toque guarda al instante.
class EvaluarAlumnoScreen extends StatelessWidget {
  const EvaluarAlumnoScreen({
    super.key,
    required this.alumnoId,
    required this.planId,
  });
  final String alumnoId;
  final String planId;

  static Color colorNivel(NivelLogro n) {
    switch (n) {
      case NivelLogro.inicial:
        return const Color(0xFFC13515); // clay
      case NivelLogro.enProceso:
        return const Color(0xFFF2A93B); // ámbar
      case NivelLogro.logrado:
        return teal;
    }
  }

  static Color colorDesempeno(DesempenoClase d) {
    switch (d) {
      case DesempenoClase.muyBien:
        return teal;
      case DesempenoClase.bien:
        return const Color(0xFFF2A93B); // ámbar
      case DesempenoClase.aReforzar:
        return const Color(0xFFC13515); // clay
    }
  }

  /// Abre la hoja para registrar la clase de hoy y persiste la nota.
  Future<void> _registrarClase(
      BuildContext context, PlanTrabajo plan, String alumnoId) async {
    final res = await showModalBottomSheet<_ResultadoNota>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _HojaNotaClase(plan: plan),
    );
    if (res == null) return;
    appState.agregarNotaClase(
      academiaId: plan.academiaId,
      alumnoId: alumnoId,
      planId: plan.id,
      sesionNumero: res.sesion,
      desempeno: res.desempeno,
      nota: res.nota,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Evaluación')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final plan = appState.planPorId(planId);
          Alumno? al;
          for (final a in appState.alumnos) {
            if (a.id == alumnoId) al = a;
          }
          if (plan == null || al == null) {
            return const Center(child: Text('No disponible'));
          }
          final alumno = al;
          final prog = appState.progresoAlumno(alumnoId, plan);
          // Bitácora: notas de ESTE plan (o sueltas) del alumno, recientes 1º.
          final notas = appState
              .notasDe(alumnoId)
              .where((n) => n.planId == planId || n.planId.isEmpty)
              .toList();
          final tieneFoto =
              alumno.fotoUrl != null && alumno.fotoUrl!.isNotEmpty;
          return AnchoLectura(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
              children: [
                // Encabezado alumno + progreso.
                Row(
                  children: [
                    CircleAvatar(
                      radius: 26,
                      backgroundColor: verdeClaro,
                      backgroundImage:
                          tieneFoto ? NetworkImage(alumno.fotoUrl!) : null,
                      child: tieneFoto
                          ? null
                          : Text(
                              alumno.nombre.isNotEmpty
                                  ? alumno.nombre[0].toUpperCase()
                                  : '?',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(alumno.nombre,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w800, fontSize: 18)),
                          Text(plan.nombre,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  color: textoTenueDe(context), fontSize: 13)),
                        ],
                      ),
                    ),
                    Text('${prog.pct.round()}%',
                        style: const TextStyle(
                            fontWeight: FontWeight.w900,
                            fontSize: 22,
                            color: bosque)),
                  ],
                ),
                const SizedBox(height: 12),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: prog.total == 0 ? 0 : prog.pct / 100,
                    minHeight: 9,
                    backgroundColor: Colors.black.withOpacity(0.07),
                    valueColor: const AlwaysStoppedAnimation(lima),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '${prog.logrado} logradas · ${prog.enProceso} en proceso · '
                  '${prog.sinEvaluar} sin evaluar',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 12.5),
                ),
                const SizedBox(height: 18),

                if (plan.habilidades.isEmpty)
                  Text(
                    'Este plan aún no tiene habilidades. Agrégalas desde el plan '
                    'para poder evaluar.',
                    style:
                        TextStyle(color: textoTenueDe(context), fontSize: 13.5),
                  ),
                for (final h in plan.habilidades)
                  _FilaHabilidad(
                    habilidad: h,
                    actual: appState.nivelDe(alumnoId, planId, h),
                    onElegir: (n) =>
                        appState.evaluar(alumnoId, planId, h, n),
                  ),

                // ── Bitácora de clases (evaluación DIARIA) ──────────────────
                const Divider(height: 34),
                Row(
                  children: [
                    const Expanded(
                      child: Text('Bitácora de clases',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 16)),
                    ),
                    Text(
                        '${appState.clasesConNota(alumnoId, planId)}/'
                        '${plan.totalClases} clases',
                        style: TextStyle(
                            color: textoTenueDe(context), fontSize: 12.5)),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  'Registra cómo le fue en cada clase. Queda el historial con '
                  'fecha (distinto de la rúbrica de arriba, que es el acumulado).',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13),
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: bosque,
                    minimumSize: const Size.fromHeight(46),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  onPressed: () => _registrarClase(context, plan, alumnoId),
                  icon: const Icon(Icons.add_task),
                  label: const Text('Registrar clase de hoy'),
                ),
                const SizedBox(height: 12),
                if (notas.isEmpty)
                  Text('Aún no registras clases de este alumno.',
                      style: TextStyle(
                          color: textoTenueDe(context), fontSize: 13))
                else
                  for (final n in notas)
                    _CardNota(
                      nota: n,
                      plan: plan,
                      onEliminar: () => appState.eliminarNotaClase(n.id),
                    ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _FilaHabilidad extends StatelessWidget {
  const _FilaHabilidad({
    required this.habilidad,
    required this.actual,
    required this.onElegir,
  });
  final String habilidad;
  final NivelLogro? actual;
  final ValueChanged<NivelLogro> onElegir;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(habilidad,
              style: const TextStyle(
                  fontWeight: FontWeight.w700, fontSize: 14.5)),
          const SizedBox(height: 8),
          Row(
            children: [
              for (final n in NivelLogro.values) ...[
                Expanded(child: _pastilla(n)),
                if (n != NivelLogro.values.last) const SizedBox(width: 8),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _pastilla(NivelLogro n) {
    final sel = actual == n;
    final color = EvaluarAlumnoScreen.colorNivel(n);
    return InkWell(
      onTap: () => onElegir(n),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: sel ? color.withOpacity(0.16) : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: sel ? color : Colors.black.withOpacity(0.18),
              width: sel ? 1.6 : 1),
        ),
        child: Text(
          n.etiqueta,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: sel ? FontWeight.w800 : FontWeight.w600,
            color: sel ? color : Colors.black.withOpacity(0.6),
          ),
        ),
      ),
    );
  }
}

/// Resultado de la hoja "registrar clase".
class _ResultadoNota {
  const _ResultadoNota(this.sesion, this.desempeno, this.nota);
  final int sesion;
  final DesempenoClase desempeno;
  final String nota;
}

/// Tarjeta de una nota de clase (bitácora): fecha, desempeño, clase y observación.
class _CardNota extends StatelessWidget {
  const _CardNota({
    required this.nota,
    required this.plan,
    required this.onEliminar,
  });
  final NotaClase nota;
  final PlanTrabajo plan;
  final VoidCallback onEliminar;

  String get _tituloSesion {
    if (nota.sesionNumero <= 0) return 'Clase suelta';
    for (final s in plan.sesiones) {
      if (s.numero == nota.sesionNumero) {
        return 'Clase ${s.numero}: ${s.titulo}';
      }
    }
    return 'Clase ${nota.sesionNumero}';
  }

  String get _fechaBonita {
    // 'YYYY-MM-DD' → 'DD/MM/YYYY'
    final p = nota.fecha.split('-');
    if (p.length == 3) return '${p[2]}/${p[1]}/${p[0]}';
    return nota.fecha;
  }

  @override
  Widget build(BuildContext context) {
    final color = EvaluarAlumnoScreen.colorDesempeno(nota.desempeno);
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 10,
            height: 10,
            margin: const EdgeInsets.only(top: 5),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(_fechaBonita,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 13.5)),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: color.withOpacity(0.14),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(nota.desempeno.etiqueta,
                          style: TextStyle(
                              color: color,
                              fontWeight: FontWeight.w800,
                              fontSize: 11.5)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(_tituloSesion,
                    style: TextStyle(
                        color: textoTenueDe(context), fontSize: 12.5)),
                if (nota.nota.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(nota.nota, style: const TextStyle(fontSize: 13.5)),
                ],
              ],
            ),
          ),
          IconButton(
            icon: Icon(Icons.close, size: 18, color: textoTenueDe(context)),
            onPressed: onEliminar,
            tooltip: 'Eliminar',
          ),
        ],
      ),
    );
  }
}

/// Hoja para registrar la clase de hoy: desempeño (semáforo) + clase + nota.
class _HojaNotaClase extends StatefulWidget {
  const _HojaNotaClase({required this.plan});
  final PlanTrabajo plan;

  @override
  State<_HojaNotaClase> createState() => _HojaNotaClaseState();
}

class _HojaNotaClaseState extends State<_HojaNotaClase> {
  DesempenoClase _desempeno = DesempenoClase.bien;
  int _sesion = 0; // 0 = clase suelta
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(999)),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Clase de hoy',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 14),
            const Text('¿Cómo le fue?',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
            const SizedBox(height: 8),
            Row(
              children: [
                for (final d in DesempenoClase.values) ...[
                  Expanded(child: _chipDesempeno(d)),
                  if (d != DesempenoClase.values.last)
                    const SizedBox(width: 8),
                ],
              ],
            ),
            const SizedBox(height: 16),
            const Text('Clase del plan (opcional)',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(
              value: _sesion,
              isExpanded: true,
              decoration: InputDecoration(
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12)),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              ),
              items: [
                const DropdownMenuItem(value: 0, child: Text('Clase suelta')),
                for (final s in widget.plan.sesiones)
                  DropdownMenuItem(
                    value: s.numero,
                    child: Text('Clase ${s.numero}: ${s.titulo}',
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (v) => setState(() => _sesion = v ?? 0),
            ),
            const SizedBox(height: 16),
            const Text('Observación',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
            const SizedBox(height: 8),
            TextField(
              controller: _ctrl,
              minLines: 2,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(
                hintText: 'Ej.: buena derecha, mejorar el saque…',
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: bosque,
                  minimumSize: const Size.fromHeight(48),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                onPressed: () => Navigator.of(context).pop(
                    _ResultadoNota(_sesion, _desempeno, _ctrl.text)),
                child: const Text('Guardar clase',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _chipDesempeno(DesempenoClase d) {
    final sel = _desempeno == d;
    final color = EvaluarAlumnoScreen.colorDesempeno(d);
    return InkWell(
      onTap: () => setState(() => _desempeno = d),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: sel ? color.withOpacity(0.16) : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: sel ? color : Colors.black.withOpacity(0.18),
              width: sel ? 1.6 : 1),
        ),
        child: Text(
          d.etiqueta,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: sel ? FontWeight.w800 : FontWeight.w600,
            color: sel ? color : Colors.black.withOpacity(0.6),
          ),
        ),
      ),
    );
  }
}
