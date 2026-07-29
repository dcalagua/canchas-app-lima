import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

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
  });

  final String callId;
  final bool video;
  final bool iniciar; // true = yo llamo; false = yo contesto
  final String nombreOtro;
  final String fotoUrl;

  @override
  State<LlamadaScreen> createState() => _LlamadaScreenState();
}

class _LlamadaScreenState extends State<LlamadaScreen> {
  final _svc = LlamadaWebRTC.instance;
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _svc.addListener(_onCambio);
    _arrancar();
    // Refresca la duración cada segundo.
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _svc.estado == EstadoLlamada.enLlamada) setState(() {});
    });
  }

  Future<void> _arrancar() async {
    try {
      if (widget.iniciar) {
        await _svc.iniciar(
            callId: widget.callId,
            video: widget.video,
            nombreOtro: widget.nombreOtro);
      } else {
        await _svc.contestar(
            callId: widget.callId,
            video: widget.video,
            nombreOtro: widget.nombreOtro);
      }
    } catch (_) {
      if (mounted) _cerrar();
    }
  }

  void _onCambio() {
    if (!mounted) return;
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
    final enLlamada = _svc.estado == EstadoLlamada.enLlamada;
    final hayVideoRemoto = _svc.video && _svc.remoto.srcObject != null;
    return PopScope(
      canPop: false,
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
