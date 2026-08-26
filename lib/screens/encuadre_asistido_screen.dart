import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_mlkit_pose_detection/google_mlkit_pose_detection.dart';

import '../theme.dart';

/// ENCUADRE ASISTIDO 📐 — cámara PROPIA del entrenador virtual.
///
/// La cámara detecta tu cuerpo en vivo (ML Kit Pose, on-device) y te guía al
/// ángulo que el coach necesita: "retrocede unos pasos", "no se ven tus pies",
/// "gírate de costado". Cuando el encuadre queda bien un instante, corre la
/// cuenta 3-2-1 (con vibración, para que la sientas sin mirar la pantalla) y
/// graba solo. El clip nace en el espacio PRIVADO del app — nunca pasa por la
/// galería del teléfono — y quien lo recibe (entrenador_screen) lo borra
/// apenas lo sube. Devuelve la ruta del clip vía `Navigator.pop`.
class EncuadreAsistidoScreen extends StatefulWidget {
  const EncuadreAsistidoScreen(
      {super.key, required this.deporte, required this.golpe});

  final String deporte;
  final String golpe;

  @override
  State<EncuadreAsistidoScreen> createState() => _EncuadreAsistidoScreenState();
}

class _EncuadreAsistidoScreenState extends State<EncuadreAsistidoScreen> {
  static const int _segundosMax = 10; // clip corto: el coach ve mejor 5-10 s

  CameraController? _camara;
  List<CameraDescription> _camaras = const [];
  int _camIndex = 0;
  final PoseDetector _detector = PoseDetector(
    options: PoseDetectorOptions(
      model: PoseDetectionModel.base,
      mode: PoseDetectionMode.stream,
    ),
  );

  bool _procesandoFrame = false;
  bool _streamActivo = false;
  int _framesOk = 0; // frames seguidos con buen encuadre
  String _guia = 'Buscándote… ponte donde la cámara te vea completo';
  bool _encuadreOk = false;

  int _cuenta = 0; // 3-2-1 (0 = sin cuenta)
  Timer? _timerCuenta;
  bool _grabando = false;
  int _segundosGrabados = 0;
  Timer? _timerGrabacion;
  bool _cerrando = false;
  String? _error;

  // Los deportes de raqueta se analizan mejor de PERFIL; en los de equipo
  // (penal, tiro libre…) el ángulo frontal o diagonal es válido.
  bool get _pideCostado =>
      const {'tenis', 'padel', 'pickleball'}.contains(widget.deporte);

  @override
  void initState() {
    super.initState();
    _iniciar();
  }

  Future<void> _iniciar() async {
    try {
      _camaras = await availableCameras();
      if (_camaras.isEmpty) {
        setState(() => _error = 'Este equipo no tiene cámara disponible.');
        return;
      }
      // Trasera por defecto (lo normal: teléfono apoyado o un amigo grabando).
      _camIndex = _camaras.indexWhere(
          (c) => c.lensDirection == CameraLensDirection.back);
      if (_camIndex < 0) _camIndex = 0;
      await _abrirCamara();
    } on CameraException catch (e) {
      setState(() => _error = e.code == 'CameraAccessDenied'
          ? 'Pichangol necesita permiso de cámara. Actívalo en Ajustes → '
              'Apps → Pichangol → Permisos.'
          : 'No se pudo abrir la cámara (${e.code}).');
    } catch (e) {
      setState(() => _error = 'No se pudo abrir la cámara.');
    }
  }

  Future<void> _abrirCamara() async {
    final vieja = _camara;
    _camara = null;
    _streamActivo = false;
    if (vieja != null) {
      try {
        await vieja.dispose();
      } catch (_) {}
    }
    final ctrl = CameraController(
      _camaras[_camIndex],
      ResolutionPreset.medium,
      enableAudio: false, // el coach no necesita audio (y evita un permiso)
      imageFormatGroup: Platform.isAndroid
          ? ImageFormatGroup.nv21
          : ImageFormatGroup.bgra8888,
    );
    await ctrl.initialize();
    if (!mounted) return;
    setState(() {
      _camara = ctrl;
      _error = null;
    });
    await ctrl.startImageStream(_onFrame);
    _streamActivo = true;
  }

  Future<void> _cambiarCamara() async {
    if (_camaras.length < 2 || _grabando || _cuenta > 0) return;
    _camIndex = (_camIndex + 1) % _camaras.length;
    _framesOk = 0;
    await _abrirCamara();
  }

  // ---------- Detección en vivo ----------

  static const _rotaciones = <DeviceOrientation, int>{
    DeviceOrientation.portraitUp: 0,
    DeviceOrientation.landscapeLeft: 90,
    DeviceOrientation.portraitDown: 180,
    DeviceOrientation.landscapeRight: 270,
  };

