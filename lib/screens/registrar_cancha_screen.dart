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
import '../services/sport_detector.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/selector_horario.dart';
import 'login_google_sheet.dart';

/// Registrar una cancha escribiendo la dirección: se geocodifica y aparece en el
/// mapa automáticamente (estilo eSupplier). Un local puede tener varias canchas
/// de distintos deportes, así que el deporte es de selección múltiple.
class RegistrarCanchaScreen extends StatefulWidget {
  /// Si se pasa [base] (una cancha descubierta en Google que se está
  /// reclamando), el formulario abre pre-rellenado con su nombre, dirección,
  /// ubicación (pin) y deporte.
  const RegistrarCanchaScreen({super.key, this.base});

  final Cancha? base;

  @override
  State<RegistrarCanchaScreen> createState() => _RegistrarCanchaScreenState();
}

class _RegistrarCanchaScreenState extends State<RegistrarCanchaScreen> {
  final _nombre = TextEditingController();
  final _direccion = TextEditingController();
  final _precio = TextEditingController(text: '120.00');
  final _ruc = TextEditingController(); // opcional: refuerza la verificación
  final _contacto = TextEditingController(); // WhatsApp del dueño (obligatorio)
  final _dni = TextEditingController(); // DNI del reclamante (obligatorio)

  /// true cuando se está RECLAMANDO una cancha descubierta en Google (trae base).
  bool get _esReclamo => widget.base != null;

  // Resultado de la consulta a Factiliza (se muestra debajo del campo).
  String? _dniNombre;
  bool _dniCargando = false;
  String? _rucRazon;
  bool _rucCargando = false;

  // Relación del reclamante con la cancha (combo).
  String _relacion = 'dueño';

  /// Etiqueta con asterisco rojo para campos obligatorios.
  Widget _lblReq(String s) => Text.rich(TextSpan(text: s, children: const [
        TextSpan(
            text: ' *',
            style: TextStyle(
                color: Color(0xFFD11F2E), fontWeight: FontWeight.w900)),
      ]));

  Future<void> _consultarDni(String v) async {
    final d = v.replaceAll(RegExp(r'[^0-9]'), '');
    if (d.length != 8) {
      setState(() => _dniNombre = null);
      return;
    }
    setState(() => _dniCargando = true);
    final r = await PropiedadService.consultarDni(d);
    if (!mounted) return;
    setState(() {
      _dniCargando = false;
      _dniNombre = (r != null && r['ok'] == true)
          ? (r['nombre_completo'] as String?)
          : null;
    });
  }

  Future<void> _consultarRuc(String v) async {
    final d = v.replaceAll(RegExp(r'[^0-9]'), '');
    if (d.length != 11) {
      setState(() => _rucRazon = null);
      return;
    }
    setState(() => _rucCargando = true);
    final r = await PropiedadService.consultarRuc(d);
    if (!mounted) return;
    setState(() {
      _rucCargando = false;
      _rucRazon = (r != null && r['ok'] == true)
          ? (r['razon_social'] as String?)
          : null;
    });
  }

  // Deportes del local (varios a la vez). Fútbol viene marcado por defecto.
  final Set<Deporte> _deportes = {Deporte.futbol};

  // Horario de atención y duración de turno (se aplican a las canchas creadas).
  String _apertura = '07:00';
  String _cierre = '23:00';
  int _duracion = 60;

  GoogleMapController? _map;
  LatLng? _ubicacion; // null hasta geocodificar o tocar el mapa
  bool _geocodificando = false;
  String? _errorGeo;

  Uint8List? _foto;
  bool _analizando = false;
  DeteccionDeporte? _deteccion;

  // Fotos que ya traía la cancha descubierta (Google): se conservan al reclamar.
  List<String> _fotosBase = const [];

  static const _limaCentro = LatLng(-12.0931, -77.0465);

