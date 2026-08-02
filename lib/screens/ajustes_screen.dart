import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../brand.dart';
import '../services/whatsapp_link.dart';
import '../services/llamada_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'editar_perfil_screen.dart';
import 'privacidad_screen.dart';
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

  /// Diagnóstico de la llamada entrante a pantalla completa (sin necesitar otro
  /// teléfono ni el push): muestra si el permiso está activo, deja concederlo, y
  /// simula una llamada entrante LOCAL para ver si aparece la pantalla completa.
  Future<void> _diagnosticoLlamada(BuildContext context) async {
    final puede = await LlamadaService.puedePantallaCompleta();
    if (!context.mounted) return;
    final ok = await confirmarPichangol(
      context,
      titulo: 'Probar llamada entrante',
      mensaje: 'Pantalla completa permitida en este equipo: '
          '${puede ? 'SÍ ✓' : 'NO ✗'}.\n\n'
          '${puede ? 'Toca "Simular", BLOQUEA la pantalla y espera 6 s: debe '
              'aparecer la llamada entrante a pantalla completa (con Contestar/'
              'Rechazar).' : 'Primero toca "Activar permiso" y concédelo en los '
              'ajustes que se abren; luego vuelve y repite.'}',
      textoConfirmar: puede ? 'Simular en 6 s' : 'Activar permiso',
      textoCancelar: 'Cerrar',
      icono: Icons.phone_in_talk,
    );
    if (!ok) return;
    if (!puede) {
      await LlamadaService.abrirAjustesPantallaCompleta();
      return;
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Bloquea la pantalla ahora — sonará en 6 segundos…')));
    }
    await LlamadaService.simularEntrante(delaySeg: 6);
  }

  /// Muestra el registro interno de eventos de llamada (para diagnóstico).
  Future<void> _verRegistroLlamadas(BuildContext context) async {
    final lineas = await LlamadaService.leerRegistro();
    if (!context.mounted) return;
    await avisarPichangol(
      context,
      titulo: 'Registro de llamadas',
      mensaje: lineas.isEmpty
          ? 'Aún no hay eventos. Haz una llamada (o "Simular"), acepta, y vuelve '
              'a abrir esto.'
          : lineas.reversed.take(25).join('\n'),
      icono: Icons.receipt_long,
    );
    await LlamadaService.limpiarRegistro();
  }

  Future<void> _empezarDeCero(BuildContext context) async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Empezar de cero?',
      mensaje: 'Borra TODO en este dispositivo (academias, alumnos, reservas, '
          'saldo, sesión) y también tus academias/matrículas en la nube. '
          'No se puede deshacer. Ideal para una prueba limpia.',
      textoConfirmar: 'Sí, borrar todo',
      destructivo: true,
      icono: Icons.delete_forever_outlined,
    );
    if (!ok || !context.mounted) return;
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
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Dejar en virgen?',
      mensaje: 'Borra TODO lo tuyo: academias, alumnos, matrículas, reservas, '
          'cobros, cuotas, saldo, movimientos, chats, reseñas y campeonatos. '
          'También quita TUS canchas reclamadas (y borra su reclamo en la torre '
          'de control), para que puedas reclamarlas de cero.\n\n'
          'Solo MANTIENE tu sesión iniciada (no cierra sesión). No se puede '
          'deshacer.\n\n'
          'Ojo: el saldo/pagos del servidor se limpian aparte desde la torre '
          'de control (botón "Dejar el servidor en virgen").',
      textoConfirmar: 'Sí, dejar en virgen',
      destructivo: true,
      icono: Icons.cleaning_services_outlined,
    );
    if (!ok || !context.mounted) return;
    await appState.resetVirgen();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Listo: todo en blanco (academias, alumnos, reservas y '
            'canchas). Sigues con tu sesión iniciada.')));
  }

  /// Depurar academias: lista TODAS (con su dueño) y deja borrar cualquiera,
  /// aunque no sea tuya. Sirve para limpiar academias basura (ej. las creadas
  /// con la cuenta demo). El borrado es durable (también en la nube).
  Future<void> _depurarAcademias(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (dctx) => DialogoPichangol(
        titulo: 'Depurar academias',
        icono: Icons.cleaning_services_outlined,
        contenido: SizedBox(
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
                          final ok = await confirmarPichangol(
                            dctx,
                            titulo: '¿Borrar esta academia?',
                            mensaje: '"${a.nombre}". Se borra también en la nube '
                                'y no reaparece. No se puede deshacer.',
                            textoConfirmar: 'Borrar',
                            destructivo: true,
                            icono: Icons.delete_outline,
                          );
                          if (ok) appState.eliminarAcademia(a.id);
                        },
                      ),
                    ),
                ],
              );
            },
          ),
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(dctx),
              style: TextButton.styleFrom(foregroundColor: textoTenue),
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
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 18, 600), 12, ladoTablet(context, 18, 600), 30),
            children: [
              Text('Tu cuenta',
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              if (u != null)
                _AccionTile(
                  icon: Icons.badge_outlined,
                  color: teal,
                  title: 'Mi nombre y foto',
                  subtitle: 'Edita cómo te ven en el chat, ranking y retos',
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const EditarPerfilScreen())),
                ),
              if (u != null)
                _AccionTile(
                  icon: appState.jugadorVerificado
                      ? Icons.verified
                      : Icons.verified_user_outlined,
                  color: lima,
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
                color: amarillo,
                title: 'Invita y gana 🎁',
                subtitle: 'Comparte tu código; tú y tu amigo ganan un bono',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const ReferidosScreen())),
              ),
              _AccionTile(
                icon: Icons.lock_outline,
                color: bosque,
                title: 'Privacidad',
                subtitle: 'Última vez, en línea y confirmaciones de lectura',
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const PrivacidadScreen())),
              ),
              _AccionTile(
                icon: Icons.ios_share,
                color: morado,
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
                  label: const Text('Dejar en virgen (borra todo, mantiene sesión)',
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
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: teal,
                    side: const BorderSide(color: teal),
                    minimumSize: const Size.fromHeight(50),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.phone_in_talk),
                  label: const Text('Probar llamada entrante (pantalla completa)',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onPressed: () => _diagnosticoLlamada(context),
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(50),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.receipt_long),
                  label: const Text('Ver registro de llamadas',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onPressed: () => _verRegistroLlamadas(context),
                ),
              ],
              const SizedBox(height: 28),
              const _VersionApp(),
            ],
          );
        },
      ),
    );
  }
}

