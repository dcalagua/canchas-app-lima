import 'dart:typed_data';

import 'package:flutter/foundation.dart' show Factory;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../models/models.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/selector_horario.dart';
import 'agregar_cancha_screen.dart';

/// Edición de una cancha ya registrada por el dueño: cambiar nombre, precio,
/// deporte, horario/duración, dirección/ubicación, agregar foto o eliminarla.
class EditarCanchaScreen extends StatefulWidget {
  const EditarCanchaScreen({super.key, required this.cancha});
  final Cancha cancha;

  @override
  State<EditarCanchaScreen> createState() => _EditarCanchaScreenState();
}

class _EditarCanchaScreenState extends State<EditarCanchaScreen> {
  late final TextEditingController _local =
      TextEditingController(text: widget.cancha.club);
  late final TextEditingController _nombre =
      TextEditingController(text: widget.cancha.nombre);
  late final TextEditingController _direccion =
      TextEditingController(text: widget.cancha.direccion ?? '');
  late final TextEditingController _precio =
      TextEditingController(text: widget.cancha.precioHora.toStringAsFixed(2));
  final TextEditingController _ruc =
      TextEditingController(); // opcional, refuerza la verificación al reclamar
  final TextEditingController _contacto =
      TextEditingController(); // WhatsApp del dueño al reclamar (obligatorio)
  final TextEditingController _dni =
      TextEditingController(); // DNI del reclamante (obligatorio al reclamar)

