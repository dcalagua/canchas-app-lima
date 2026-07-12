import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'agregar_cancha_screen.dart';
import 'editar_cancha_screen.dart';
import 'registrar_cancha_screen.dart';

/// Canchas del dueño agrupadas por LOCAL (un local = varias canchas, posibles
/// de distintos deportes). Cada local permite agregar más canchas y editar las
/// existentes (precio, deporte, horario, fotos).
class MisCanchasScreen extends StatefulWidget {
  const MisCanchasScreen({super.key});

  @override
  State<MisCanchasScreen> createState() => _MisCanchasScreenState();
}

class _MisCanchasScreenState extends State<MisCanchasScreen> {
  @override
  void initState() {
    super.initState();
    // Al abrir, pregunta al backend si el admin ya aprobó alguna cancha pendiente
    // (quita el cartel "pendiente" y habilita reservas si así fue).
    appState.sincronizarPropiedades();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: pino,
        foregroundColor: lima,
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const RegistrarCanchaScreen()),
        ),
        icon: const Icon(Icons.add_location_alt),
        label: const Text('Nuevo local'),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final hayPendientes = canchas.any((c) => c.pendienteVerificacion);
          final locales = Club.agrupar(canchas);
          return Column(
            children: [
              _HeaderMisCanchas(
                  nLocales: locales.length, nCanchas: canchas.length),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () => appState.sincronizarPropiedades(),
                  child: canchas.isEmpty
                      ? ListView(
                          children: const [SizedBox(height: 60), _Vacio()])
                      : ListView(
                          padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                          children: [
                            if (hayPendientes) ...[
                              const _AvisoPendiente(),
                              const SizedBox(height: 14),
                            ],
                            for (final local in locales) ...[
                              _LocalCard(local: local),
                              const SizedBox(height: 14),
                            ],
                          ],
                        ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Header premium (degradado sage) del panel "Mis canchas", igual que la Agenda.
class _HeaderMisCanchas extends StatelessWidget {
  const _HeaderMisCanchas({required this.nLocales, required this.nCanchas});
  final int nLocales;
  final int nCanchas;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 18 + MediaQuery.of(context).padding.top, 22, 20),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [sage, verde, bosque],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Mis canchas',
              style: t.headlineSmall
                  ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(
            nCanchas == 0
                ? 'Registra o reclama tu primer local'
                : '$nLocales ${nLocales == 1 ? 'local' : 'locales'} · '
                    '$nCanchas ${nCanchas == 1 ? 'cancha' : 'canchas'}',
            style: t.bodyMedium?.copyWith(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

/// Aviso para el dueño cuando tiene canchas en revisión.
class _AvisoPendiente extends StatelessWidget {
  const _AvisoPendiente();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFBF3E2),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFF0DDB8)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('⏳', style: TextStyle(fontSize: 18)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Tienes canchas en revisión',
                    style: t.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w800, color: clayOscuro)),
                const SizedBox(height: 3),
                Text(
                  'Ya puedes editar precio, deporte, horario y fotos tocando la '
                  'cancha. Cuando el equipo apruebe la propiedad se habilitan las '
                  'reservas. Desliza hacia abajo para actualizar el estado.',
                  style:
                      t.bodySmall?.copyWith(color: textoTenue, height: 1.35),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tarjeta de un LOCAL: cabecera + sus canchas (editar al tocar) + botón para
/// agregar otra cancha al mismo local.
class _LocalCard extends StatelessWidget {
  const _LocalCard({required this.local});
  final Club local;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final n = local.canchas.length;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.storefront, color: pino, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(local.nombre,
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
              ),
              Text('$n ${n == 1 ? 'cancha' : 'canchas'}',
                  style: t.bodySmall?.copyWith(color: textoTenue)),
            ],
          ),
          if (local.direccion != null) ...[
            const SizedBox(height: 3),
            Text(local.direccion!,
                style: t.bodySmall?.copyWith(color: textoTenue),
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 8),
          for (final c in local.canchas) _FilaCancha(cancha: c),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => AgregarCanchaScreen(local: local.principal)),
              ),
              icon: const Icon(Icons.add, color: pino, size: 20),
              label: const Text('Agregar cancha',
                  style:
                      TextStyle(color: pino, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }
}

/// Una cancha dentro del local: punto del deporte, nombre, deporte/precio/horario
/// y acceso a editar. Marca "⏳" si está pendiente de verificación.
class _FilaCancha extends StatelessWidget {
  const _FilaCancha({required this.cancha});
  final Cancha cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => EditarCanchaScreen(cancha: cancha)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                  color: colorDeporte(cancha.deporte),
                  borderRadius: BorderRadius.circular(3)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(cancha.nombre,
                      style:
                          t.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  Text(
                    '${cancha.deporte.etiqueta} · S/ ${cancha.precioHora.toStringAsFixed(2)}/h · '
                    '${cancha.horaApertura}–${cancha.horaCierre}',
                    style: t.bodySmall?.copyWith(color: textoTenue),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (cancha.pendienteVerificacion)
              Container(
                margin: const EdgeInsets.only(right: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                    color: const Color(0xFFFBEAD2),
                    borderRadius: BorderRadius.circular(999)),
                child: const Text('⏳ Por verificar',
                    style: TextStyle(
                        color: clayOscuro,
                        fontSize: 10,
                        fontWeight: FontWeight.w700)),
              ),
            const Icon(Icons.chevron_right, color: textoTenue),
          ],
        ),
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.add_location_alt, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            Text('Aún no registras canchas',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'Registra tu local para que aparezca en el mapa; luego puedes '
              'agregarle todas las canchas que tengas.',
              textAlign: TextAlign.center,
              style: t.bodyMedium?.copyWith(color: textoTenue),
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: pino, foregroundColor: lima),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => const RegistrarCanchaScreen()),
              ),
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Registrar mi local'),
            ),
          ],
        ),
      ),
    );
  }
}