  @override
  void initState() {
    super.initState();
    final b = widget.base;
    if (b != null) {
      _nombre.text = b.nombre;
      _direccion.text = b.direccion ?? '';
      _ubicacion = b.ubicacion; // marca el pin en la ubicación de Google
      _deportes
        ..clear()
        ..add(b.deporte);
      _fotosBase = b.fotos.isNotEmpty
          ? b.fotos
          : (b.fotoUrl != null ? [b.fotoUrl!] : const []);
    }
  }

  @override
  void dispose() {
    _nombre.dispose();
    _direccion.dispose();
    _precio.dispose();
    _ruc.dispose();
    _contacto.dispose();
    _dni.dispose();
    _map?.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final XFile? file = await ImagePicker()
        .pickImage(source: ImageSource.gallery, maxWidth: 1024);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() {
      _foto = bytes;
      _analizando = true;
      _deteccion = null;
    });
    final det = await SportDetector.detectar(bytes);
    if (!mounted) return;
    setState(() {
      _analizando = false;
      _deteccion = det;
      _deportes.add(det.deporte); // la IA agrega el deporte que detectó
    });
  }

  /// Geocodifica la dirección escrita y coloca el marcador en el mapa.
  Future<void> _ubicarDireccion() async {
    final q = _direccion.text.trim();
    if (q.isEmpty) {
      setState(() => _errorGeo = 'Escribe la dirección de tu cancha.');
      return;
    }
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
          _errorGeo = 'No encontré esa dirección. Revísala o mueve el pin a mano.';
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
        _errorGeo = 'No pude ubicar la dirección. Toca el mapa para marcarla a mano.';
      });
    }
  }

  /// Mueve el pin y **rellena la dirección automáticamente** desde esa
  /// coordenada (geocodificación inversa). Fail-safe.
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
    final calle =
        [m.thoroughfare, m.subThoroughfare].where(ok).join(' ').trim();
    final base = calle.isNotEmpty ? calle : (m.street ?? '');
    final partes = <String>[
      if (base.trim().isNotEmpty) base.trim(),
      if (ok(m.subLocality)) m.subLocality!,
      if (ok(m.locality) && m.locality != m.subLocality) m.locality!,
    ];
    return partes.join(', ');
  }

  /// Best-effort: deduce el distrito desde las coordenadas (para clasificar).
  Future<Distrito> _distritoDe(LatLng p) async {
    try {
      final marks = await placemarkFromCoordinates(p.latitude, p.longitude);
      for (final m in marks) {
        final texto = '${m.subLocality} ${m.locality} ${m.subAdministrativeArea}'
            .toLowerCase();
        for (final d in Distrito.values) {
          if (texto.contains(d.etiqueta.toLowerCase())) return d;
        }
      }
    } catch (_) {}
    return Distrito.sanBorja;
  }

  Future<void> _publicar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      _avisar('Ponle un nombre al local / cancha.');
      return;
    }
    if (_ubicacion == null) {
      _avisar('Ubica la dirección en el mapa primero.');
      return;
    }
    if (_deportes.isEmpty) {
      _avisar('Elige al menos un deporte.');
      return;
    }
    final aMin = horaEnMinutos(_apertura), cMin = horaEnMinutos(_cierre);
    if (aMin == null || cMin == null || cMin <= aMin) {
      _avisar('El cierre debe ser después de la apertura.');
      return;
    }
    final contacto = _contacto.text.trim();
    if (contacto.replaceAll(RegExp(r'[^0-9]'), '').length < 9) {
      _avisar('Pon tu WhatsApp de contacto para que el equipo te valide.');
      return;
    }
    final dni = _dni.text.trim();
    if (dni.replaceAll(RegExp(r'[^0-9]'), '').length != 8) {
      _avisar('Pon tu DNI (8 dígitos) para validar tu identidad.');
      return;
    }
    final rucDigs = _ruc.text.replaceAll(RegExp(r'[^0-9]'), '');
    if (rucDigs.isNotEmpty && rucDigs.length != 11) {
      _avisar('El RUC debe tener 11 dígitos (o déjalo vacío).');
      return;
    }
    // Anti-fraude: para registrar/reclamar hay que identificarse con Google, así
    // la cancha queda atada a una cuenta real y pasa a verificación.
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) {
        _avisar('Inicia sesión para registrar tu cancha.');
        return;
      }
    }
    final precio =
        double.tryParse(_precio.text.trim().replaceAll(',', '.')) ?? 100;
    final direccion = _direccion.text.trim();
    final distrito = await _distritoDe(_ubicacion!);
    final ts = DateTime.now().millisecondsSinceEpoch;

    // Sube la foto nueva (si hay) y conserva las que ya traía de Google.
    String? fotoSubida;
    if (_foto != null) {
      fotoSubida = await CanchasRepo.subirFoto('u$ts', _foto!);
    }
    final fotos = <String>[
      if (fotoSubida != null) fotoSubida,
      ..._fotosBase,
    ];
    final fotoUrl = fotos.isNotEmpty ? fotos.first : null;

    // Atamos la cancha a la cuenta del dueño (correo) para recuperarla luego en
    // "Mis canchas" desde cualquier dispositivo.
    final dueno = appState.usuario?.email ?? '';

    // Un local con varias canchas = una Cancha por deporte, mismo punto y dirección.
    final deportes = _deportes.toList();
    final creadas = <Cancha>[];
    for (final dep in deportes) {
      final nombreCancha =
          deportes.length > 1 ? '$nombre · ${dep.etiqueta}' : nombre;
      final cancha = Cancha(
        id: 'u${ts}_${dep.name}',
        nombre: nombreCancha,
        club: nombre, // el local es su propio club (nombre que escribió el dueño)
        distrito: distrito,
        deporte: dep,
        precioHora: precio,
        ubicacion: _ubicacion!,
        clubFundador: false,
        digitalizada: true,
        direccion: direccion.isEmpty ? null : direccion,
        fotoUrl: fotoUrl,
        fotos: fotos,
        dueno: dueno,
        verificada: false, // pendiente de verificación hasta validar al dueño
        horaApertura: _apertura,
        horaCierre: _cierre,
        duracionSlotMin: _duracion,
      );
      creadas.add(cancha);
      appState.agregarCancha(cancha);
    }

    // Verificación de EXISTENCIA en segundo plano (no bloquea el cierre). Confirma
    // que el local es real, pero NO te da la propiedad: la cancha queda "en
    // revisión de propiedad" hasta validar al dueño (código al teléfono del local,
    // aprobación manual o visita). Recién ahí se habilitan reservas.
    appState.verificarVenue(creadas,
        ruc: _ruc.text.trim(), razonSocial: nombre);

    // Modelo concierge: al reclamar/registrar se crea una SOLICITUD DE RECLAMO y
    // le llega un WhatsApp al equipo de Pichangol con un código para vetear al
    // dueño. Nada se activa hasta validarlo (revisión + visita en sitio).
    // Se ESPERA la respuesta para confirmar que el reclamo quedó en el servidor.
    bool reclamoOk = true;
    if (creadas.isNotEmpty) {
      final r = await PropiedadService.crearReclamo(
        canchaId: creadas.first.id,
        solicitanteId: dueno,
        nombreLocal: nombre,
        telefonoContacto: contacto,
        dni: dni,
        ruc: _ruc.text.trim(),
        relacion: _relacion,
        ubicacion: _ubicacion,
      );
      reclamoOk = r != null && r['ok'] == true;
    }

    if (!mounted) return;
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: reclamoOk ? verdeCancha : const Color(0xFFB4471F),
        content: Text(
            reclamoOk
                ? '✅ Reclamo enviado. En revisión: te contactaremos por WhatsApp '
                    'para validar que eres el dueño antes de activar la cancha.'
                : '⚠️ Cancha registrada, pero la solicitud no llegó al servidor. '
                    'Ábrela y toca "Reenviar solicitud de verificación".'),
        duration: const Duration(seconds: 5),
      ),
    );
  }

  void _avisar(String msg) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(_esReclamo ? 'Reclamar cancha' : 'Registrar cancha')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // La subida manual de fotos solo tiene sentido al CREAR una cancha
          // nueva. Al reclamar, las fotos ya vienen de Google y luego el dueño
          // conecta sus redes (tras verificar), así que aquí se oculta.
          if (!_esReclamo) ...[
            _ZonaFoto(foto: _foto, onTap: _elegirFoto),
            const SizedBox(height: 12),
            if (_analizando)
              Row(
                children: const [
                  SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2)),
                  SizedBox(width: 10),
                  Text('Analizando la foto con IA…'),
                ],
              )
            else if (_deteccion != null)
              _ResultadoIA(deteccion: _deteccion!),
          ] else
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(10)),
              child: Text(
                'Las fotos ya las trajimos de Google. Cuando verifiques que eres '
                'el dueño, podrás conectar tus redes e importar más.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: tinta),
              ),
            ),
          const SizedBox(height: 20),

          // ORDEN del reclamo: identidad primero (DNI, WhatsApp, relación, RUC),
          // luego nombre, dirección y mapa. Los deportes/precio/redes se
          // configuran DESPUÉS de aprobada la cancha.

          // DNI del reclamante (OBLIGATORIO): filtro de identidad. Dato personal
          // (Ley 29733): con consentimiento, solo lo ve el equipo para validar y
          // no se publica. Al completar 8 dígitos consulta sus datos (Factiliza).
          TextField(
            controller: _dni,
            keyboardType: TextInputType.number,
            maxLength: 8,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(8),
            ],
            onChanged: _consultarDni,
            decoration: InputDecoration(
              label: _lblReq('Tu DNI'),
              hintText: '8 dígitos — validamos tu identidad',
              prefixIcon: const Icon(Icons.badge_outlined, color: verdeCancha),
              suffixIcon: _dniCargando
                  ? const Padding(
                      padding: EdgeInsets.all(14),
                      child: SizedBox(
                          width: 16,
                          height: 16,
                          child:
                              CircularProgressIndicator(strokeWidth: 2)))
                  : null,
              counterText: '',
              border: const OutlineInputBorder(),
            ),
          ),
          if (_dniNombre != null)
            _ResultadoConsulta(icono: Icons.check_circle, texto: _dniNombre!)
          else
            Padding(
              padding: const EdgeInsets.only(top: 2, left: 4, bottom: 8),
              child: Text(
                'Tu DNI solo se usa para validar que eres el dueño. No se publica.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: textoTenue, fontSize: 11),
              ),
            ),
          const SizedBox(height: 8),

          // WhatsApp de contacto del dueño (OBLIGATORIO): por aquí el equipo de
          // Pichangol se comunica para validar el reclamo.
          TextField(
            controller: _contacto,
            keyboardType: TextInputType.phone,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(9),
            ],
            decoration: InputDecoration(
              label: _lblReq('Tu WhatsApp de contacto'),
              hintText: '987 654 321',
              prefixIcon: const _PrefijoPeru(),
              prefixIconConstraints: const BoxConstraints(minWidth: 76),
              suffixIcon: const Padding(
                padding: EdgeInsets.all(12),
                child: FaIcon(FontAwesomeIcons.whatsapp,
                    color: Color(0xFF25D366), size: 20),
              ),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 14),

          // Relación con la cancha (dueño / concesionario / arrendatario).
          DropdownButtonFormField<String>(
            value: _relacion,
            decoration: InputDecoration(
              label: _lblReq('Tu relación con la cancha'),
              prefixIcon:
                  const Icon(Icons.handshake_outlined, color: verdeCancha),
              border: const OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'dueño', child: Text('Dueño')),
              DropdownMenuItem(
                  value: 'concesionario', child: Text('Concesionario')),
              DropdownMenuItem(
                  value: 'arrendatario', child: Text('Arrendatario')),
            ],
            onChanged: (v) => setState(() => _relacion = v ?? 'dueño'),
          ),
          const SizedBox(height: 14),

          // RUC opcional (solo si quiere ser cliente formal). Al completar 11
          // dígitos consulta la razón social (Factiliza).
          TextField(
            controller: _ruc,
            keyboardType: TextInputType.number,
            maxLength: 11,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(11),
            ],
            onChanged: _consultarRuc,
            decoration: InputDecoration(
              labelText: 'RUC del negocio (opcional)',
              hintText: '11 dígitos — si quieres ser cliente formal',
              prefixIcon:
                  const Icon(Icons.verified_outlined, color: verdeCancha),
              suffixIcon: _rucCargando
                  ? const Padding(
                      padding: EdgeInsets.all(14),
                      child: SizedBox(
                          width: 16,
                          height: 16,
                          child:
                              CircularProgressIndicator(strokeWidth: 2)))
                  : null,
              counterText: '',
              border: const OutlineInputBorder(),
            ),
          ),
          if (_rucRazon != null)
            _ResultadoConsulta(icono: Icons.store, texto: _rucRazon!),
          const SizedBox(height: 14),

          // Nombre del local / cancha.
          TextField(
            controller: _nombre,
            decoration: InputDecoration(
              label: _lblReq('Nombre del local / cancha'),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 14),

          // Dirección + botón geocodificar (auto-ubica en el mapa).
          TextField(
            controller: _direccion,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _ubicarDireccion(),
            decoration: InputDecoration(
              label: _lblReq('Dirección (calle y número, distrito)'),
              hintText: 'Ej.: Av. Aviación 2345, San Borja',
              prefixIcon: const Icon(Icons.place, color: coral),
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
                      icon: const Icon(Icons.search, color: verdeCancha),
                      onPressed: _ubicarDireccion,
                    ),
            ),
          ),
          if (_errorGeo != null) ...[
            const SizedBox(height: 8),
            Text(_errorGeo!, style: const TextStyle(color: coralOscuro)),
          ],
          const SizedBox(height: 12),

          // Mapa de confirmación: marcador arrastrable + tocar para ajustar.
          _MapaUbicacion(
            inicial: _ubicacion ?? _limaCentro,
            ubicacion: _ubicacion,
            onMapCreated: (c) => _map = c,
            onElegir: _moverPin,
          ),
          const SizedBox(height: 6),
          Text(
            _ubicacion == null
                ? 'Escribe la dirección y toca buscar, o toca el mapa para marcar el punto.'
                : 'Arrastra el pin o toca el mapa: la dirección se actualiza sola.',
            style: const TextStyle(color: Colors.grey, fontSize: 12),
          ),
          const SizedBox(height: 18),

          // Deportes y precio: SOLO al crear una cancha nueva. Al reclamar, esto
          // (más fotos y redes) se configura DESPUÉS de aprobada la cancha.
          if (!_esReclamo) ...[
            const Text('¿Qué deportes hay en este local?',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            const Text('Puedes marcar más de uno.',
                style: TextStyle(color: Colors.grey, fontSize: 12)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 8,
              children: [
                for (final d in Deporte.values)
                  FilterChip(
                    avatar: Icon(iconoDeporte(d),
                        size: 18,
                        color: _deportes.contains(d)
                            ? Colors.white
                            : colorDeporte(d)),
                    label: Text(d.etiqueta),
                    selected: _deportes.contains(d),
                    selectedColor: colorDeporte(d),
                    checkmarkColor: Colors.white,
                    labelStyle: TextStyle(
                      color: _deportes.contains(d) ? Colors.white : tinta,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (s) => setState(() {
                      if (s) {
                        _deportes.add(d);
                      } else {
                        _deportes.remove(d);
                      }
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _precio,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'Precio por hora',
                prefixText: 'S/ ',
                border: OutlineInputBorder(),
              ),
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
          ] else
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                  color: const Color(0xFFEAF6C2),
                  borderRadius: BorderRadius.circular(10)),
              child: Text(
                'Los deportes, el precio y la conexión con tus redes los '
                'configuras cuando aprobemos tu cancha.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: tinta),
              ),
            ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: bosque,
                foregroundColor: lima,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
              onPressed: _publicar,
              icon: Icon(_esReclamo ? Icons.verified_user : Icons.send),
              label: Text(_esReclamo
                  ? 'Reclamar cancha'
                  : 'Enviar para validación'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Mapa de confirmación de ubicación con marcador arrastrable.
class _MapaUbicacion extends StatelessWidget {
  final LatLng inicial;
  final LatLng? ubicacion;
  final void Function(GoogleMapController) onMapCreated;
  final void Function(LatLng) onElegir;

  const _MapaUbicacion({
    required this.inicial,
    required this.ubicacion,
    required this.onMapCreated,
    required this.onElegir,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: SizedBox(
        height: 220,
        child: GoogleMap(
          initialCameraPosition: CameraPosition(
            target: inicial,
            zoom: ubicacion == null ? 11 : 16,
          ),
          onMapCreated: onMapCreated,
          myLocationButtonEnabled: false,
          zoomControlsEnabled: false,
          // Reclama los gestos para poder panear/ajustar el pin dentro del scroll.
          gestureRecognizers: <Factory<OneSequenceGestureRecognizer>>{
            Factory<OneSequenceGestureRecognizer>(
                () => EagerGestureRecognizer()),
          },
          onTap: onElegir,
          markers: ubicacion == null
              ? const {}
              : {
                  Marker(
                    markerId: const MarkerId('cancha'),
                    position: ubicacion!,
                    draggable: true,
                    onDragEnd: onElegir,
                  ),
                },
        ),
      ),
    );
  }
}

class _ZonaFoto extends StatelessWidget {
  final Uint8List? foto;
  final VoidCallback onTap;
  const _ZonaFoto({required this.foto, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 180,
        decoration: BoxDecoration(
          color: const Color(0xFFEAF6EF),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: verdeClaro),
        ),
        clipBehavior: Clip.antiAlias,
        child: foto == null
            ? Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Icon(Icons.add_a_photo, color: verdeCancha, size: 40),
                  SizedBox(height: 8),
                  Text('Sube una foto de la cancha',
                      style: TextStyle(
                          color: verdeOscuro, fontWeight: FontWeight.w600)),
                  Text('la IA detectará el deporte',
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                ],
              )
            : Image.memory(foto!, fit: BoxFit.cover, width: double.infinity),
      ),
    );
  }
}

class _ResultadoIA extends StatelessWidget {
  final DeteccionDeporte deteccion;
  const _ResultadoIA({required this.deteccion});

  @override
  Widget build(BuildContext context) {
    final pct = (deteccion.confianza * 100).round();
    final color = colorDeporte(deteccion.deporte);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color),
      ),
      child: Row(
        children: [
          Icon(Icons.auto_awesome, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'IA detectó: ${deteccion.deporte.etiqueta}  ·  $pct% de confianza',
              style: TextStyle(fontWeight: FontWeight.w600, color: color),
            ),
          ),
        ],
      ),
    );
  }
}

/// Prefijo de teléfono peruano: banderita 🇵🇪 + "+51".
class _PrefijoPeru extends StatelessWidget {
  const _PrefijoPeru();
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

/// Línea verde con el dato traído de Factiliza (nombre / razón social).
class _ResultadoConsulta extends StatelessWidget {
  final IconData icono;
  final String texto;
  const _ResultadoConsulta({required this.icono, required this.texto});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, left: 2, bottom: 6),
      child: Row(
        children: [
          Icon(icono, color: sage, size: 16),
          const SizedBox(width: 6),
          Expanded(
            child: Text(texto,
                style: const TextStyle(
                    color: tinta, fontWeight: FontWeight.w700, fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
