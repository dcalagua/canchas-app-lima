import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../brand.dart';
import '../theme.dart';
import '../widgets/responsive.dart';

/// Onboarding de permisos (una sola vez, al instalar). Explica y pide los
/// permisos que Pichangol necesita para chatear y llamar sin problemas:
/// notificaciones, micrófono, cámara y "pantalla completa" (llamadas entrantes).
class PermisosOnboardingScreen extends StatefulWidget {
  const PermisosOnboardingScreen({super.key});

  static const _kFlag = 'onboarding_permisos_v1';

  /// Muestra el onboarding SOLO la primera vez (tras instalar).
  static Future<void> mostrarSiHaceFalta(BuildContext context) async {
    try {
      final p = await SharedPreferences.getInstance();
      if (p.getBool(_kFlag) == true) return;
      if (!context.mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => const PermisosOnboardingScreen(),
      ));
    } catch (_) {}
  }

  static Future<void> _marcarHecho() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(_kFlag, true);
      // Que el otro aviso de pantalla completa no vuelva a salir aparte.
      await p.setBool('perm_full_screen_llamada', true);
    } catch (_) {}
  }

  @override
  State<PermisosOnboardingScreen> createState() =>
      _PermisosOnboardingScreenState();
}

class _PermisosOnboardingScreenState extends State<PermisosOnboardingScreen> {
  bool _pidiendo = false;

  Future<void> _permitir() async {
    setState(() => _pidiendo = true);
    try {
      // Se piden en orden, cada uno con su diálogo del sistema.
      await Permission.notification.request();
      await Permission.microphone.request();
      await Permission.camera.request();
      try {
        if (!await FlutterCallkitIncoming.canUseFullScreenIntent()) {
          await FlutterCallkitIncoming.requestFullIntentPermission();
        }
      } catch (_) {}
    } catch (_) {}
    await PermisosOnboardingScreen._marcarHecho();
    if (mounted) Navigator.of(context).maybePop();
  }

  Future<void> _ahoraNo() async {
    await PermisosOnboardingScreen._marcarHecho();
    if (mounted) Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: AnchoTablet(
          maxWidth: 560,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 8),
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(Icons.verified_user_outlined,
                      color: bosque, size: 30),
                ),
                const SizedBox(height: 18),
                Text('Permisos de $kBrandName',
                    style: const TextStyle(
                        fontSize: 24, fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                Text(
                  'Para chatear y llamar sin problemas, $kBrandName necesita '
                  'estos permisos. Puedes cambiarlos luego en Ajustes.',
                  style: TextStyle(
                      fontSize: 14.5,
                      color: Colors.black.withOpacity(0.6),
                      height: 1.35),
                ),
                const SizedBox(height: 24),
                Expanded(
                  child: ListView(
                    children: const [
                      _PermisoItem(
                        icono: Icons.notifications_active_outlined,
                        color: teal,
                        titulo: 'Notificaciones',
                        desc: 'Avisos de mensajes y llamadas entrantes.',
                      ),
                      _PermisoItem(
                        icono: Icons.mic_none,
                        color: lima,
                        titulo: 'Micrófono',
                        desc: 'Para las llamadas de voz y video.',
                      ),
                      _PermisoItem(
                        icono: Icons.photo_camera_outlined,
                        color: amarillo,
                        titulo: 'Cámara',
                        desc: 'Para las videollamadas y enviar fotos.',
                      ),
                      _PermisoItem(
                        icono: Icons.fullscreen,
                        color: morado,
                        titulo: 'Pantalla completa',
                        desc: 'Para ver las llamadas entrantes como en WhatsApp, '
                            'incluso con el teléfono bloqueado.',
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _pidiendo ? null : _permitir,
                    style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    child: _pidiendo
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                                strokeWidth: 2.4, color: Colors.white))
                        : const Text('Permitir',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 16)),
                  ),
                ),
                const SizedBox(height: 6),
                Center(
                  child: TextButton(
                    onPressed: _pidiendo ? null : _ahoraNo,
                    child: Text('Ahora no',
                        style: TextStyle(color: Colors.black.withOpacity(0.55))),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PermisoItem extends StatelessWidget {
  const _PermisoItem({
    required this.icono,
    required this.color,
    required this.titulo,
    required this.desc,
  });

  final IconData icono;
  final Color color;
  final String titulo;
  final String desc;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withOpacity(0.14),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icono, color: color, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo,
                    style: const TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 15.5)),
                const SizedBox(height: 2),
                Text(desc,
                    style: TextStyle(
                        fontSize: 13,
                        color: Colors.black.withOpacity(0.55),
                        height: 1.3)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
