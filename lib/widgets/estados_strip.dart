import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../screens/estado_composer_screen.dart';
import '../screens/estado_viewer_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Tira horizontal de ESTADOS / HISTORIAS (tipo WhatsApp) para la cabecera de
/// Mensajes: "Mi estado" (agregar/ver) + los aros de los conocidos que tienen
/// historias vigentes. Aro lima = sin ver; aro gris = ya visto.
class EstadosStrip extends StatelessWidget {
  const EstadosStrip({super.key});

  Future<void> _agregar(BuildContext context) async {
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
    if (r == null || !context.mounted) return;
    if (r == 'texto') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const EstadoComposerScreen(), fullscreenDialog: true));
      return;
    }
    final XFile? f = await ImagePicker().pickImage(
        source: r == 'camara' ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1600,
        imageQuality: 82);
    if (f == null || !context.mounted) return;
    final bytes = await f.readAsBytes();
    if (!context.mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoFotoComposerScreen(bytes: bytes),
        fullscreenDialog: true));
  }

  Future<void> _tocarMiEstado(BuildContext context) async {
    final tengo = appState.misEstados.isNotEmpty;
    if (!tengo) {
      await _agregar(context);
      return;
    }
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
            ListTile(
              leading: const Icon(Icons.remove_red_eye_outlined, color: teal),
              title: const Text('Ver mi estado'),
              onTap: () => Navigator.pop(context, 'ver'),
            ),
            ListTile(
              leading: const Icon(Icons.add_circle_outline, color: teal),
              title: const Text('Añadir a mi estado'),
              onTap: () => Navigator.pop(context, 'add'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (r == null || !context.mounted) return;
    if (r == 'ver') {
      await _verDe(context, appState.usuario?.email ?? '');
    } else {
      await _agregar(context);
    }
  }

  Future<void> _verDe(BuildContext context, String email) async {
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoViewerScreen(autorEmail: email)));
  }

  @override
  Widget build(BuildContext context) {
    if (!appState.logueado) return const SizedBox.shrink();
    final autores = appState.autoresConEstado();
    final miFoto = appState.usuario?.fotoUrl;
    final tengoEstado = appState.misEstados.isNotEmpty;

    return Container(
      color: Colors.white,
      padding: const EdgeInsets.only(top: 6, bottom: 8),
      child: SizedBox(
        height: 96,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          children: [
            _Burbuja(
              titulo: 'Mi estado',
              foto: miFoto,
              inicial: (appState.usuario?.nombre ?? '?'),
              aro: tengoEstado
                  ? (appState.autorTieneNoVisto(appState.usuario?.email) ? 1 : 2)
                  : 0,
              mostrarMas: true,
              onTap: () => _tocarMiEstado(context),
            ),
            for (final e in autores)
              _Burbuja(
                titulo: appState.nombreMostrableDe(e) ?? e.split('@').first,
                foto: appState.fotoDe(e),
                inicial: appState.nombreMostrableDe(e) ?? e,
                aro: appState.autorTieneNoVisto(e) ? 1 : 2,
                onTap: () => _verDe(context, e),
              ),
          ],
        ),
      ),
    );
  }
}

/// Una burbuja de estado: avatar con aro (0 sin aro, 1 lima=sin ver, 2 gris=visto)
/// y, opcionalmente, un badge "+" (Mi estado).
class _Burbuja extends StatelessWidget {
  const _Burbuja({
    required this.titulo,
    required this.foto,
    required this.inicial,
    required this.aro,
    required this.onTap,
    this.mostrarMas = false,
  });
  final String titulo;
  final String? foto;
  final String inicial;
  final int aro; // 0 nada, 1 lima, 2 gris
  final bool mostrarMas;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ini =
        (inicial.trim().isNotEmpty ? inicial.trim()[0] : '?').toUpperCase();
    final ring = aro == 1
        ? lima
        : aro == 2
            ? trazo
            : Colors.transparent;
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 74,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Container(
                  padding: const EdgeInsets.all(2.5),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(width: 2.5, color: ring),
                  ),
                  child: CircleAvatar(
                    radius: 27,
                    backgroundColor: limaSuave,
                    backgroundImage: (foto != null && foto!.isNotEmpty)
                        ? NetworkImage(foto!)
                        : null,
                    child: (foto == null || foto!.isEmpty)
                        ? Text(ini,
                            style: const TextStyle(
                                color: teal,
                                fontWeight: FontWeight.bold,
                                fontSize: 20))
                        : null,
                  ),
                ),
                if (mostrarMas)
                  Positioned(
                    right: 0,
                    bottom: 0,
                    child: Container(
                      decoration: BoxDecoration(
                        color: lima,
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                      child: const Icon(Icons.add,
                          size: 15, color: Colors.white),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              titulo,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 11, color: bosque),
            ),
          ],
        ),
      ),
    );
  }
}