  InputImage? _aInputImage(CameraImage img) {
    final ctrl = _camara;
    if (ctrl == null) return null;
    final cam = _camaras[_camIndex];
    InputImageRotation? rot;
    if (Platform.isIOS) {
      rot = InputImageRotationValue.fromRawValue(cam.sensorOrientation);
    } else {
      var comp = _rotaciones[ctrl.value.deviceOrientation] ?? 0;
      comp = cam.lensDirection == CameraLensDirection.front
          ? (cam.sensorOrientation + comp) % 360
          : (cam.sensorOrientation - comp + 360) % 360;
      rot = InputImageRotationValue.fromRawValue(comp);
    }
    final fmt = InputImageFormatValue.fromRawValue(img.format.raw);
    if (rot == null || fmt == null || img.planes.isEmpty) return null;
    final plano = img.planes.first;
    return InputImage.fromBytes(
      bytes: plano.bytes,
      metadata: InputImageMetadata(
        size: Size(img.width.toDouble(), img.height.toDouble()),
        rotation: rot,
        format: fmt,
        bytesPerRow: plano.bytesPerRow,
      ),
    );
  }

  Future<void> _onFrame(CameraImage img) async {
    if (_procesandoFrame || _cuenta > 0 || _grabando || _cerrando) return;
    _procesandoFrame = true;
    try {
      final input = _aInputImage(img);
      if (input == null) return;
      final poses = await _detector.processImage(input);
      if (!mounted || _cuenta > 0 || _grabando) return;
      final rot = input.metadata!.rotation;
      final girada = rot == InputImageRotation.rotation90deg ||
          rot == InputImageRotation.rotation270deg;
      final w = girada ? img.height.toDouble() : img.width.toDouble();
      final h = girada ? img.width.toDouble() : img.height.toDouble();
      final mensaje = poses.isEmpty
          ? 'Buscándote… ponte donde la cámara te vea completo'
          : _evaluarEncuadre(poses.first, w, h);
      final ok = mensaje == null;
      _framesOk = ok ? _framesOk + 1 : 0;
      setState(() {
        _encuadreOk = ok;
        _guia = mensaje ?? '¡Encuadre perfecto! Quédate ahí…';
      });
      // ~4 frames buenos seguidos (≈1 s de estabilidad) → cuenta regresiva.
      if (_framesOk >= 4) _arrancarCuenta();
    } catch (_) {
      // Un frame malo no rompe la guía; se intenta con el siguiente.
    } finally {
      _procesandoFrame = false;
    }
  }

  /// Devuelve la corrección a pedir, o null si el encuadre está listo.
  String? _evaluarEncuadre(Pose pose, double w, double h) {
    PoseLandmark? p(PoseLandmarkType t) {
      final lm = pose.landmarks[t];
      return (lm != null && lm.likelihood >= 0.5) ? lm : null;
    }

    final nariz = p(PoseLandmarkType.nose);
    final tobIzq = p(PoseLandmarkType.leftAnkle);
    final tobDer = p(PoseLandmarkType.rightAnkle);
    if (nariz == null) return 'No se ve tu cabeza — sube o aleja el teléfono';
    if (tobIzq == null && tobDer == null) {
      return 'No se ven tus pies — aleja o inclina el teléfono';
    }
    final visibles = pose.landmarks.values
        .where((lm) => lm.likelihood >= 0.5)
        .toList();
    double minY = h, maxY = 0, sumX = 0;
    for (final lm in visibles) {
      if (lm.y < minY) minY = lm.y;
      if (lm.y > maxY) maxY = lm.y;
      sumX += lm.x;
    }
    final altura = (maxY - minY) / h;
    if (altura > 0.92) return 'Retrocede unos pasos 👣';
    if (altura < 0.35) return 'Acércate un poco';
    final centroX = (sumX / visibles.length) / w;
    if (centroX < 0.22 || centroX > 0.78) return 'Ponte al centro del cuadro';
    if (_pideCostado) {
      final hi = p(PoseLandmarkType.leftShoulder);
      final hd = p(PoseLandmarkType.rightShoulder);
      if (hi != null && hd != null && maxY > minY) {
        final anchoHombros = (hi.x - hd.x).abs() / (maxY - minY);
        // Hombros muy "anchos" respecto a la altura = estás de frente.
        if (anchoHombros > 0.30) {
          return 'Gírate de costado (perfil a la cámara)';
        }
      }
    }
    return null;
  }

  // ---------- Cuenta 3-2-1 y grabación ----------

  void _arrancarCuenta() {
    if (_cuenta > 0 || _grabando || _cerrando) return;
    HapticFeedback.heavyImpact();
    setState(() => _cuenta = 3);
    _timerCuenta = Timer.periodic(const Duration(seconds: 1), (t) async {
      if (!mounted) {
        t.cancel();
        return;
      }
      if (_cuenta > 1) {
        HapticFeedback.heavyImpact();
        setState(() => _cuenta -= 1);
      } else {
        t.cancel();
        setState(() => _cuenta = 0);
        await _empezarGrabacion();
      }
    });
  }

