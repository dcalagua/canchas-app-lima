import 'package:flutter/material.dart';

import '../brand.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'referidos_screen.dart';
import 'verificar_identidad_screen.dart';

/// Ajustes de la app. Por ahora: selector de tema (Claro / Oscuro / Automático).
/// Theme-aware a propósito (usa el ColorScheme) para verse bien en ambos modos.
class AjustesScreen extends StatelessWidget {
  const AjustesScreen({super.key});

  static const _entorno =
      String.fromEnvironment('ENTORNO', defaultValue: 'dev');
  // Herramientas de limpieza para el PILOTO: visibles en todos los builds
  // (incluido prod, que es el que usa Google real) salvo que se pida ocultarlas
  // con --dart-define=OCULTAR_PRUEBAS=1 para el lanzamiento en Play Store.
  static const _ocultarPruebas =
      String.fromEnvironment('OCULTAR_PRUEBAS', defaultValue: '0');
  static bool get _mostrarHerramientasPrueba => _ocultarPruebas != '1';

  static const _kReleaseUrl =
      'https://github.com/dcalagua/canchas-app-lima/releases/tag/v0.1.0';

  /// Comparte la app (link de descarga) por WhatsApp — el canal que más usa la
  /// gente en Perú.
  Future<void> _compartirApp(BuildContext context) async {
    final msg =
        '¡Descárgate $kBrandName! 🎾⚽ Reserva canchas de fútbol, tenis y '
        'más cerca de ti, y únete a academias y campeonatos.\n\n'
        'Bájala aquí: $_kReleaseUrl';
    final ok = await WhatsAppLink.compartir(msg);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No pude abrir WhatsApp para compartir.')));
    }
  }

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

  /// "Dejar en virgen": borra alumnos, reservas y todo lo transaccional pero
  /// CONSERVA las canchas reclamadas y las academias creadas (y la sesión).
  Future<void> _dejarEnVirgen(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('¿Dejar en virgen?'),
        content: const Text(
            'Borra alumnos, reservas, cobros, cuotas, saldo, movimientos, '
            'chats, reseñas y campeonatos — como si nunca hubiera pasado nada.\n\n'
            'CONSERVA tus canchas reclamadas y tus academias creadas (y tu '
            'sesión). No se puede deshacer.\n\n'
            'Ojo: el saldo/pagos del servidor se limpian aparte desde la torre '
            'de control (botón "Dejar el servidor en virgen").'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: clayOscuro),
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Sí, dejar en virgen')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await appState.resetVirgen();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Listo: sin alumnos ni reservas. Tus canchas y '
            'academias se conservan.')));
  }

  /// Depurar academias: lista TODAS (con su dueño) y deja borrar cualquiera,
  /// aunque no sea tuya. Sirve para limpiar academias basura (ej. las creadas
  /// con la cuenta demo). El borrado es durable (también en la nube).
  Future<void> _depurarAcademias(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Depurar academias'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListenableBuilder(
            listenable: appState,
            builder: (_, __) {
              final acs = appState.academias;
              if (acs.isEmpty) {
                return const Text('No hay academias.');
              }
              return ListView(
                shrinkWrap: true,
                children: [
                  for (final a in acs)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(a.nombre,
                          style:
                              const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text('Dueño: ${a.dueno.isEmpty ? '—' : a.dueno}',
                          style: const TextStyle(fontSize: 12)),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline,
                            color: clayOscuro),
                        onPressed: () async {
                          final ok = await showDialog<bool>(
                            context: dctx,
                            builder: (_) => AlertDialog(
                              title: const Text('¿Borrar esta academia?'),
                              content: Text(
                                  '"${a.nombre}". Se borra también en la nube '
                                  'y no reaparece. No se puede deshacer.'),
                              actions: [
                                TextButton(
                                    onPressed: () =>
                                        Navigator.pop(dctx, false),
                                    child: const Text('Cancelar')),
                                FilledButton(
                                    style: FilledButton.styleFrom(
                                        backgroundColor: clayOscuro),
                                    onPressed: () =>
                                        Navigator.pop(dctx, true),
                                    child: const Text('Borrar')),
                              ],
                            ),
                          );
                          if (ok == true) appState.eliminarAcademia(a.id);
                        },
                      ),
                    ),
                ],
              );
            },
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx),
              child: const Text('Cerrar')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Ajustes')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final u = appState.usuario;
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 30),
            children: [
              Text('Tu cuenta',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              if (u != null)
                _AccionTile(
                  icon: appState.jugadorVerificado
                      ? Icons.verified
                      : Icons.verified_user_outlined,
                  title: appState.jugadorVerificado
                      ? 'Identidad verificada ✓'
                      : 'Verifica tu identidad',
                  subtitle: appState.jugadorVerificado
                      ? 'Tu perfil muestra la insignia de jugador verificado'
                      : 'Da confianza a los dueños y reserva sin fricción',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const VerificarIdentidadScreen())),
                ),
              _AccionTile(
                icon: Icons.card_giftcard,
                title: 'Invita y gana 🎁',
                subtitle: 'Comparte tu código; tú y tu amigo ganan un bono',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const ReferidosScreen())),
              ),
              _AccionTile(
                icon: Icons.ios_share,
                title: 'Comparte Pichangol',
                subtitle: 'Invita a tus amigos a reservar y jugar',
                onTap: () => _compartirApp(context),
              ),
              const SizedBox(height: 28),
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
              if (_mostrarHerramientasPrueba) ...[
                const SizedBox(height: 28),
                Text('Zona de pruebas',
                    style:
                        t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(
                    'Herramientas del piloto (entorno: $_entorno). Deja la app '
                    'como recién instalada o limpia academias sueltas.',
                    style: t.bodySmall?.copyWith(
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withOpacity(0.6))),
                const SizedBox(height: 12),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    minimumSize: const Size.fromHeight(50),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.auto_awesome),
                  label: const Text('Dejar en virgen (conservar canchas y academias)',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onPressed: () => _dejarEnVirgen(context),
                ),
                const SizedBox(height: 10),
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
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(50),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.cleaning_services_outlined),
                  label: const Text('Depurar academias (borrar sueltas)',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onPressed: () => _depurarAcademias(context),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

/// Tile de acción de cuenta (verificar, invitar, compartir) — estilo Airbnb.
class _AccionTile extends StatelessWidget {
  const _AccionTile(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x0F000000), blurRadius: 8, offset: Offset(0, 3)),
        ],
      ),
      child: ListTile(
        leading: CircleAvatar(
          radius: 20,
          backgroundColor: limaSuave,
          child: Icon(icon, color: bosque, size: 20),
        ),
        title: Text(title,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle,
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: onTap,
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
