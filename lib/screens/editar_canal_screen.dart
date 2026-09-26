import 'dart:typed_data';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canales_repo.dart';
import '../models/canal.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';

/// Editar un canal propio: nombre, descripción y foto.
class EditarCanalScreen extends StatefulWidget {
  const EditarCanalScreen({super.key, required this.canal});
  final Canal canal;

  @override
  State<EditarCanalScreen> createState() => _EditarCanalScreenState();
}

class _EditarCanalScreenState extends State<EditarCanalScreen> {
  late final TextEditingController _nombre;
  late final TextEditingController _desc;
  Uint8List? _fotoNueva;
  bool _guardando = false;

  @override
  void initState() {
    super.initState();
    _nombre = TextEditingController(text: widget.canal.nombre);
    _desc = TextEditingController(text: widget.canal.descripcion);
  }

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
    if (mounted) setState(() => _fotoNueva = b);
  }

  Future<void> _guardar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty || _guardando) return;
    setState(() => _guardando = true);
    // REGLA de la app: acción que demora → preload de marca (nunca spinner pelado).
    final fotoUrl = await conPreload<String?>(context, () async {
      var url = widget.canal.fotoUrl;
      if (_fotoNueva != null) {
        final subida = await CanalesRepo.subirMedia(
            '${widget.canal.id}/portada.jpg', _fotoNueva!);
        if (subida != null) url = subida;
      }
      final ok = await CanalesRepo.actualizar(widget.canal.id,
          nombre: nombre, descripcion: _desc.text.trim(), fotoUrl: url);
      return ok ? url : null;
    }, texto: 'Guardando canal…');
    if (!mounted) return;
    if (fotoUrl != null) {
      Navigator.of(context).pop(widget.canal.copyWith(
          nombre: nombre, descripcion: _desc.text.trim(), fotoUrl: fotoUrl));
    } else {
      setState(() => _guardando = false);
      await avisarPichangol(context,
          titulo: 'No se pudo guardar',
          mensaje: 'Revisa tu conexión e inténtalo de nuevo.',
          icono: Icons.cloud_off);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final foto = widget.canal.fotoUrl;
    return Scaffold(
      appBar: AppBar(title: const Text('Editar canal')),
      body: AnchoTablet(
        maxWidth: 560,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Center(
              child: GestureDetector(
                onTap: _elegirFoto,
                child: Stack(
                  children: [
                    CircleAvatar(
                      radius: 52,
                      backgroundColor: limaSuave,
                      backgroundImage: _fotoNueva != null
                          ? MemoryImage(_fotoNueva!)
                          : (foto.isNotEmpty
                              ? CachedNetworkImageProvider(foto)
                                  as ImageProvider
                              : null),
                      child: (_fotoNueva == null && foto.isEmpty)
                          ? const Icon(Icons.campaign, color: lima, size: 40)
                          : null,
                    ),
                    const Positioned(
                      right: 0,
                      bottom: 0,
                      child: CircleAvatar(
                        radius: 15,
                        backgroundColor: lima,
                        child: Icon(Icons.camera_alt,
                            size: 15, color: Colors.white),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _nombre,
              textCapitalization: TextCapitalization.sentences,
              maxLength: 50,
              decoration: const InputDecoration(labelText: 'Nombre del canal'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _desc,
              textCapitalization: TextCapitalization.sentences,
              maxLength: 160,
              maxLines: 3,
              decoration: const InputDecoration(
                  labelText: 'Descripción', alignLabelWithHint: true),
            ),
            const SizedBox(height: 20),
            FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima, minimumSize: const Size.fromHeight(50)),
              onPressed: _guardando ? null : _guardar,
              child: Text('Guardar cambios',
                  style: TextStyle(
                      color: cs.onPrimary, fontWeight: FontWeight.w800)),
            ),
          ],
        ),
      ),
    );
  }
}
