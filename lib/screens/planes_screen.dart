import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/plan_trabajo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/dialogo_pichangol.dart';
import 'plan_detalle_screen.dart';

/// Planes de TRABAJO del profe: la malla de clases por deporte + evaluación de
/// alumnos. Usa la plantilla de Pichangol (editable) o crea/duplica la suya.
class PlanesScreen extends StatelessWidget {
  const PlanesScreen({super.key, required this.academia});
  final Academia academia;

  void _abrir(BuildContext context, String planId) {
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => PlanDetalleScreen(planId: planId)));
  }

  Future<void> _usarPlantilla(BuildContext context, PlanTrabajo plantilla) async {
    final id = appState.clonarPlan(plantilla);
    if (context.mounted) _abrir(context, id);
  }

  void _crearVacio(BuildContext context) {
    final id = appState.crearPlanVacio(academia.id, academia.deporte.name,
        nombre: 'Mi plan de trabajo');
    _abrir(context, id);
  }

  Future<void> _eliminar(BuildContext context, PlanTrabajo p) async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Eliminar el plan?',
      mensaje: 'Se elimina "${p.nombre}" y sus evaluaciones. No se puede '
          'deshacer.',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (ok) appState.eliminarPlan(p.id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plan de trabajo')),
      body: AnchoLectura(
        child: ListenableBuilder(
          listenable: appState,
          builder: (context, _) {
            final mios = appState.planesDe(academia.id);
            final plantilla = appState.plantillaDe(academia);
            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
              children: [
                Text(
                  'Arma tu programa de clases y evalúa a tus alumnos habilidad '
                  'por habilidad.',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13.5),
                ),
                const SizedBox(height: 14),

                // Mis planes guardados.
                if (mios.isNotEmpty) ...[
                  const _Titulo('Mis planes'),
                  for (final p in mios) _CardPlan(
                    plan: p,
                    onTap: () => _abrir(context, p.id),
                    onDuplicar: () {
                      final id = appState.clonarPlan(p, nombre: '${p.nombre} (copia)');
                      _abrir(context, id);
                    },
                    onEliminar: () => _eliminar(context, p),
                  ),
                  const SizedBox(height: 8),
                ],

                // Plantilla Pichangol (si hay para el deporte).
                if (plantilla != null) ...[
                  const _Titulo('Plantilla Pichangol'),
                  _CardPlantilla(
                    plan: plantilla,
                    onUsar: () => _usarPlantilla(context, plantilla),
                  ),
                ] else ...[
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: limaSuave.withOpacity(0.5),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      'Aún no tenemos plantilla para este deporte. Puedes crear tu '
                      'plan desde cero.',
                      style: TextStyle(color: textoTenueDe(context), fontSize: 13),
                    ),
                  ),
                ],
                const SizedBox(height: 16),

                OutlinedButton.icon(
                  onPressed: () => _crearVacio(context),
                  icon: const Icon(Icons.add),
                  label: const Text('Crear plan desde cero'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: bosque,
                    side: const BorderSide(color: lima),
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _Titulo extends StatelessWidget {
  const _Titulo(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 6, bottom: 8),
        child: Text(texto,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
      );
}

class _CardPlan extends StatelessWidget {
  const _CardPlan({
    required this.plan,
    required this.onTap,
    required this.onDuplicar,
    required this.onEliminar,
  });
  final PlanTrabajo plan;
  final VoidCallback onTap;
  final VoidCallback onDuplicar;
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
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
        onTap: onTap,
        leading: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
              color: limaSuave, borderRadius: BorderRadius.circular(12)),
          child: const Icon(Icons.assignment_outlined, color: bosque),
        ),
        title: Text(plan.nombre,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800)),
        subtitle: Text(
          '${plan.nivel.isEmpty ? '' : '${plan.nivel} · '}'
          '${plan.totalClases} clases · ${plan.habilidades.length} habilidades',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(color: textoTenueDe(context), fontSize: 12.5),
        ),
        trailing: PopupMenuButton<String>(
          onSelected: (v) {
            if (v == 'dup') onDuplicar();
            if (v == 'del') onEliminar();
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'dup', child: Text('Duplicar')),
            PopupMenuItem(value: 'del', child: Text('Eliminar')),
          ],
        ),
      ),
    );
  }
}

class _CardPlantilla extends StatelessWidget {
  const _CardPlantilla({required this.plan, required this.onUsar});
  final PlanTrabajo plan;
  final VoidCallback onUsar;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [lima, teal],
        ),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(plan.nombre,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        fontSize: 16)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${plan.totalClases} clases progresivas · '
            '${plan.habilidades.length} habilidades para evaluar',
            style: TextStyle(color: Colors.white.withOpacity(0.92), fontSize: 13),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: Colors.white, foregroundColor: bosque),
              onPressed: onUsar,
              icon: const Icon(Icons.playlist_add_check),
              label: const Text('Usar esta plantilla'),
            ),
          ),
        ],
      ),
    );
  }
}