/// Pie de "Ajustes": versión y `build` (versionCode de Android) para que el
/// usuario diga qué versión tiene instalada. Toca para COPIAR. OJO: el
/// versionCode NO es el número del APK (`pichangol-N.apk`): Android le antepone
/// un dígito por arquitectura (arm64 → 2xxx), así que no se construye el nombre
/// del archivo con él. Para comparar dos equipos, basta que el build coincida.
class _VersionApp extends StatelessWidget {
  const _VersionApp();

  @override
  Widget build(BuildContext context) {
    final tenue = Theme.of(context).colorScheme.onSurface.withOpacity(0.55);
    return FutureBuilder<PackageInfo>(
      future: PackageInfo.fromPlatform(),
      builder: (context, snap) {
        final info = snap.data;
        final version = info?.version ?? '—';
        final build = info?.buildNumber ?? '—';
        final texto = '$kBrandName · versión $version (build $build)';
        return Center(
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: () async {
              await Clipboard.setData(ClipboardData(text: texto));
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                  content: Text('Versión copiada'),
                  duration: Duration(seconds: 2)));
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
              child: Column(
                children: [
                  Text(texto,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: tenue,
                          fontSize: 12.5,
                          fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  const Text('Toca para copiar',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: textoTenue, fontSize: 11)),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Tile de acción de cuenta (verificar, invitar, compartir) — estilo Airbnb.
class _AccionTile extends StatelessWidget {
  const _AccionTile(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap,
      this.color = lima});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color color;

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
          backgroundColor: color,
          child: Icon(icon, color: Colors.white, size: 20),
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
