import 'dart:typed_data';

import 'package:flutter/foundation.dart' show Factory;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../models/models.dart';
import '../services/propiedad_service.dart';
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
  final TextEditingController _ruc =
      TextEditingController(); // opcional, refuerza la verificación al reclamar
  final TextEditingController _contacto =
      TextEditingController(); // WhatsApp del dueño al reclamar (obligatorio)

  late Deporte _deporte = widget.cancha.deporte;
  late LatLng _ubicacion = widget.cancha.ubicacion;
  GoogleMapController? _map;

  bool _geocodificando = false;
  String? _errorGeo;

  // Galería: URLs ya subidas + fotos nuevas (locales, aún sin subir).
  late final List<String> _fotosUrl = List.of(
    widget.cancha.fotos.isNotEmpty
        ? widget.cancha.fotos
        : (widget.cancha.fotoUrl != null ? [widget.cancha.fotoUrl!] : []),
  );
  final List<Uint8List> _fotosNuevas = [];
  bool _guardando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _direccion.dispose();
    _precio.dispose();
    _ruc.dispose();
    _contacto.dispose();
    _map?.dispose();
    super.dispose();
  }

  Future<void> _agregarFotos() async {
    final files = await ImagePicker().pickMultiImage(maxWidth: 1280);
    if (files.isEmpty) return;
    final nuevas = <Uint8List>[];
    for (final f in files) {
      nuevas.add(await f.readAsBytes());
    }
    if (!mounted) return;
    setState(() => _fotosNuevas.addAll(nuevas));
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

  /// Mueve el pin y **rellena la dirección automáticamente** desde esa
  /// coordenada (geocodificación inversa). Fail-safe: si no resuelve, conserva
  /// la dirección actual.
  Future<void> _moverPin(LatLng p) async {
    setState(() {
      _ubicacion = p;
      _errorGeo = null;
    });
    try {
      final marks = await placemarkFromCoordinates(p.latitude, p.longitude);
      if (!mounted || marks.isEmpty) return;
      final dir = _direccionDePlacemark(marks.first);
      if (dir.isNotEmpty) setState(() => _direccion.text = dir);
    } catch (_) {
      // sin red / sin resultado: deja la dirección como está
    }
  }

  String _direccionDePlacemark(Placemark m) {
    bool ok(String? s) => s != null && s.trim().isNotEmpty;
    final calle = [m.thoroughfare, m.subThoroughfare]
        .where(ok)
        .join(' ')
        .trim();
    final base = calle.isNotEmpty ? calle : (m.street ?? '');
    final partes = <String>[
      if (base.trim().isNotEmpty) base.trim(),
      if (ok(m.subLocality)) m.subLocality!,
      if (ok(m.locality) && m.locality != m.subLocality) m.locality!,
    ];
    return partes.join(', ');
  }

  Future<void> _guardar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      _avisar('Ponle un nombre a la cancha.');
      return;
    }
    final esReclamo = widget.cancha.dueno.isEmpty;
    final contacto = _contacto.text.trim();
    if (esReclamo &&
        contacto.replaceAll(RegExp(r'[^0-9]'), '').length < 9) {
      _avisar('Pon tu WhatsApp de contacto para que el equipo te valide.');
      return;
    }
    setState(() => _guardando = true);

    // Sube las fotos nuevas y arma la galería final (existentes + nuevas).
    final fotos = List<String>.of(_fotosUrl);
    for (var i = 0; i < _fotosNuevas.length; i++) {
      final url = await CanchasRepo.subirFoto(
        widget.cancha.id,
        _fotosNuevas[i],
        sufijo: '${DateTime.now().millisecondsSinceEpoch}_$i',
      );
      if (url != null) fotos.add(url);
    }
    final fotoUrl = fotos.isNotEmpty ? fotos.first : null;

    // Si la cancha no tenía dueño (legado, p. ej. registrada antes de atarla a
    // una cuenta), al guardar la reclamamos con el correo del usuario logueado y
    // queda pendiente de verificación (anti-fraude).
    final eraReclamo = widget.cancha.dueno.isEmpty;
    final dueno =
        eraReclamo ? (appState.usuario?.email ?? '') : widget.cancha.dueno;
    final verificada = eraReclamo ? false : widget.cancha.verificada;

    final actualizada = widget.cancha.copyWith(
      nombre: nombre,
      precioHora: int.tryParse(_precio.text.trim()) ?? widget.cancha.precioHora,
      deporte: _deporte,
      ubicacion: _ubicacion,
      fotos: fotos,
      direccion: _direccion.text.trim().isEmpty ? null : _direccion.text.trim(),
      fotoUrl: fotoUrl,
      dueno: dueno,
      verificada: verificada,
    );
    appState.actualizarCancha(actualizada);

    // Al reclamar, dispara la verificación de EXISTENCIA en segundo plano. Esto
    // confirma que el local es real, pero NO te convierte en dueño: la cancha
    // queda en revisión de propiedad hasta validar al titular (código al teléfono
    // del local, aprobación manual o visita). Un RUC válido por sí solo no basta.
    // Modelo concierge: al reclamar se crea una SOLICITUD DE RECLAMO y le llega
    // un WhatsApp al equipo de Pichangol con un código para vetear al dueño. Nada
    // se activa hasta validarlo (revisión + visita en sitio).
    if (eraReclamo) {
      appState.verificarCancha(actualizada, ruc: _ruc.text.trim());
      PropiedadService.crearReclamo(
        canchaId: actualizada.id,
        solicitanteId: dueno,
        nombreLocal: nombre,
        telefonoContacto: contacto,
        ubicacion: _ubicacion,
      );
    }

    if (!mounted) return;
    setState(() => _guardando = false);
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: pino,
        content: Text(
            eraReclamo
                ? '✅ "$nombre" reclamada. En revisión: te contactaremos por WhatsApp para validarla antes de activarla.'
                : '✅ "$nombre" actualizada.',
            style: const TextStyle(color: Colors.white)),
        duration: const Duration(seconds: 5),
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
          Row(
            children: [
              const Text('Fotos', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              Text('(la 1ª es la portada)',
                  style: TextStyle(color: textoTenue, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 8),
          _GaleriaEditor(
            fotosUrl: _fotosUrl,
            fotosNuevas: _fotosNuevas,
            onAgregar: _agregarFotos,
            onQuitarUrl: (i) => setState(() => _fotosUrl.removeAt(i)),
            onQuitarNueva: (i) => setState(() => _fotosNuevas.removeAt(i)),
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
                // El mapa reclama los gestos de arrastre/zoom para que se pueda
                // panear y ajustar el pin dentro de la lista que hace scroll.
                gestureRecognizers: <Factory<OneSequenceGestureRecognizer>>{
                  Factory<OneSequenceGestureRecognizer>(
                      () => EagerGestureRecognizer()),
                },
                onTap: _moverPin,
                markers: {
                  Marker(
                    markerId: const MarkerId('cancha'),
                    position: _ubicacion,
                    draggable: true,
                    onDragEnd: _moverPin,
                  ),
                },
              ),
            ),
          ),
          const SizedBox(height: 6),
          const Text(
              'Arrastra el pin o toca el mapa: la dirección se actualiza sola.',
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
          if (widget.cancha.dueno.isEmpty) ...[
            const SizedBox(height: 16),
            TextField(
              controller: _contacto,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Tu WhatsApp de contacto *',
                hintText: 'Ej.: 987 654 321 — te escribiremos para validarte',
                prefixIcon: Padding(
                  padding: EdgeInsets.all(12),
                  child: FaIcon(FontAwesomeIcons.whatsapp,
                      color: Color(0xFF25D366), size: 20),
                ),
                prefixIconConstraints: BoxConstraints(minWidth: 44),
                border: OutlineInputBorder(),
              ),
            ),
          ],
          if (!widget.cancha.verificada) ...[
            const SizedBox(height: 16),
            TextField(
              controller: _ruc,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'RUC del negocio (opcional)',
                hintText: 'Ayuda a confirmar que el local existe (no reemplaza la validación del dueño)',
                prefixIcon: Icon(Icons.verified_outlined, color: pino),
                border: OutlineInputBorder(),
              ),
            ),
          ],
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

/// Editor de galería: miniaturas (existentes + nuevas) con botón de quitar y un
/// recuadro para agregar más fotos.
class _GaleriaEditor extends StatelessWidget {
  const _GaleriaEditor({
    required this.fotosUrl,
    required this.fotosNuevas,
    required this.onAgregar,
    required this.onQuitarUrl,
    required this.onQuitarNueva,
  });

  final List<String> fotosUrl;
  final List<Uint8List> fotosNuevas;
  final VoidCallback onAgregar;
  final ValueChanged<int> onQuitarUrl;
  final ValueChanged<int> onQuitarNueva;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 110,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          for (var i = 0; i < fotosUrl.length; i++)
            _Miniatura(
              imagen: Image.network(fotosUrl[i],
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      const ColoredBox(color: Color(0xFFEFEBE1))),
              esPortada: i == 0,
              onQuitar: () => onQuitarUrl(i),
            ),
          for (var i = 0; i < fotosNuevas.length; i++)
            _Miniatura(
              imagen: Image.memory(fotosNuevas[i], fit: BoxFit.cover),
              esPortada: fotosUrl.isEmpty && i == 0,
              onQuitar: () => onQuitarNueva(i),
            ),
          // Botón agregar
          GestureDetector(
            onTap: onAgregar,
            child: Container(
              width: 100,
              margin: const EdgeInsets.only(right: 2),
              decoration: BoxDecoration(
                color: const Color(0xFFEFEBE1),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: trazo),
              ),
              child: const Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.add_a_photo, color: pino, size: 28),
                  SizedBox(height: 6),
                  Text('Agregar',
                      style: TextStyle(
                          color: verdeOscuro,
                          fontWeight: FontWeight.w600,
                          fontSize: 12)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Miniatura extends StatelessWidget {
  const _Miniatura(
      {required this.imagen, required this.esPortada, required this.onQuitar});
  final Widget imagen;
  final bool esPortada;
  final VoidCallback onQuitar;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 100,
      margin: const EdgeInsets.only(right: 8),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ClipRRect(borderRadius: BorderRadius.circular(14), child: imagen),
          if (esPortada)
            Positioned(
              left: 6,
              top: 6,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                    color: pino, borderRadius: BorderRadius.circular(999)),
                child: const Text('Portada',
                    style: TextStyle(
                        color: lima,
                        fontSize: 10,
                        fontWeight: FontWeight.w700)),
              ),
            ),
          Positioned(
            right: 4,
            top: 4,
            child: GestureDetector(
              onTap: onQuitar,
              child: const CircleAvatar(
                radius: 12,
                backgroundColor: Colors.black54,
                child: Icon(Icons.close, color: Colors.white, size: 15),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
