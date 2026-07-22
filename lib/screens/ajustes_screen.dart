import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';

/// Ajustes de la app. Por ahora: selector de tema (Claro / Oscuro / Automático).
/// Theme-aware a propósito (usa el ColorScheme) para verse bien en ambos modos.
class AjustesScreen extends StatelessWidget {
  const AjustesScreen({super.key});

  static const _entorno =
      String.fromEnvironment('ENTORNO', defaultValue: 'dev');
  static bool get _modoPruebas => _entorno != 'prod';

  Future<void> _empezarDeCero(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('¿Empezar de cero?'),
        content: const Text(
            'Borra TODO en este dispositivo (academias, alumnos, reservas, '
            'saldo, sesión) y también tus academias/matrículas en la nube. '
            'No se puede deshacer. Ideal para una prueba limpia.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Sí, borrar todo')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await appState.borrarTodoParaPruebas();
    if (!context.mounted) return;
    // Vuelve al inicio: la app queda como recién instalada.
    Navigator.of(context).popUntil((r) => r.isFirst);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Listo: app en blanco. Inicia sesión para probar.')));
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Ajustes')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 30),
            children: [
              Text('Apariencia',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text('Elige cómo se ve Pichangol. Por defecto es claro.',
                  style: t.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurface
                          .withOpacity(0.6))),
              const SizedBox(height: 16),
              _OpcionTema(
                icon: Icons.light_mode_outlined,
                titulo: 'Claro',
                subtitulo: 'Fondos claros, ideal de día',
                seleccionado: appState.temaModo == ThemeMode.light,
                onTap: () => appState.setTemaModo(ThemeMode.light),
              ),
              _OpcionTema(
                icon: Icons.dark_mode_outlined,
                titulo: 'Oscuro',
                subtitulo: 'Verde bosque, descansa la vista de noche',
                seleccionado: appState.temaModo == ThemeMode.dark,
                onTap: () => appState.setTemaModo(ThemeMode.dark),
              ),
              if (_modoPruebas) ...[
                const SizedBox(height: 28),
                Text('Zona de pruebas',
                    style:
                        t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(
                    'Solo en builds de prueba ($_entorno). Deja la app como '
                    'recién instalada para probar desde cero.',
                    style: t.bodySmall?.copyWith(
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withOpacity(0.6))),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: clayOscuro,
                    side: const BorderSide(color: clayOscuro),
                    minimumSize: const Size.fromHeight(50),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.restart_alt),
                  label: const Text('Empezar de cero (borrar todo)',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onPressed: () => _empezarDeCero(context),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _OpcionTema extends StatelessWidget {
  const _OpcionTema({
    required this.icon,
    required this.titulo,
    required this.subtitulo,
    required this.seleccionado,
    required this.onTap,
  });
  final IconData icon;
  final String titulo;
  final String subtitulo;
  final bool seleccionado;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: seleccionado ? lima : cs.outlineVariant.withOpacity(0.4),
            width: seleccionado ? 2 : 1),
      ),
      child: ListTile(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        leading: CircleAvatar(
          radius: 20,
          backgroundColor: lima.withOpacity(0.18),
          child: Icon(icon, color: seleccionado ? cs.primary : cs.onSurface),
        ),
        title: Text(titulo,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitulo,
            style: t.bodySmall
                ?.copyWith(color: cs.onSurface.withOpacity(0.6))),
        trailing: seleccionado
            ? Icon(Icons.check_circle, color: cs.primary)
            : Icon(Icons.circle_outlined,
                color: cs.onSurface.withOpacity(0.25)),
        onTap: onTap,
      ),
    );
  }
}
