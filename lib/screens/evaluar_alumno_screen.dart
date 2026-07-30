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
