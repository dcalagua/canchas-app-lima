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
import '../services/location_service.dart';
import '../services/propiedad_service.dart';
import '../services/sport_detector.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import '../widgets/selector_horario.dart';
import 'login_google_sheet.dart';
import '../utils/moneda.dart';
import '../config/pais.dart';

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
  final _nombre = TextEditingController(); // nombre del LOCAL (club)
  final _nombreCancha = TextEditingController(); // nombre de la cancha (opcional)
  final _direccion = TextEditingController();
  final _precio = TextEditingController(text: '120.00');
  final _contacto = TextEditingController(); // WhatsApp del dueño (obligatorio)
  final _dni = TextEditingController(); // DNI del reclamante (OPCIONAL)
  final _nota = TextEditingController(); // nota para el equipo (OPCIONAL)
  Uint8List? _fotoEvidencia; // prueba de propiedad: fachada/cartel/recibo (OPC.)

  /// true cuando se está RECLAMANDO una cancha descubierta en Google (trae base).
  bool get _esReclamo => widget.base != null;

  // Resultado de la consulta a Factiliza (se muestra debajo del campo).
  String? _dniNombre;
  bool _dniCargando = false;

  /// Evita doble-envío (doble tap / red lenta): sin esto, cada envío genera un
  /// id de cancha nuevo (basado en timestamp) y por lo tanto un reclamo
  /// duplicado en el panel de administración.
  bool _enviando = false;

  /// Etiqueta con asterisco rojo para campos obligatorios.
  Widget _lblReq(String s) => Text.rich(TextSpan(text: s, children: const [
        TextSpan(
            text: ' *',
            style: TextStyle(
                color: Color(0xFFD11F2E), fontWeight: FontWeight.w900)),
      ]));

  Future<void> _consultarDni(String v) async {
    // Consulta automática donde hay registro oficial (Perú: DNI/RENIEC vía
    // Factiliza; Ecuador: cédula vía CipherByte). En otros países el documento
    // se ingresa sin verificación en línea.
    if (!paisActual.consultaDoc) return;
    final d = v.replaceAll(RegExp(r'[^0-9]'), '');
    if (d.length != (paisActual.docLongitud ?? 8)) {
      setState(() => _dniNombre = null);
      return;
    }
    setState(() => _dniCargando = true);
    final r = paisActual.iso == 'EC'
        ? await PropiedadService.consultarCedula(d)
        : await PropiedadService.consultarDni(d);
    if (!mounted) return;
    setState(() {
      _dniCargando = false;
      _dniNombre = (r != null && r['ok'] == true)
          ? (r['nombre_completo'] as String?)
          : null;
    });
  }

  // Deportes del local (varios a la vez). Fútbol viene marcado por defecto.
  final Set<Deporte> _deportes = {Deporte.futbol};
  // Tipo de piso por deporte (cuando son canchas SEPARADAS).
  final Map<Deporte, String> _superficies = {};
  // ¿Los deportes marcados se juegan en la MISMA cancha (loza multiuso)? Por
  // defecto sí (caso más común): una sola cancha con varios deportes y agenda
  // compartida. Si es false, se crean canchas separadas (una por deporte).
  bool _lozaMultiuso = true;
  // Tipo de piso ÚNICO cuando es loza multiuso (o un solo deporte).
  String _superficie = '';
  // El deporte "principal" (ícono/color): el primero según el orden de catálogo.
  Deporte get _deportePrincipal => deportesActivos.firstWhere(
        (d) => _deportes.contains(d),
        orElse: () => _deportes.isEmpty ? Deporte.futbol : _deportes.first,
      );
  // Superficies posibles para una loza multiuso: unión de las de cada deporte.
  List<String> get _superficiesUnion {
    final out = <String>[];
    for (final d in deportesActivos.where(_deportes.contains)) {
      for (final s in superficiesDe(d)) {
        if (!out.contains(s)) out.add(s);
      }
    }
    return out;
  }
  // ¿Se debe tratar como UNA sola cancha? (un solo deporte, o loza multiuso).
  bool get _esCanchaUnica => _deportes.length == 1 || _lozaMultiuso;

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
  // Centro inicial del mapa detectado por GPS (Perú/Bolivia/Ecuador…), para no
  // arrancar clavado en Lima cuando el dueño registra desde otro país/ciudad.
  LatLng? _centroInicial;

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
    } else {
      // Cancha nueva (sin ubicación fija): centra el mapa en donde está el dueño.
      _autoCentrarMapa();
    }
  }

  /// Detecta la ubicación del dueño y centra el mapa ahí (sin fijar el pin: el
  /// dueño confirma el punto exacto tocando/arrastrando o por dirección).
  Future<void> _autoCentrarMapa() async {
    // 1) Rápida (última conocida) para reubicar de inmediato; 2) precisa (GPS).
    final rapida = await LocationService.ultimaConocida();
    if (rapida != null) _aplicarCentro(rapida);
    final precisa = await LocationService.ubicacionActual();
    if (precisa != null) _aplicarCentro(precisa);
  }

  void _aplicarCentro(LatLng pos) {
    if (!mounted || _ubicacion != null) return; // no pisar un pin ya elegido
    setState(() => _centroInicial = pos); // por si el mapa aún no se creó
    _map?.animateCamera(CameraUpdate.newLatLngZoom(pos, 14));
  }

  @override
  void dispose() {
    _nombre.dispose();
    _nombreCancha.dispose();
    _direccion.dispose();
    _precio.dispose();
    _contacto.dispose();
    _dni.dispose();
    _nota.dispose();
    _map?.dispose();
    super.dispose();
  }

  /// Foto de EVIDENCIA (prueba de propiedad): fachada/cartel/recibo. Opcional; no
  /// pasa por la detección de deporte (no es la foto de la cancha). Cámara o
  /// galería para que el reclamante pueda tomarla en el momento.
  Future<void> _elegirEvidencia(ImageSource fuente) async {
    final XFile? file =
        await ImagePicker().pickImage(source: fuente, maxWidth: 1280);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() => _fotoEvidencia = bytes);
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
      final locs = await locationFromAddress('$q, ${paisActual.geocodeHint}');
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

  /// Best-effort desde las coordenadas, en UNA sola llamada de reverse-geocode:
  /// - `distrito`: clasificación gruesa heredada (Lima) para compat.
  /// - `barrio`: nombre REAL de la zona (sublocalidad/localidad), lo que ve el
  ///   usuario en cualquier país (ej. "Sopocachi", "Equipetrol", "San Borja").
  Future<(Distrito, String)> _zonaDe(LatLng p) async {
    var distrito = Distrito.sanBorja;
    var barrio = '';
    try {
      final marks = await placemarkFromCoordinates(p.latitude, p.longitude);
      for (final m in marks) {
        final sub = (m.subLocality ?? '').trim();
        final loc = (m.locality ?? '').trim();
        final sa = (m.subAdministrativeArea ?? '').trim();
        if (barrio.isEmpty) {
          barrio = sub.isNotEmpty ? sub : (loc.isNotEmpty ? loc : sa);
        }
        final texto = '$sub $loc $sa'.toLowerCase();
        for (final d in Distrito.values) {
          if (texto.contains(d.etiqueta.toLowerCase())) {
            distrito = d;
            break;
          }
        }
      }
    } catch (_) {}
    return (distrito, barrio);
  }

  Future<void> _publicar() async {
    if (_enviando) return;
    setState(() => _enviando = true);
    try {
      await _publicarInterno();
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  Future<void> _publicarInterno() async {
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
    // Tipo de piso OBLIGATORIO (solo al crear cancha nueva; al reclamar, el piso
    // se define después en Editar). Una sola superficie para loza multiuso /
    // deporte único; una por deporte cuando son canchas separadas.
    if (!_esReclamo) {
      if (_esCanchaUnica) {
        if (_superficie.isEmpty) {
          _avisar('Marca el tipo de piso de la cancha.');
          return;
        }
      } else {
        final faltan =
            _deportes.where((d) => (_superficies[d] ?? '').isEmpty).toList();
        if (faltan.isNotEmpty) {
          _avisar(
              'Marca el tipo de piso de: ${faltan.map((d) => d.etiqueta).join(', ')}.');
          return;
        }
      }
    }
    final aMin = horaEnMinutos(_apertura), cMin = horaEnMinutos(_cierre);
    if (aMin == null || cMin == null || cMin <= aMin) {
      _avisar('El cierre debe ser después de la apertura.');
      return;
    }
    final contacto = _contacto.text.trim();
    if (contacto.replaceAll(RegExp(r'[^0-9]'), '').length < paisActual.telLongitud) {
      _avisar('Pon tu WhatsApp de contacto para que el equipo te valide.');
      return;
    }
    // Documento OPCIONAL: solo se valida el formato si el dueño lo escribió y el
    // país tiene un largo fijo (el CI boliviano no lo tiene → no se valida largo).
    final dni = _dni.text.trim();
    final dniDigs = dni.replaceAll(RegExp(r'[^0-9]'), '');
    final docLen = paisActual.docLongitud;
    if (docLen != null && dniDigs.isNotEmpty && dniDigs.length != docLen) {
      _avisar('Si pones tu ${docIdActual}, debe tener $docLen dígitos (o déjalo vacío).');
      return;
    }
    // Anti-fraude: para registrar/reclamar hay que identificarse con Google, así
    // la cancha queda atada a una cuenta real y pasa a verificación.
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'registrar tu cancha')) {
      if (mounted) _avisar('Inicia sesión para registrar tu cancha.');
      return;
    }
    if (!mounted) return;
    final precio =
        double.tryParse(_precio.text.trim().replaceAll(',', '.')) ?? 100;
    final direccion = _direccion.text.trim();

    // Regla: el envío real (geolocaliza la zona, sube la foto y crea el reclamo
    // en el servidor) demora → se muestra el preload de marca, no un spinner.
    final res = await conPreload(context, () async {
      final (distrito, barrio) = await _zonaDe(_ubicacion!);
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

      final deportes = _deportes.toList();
      final nombreCanchaInput = _nombreCancha.text.trim();
      final creadas = <Cancha>[];
      if (_esCanchaUnica) {
        // UNA sola cancha: un deporte, o loza multiuso (varios deportes, misma
        // superficie y AGENDA COMPARTIDA). El principal define ícono/color.
        final principal = _deportePrincipal;
        final nombreCancha = nombreCanchaInput.isNotEmpty
            ? nombreCanchaInput
            : (deportes.length == 1 ? '${principal.etiqueta} 1' : 'Cancha 1');
        final cancha = Cancha(
          id: 'u$ts',
          nombre: nombreCancha,
          club: nombre,
          distrito: distrito,
          barrio: barrio,
          deporte: principal,
          deportes: deportes, // todos los deportes jugables en esta loza
          precioHora: precio,
          ubicacion: _ubicacion!,
          clubFundador: false,
          digitalizada: true,
          direccion: direccion.isEmpty ? null : direccion,
          fotoUrl: fotoUrl,
          fotos: fotos,
          dueno: dueno,
          verificada: false,
          horaApertura: _apertura,
          horaCierre: _cierre,
          duracionSlotMin: _duracion,
          superficie: _superficie,
          // La moneda se congela por el país donde ESTÁ la cancha (su GPS), no
          // por el país del dispositivo del dueño: una cancha en La Paz cobra en
          // Bs aunque el dueño la registre desde Perú.
          moneda: monedaDeCoordenadas(
              _ubicacion!.latitude, _ubicacion!.longitude),
        );
        creadas.add(cancha);
        appState.agregarCancha(cancha);
      } else {
        // Canchas SEPARADAS: una Cancha por deporte (superficies y agendas propias).
        for (final dep in deportes) {
          final cancha = Cancha(
            id: 'u${ts}_${dep.name}',
            nombre: '${dep.etiqueta} 1',
            club: nombre, // el local es su propio club
            distrito: distrito,
            barrio: barrio,
            deporte: dep,
            deportes: [dep],
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
            superficie: _superficies[dep] ?? '',
            // Moneda por la ubicación real de la cancha, no por el país del
            // dispositivo del dueño (ver nota arriba).
            moneda: monedaDeCoordenadas(
                _ubicacion!.latitude, _ubicacion!.longitude),
          );
          creadas.add(cancha);
          appState.agregarCancha(cancha);
        }
      }

      // Verificación de EXISTENCIA en segundo plano (no bloquea el cierre).
      // Confirma que el local es real, pero NO te da la propiedad: la cancha
      // queda "en revisión de propiedad" hasta validar al dueño (código al
      // teléfono del local, aprobación manual o visita). Recién ahí hay reservas.
      appState.verificarVenue(creadas, razonSocial: nombre);

      // Modelo concierge: al reclamar/registrar se crea una SOLICITUD DE RECLAMO
      // y le llega un WhatsApp al equipo de Pichangol con un código para vetear
      // al dueño. Nada se activa hasta validarlo (revisión + visita en sitio).
      // Se ESPERA la respuesta para confirmar que el reclamo quedó en el servidor.
      var reclamoOk = true;
      var yaReclamada = false;
      if (creadas.isNotEmpty) {
        // GPS del dispositivo AL reclamar: el admin puede exigir (torre de
        // control) que coincida con la cancha para aprobar (anti-fraude).
        final desdeAqui = await LocationService.ubicacionPrecisa();
        // Prueba de propiedad (opcional): sube la foto de evidencia si la puso.
        var evidenciaUrl = '';
        if (_fotoEvidencia != null) {
          evidenciaUrl =
              await CanchasRepo.subirFoto('ev$ts', _fotoEvidencia!) ?? '';
        }
        final r = await PropiedadService.crearReclamo(
          canchaId: creadas.first.id,
          solicitanteId: dueno,
          solicitanteNombre: appState.usuario?.nombre ?? '',
          nombreLocal: nombre,
          fotoEvidenciaUrl: evidenciaUrl,
          notaReclamante: _nota.text.trim(),
          telefonoContacto: contacto,
          dni: dni, // opcional (puede ir vacío)
          ubicacion: _ubicacion,
          solicitanteUbicacion: desdeAqui,
        );
        reclamoOk = r != null && r['ok'] == true;
        yaReclamada = r != null && r['error'] == 'ya_reclamada';
      }

      // Si OTRO usuario ya reclamó esta cancha (o el mismo lugar), no puedes
      // reclamarla: revierte las canchas locales recién creadas.
      if (yaReclamada) {
        for (final c in creadas) {
          appState.eliminarCancha(c.id);
        }
      }
      return (
        creadas: creadas,
        reclamoOk: reclamoOk,
        yaReclamada: yaReclamada,
      );
    }, texto: 'Enviando tu solicitud…');

    final creadas = res.creadas;
    final reclamoOk = res.reclamoOk;
    final yaReclamada = res.yaReclamada;

    if (!mounted) return;
    // Devuelve la cancha creada (si no fue revertida) para que la ficha anterior
    // la re-resuelva por ID EXACTO y no "salte" a otra cancha del mismo lugar.
    Navigator.of(context)
        .pop(creadas.isNotEmpty && !yaReclamada ? creadas.first : null);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: (reclamoOk && !yaReclamada)
            ? verdeCancha
            : const Color(0xFFB4471F),
        content: Text(
            yaReclamada
                ? '⚠️ Esta cancha ya fue reclamada por otro usuario y está en '
                    'revisión. No puedes reclamarla.'
                : reclamoOk
                    ? '✅ ¡Listo! Tu cancha quedó EN REVISIÓN. Nuestro equipo la '
                        'valida y la activamos pronto; verás el estado en "Mis canchas".'
                    : '⚠️ Cancha registrada, pero la solicitud no llegó al '
                        'servidor. Ábrela y toca "Reenviar solicitud de verificación".'),
        duration: const Duration(seconds: 5),
      ),
    );
  }

  void _avisar(String msg) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  // ── WIZARD estilo Airbnb (pedido del director): pasos a pantalla
  // completa con título grande, barra de progreso segmentada y Atrás /
  // Siguiente. La lógica de guardado (_publicar) es la misma de siempre.
  int _paso = 0;

  List<({String titulo, String sub, List<Widget> hijos})> _pasosDe(
      BuildContext context) {
    if (_esReclamo) {
      return [
        (
          titulo: 'Ubica tu cancha',
          sub: 'Confirma el nombre del local y el punto exacto en el mapa. '
              'Las fotos ya las trajimos de Google.',
          hijos: [..._hijosNombre(context), ..._hijosMapa(context)],
        ),
        (
          titulo: 'Cuéntanos de ti',
          sub: 'El equipo usa estos datos solo para validar que el local es '
              'tuyo. Nada se publica.',
          hijos: _hijosContacto(context),
        ),
        (
          titulo: 'Revisa y envía',
          sub: 'Tu solicitud viaja a la torre de control de Pichangol; te '
              'avisamos con una notificación cuando quede aprobada.',
          hijos: _hijosResumen(context),
        ),
      ];
    }
    return [
      (
        titulo: 'Describe tu local',
        sub: 'Una buena foto y el nombre con el que te conocen tus clientes.',
        hijos: [..._hijosFoto(context), ..._hijosNombre(context)],
      ),
      (
        titulo: 'Ubícalo en el mapa',
        sub: 'Los jugadores te encuentran por este punto: afínalo bien.',
        hijos: _hijosMapa(context),
      ),
      (
        titulo: 'Deportes, precio y horario',
        sub: 'Qué se juega en tu local y cuánto cuesta la hora.',
        hijos: _hijosDeportes(context),
      ),
      (
        titulo: 'Cuéntanos de ti',
        sub: 'El equipo valida contigo por WhatsApp antes de activar tu local.',
        hijos: _hijosContacto(context),
      ),
    ];
  }

  /// Validación LIGERA por paso (la final la hace _publicar como siempre).
  bool _validarPaso(int i) {
    final esNombre = i == 0;
    final esUbicacion = _esReclamo ? i == 0 : i == 1;
    final esContacto = (_esReclamo && i == 1) || (!_esReclamo && i == 3);
    String? falta;
    if (esNombre && _nombre.text.trim().isEmpty) {
      falta = 'Ponle nombre al local para continuar.';
    }
    if (falta == null && esUbicacion && _direccion.text.trim().isEmpty) {
      falta = 'Escribe la dirección del local.';
    }
    if (falta == null && esContacto && _contacto.text.trim().isEmpty) {
      falta = 'Déjanos tu WhatsApp: es como el equipo valida contigo.';
    }
    if (falta != null) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(falta)));
      return false;
    }
    return true;
  }

  List<Widget> _hijosFoto(BuildContext context) => [
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
          const SizedBox(height: 20),
      ];

  List<Widget> _hijosNombre(BuildContext context) => [
          // Nombre del LOCAL (el negocio: agrupa todas sus canchas).
          TextField(
            controller: _nombre,
            decoration: InputDecoration(
              label: _lblReq('Nombre del local'),
              hintText: 'Ej.: Campo Deportivo Machuca',
            ),
          ),
          const SizedBox(height: 14),
          // Nombre de la CANCHA (opcional). Si se deja vacío, se nombra sola por
          // deporte ("Fútbol 1", "Tenis 1"…). Con varios deportes se ignora y
          // cada cancha se nombra por su deporte.
          TextField(
            controller: _nombreCancha,
            decoration: const InputDecoration(
              labelText: 'Nombre de la cancha (opcional)',
              hintText: 'Ej.: Cancha 1 — si lo dejas vacío la nombramos sola',
            ),
          ),
          const SizedBox(height: 14),
      ];

  List<Widget> _hijosMapa(BuildContext context) => [
          // Dirección + botón geocodificar (auto-ubica en el mapa).
          TextField(
            controller: _direccion,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _ubicarDireccion(),
            decoration: InputDecoration(
              label: _lblReq('Dirección (calle y número, distrito)'),
              hintText: 'Ej.: Av. Aviación 2345, San Borja',
              prefixIcon: const Icon(Icons.place, color: coral),
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
                      icon: Icon(Icons.search,
                          color: Theme.of(context).colorScheme.primary),
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
            inicial: _ubicacion ?? _centroInicial ?? _limaCentro,
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
      ];

  List<Widget> _hijosDeportes(BuildContext context) => [
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
                for (final d in deportesActivos)
                  FilterChip(
                    label: Text('${emojiDeporte(d)}  ${d.etiqueta}'),
                    selected: _deportes.contains(d),
                    selectedColor: colorDeporte(d),
                    checkmarkColor: Colors.white,
                    labelStyle: TextStyle(
                      color: _deportes.contains(d)
                          ? Colors.white
                          : Theme.of(context).colorScheme.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                    onSelected: (s) => setState(() {
                      if (s) {
                        _deportes.add(d);
                      } else {
                        _deportes.remove(d);
                        _superficies.remove(d); // se limpia su piso
                      }
                    }),
                  ),
              ],
            ),
            // Si marcó VARIOS deportes: ¿es la misma cancha (loza multiuso) o
            // canchas separadas? Define si se crea 1 cancha o N.
            if (_deportes.length > 1) ...[
              const SizedBox(height: 16),
              const Text('¿Cómo son estas canchas?',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 10,
                runSpacing: 8,
                children: [
                  ChoiceChip(
                    label: const Text('Una loza multiuso'),
                    selected: _lozaMultiuso,
                    selectedColor: lima,
                    labelStyle: TextStyle(
                        color: _lozaMultiuso
                            ? bosque
                            : Theme.of(context).colorScheme.onSurface,
                        fontWeight: FontWeight.w600),
                    onSelected: (_) => setState(() => _lozaMultiuso = true),
                  ),
                  ChoiceChip(
                    label: const Text('Canchas separadas'),
                    selected: !_lozaMultiuso,
                    selectedColor: lima,
                    labelStyle: TextStyle(
                        color: !_lozaMultiuso
                            ? bosque
                            : Theme.of(context).colorScheme.onSurface,
                        fontWeight: FontWeight.w600),
                    onSelected: (_) => setState(() => _lozaMultiuso = false),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                  _lozaMultiuso
                      ? 'Una sola cancha donde se juegan todos: misma superficie y '
                          'una sola agenda (reservar ocupa la cancha para todos).'
                      : 'Canchas físicas distintas: cada una con su superficie y '
                          'su propia agenda.',
                  style: const TextStyle(color: Colors.grey, fontSize: 12)),
            ],
            const SizedBox(height: 16),
            // Superficie: ÚNICA para loza multiuso / deporte único; una por
            // deporte cuando son canchas separadas.
            if (_esCanchaUnica) ...[
              const Text('Tipo de piso',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              const Text('Obligatorio: la superficie de la cancha.',
                  style: TextStyle(color: Colors.grey, fontSize: 12)),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final s in _superficiesUnion)
                    ChoiceChip(
                      avatar: Icon(iconoSuperficie(s),
                          size: 16,
                          color: _superficie == s ? Colors.white : textoTenue),
                      label: Text(s),
                      selected: _superficie == s,
                      selectedColor: lima,
                      labelStyle: TextStyle(
                          color: _superficie == s
                              ? Colors.white
                              : Theme.of(context).colorScheme.onSurface,
                          fontWeight: FontWeight.w600),
                      onSelected: (sel) =>
                          setState(() => _superficie = sel ? s : ''),
                    ),
                ],
              ),
              const SizedBox(height: 12),
            ] else ...[
              const Text('Tipo de piso de cada cancha',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              const Text('Obligatorio: elige la superficie de cada deporte.',
                  style: TextStyle(color: Colors.grey, fontSize: 12)),
              const SizedBox(height: 10),
              for (final d in deportesActivos.where(_deportes.contains)) ...[
                Row(
                  children: [
                    Text(emojiDeporte(d), style: const TextStyle(fontSize: 15)),
                    const SizedBox(width: 6),
                    Text(d.etiqueta,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                  ],
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final s in superficiesDe(d))
                      ChoiceChip(
                        avatar: Icon(iconoSuperficie(s),
                            size: 16,
                            color: _superficies[d] == s ? Colors.white : textoTenue),
                        label: Text(s),
                        selected: _superficies[d] == s,
                        selectedColor: lima,
                        labelStyle: TextStyle(
                            color: _superficies[d] == s
                                ? Colors.white
                                : Theme.of(context).colorScheme.onSurface,
                            fontWeight: FontWeight.w600),
                        onSelected: (sel) => setState(
                            () => _superficies[d] = sel ? s : ''),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
              ],
            ],
            const SizedBox(height: 4),
            TextField(
              controller: _precio,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Precio por hora',
                prefixText: '$monedaSimbolo ',
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
      ];

  List<Widget> _hijosContacto(BuildContext context) => [
          TextField(
            controller: _contacto,
            keyboardType: TextInputType.phone,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(paisActual.telLongitud),
            ],
            decoration: InputDecoration(
              label: _lblReq('Tu WhatsApp de contacto'),
              hintText: 'Tu número de celular',
              prefixIcon: const _PrefijoPeru(),
              prefixIconConstraints: const BoxConstraints(minWidth: 76),
              suffixIcon: const Padding(
                padding: EdgeInsets.all(12),
                child: FaIcon(FontAwesomeIcons.whatsapp,
                    color: Color(0xFF25D366), size: 20),
              ),
            ),
          ),
          const SizedBox(height: 14),
          // DNI OPCIONAL: acelera la validación. Dato personal (Ley 29733): solo
          // lo ve el equipo para validar y no se publica.
          TextField(
            controller: _dni,
            keyboardType: TextInputType.number,
            maxLength: paisActual.docLongitud,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(paisActual.docLongitud ?? 20),
            ],
            onChanged: _consultarDni,
            decoration: InputDecoration(
              labelText: 'Tu ${docIdActual} (opcional)',
              hintText: paisActual.consultaDoc
                  ? '${paisActual.docLongitud} dígitos — acelera la validación'
                  : 'Ayuda a validar que eres el dueño',
              prefixIcon: Icon(Icons.badge_outlined,
                  color: Theme.of(context).colorScheme.primary),
              suffixIcon: _dniCargando
                  ? const Padding(
                      padding: EdgeInsets.all(14),
                      child: SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2)))
                  : null,
              counterText: '',
            ),
          ),
          if (_dniNombre != null)
            _ResultadoConsulta(icono: Icons.check_circle, texto: _dniNombre!)
          else
            Padding(
              padding: const EdgeInsets.only(top: 2, left: 4),
              child: Text(
                'Tu ${docIdActual} solo se usa para validar que eres el dueño. No se publica.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: textoTenue, fontSize: 11),
              ),
            ),

          const SizedBox(height: 16),
          // PRUEBA DE PROPIEDAD (opcional): nota + foto (fachada/cartel/recibo).
          // Acelera el triage del equipo (no es obligatorio para reclamar).
          Text('Prueba de propiedad (opcional)',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          TextField(
            controller: _nota,
            maxLines: 2,
            maxLength: 240,
            decoration: const InputDecoration(
              labelText: 'Nota para el equipo',
              hintText: 'Ej.: soy el administrador, atendemos de 8am a 11pm.',
              counterText: '',
            ),
          ),
          const SizedBox(height: 10),
          _EvidenciaFoto(
            foto: _fotoEvidencia,
            onCamara: () => _elegirEvidencia(ImageSource.camera),
            onGaleria: () => _elegirEvidencia(ImageSource.gallery),
            onQuitar: () => setState(() => _fotoEvidencia = null),
          ),
      ];

  /// Paso final del RECLAMO: resumen de la solicitud + qué sigue.
  List<Widget> _hijosResumen(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget fila(IconData icono, String etiqueta, String valor) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 7),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icono, size: 18, color: lima),
              const SizedBox(width: 10),
              SizedBox(
                width: 86,
                child: Text(etiqueta,
                    style: t.bodySmall
                        ?.copyWith(color: textoTenueDe(context))),
              ),
              Expanded(
                child: Text(valor,
                    style:
                        t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
            ],
          ),
        );
    final dni = _dni.text.trim();
    final nota = _nota.text.trim();
    return [
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: trazo),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            fila(Icons.storefront, 'Local', _nombre.text.trim()),
            if (_nombreCancha.text.trim().isNotEmpty)
              fila(Icons.sports_soccer, 'Cancha', _nombreCancha.text.trim()),
            fila(Icons.place_outlined, 'Dirección', _direccion.text.trim()),
            fila(Icons.chat, 'WhatsApp', _contacto.text.trim()),
            if (dni.isNotEmpty)
              fila(Icons.badge_outlined, docIdActual,
                  _dniNombre != null ? '$dni · verificado ✓' : dni),
            if (_fotoEvidencia != null)
              fila(Icons.photo_camera_outlined, 'Evidencia',
                  'Foto adjunta ✓'),
            if (nota.isNotEmpty) fila(Icons.notes, 'Nota', nota),
          ],
        ),
      ),
      const SizedBox(height: 18),
      Text('¿Qué sigue?',
          style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 10),
      for (final (n, txt) in const [
        (1, 'El equipo de Pichangol revisa tu solicitud y te contacta por '
            'WhatsApp si necesita confirmar algo.'),
        (2, 'Cuando quede aprobada, te llega una notificación al celular.'),
        (3, 'Recién ahí configuras deportes, precios y horarios — y empiezas '
            'a recibir reservas.'),
      ])
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 24,
                height: 24,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                    color: limaSuave, shape: BoxShape.circle),
                child: Text('$n',
                    style: const TextStyle(
                        color: bosque,
                        fontWeight: FontWeight.w800,
                        fontSize: 12)),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(txt,
                    style: t.bodySmall?.copyWith(
                        color: textoTenueDe(context), height: 1.35)),
              ),
            ],
          ),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final pasos = _pasosDe(context);
    final i = _paso.clamp(0, pasos.length - 1);
    final p = pasos[i];
    final ultimo = i >= pasos.length - 1;
    final t = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Barra superior estilo Airbnb: pill "Salir" a la izquierda.
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Row(
                children: [
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor:
                          Theme.of(context).colorScheme.onSurface,
                      side: const BorderSide(color: trazo),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999)),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                    ),
                    onPressed: () async {
                      final ok = await confirmarPichangol(
                        context,
                        titulo: _esReclamo
                            ? '¿Salir del reclamo?'
                            : '¿Salir del registro?',
                        mensaje: 'Se perderá lo que llenaste hasta ahora.',
                        textoConfirmar: 'Salir',
                        icono: Icons.logout,
                      );
                      if (ok && context.mounted) {
                        Navigator.of(context).maybePop();
                      }
                    },
                    child: const Text('Salir',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: EdgeInsets.fromLTRB(ladoTablet(context, 20), 16,
                    ladoTablet(context, 20), 24),
                children: [
                  Text('Paso ${i + 1} de ${pasos.length}',
                      style: t.bodySmall?.copyWith(
                          color: textoTenueDe(context),
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text(p.titulo,
                      style: t.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w800, height: 1.05)),
                  const SizedBox(height: 8),
                  Text(p.sub,
                      style: t.bodyMedium?.copyWith(
                          color: textoTenueDe(context), height: 1.35)),
                  const SizedBox(height: 22),
                  ...p.hijos,
                ],
              ),
            ),
            // Progreso segmentado + Atrás / Siguiente (estilo Airbnb).
            Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                border: const Border(top: BorderSide(color: trazo)),
              ),
              padding: EdgeInsets.fromLTRB(ladoTablet(context, 20), 0,
                  ladoTablet(context, 20), 12),
              child: Column(
                children: [
                  Row(
                    children: [
                      for (var s = 0; s < pasos.length; s++)
                        Expanded(
                          child: Container(
                            height: 4,
                            margin: EdgeInsets.only(
                                right: s == pasos.length - 1 ? 0 : 6),
                            decoration: BoxDecoration(
                              color: s <= i
                                  ? lima
                                  : const Color(0xFFE4E4E4),
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      if (i > 0)
                        TextButton(
                          onPressed: _enviando
                              ? null
                              : () => setState(() => _paso = i - 1),
                          child: Text('Atrás',
                              style: TextStyle(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurface,
                                  fontWeight: FontWeight.w800,
                                  decoration: TextDecoration.underline)),
                        ),
                      const Spacer(),
                      FilledButton(
                        style: FilledButton.styleFrom(
                          backgroundColor: ultimo ? lima : tinta,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 26, vertical: 13),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: _enviando
                            ? null
                            : () {
                                if (ultimo) {
                                  _publicar();
                                  return;
                                }
                                if (!_validarPaso(i)) return;
                                setState(() => _paso = i + 1);
                              },
                        child: Text(
                            ultimo
                                ? (_esReclamo
                                    ? 'Enviar solicitud'
                                    : 'Enviar para validación')
                                : 'Siguiente',
                            style:
                                const TextStyle(fontWeight: FontWeight.w800)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
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

/// Selector de FOTO DE EVIDENCIA (prueba de propiedad): preview + tomar/elegir +
/// quitar. Estilo Airbnb (tarjeta blanca, borde suave). Opcional.
class _EvidenciaFoto extends StatelessWidget {
  final Uint8List? foto;
  final VoidCallback onCamara;
  final VoidCallback onGaleria;
  final VoidCallback onQuitar;
  const _EvidenciaFoto({
    required this.foto,
    required this.onCamara,
    required this.onGaleria,
    required this.onQuitar,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (foto != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Image.memory(foto!, height: 150, fit: BoxFit.cover),
          ),
          const SizedBox(height: 6),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: onQuitar,
              icon: const Icon(Icons.close, size: 16),
              label: const Text('Quitar foto'),
            ),
          ),
        ],
      );
    }
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onCamara,
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text('Tomar foto'),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onGaleria,
            icon: Icon(Icons.image_outlined, color: cs.primary),
            label: const Text('Galería'),
          ),
        ),
      ],
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

/// Prefijo de teléfono según el país detectado: bandera + código (ej. 🇧🇴 +591).
class _PrefijoPeru extends StatelessWidget {
  const _PrefijoPeru();
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 12, right: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(banderaActual, style: const TextStyle(fontSize: 18)),
          const SizedBox(width: 4),
          Text(codigoTelActual,
              style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: Theme.of(context).colorScheme.onSurface)),
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
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w700,
                    fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
