import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Edición de una cancha ya registrada por el dueño: cambiar nombre, precio,
/// deporte, dirección/ubicación, agregar foto de portada o eliminarla.
class EditarCanchaScreen extends StatefulWidget {
  const EditarCanchaScreen({super.key, required this.cancha});
  final Cancha cancha;

  @override
  State<EditarCanchaScreen> createState() => _EditarCanchaScreenState();
}

class _EditarCanchaScreenState extends State<EditarCanchaScreen> {
  late final TextEditingController _nombre =
      TextEditingController(text: widget.cancha.nombre);
  late final TextEditingController _direccion =
      TextEditingController(text: widget.cancha.direccion ?? '');
  late final TextEditingController _precio =
      TextEditingController(text: widget.cancha.precioHora.toString());

  late Deporte _deporte = widget.cancha.deporte;
  late LatLng _ubicacion = widget.cancha.ubicacion;
  GoogleMapController? _map;

  bool _geocodificando = false;
  String? _errorGeo;

  Uint8List? _fotoNueva; // foto recién elegida (aún no subida)
  bool _guardando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _direccion.dispose();
    _precio.dispose();
    _map?.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final XFile? file = await ImagePicker()
        .pickImage(source: ImageSource.gallery, maxWidth: 1280);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() => _fotoNueva = bytes);
  }

  Future<void> _ubicarDireccion() async {
    final q = _direccion.text.trim();
    if (q.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _geocodificando = true;
      _errorGeo = null;
    });
    try {
      final locs = await locationFromAddress('$q, Lima, Perú');
      if (locs.isEmpty) {
        setState(() {
          _geocodificando = false;
          _errorGeo = 'No encontré esa dirección. Mueve el pin a mano.';
        });
        return;
      }
      final l = locs.first;
      final destino = LatLng(l.latitude, l.longitude);
      if (!mounted) return;
      setState(() {
        _geocodificando = false;
        _ubicacion = destino;
      });
      _map?.animateCamera(CameraUpdate.newLatLngZoom(destino, 16));
    } catch (_) {
      setState(() {
        _geocodificando = false;
        _errorGeo = 'No pude ubicar la dirección. Toca el mapa para marcarla.';
      });
    }
  }

  Future<void> _guardar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      _avisar('Ponle un nombre a la cancha.');
      return;
    }
    setState(() => _guardando = true);

    // Sube la foto nueva (si hay) y obtiene su URL.
    String? fotoUrl = widget.cancha.fotoUrl;
    if (_fotoNueva != null) {
      final url = await CanchasRepo.subirFoto(widget.cancha.id, _fotoNueva!);
      if (url != null) fotoUrl = url;
    }

    final actualizada = widget.cancha.copyWith(
      nombre: nombre,
      precioHora: int.tryParse(_precio.text.trim()) ?? widget.cancha.precioHora,
      deporte: _deporte,
      ubicacion: _ubicacion,
      direccion: _direccion.text.trim().isEmpty ? null : _direccion.text.trim(),
      fotoUrl: fotoUrl,
    );
    appState.actualizarCancha(actualizada);

    if (!mounted) return;
    setState(() => _guardando = false);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: pino,
        content: Text('✅ "$nombre" actualizada.',
            style: const TextStyle(color: Colors.white)),
      ),
    );
  }

  Future<void> _eliminar() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eliminar cancha'),
        content: Text('¿Seguro que quieres eliminar "${widget.cancha.nombre}"? '
            'Dejará de aparecer en el mapa.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: clayOscuro),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    appState.eliminarCancha(widget.cancha.id);
    if (!mounted) return;
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Cancha eliminada.')),
    );
  }

  void _avisar(String msg) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(msg)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(
        title: const Text('Editar cancha'),
        actions: [
          IconButton(
            tooltip: 'Eliminar',
            onPressed: _guardando ? null : _eliminar,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          _ZonaFoto(
            fotoNueva: _fotoNueva,
            fotoUrl: widget.cancha.fotoUrl,
            onTap: _elegirFoto,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
              labelText: 'Nombre de la cancha',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _direccion,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _ubicarDireccion(),
            decoration: InputDecoration(
              labelText: 'Dirección',
              prefixIcon: const Icon(Icons.place, color: clay),
              border: const OutlineInputBorder(),
              suffixIcon: _geocodificando
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : IconButton(
                      tooltip: 'Ubicar en el mapa',
                      icon: const Icon(Icons.search, color: pino),
                      onPressed: _ubicarDireccion,
                    ),
            ),
          ),
          if (_errorGeo != null) ...[
            const SizedBox(height: 8),
            Text(_errorGeo!, style: const TextStyle(color: clayOscuro)),
          ],
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              height: 200,
              child: GoogleMap(
                initialCameraPosition:
                    CameraPosition(target: _ubicacion, zoom: 16),
                onMapCreated: (c) => _map = c,
                myLocationButtonEnabled: false,
                zoomControlsEnabled: false,
                onTap: (p) => setState(() => _ubicacion = p),
                markers: {
                  Marker(
                    markerId: const MarkerId('cancha'),
                    position: _ubicacion,
                    draggable: true,
                    onDragEnd: (p) => setState(() => _ubicacion = p),
                  ),
                },
              ),
            ),
          ),
          const SizedBox(height: 6),
          const Text('Arrastra el pin o toca el mapa para ajustar el punto.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 16),
          const Text('Deporte', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            children: [
              for (final d in Deporte.values)
                ChoiceChip(
                  avatar: Icon(iconoDeporte(d),
                      size: 18,
                      color: _deporte == d ? Colors.white : colorDeporte(d)),
                  label: Text(d.etiqueta),
                  selected: _deporte == d,
                  selectedColor: colorDeporte(d),
                  labelStyle: TextStyle(
                      color: _deporte == d ? Colors.white : tinta,
                      fontWeight: FontWeight.w600),
                  onSelected: (_) => setState(() => _deporte = d),
                ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _precio,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Precio por hora (S/)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: pino,
                foregroundColor: lima,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
              onPressed: _guardando ? null : _guardar,
              icon: _guardando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.save),
              label: Text(_guardando ? 'Guardando…' : 'Guardar cambios'),
            ),
          ),
        ],
      ),
    );
  }
}

class _ZonaFoto extends StatelessWidget {
  const _ZonaFoto(
      {required this.fotoNueva, required this.fotoUrl, required this.onTap});
  final Uint8List? fotoNueva;
  final String? fotoUrl;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    Widget contenido;
    if (fotoNueva != null) {
      contenido = Image.memory(fotoNueva!, fit: BoxFit.cover, width: double.infinity);
    } else if (fotoUrl != null) {
      contenido = Image.network(fotoUrl!, fit: BoxFit.cover, width: double.infinity,
          errorBuilder: (_, __, ___) => _placeholder());
    } else {
      contenido = _placeholder();
    }
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 180,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: const Color(0xFFEFEBE1),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo),
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            contenido,
            Positioned(
              right: 10,
              bottom: 10,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: BoxDecoration(
                    color: pino, borderRadius: BorderRadius.circular(999)),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.add_a_photo, color: lima, size: 16),
                    SizedBox(width: 6),
                    Text('Cambiar foto',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                            fontSize: 12)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _placeholder() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.add_a_photo, color: pino, size: 40),
          SizedBox(height: 8),
          Text('Agrega una foto de la cancha',
              style: TextStyle(color: verdeOscuro, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
