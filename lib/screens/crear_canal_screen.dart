import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canales_repo.dart';
import '../models/canal.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';

/// Crea un canal de difusión (tipo WhatsApp): nombre, descripción y foto.
class CrearCanalScreen extends StatefulWidget {
  const CrearCanalScreen({super.key});

  @override
  State<CrearCanalScreen> createState() => _CrearCanalScreenState();
}

class _CrearCanalScreenState extends State<CrearCanalScreen> {
  final _nombre = TextEditingController();
  final _desc = TextEditingController();
  Uint8List? _foto;
  bool _creando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _desc.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final x = await ImagePicker().pickImage(
        source: ImageSource.gallery, maxWidth: 1024, imageQuality: 85);
    if (x == null) return;
    final b = await x.readAsBytes();
    if (mounted) setState(() => _foto = b);
  }

  Future<void> _crear() async {
    final nombre = _nombre.text.trim();
    final u = appState.usuario;
    if (nombre.isEmpty || u == null || _creando) return;
    setState(() => _creando = true);
    final id = 'ch_${DateTime.now().microsecondsSinceEpoch}';
    // REGLA de la app: acción que demora → preload de marca (nunca spinner pelado).
    final canal = await conPreload<Canal?>(context, () async {
      var fotoUrl = '';
      if (_foto != null) {
        final url = await CanalesRepo.subirMedia('$id/portada.jpg', _foto!);
        if (url != null) fotoUrl = url;
      }
      final c = Canal(
        id: id,
        nombre: nombre,
        descripcion: _desc.text.trim(),
        fotoUrl: fotoUrl,
        ownerEmail: u.email,
        creado: DateTime.now(),
      );
      final ok = await CanalesRepo.crear(c);
      return ok ? c : null;
    }, texto: 'Creando canal…');
    if (!mounted) return;
    if (canal != null) {
      Navigator.of(context).pop(canal);
    } else {
      setState(() => _creando = false);
      await avisarPichangol(context,
          titulo: 'No se pudo crear',
          mensaje: 'Revisa tu conexión e inténtalo de nuevo.',
          icono: Icons.cloud_off);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Crear canal')),
      body: AnchoTablet(
        maxWidth: 560,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Center(
              child: GestureDetector(
                onTap: _elegirFoto,
                child: CircleAvatar(
                  radius: 52,
                  backgroundColor: limaSuave,
                  backgroundImage:
                      _foto != null ? MemoryImage(_foto!) : null,
                  child: _foto == null
                      ? const Icon(Icons.add_a_photo_outlined,
                          color: lima, size: 34)
                      : null,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Center(
              child: Text('Foto del canal',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13)),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _nombre,
              textCapitalization: TextCapitalization.sentences,
              maxLength: 50,
              decoration: const InputDecoration(
                labelText: 'Nombre del canal',
                hintText: 'Ej. Pichangol San Borja',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _desc,
              textCapitalization: TextCapitalization.sentences,
              maxLength: 160,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Descripción (opcional)',
                hintText: '¿De qué trata tu canal?',
                alignLabelWithHint: true,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Tú serás el administrador. Solo tú publicas; los seguidores ven '
              'tus novedades y pueden reaccionar.',
              style: TextStyle(color: textoTenueDe(context), fontSize: 12.5),
            ),
            const SizedBox(height: 20),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima, minimumSize: const Size.fromHeight(50)),
              onPressed: _creando ? null : _crear,
              icon: const Icon(Icons.campaign_outlined),
              label: Text('Crear canal',
                  style: TextStyle(
                      color: cs.onPrimary, fontWeight: FontWeight.w800)),
            ),
          ],
        ),
      ),
    );
  }
}