  Future<void> _empezarGrabacion() async {
    final ctrl = _camara;
    if (ctrl == null || _grabando || _cerrando) return;
    try {
      if (_streamActivo) {
        await ctrl.stopImageStream();
        _streamActivo = false;
      }
      await ctrl.startVideoRecording();
      HapticFeedback.vibrate(); // "¡ya!": vibración larga = grabando
      if (!mounted) return;
      setState(() {
        _grabando = true;
        _segundosGrabados = 0;
      });
      _timerGrabacion = Timer.periodic(const Duration(seconds: 1), (t) {
        if (!mounted) {
          t.cancel();
          return;
        }
        setState(() => _segundosGrabados += 1);
        if (_segundosGrabados >= _segundosMax) {
          t.cancel();
          _terminarGrabacion();
        }
      });
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'No se pudo grabar. Inténtalo de nuevo.');
      }
    }
  }

  Future<void> _terminarGrabacion() async {
    final ctrl = _camara;
    if (ctrl == null || !_grabando || _cerrando) return;
    _cerrando = true;
    _timerGrabacion?.cancel();
    try {
      final XFile clip = await ctrl.stopVideoRecording();
      HapticFeedback.mediumImpact();
      if (!mounted) return;
      Navigator.pop(context, clip.path);
    } catch (_) {
      _cerrando = false;
      if (mounted) {
        setState(() {
          _grabando = false;
          _error = 'La grabación falló. Inténtalo de nuevo.';
        });
      }
    }
  }

  @override
  void dispose() {
    _timerCuenta?.cancel();
    _timerGrabacion?.cancel();
    final ctrl = _camara;
    if (ctrl != null) {
      Future(() async {
        try {
          if (_streamActivo) await ctrl.stopImageStream();
        } catch (_) {}
        try {
          if (ctrl.value.isRecordingVideo) await ctrl.stopVideoRecording();
        } catch (_) {}
        try {
          await ctrl.dispose();
        } catch (_) {}
      });
    }
    _detector.close();
    super.dispose();
  }

  // ---------- UI ----------

  @override
  Widget build(BuildContext context) {
    final ctrl = _camara;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          if (ctrl != null && ctrl.value.isInitialized)
            Center(
              child: AspectRatio(
                aspectRatio: 1 / ctrl.value.aspectRatio,
                child: CameraPreview(ctrl),
              ),
            )
          else
            Center(
              child: _error != null
                  ? Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(_error!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 14.5)),
                    )
                  : const CircularProgressIndicator(color: lima),
            ),
          // Marco guía: la zona vertical donde debe caber el cuerpo completo.
          if (ctrl != null && !_grabando)
            IgnorePointer(
              child: Center(
                child: FractionallySizedBox(
                  heightFactor: 0.78,
                  widthFactor: 0.52,
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(28),
                      border: Border.all(
                        color: _encuadreOk
                            ? lima
                            : Colors.white.withOpacity(0.55),
                        width: _encuadreOk ? 3 : 2,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          // Cuenta regresiva gigante.
          if (_cuenta > 0)
            Center(
              child: Text(
                '$_cuenta',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 120,
                  fontWeight: FontWeight.w800,
                  shadows: [Shadow(color: Colors.black54, blurRadius: 16)],
                ),
              ),
            ),
          // Barra superior: cerrar + golpe + cambiar cámara.
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Row(
                    children: [
                      IconButton(
                        onPressed:
                            _grabando ? null : () => Navigator.pop(context),
                        icon: const Icon(Icons.close,
                            color: Colors.white, size: 28),
                      ),
                      Expanded(
                        child: Text(
                          '${widget.golpe} · ${widget.deporte}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 15),
                        ),
                      ),
                      IconButton(
                        onPressed: _cambiarCamara,
                        icon: const Icon(Icons.cameraswitch_outlined,
                            color: Colors.white, size: 26),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                // Pastilla de guía (o estado de grabación) + controles.
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 18),
                  child: Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 10),
                        decoration: BoxDecoration(
                          color: _grabando
                              ? const Color(0xE6C62828)
                              : (_encuadreOk
                                  ? bosque.withOpacity(0.92)
                                  : Colors.black.withOpacity(0.65)),
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (_grabando) ...[
                              const Icon(Icons.fiber_manual_record,
                                  color: Colors.white, size: 16),
                              const SizedBox(width: 8),
                            ],
                            Flexible(
                              child: Text(
                                _grabando
                                    ? 'Grabando… ${_segundosGrabados}s / '
                                        '${_segundosMax}s — ¡dale a tu golpe!'
                                    : _guia,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14.5),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (_grabando)
                        FilledButton.icon(
                          style: FilledButton.styleFrom(
                              backgroundColor: Colors.white,
                              foregroundColor: tinta,
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 22, vertical: 12)),
                          onPressed: _terminarGrabacion,
                          icon: const Icon(Icons.stop_circle_outlined),
                          label: const Text('Listo, ese fue mi golpe',
                              style: TextStyle(fontWeight: FontWeight.w800)),
                        )
                      else if (_cuenta == 0 && ctrl != null)
                        TextButton(
                          onPressed: _arrancarCuenta,
                          child: const Text(
                            'Grabar ya (sin esperar la guía)',
                            style: TextStyle(
                                color: Colors.white70,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
