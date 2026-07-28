import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart' show AnchoTablet;
import 'estado_composer_screen.dart';
import 'estado_viewer_screen.dart';
import 'login_google_sheet.dart';

/// NOVEDADES (tipo WhatsApp "Novedades/Estados"): pantalla dedicada donde el
/// usuario sube su historia (24 h) y ve las de sus conocidos. "Mi estado" arriba
/// + "Actualizaciones recientes" abajo. Vive como sección contextual de Mensajes.
class NovedadesScreen extends StatefulWidget {
  const NovedadesScreen({super.key});

  @override
  State<NovedadesScreen> createState() => _NovedadesScreenState();
}

class _NovedadesScreenState extends State<NovedadesScreen> {
  @override
  void initState() {
    super.initState();
    appState.cargarEstados(); // refresca al entrar (best-effort)
  }

  String _hace(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'ahora';
    if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
    if (d.inHours < 24) return 'hace ${d.inHours} h';
    return 'hace ${d.inDays} d';
  }

  Future<void> _agregar() async {
    final r = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 8, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Añadir a mi estado',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.text_fields, color: teal)),
              title: const Text('Escribir'),
              onTap: () => Navigator.pop(context, 'texto'),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.photo_library_outlined, color: teal)),
              title: const Text('Galería'),
              onTap: () => Navigator.pop(context, 'galeria'),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.photo_camera_outlined, color: teal)),
              title: const Text('Cámara'),
              onTap: () => Navigator.pop(context, 'camara'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (r == null || !mounted) return;
    if (r == 'texto') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const EstadoComposerScreen(),
          fullscreenDialog: true));
      if (mounted) setState(() {});
      return;
    }
    final XFile? f = await ImagePicker().pickImage(
        source: r == 'camara' ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1600,
        imageQuality: 82);
    if (f == null || !mounted) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoFotoComposerScreen(bytes: bytes),
        fullscreenDialog: true));
    if (mounted) setState(() {});
  }

  Future<void> _verDe(String email) async {
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoViewerScreen(autorEmail: email)));
    if (mounted) setState(() {});
  }

  Future<void> _tocarMiEstado() async {
    if (appState.misEstados.isEmpty) {
      await _agregar();
      return;
    }
    await _verDe(appState.usuario?.email ?? '');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Novedades',
            style: TextStyle(fontWeight: FontWeight.w800)),
        centerTitle: false,
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (!appState.logueado) {
            return _Aviso(
              texto: 'Inicia sesión para ver y publicar novedades.',
              accion: FilledButton.icon(
                style: FilledButton.styleFrom(backgroundColor: lima),
                onPressed: () async {
                  if (await LoginGoogleSheet.mostrar(context,
                      motivo: 'ver novedades')) {
                    setState(() {});
                  }
                },
                icon: const Icon(Icons.login),
                label: const Text('Iniciar sesión'),
              ),
            );
          }
          final autores = appState.autoresConEstado();
          final misEstados = appState.misEstados;
          final tengo = misEstados.isNotEmpty;
          return AnchoTablet(
            child: RefreshIndicator(
              onRefresh: () => appState.cargarEstados(),
              child: ListView(
                children: [
                  const SizedBox(height: 6),
                  // "Mi estado"
                  ListTile(
                    onTap: _tocarMiEstado,
                    leading: _AnilloAvatar(
                      email: appState.usuario?.email ?? '',
                      fotoUrl: appState.usuario?.fotoUrl,
                      nombre: appState.usuario?.nombre ?? '',
                      aro: tengo
                          ? (appState.autorTieneNoVisto(
                                  appState.usuario?.email)
                              ? 1
                              : 2)
                          : 0,
                      mostrarMas: true,
                    ),
                    title: const Text('Mi estado',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(tengo
                        ? _hace(misEstados.last.creadoEn)
                        : 'Toca para añadir una novedad'),
                    trailing: tengo
                        ? IconButton(
                            icon: const Icon(Icons.add_circle_outline,
                                color: teal),
                            onPressed: _agregar,
                          )
                        : null,
                  ),
                  Divider(height: 8, thickness: 8, color: trazo.withOpacity(0.25)),
                  if (autores.isNotEmpty) ...[
                    const Padding(
                      padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
                      child: Text('Actualizaciones recientes',
                          style: TextStyle(
                              color: textoTenue,
                              fontWeight: FontWeight.w700,
                              fontSize: 13)),
                    ),
                    for (final e in autores)
                      ListTile(
                        onTap: () => _verDe(e),
                        leading: _AnilloAvatar(
                          email: e,
                          fotoUrl: appState.fotoDe(e),
                          nombre: appState.nombreMostrableDe(e) ?? e,
                          aro: appState.autorTieneNoVisto(e) ? 1 : 2,
                        ),
                        title: Text(
                            appState.nombreMostrableDe(e) ?? e.split('@').first,
                            style:
                                const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text(_hace(appState.estadosDe(e).last.creadoEn)),
                      ),
                  ] else
                    const Padding(
                      padding: EdgeInsets.fromLTRB(24, 40, 24, 24),
                      child: Text(
                        'Aún no hay novedades de tus contactos. Cuando alguien '
                        'que conoces publique una historia, aparecerá aquí.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: textoTenue),
                      ),
                    ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          );
        },
      ),
      floatingActionButton: appState.logueado
          ? FloatingActionButton(
              backgroundColor: lima,
              onPressed: _agregar,
              child: const Icon(Icons.camera_alt, color: Colors.white),
            )
          : null,
    );
  }
}

/// Avatar con aro de estado (0 sin aro, 1 lima=sin ver, 2 gris=visto) y badge +
/// opcional (Mi estado).
class _AnilloAvatar extends StatelessWidget {
  const _AnilloAvatar({
    required this.email,
    required this.fotoUrl,
    required this.nombre,
    required this.aro,
    this.mostrarMas = false,
  });
  final String email;
  final String? fotoUrl;
  final String nombre;
  final int aro;
  final bool mostrarMas;

  @override
  Widget build(BuildContext context) {
    final ini =
        (nombre.trim().isNotEmpty ? nombre.trim()[0] : '?').toUpperCase();
    final ring = aro == 1
        ? lima
        : aro == 2
            ? trazo
            : Colors.transparent;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(width: 2.2, color: ring),
          ),
          child: CircleAvatar(
            radius: 24,
            backgroundColor: limaSuave,
            backgroundImage: (fotoUrl != null && fotoUrl!.isNotEmpty)
                ? NetworkImage(fotoUrl!)
                : null,
            child: (fotoUrl == null || fotoUrl!.isEmpty)
                ? Text(ini,
                    style: const TextStyle(
                        color: teal,
                        fontWeight: FontWeight.bold,
                        fontSize: 18))
                : null,
          ),
        ),
        if (mostrarMas)
          Positioned(
            right: -1,
            bottom: -1,
            child: Container(
              decoration: BoxDecoration(
                color: lima,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 2),
              ),
              child: const Icon(Icons.add, size: 15, color: Colors.white),
            ),
          ),
      ],
    );
  }
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.texto, this.accion});
  final String texto;
  final Widget? accion;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
              if (accion != null) ...[
                const SizedBox(height: 16),
                accion!,
              ],
            ],
          ),
        ),
      );
}
