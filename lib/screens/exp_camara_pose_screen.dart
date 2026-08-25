import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:google_mlkit_pose_detection/google_mlkit_pose_detection.dart';

/// EXPERIMENTO (rama exp/camara-pose): prueba de COMPILACIÓN y humo del
/// encuadre asistido — cámara propia (preview) + detector de pose on-device.
/// No está enlazada a ninguna ruta del app: solo verifica que los plugins
/// nativos (`camera` + `google_mlkit_pose_detection`) construyen y corren
/// con Flutter 3.24.5. Si el CI sale verde, sobre esta base se arma la
/// pantalla real de guía ("retrocede dos pasos", "gírate de costado", 3-2-1).
class ExpCamaraPoseScreen extends StatefulWidget {
  const ExpCamaraPoseScreen({super.key});

  @override
  State<ExpCamaraPoseScreen> createState() => _ExpCamaraPoseScreenState();
}

class _ExpCamaraPoseScreenState extends State<ExpCamaraPoseScreen> {
  CameraController? _camara;
  final PoseDetector _detector = PoseDetector(
    options: PoseDetectorOptions(
      model: PoseDetectionModel.base,
      mode: PoseDetectionMode.single,
    ),
  );
  String _estado = 'Iniciando cámara…';

  @override
  void initState() {
    super.initState();
    _iniciar();
  }

  Future<void> _iniciar() async {
    try {
      final camaras = await availableCameras();
      if (camaras.isEmpty) {
        setState(() => _estado = 'Sin cámaras disponibles.');
        return;
      }
      final ctrl = CameraController(camaras.first, ResolutionPreset.medium,
          enableAudio: false);
      await ctrl.initialize();
      if (!mounted) return;
      setState(() {
        _camara = ctrl;
        _estado = 'Cámara lista ✅';
      });
    } catch (e) {
      if (mounted) setState(() => _estado = 'Error de cámara: $e');
    }
  }

  Future<void> _probarDetector() async {
    final c = _camara;
    if (c == null || !c.value.isInitialized) return;
    try {
      final foto = await c.takePicture();
      final poses =
          await _detector.processImage(InputImage.fromFilePath(foto.path));
      if (!mounted) return;
      setState(() => _estado = poses.isEmpty
          ? 'No se detectó cuerpo. Ponte frente a la cámara.'
          : 'Cuerpo detectado ✅ (${poses.first.landmarks.length} puntos)');
    } catch (e) {
      if (mounted) setState(() => _estado = 'Error del detector: $e');
    }
  }

  @override
  void dispose() {
    _camara?.dispose();
    _detector.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _camara;
    return Scaffold(
      appBar: AppBar(title: const Text('EXP · Cámara + Pose')),
      body: Column(
        children: [
          Expanded(
            child: c != null && c.value.isInitialized
                ? CameraPreview(c)
                : const Center(child: CircularProgressIndicator()),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(_estado, textAlign: TextAlign.center),
                const SizedBox(height: 10),
                FilledButton(
                  onPressed: _probarDetector,
                  child: const Text('Probar detección de cuerpo'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
