import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:permission_handler/permission_handler.dart';

import '../services/llamada_service.dart';
import '../services/llamada_webrtc.dart';
import '../theme.dart';

/// Pantalla de llamada 1-a-1 tipo WhatsApp (WebRTC propio): video remoto a
/// pantalla completa, cámara propia en PiP, nombre + estado/duración y los
/// controles (silenciar, altavoz, cámara, voltear, colgar). Sirve para el que
/// llama ([iniciar]=true) y el que contesta ([iniciar]=false).
class LlamadaScreen extends StatefulWidget {
  const LlamadaScreen({
    super.key,
    required this.callId,
    required this.video,
    required this.iniciar,
    this.nombreOtro = '',
    this.fotoUrl = '',
    this.emailOtro = '',
    this.reattach = false,
    this.modoEntrante = false,
  });

  final String callId;
  final bool video;
  final bool iniciar; // true = yo llamo; false = yo contesto
  final String nombreOtro;
  final String fotoUrl;
  final String emailOtro;
  // reattach = solo VOLVER a mostrar una llamada que ya está en curso (no
  // arranca nada). Lo usa la barra "volver a la llamada" y el resume.
  final bool reattach;
  // modoEntrante = pantalla de llamada ENTRANTE dentro de la app (Contestar/
  // Rechazar) ANTES de atender. Fallback para equipos (Xiaomi/HyperOS) donde el
  // botón "Contestar" de la notificación de CallKit no llega. Al contestar,
  // recién arranca el WebRTC (como si `iniciar=false`).
  final bool modoEntrante;

  @override
  State<LlamadaScreen> createState() => _LlamadaScreenState();
}

class _LlamadaScreenState extends State<LlamadaScreen> {
  final _svc = LlamadaWebRTC.instance;
  Timer? _tick;
  String? _error; // si falla arrancar (p. ej. sin permiso de mic/cámara)
  bool _errorPermiso = false; // el error es por permisos → mostrar "Ajustes"
  // En modo entrante: false hasta que el usuario toca "Contestar" (recién ahí
  // se arranca el WebRTC). Mientras, se muestra la pantalla de entrante.
  bool _entranteContestada = false;
  // Tono de timbre de la pantalla de entrante in-app (en Xiaomi/HyperOS el tono
  // de CallKit muere al segundo porque la app toma el frente: aquí lo suplimos).
  AudioPlayer? _tono;
  Timer? _tonoTimer;