  late final Deporte _deporte = widget.cancha.deporte; // fijo: no se cambia aquí
  late String _apertura = widget.cancha.horaApertura;
  late String _cierre = widget.cancha.horaCierre;
  late int _duracion = widget.cancha.duracionSlotMin;
  late final Set<String> _amenidades = {...widget.cancha.amenidades};
  late String _superficie = widget.cancha.superficie; // tipo de piso (opcional)
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
    _local.dispose();
    _nombre.dispose();
    _direccion.dispose();
    _precio.dispose();
    _ruc.dispose();
    _contacto.dispose();
    _dni.dispose();
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
    final dni = _dni.text.replaceAll(RegExp(r'[^0-9]'), '');
    if (esReclamo &&
        contacto.replaceAll(RegExp(r'[^0-9]'), '').length < 9) {
      _avisar('Pon tu WhatsApp de contacto para que el equipo te valide.');
      return;
    }
    if (esReclamo && dni.length != 8) {
      _avisar('Pon tu DNI (8 dígitos) para validar tu identidad.');
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

    // Nombre del LOCAL: si el dueño lo cambió, se propaga a TODAS sus canchas
    // (para que sigan agrupadas). Si lo dejó vacío, conserva el actual.
    final nuevoLocal = _local.text.trim();
    final club =
        nuevoLocal.isEmpty ? widget.cancha.club : nuevoLocal;

    final actualizada = widget.cancha.copyWith(
      nombre: nombre,
      club: club,
      precioHora: double.tryParse(_precio.text.trim().replaceAll(',', '.')) ??
          widget.cancha.precioHora,
      deporte: _deporte,
      ubicacion: _ubicacion,
      fotos: fotos,
      direccion: _direccion.text.trim().isEmpty ? null : _direccion.text.trim(),
      fotoUrl: fotoUrl,
      dueno: dueno,
      verificada: verificada,
      horaApertura: _apertura,
      horaCierre: _cierre,
      duracionSlotMin: _duracion,
      amenidades: _amenidades.toList(),
      superficie: _superficie,
    );
    appState.actualizarCancha(actualizada);
    if (club != widget.cancha.club) {
      appState.renombrarLocal(widget.cancha.club, club); // renombra el local entero
    }
    // Los servicios son del LOCAL: se aplican a TODAS sus canchas.
    appState.actualizarServiciosLocal(club, _amenidades.toList());

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
        dni: dni,
        ruc: _ruc.text.trim(),
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

  /// Abre "Agregar cancha" para sumar otra cancha al MISMO local (otra de este
  /// deporte o de uno distinto). La nueva hereda dueño y estado del local.
  void _agregarOtraCancha() {
    Navigator.of(context).push(
      MaterialPageRoute(
          builder: (_) => AgregarCanchaScreen(local: widget.cancha)),
    );
  }

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
            controller: _local,
            decoration: const InputDecoration(
              labelText: 'Nombre del local',
              helperText: 'El negocio; agrupa todas sus canchas.',
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
              labelText: 'Nombre de la cancha',
              helperText: 'Ej.: Fútbol 1, Tenis 1, Pádel 2…',
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
          const Text('Deporte de esta cancha',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          const Text(
              'Cada cancha es de un solo deporte. Para ofrecer otro deporte, '
              'agrega otra cancha al local.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 8),
          // Deporte FIJO de la cancha (el detectado / elegido al crearla). No se
          // cambia aquí: para otro deporte se agrega OTRA cancha al local.
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: colorDeporte(_deporte),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(iconoDeporte(_deporte), size: 18, color: Colors.white),
                  const SizedBox(width: 7),
                  Text(_deporte.etiqueta,
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w700)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          // Agregar otra cancha al MISMO local: otra de fútbol, o de otro deporte.
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _guardando ? null : _agregarOtraCancha,
              icon: const Icon(Icons.add_circle_outline, size: 20),
              label: const Text('Agregar otra cancha a este local'),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _precio,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Precio por hora',
              prefixText: 'S/ ',
            ),
          ),
          const SizedBox(height: 18),
          const Text('Tipo de piso',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(
              'La superficie de esta cancha (según el deporte). Ayuda a que el '
              'jugador la encuentre por tipo.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final s in superficiesDe(_deporte))
                ChoiceChip(
                  avatar: Icon(iconoSuperficie(s),
                      size: 18,
                      color: _superficie == s ? bosque : textoTenue),
                  label: Text(s),
                  selected: _superficie == s,
                  labelStyle: TextStyle(
                      color: _superficie == s ? bosque : tinta,
                      fontWeight: FontWeight.w600),
                  selectedColor: limaSuave,
                  onSelected: (sel) =>
                      setState(() => _superficie = sel ? s : ''),
                ),
            ],
          ),
          const SizedBox(height: 18),
          SelectorHorario(
            apertura: _apertura,
            cierre: _cierre,
            duracionMin: _duracion,
            onApertura: (v) => setState(() => _apertura = v),
            onCierre: (v) => setState(() => _cierre = v),
            onDuracion: (v) => setState(() => _duracion = v),
          ),
          const SizedBox(height: 18),
          const Text('Servicios del local',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(
              'Son del LOCAL: aplican a todas sus canchas (no solo a esta). '
              'Se muestran en la ficha.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final a in amenidadesCatalogo)
                FilterChip(
                  avatar: Icon(a.icono,
                      size: 18,
                      color: _amenidades.contains(a.clave)
                          ? bosque
                          : textoTenue),
                  label: Text(a.etiqueta),
                  selected: _amenidades.contains(a.clave),
                  selectedColor: limaSuave,
                  checkmarkColor: bosque,
                  labelStyle: TextStyle(
                      color: _amenidades.contains(a.clave) ? bosque : tinta,
                      fontWeight: FontWeight.w600),
                  onSelected: (sel) => setState(() {
                    if (sel) {
                      _amenidades.add(a.clave);
                    } else {
                      _amenidades.remove(a.clave);
                    }
                  }),
                ),
            ],
          ),
          if (widget.cancha.dueno.isEmpty) ...[
            const SizedBox(height: 16),
            TextField(
              controller: _dni,
              keyboardType: TextInputType.number,
              maxLength: 8,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(8),
              ],
              decoration: const InputDecoration(
                labelText: 'Tu DNI *',
                hintText: '8 dígitos — validamos tu identidad',
                prefixIcon: Icon(Icons.badge_outlined, color: pino),
                counterText: '',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _contacto,
              keyboardType: TextInputType.phone,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(9),
              ],
              decoration: const InputDecoration(
                labelText: 'Tu WhatsApp de contacto *',
                hintText: '987 654 321',
                prefixIcon: _PrefijoPeruEditar(),
                prefixIconConstraints: BoxConstraints(minWidth: 76),
                suffixIcon: Padding(
                  padding: EdgeInsets.all(12),
                  child: FaIcon(FontAwesomeIcons.whatsapp,
                      color: Color(0xFF25D366), size: 20),
                ),
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

/// Prefijo de teléfono peruano: banderita 🇵🇪 + "+51".
class _PrefijoPeruEditar extends StatelessWidget {
  const _PrefijoPeruEditar();
  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(left: 12, right: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('🇵🇪', style: TextStyle(fontSize: 18)),
          SizedBox(width: 4),
          Text('+51',
              style: TextStyle(fontWeight: FontWeight.w800, color: tinta)),
        ],
      ),
    );
  }
}
