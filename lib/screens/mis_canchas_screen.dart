import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';
import 'editar_cancha_screen.dart';
import 'registrar_cancha_screen.dart';
import 'verificar_propiedad_screen.dart';

/// Canchas del dueño (locales de este dispositivo + las suyas en la nube,
/// recuperadas por su correo tras reinstalar), con acceso a editarlas/eliminarlas.
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
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Mis canchas')),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: pino,
        foregroundColor: lima,
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const RegistrarCanchaScreen()),
        ),
        icon: const Icon(Icons.add_location_alt),
        label: const Text('Registrar otra'),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final hayPendientes = canchas.any((c) => c.pendienteVerificacion);
          return RefreshIndicator(
            onRefresh: () => appState.sincronizarPropiedades(),
            child: canchas.isEmpty
                ? ListView(
                    children: const [SizedBox(height: 120), _Vacio()])
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                    itemCount: canchas.length + (hayPendientes ? 1 : 0),
                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                    itemBuilder: (_, i) {
                      if (hayPendientes && i == 0) {
                        return const _AvisoPendiente();
                      }
                      final cancha =
                          canchas[i - (hayPendientes ? 1 : 0)];
                      return _CanchaItem(cancha: cancha);
                    },
                  ),
          );
        },
      ),
    );
  }
}

/// Aviso para el dueño cuando tiene canchas en revisión: explica el siguiente
/// paso y que puede deslizar para actualizar el estado tras la aprobación.
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
                  'Ya puedes editar precio, deporte y fotos tocando la cancha. '
                  'Cuando el equipo apruebe la propiedad se habilitan las reservas. '
                  'Desliza hacia abajo para actualizar el estado.',
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

class _CanchaItem extends StatelessWidget {
  const _CanchaItem({required this.cancha});
  final Cancha cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => EditarCanchaScreen(cancha: cancha)),
        ),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: trazo),
          ),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: SizedBox(
                  width: 64,
                  height: 64,
                  child: cancha.fotoUrl != null
                      ? Image.network(cancha.fotoUrl!, fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => _gradiente())
                      : _gradiente(),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cancha.nombre,
                        style: t.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w700),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                    const SizedBox(height: 2),
                    Text(
                      cancha.direccion ??
                          '${cancha.deporte.etiqueta} · ${cancha.distrito.etiqueta}',
                      style: t.bodySmall?.copyWith(color: textoTenue),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                              color: colorDeporte(cancha.deporte),
                              borderRadius: BorderRadius.circular(999)),
                          child: Text(cancha.deporte.etiqueta,
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700)),
                        ),
                        const SizedBox(width: 8),
                        Text('S/ ${cancha.precioHora.toStringAsFixed(2)} /h',
                            style: t.bodySmall?.copyWith(
                                color: tinta, fontWeight: FontWeight.w700)),
                        if (cancha.pendienteVerificacion) ...[
                          const SizedBox(width: 8),
                          if (PropiedadService.disponible)
                            InkWell(
                              borderRadius: BorderRadius.circular(999),
                              onTap: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                    builder: (_) => VerificarPropiedadScreen(
                                        cancha: cancha)),
                              ),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 9, vertical: 3),
                                decoration: BoxDecoration(
                                    color: bosque,
                                    borderRadius: BorderRadius.circular(999)),
                                child: const Text('Verificar propiedad',
                                    style: TextStyle(
                                        color: lima,
                                        fontSize: 10,
                                        fontWeight: FontWeight.w800)),
                              ),
                            )
                          else
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 7, vertical: 2),
                              decoration: BoxDecoration(
                                  color: const Color(0xFFFBEAD2),
                                  borderRadius: BorderRadius.circular(999)),
                              child: const Text('⏳ Por verificar',
                                  style: TextStyle(
                                      color: clayOscuro,
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700)),
                            ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              const Icon(Icons.edit, color: pino, size: 20),
            ],
          ),
        ),
      ),
    );
  }

  Widget _gradiente() {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
            decoration: BoxDecoration(gradient: gradienteDeporte(cancha.deporte))),
        const CourtLines(opacity: 0.5),
        Center(
            child: Icon(iconoDeporte(cancha.deporte),
                color: Colors.white, size: 24)),
      ],
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
              'Registra tu cancha para que aparezca en el mapa y puedas editarla '
              'cuando quieras.',
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
              label: const Text('Registrar mi cancha'),
            ),
          ],
        ),
      ),
    );
  }
}