  @override
  void initState() {
    super.initState();
    LlamadaWebRTC.pantallaVisible = true;
    _svc.addListener(_onCambio);
    // reattach = solo volver a mostrar una llamada en curso: NO arranca nada.
    // modoEntrante = espera a que el usuario toque "Contestar" para arrancar.
    if (!widget.reattach && !widget.modoEntrante) _arrancar();
    if (widget.modoEntrante && !widget.reattach) _iniciarTono();
    // Refresca la duración cada segundo.
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _svc.estado == EstadoLlamada.enLlamada) setState(() {});
    });
  }

  /// Pide permiso de micrófono (y cámara si es video) JUSTO antes de la llamada,
  /// como WhatsApp. Devuelve true si están concedidos.
  Future<bool> _asegurarPermisos() async {
    try {
      final mic = await Permission.microphone.request();
      var cam = PermissionStatus.granted;
      if (widget.video) cam = await Permission.camera.request();
      final faltaMic = !mic.isGranted;
      final faltaCam = widget.video && !cam.isGranted;
      if (faltaMic || faltaCam) {
        final permanente = mic.isPermanentlyDenied ||
            (widget.video && cam.isPermanentlyDenied);
        if (mounted) {
          setState(() {
            _errorPermiso = permanente;
            _error = widget.video
                ? 'Pichangol necesita permiso de micrófono y cámara para las '
                    'videollamadas.'
                : 'Pichangol necesita permiso de micrófono para las llamadas.';
          });
        }
        try {
          await _svc.finalizar(avisar: false);
        } catch (_) {}
        return false;
      }
      return true;
    } catch (_) {
      return true; // si algo falla, que getUserMedia lo intente
    }
  }

  Future<void> _arrancar() async {
    // Permisos primero (estilo WhatsApp): sin ellos, no arrancamos media.
    if (!await _asegurarPermisos()) return;
    try {
      if (widget.iniciar) {
        await _svc.iniciar(
            callId: widget.callId,
            video: widget.video,
            nombreOtro: widget.nombreOtro,
            fotoOtro: widget.fotoUrl,
            emailOtro: widget.emailOtro);
      } else {
        await _svc.contestar(
            callId: widget.callId,
            video: widget.video,
            nombreOtro: widget.nombreOtro,
            fotoOtro: widget.fotoUrl,
            emailOtro: widget.emailOtro);
      }
    } catch (e) {
      // No cerramos de golpe (se veía como "la pantalla no abre"): mostramos el
      // motivo (típicamente falta permiso de micrófono/cámara) y dejamos salir.
      if (mounted) {
        setState(() {
          _error = widget.video
              ? 'No se pudo acceder al micrófono o la cámara. Revisa los '
                  'permisos de Pichangol y vuelve a intentar.'
              : 'No se pudo acceder al micrófono. Revisa los permisos de '
                  'Pichangol y vuelve a intentar.';
        });
      }
      try {
        await _svc.finalizar(avisar: false);
      } catch (_) {}
    }
  }

  /// Timbre de la pantalla de entrante in-app: repite el jingle "Pichan" en
  /// cadencia de timbre (cada ~2.2 s) + vibración leve, hasta contestar/salir.
  void _iniciarTono() {
    try {
      _tono = AudioPlayer();
      void sonar() {
        try {
          _tono?.play(AssetSource('sonidos/pichan.mp3'));
          HapticFeedback.mediumImpact();
        } catch (_) {}
      }

      sonar();
      _tonoTimer = Timer.periodic(
          const Duration(milliseconds: 2200), (_) => sonar());
    } catch (_) {}
  }

  void _detenerTono() {
    _tonoTimer?.cancel();
    _tonoTimer = null;
    try {
      _tono?.stop();
      _tono?.dispose();
    } catch (_) {}
    _tono = null;
  }

  /// El usuario tocó "Contestar" en la pantalla de entrante in-app.
  Future<void> _contestarEntrante() async {
    _detenerTono();
    setState(() => _entranteContestada = true);
    await LlamadaService.aceptarEntranteEnApp(widget.callId);
    await _arrancar(); // iniciar=false → atiende (contestar)
  }

  /// El usuario tocó "Rechazar" en la pantalla de entrante in-app.
  Future<void> _rechazarEntrante() async {
    _detenerTono();
    await LlamadaService.rechazarEntranteEnApp(widget.callId);
    _cerrar();
  }

  void _onCambio() {
    if (!mounted) return;
    // En modo entrante, antes de contestar, no reacciones a cambios del motor
    // (no hay llamada arrancada todavía).
    if (widget.modoEntrante && !_entranteContestada) return;
    // Si estamos mostrando un error de arranque, no cierres solo: deja que el
    // usuario lea el motivo y salga con el botón.
    if (_error != null) {
      setState(() {});
      return;
    }
    if (_svc.estado == EstadoLlamada.finalizada) {
      _cerrar();
    } else {
      setState(() {});
    }
  }

  Future<void> _colgar() async {
    await _svc.finalizar();
  }

  void _cerrar() {
    if (Navigator.of(context).canPop()) Navigator.of(context).pop();
  }

  @override
  void dispose() {
    LlamadaWebRTC.pantallaVisible = false;
    _detenerTono();
    _tick?.cancel();
    _svc.removeListener(_onCambio);
    super.dispose();
  }

  String _estadoTexto() {
    switch (_svc.estado) {
      case EstadoLlamada.llamando:
        return 'Llamando…';
      case EstadoLlamada.conectando:
        return 'Conectando…';
      case EstadoLlamada.enLlamada:
        return _duracion();
      default:
        return '';
    }
  }

  String _duracion() {
    final ini = _svc.conectadoEn;
    if (ini == null) return '00:00';
    final d = DateTime.now().difference(ini);
    final m = d.inMinutes.toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) return _pantallaError();
    // Entrante dentro de la app: mostrar Contestar/Rechazar hasta que conteste.
    if (widget.modoEntrante && !_entranteContestada) return _pantallaEntrante();
    final enLlamada = _svc.estado == EstadoLlamada.enLlamada;
    final hayVideoRemoto = _svc.video && _svc.remoto.srcObject != null;
    // canPop:true → "atrás" MINIMIZA la llamada (no la corta): se cierra la
    // pantalla, la llamada sigue viva y aparece la barra "volver a la llamada".
    return PopScope(
      canPop: true,
      child: Scaffold(
        backgroundColor: const Color(0xFF0B141A),
        body: Stack(
          fit: StackFit.expand,
          children: [
            // Fondo: video remoto o avatar/degradado.
            if (hayVideoRemoto)
              RTCVideoView(_svc.remoto,
                  objectFit:
                      RTCVideoViewObjectFit.RTCVideoViewObjectFitCover)
            else
              _fondoAvatar(),

            // Cámara propia (PiP) arriba a la derecha, solo si es videollamada.
            if (_svc.video)
              Positioned(
                top: 48,
                right: 16,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(14),
                  child: SizedBox(
                    width: 108,
                    height: 150,
                    child: _svc.camOn
                        ? RTCVideoView(_svc.local,
                            mirror: true,
                            objectFit: RTCVideoViewObjectFit
                                .RTCVideoViewObjectFitCover)
                        : Container(
                            color: const Color(0xFF1F2C34),
                            child: const Icon(Icons.videocam_off,
                                color: Colors.white54)),
                  ),
                ),
              ),

            // Nombre + estado arriba.
            Positioned(
              top: 54,
              left: 20,
              right: 140,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.nombreOtro.isEmpty ? 'Pichangol' : widget.nombreOtro,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(_estadoTexto(),
                      style: const TextStyle(
                          color: Colors.white70, fontSize: 14)),
                ],
              ),
            ),

            // Controles abajo.
            Positioned(
              left: 0,
              right: 0,
              bottom: 40,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _boton(
                        icono: _svc.micOn ? Icons.mic : Icons.mic_off,
                        activo: !_svc.micOn,
                        onTap: _svc.alternarMic,
                      ),
                      const SizedBox(width: 18),
                      _boton(
                        icono: _svc.altavoz ? Icons.volume_up : Icons.hearing,
                        activo: _svc.altavoz,
                        onTap: _svc.alternarAltavoz,
                      ),
                      if (_svc.video) ...[
                        const SizedBox(width: 18),
                        _boton(
                          icono:
                              _svc.camOn ? Icons.videocam : Icons.videocam_off,
                          activo: !_svc.camOn,
                          onTap: _svc.alternarCam,
                        ),
                        const SizedBox(width: 18),
                        _boton(
                          icono: Icons.cameraswitch,
                          activo: false,
                          onTap: _svc.voltearCamara,
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 26),
                  // Colgar.
                  GestureDetector(
                    onTap: _colgar,
                    child: Container(
                      width: 68,
                      height: 68,
                      decoration: const BoxDecoration(
                          color: clayOscuro, shape: BoxShape.circle),
                      child: const Icon(Icons.call_end,
                          color: Colors.white, size: 32),
                    ),
                  ),
                ],
              ),
            ),
            if (!enLlamada) _velo(),
          ],
        ),
      ),
    );
  }

  /// Pantalla de llamada ENTRANTE dentro de la app (Contestar/Rechazar).
  Widget _pantallaEntrante() {
    final nombre =
        widget.nombreOtro.isEmpty ? 'Pichangol' : widget.nombreOtro;
    return PopScope(
      canPop: true,
      child: Scaffold(
        backgroundColor: const Color(0xFF0B141A),
        body: Stack(
          fit: StackFit.expand,
          children: [
            _fondoAvatar(),
            Positioned.fill(
              child: IgnorePointer(
                child: Container(color: Colors.black.withOpacity(0.25)),
              ),
            ),
            // Nombre + tipo de llamada arriba.
            Positioned(
              top: 96,
              left: 24,
              right: 24,
              child: Column(
                children: [
                  Text(
                    nombre,
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 26,
                        fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    widget.video
                        ? 'Videollamada de Pichangol…'
                        : 'Llamada de Pichangol…',
                    style: const TextStyle(color: Colors.white70, fontSize: 15),
                  ),
                ],
              ),
            ),
            // Botones Rechazar / Contestar abajo.
            Positioned(
              left: 0,
              right: 0,
              bottom: 56,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _accionEntrante(
                    icono: Icons.call_end,
                    color: clayOscuro,
                    etiqueta: 'Rechazar',
                    onTap: _rechazarEntrante,
                  ),
                  _accionEntrante(
                    icono: widget.video ? Icons.videocam : Icons.call,
                    color: const Color(0xFF128C7E),
                    etiqueta: 'Contestar',
                    onTap: _contestarEntrante,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _accionEntrante({
    required IconData icono,
    required Color color,
    required String etiqueta,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            child: Icon(icono, color: Colors.white, size: 32),
          ),
          const SizedBox(height: 10),
          Text(etiqueta,
              style: const TextStyle(color: Colors.white, fontSize: 14)),
        ],
      ),
    );
  }

  Widget _pantallaError() {
    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.mic_off, color: Colors.white70, size: 56),
              const SizedBox(height: 18),
              Text(
                _error ?? '',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 28),
              if (_errorPermiso) ...[
                FilledButton.icon(
                  onPressed: () => openAppSettings(),
                  icon: const Icon(Icons.settings),
                  label: const Text('Abrir ajustes'),
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 28, vertical: 14)),
                ),
                const SizedBox(height: 12),
              ],
              TextButton(
                onPressed: _cerrar,
                style: TextButton.styleFrom(foregroundColor: Colors.white70),
                child: const Text('Salir'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _fondoAvatar() {
    final foto = widget.fotoUrl;
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF14463A), Color(0xFF0B141A)],
        ),
      ),
      child: Center(
        child: CircleAvatar(
          radius: 64,
          backgroundColor: limaSuave,
          backgroundImage: foto.isNotEmpty
              ? CachedNetworkImageProvider(foto) as ImageProvider
              : null,
          child: foto.isEmpty
              ? const Icon(Icons.person, color: lima, size: 64)
              : null,
        ),
      ),
    );
  }

  // Un velo tenue mientras aún no conecta (para que el texto se lea).
  Widget _velo() => Positioned.fill(
        child: IgnorePointer(
          child: Container(color: Colors.black.withOpacity(0.12)),
        ),
      );

  Widget _boton({
    required IconData icono,
    required bool activo,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 56,
        height: 56,
        decoration: BoxDecoration(
          color: activo ? Colors.white : Colors.white24,
          shape: BoxShape.circle,
        ),
        child: Icon(icono,
            color: activo ? const Color(0xFF0B141A) : Colors.white, size: 26),
      ),
    );
  }
}
