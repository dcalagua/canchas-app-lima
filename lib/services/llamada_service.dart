import 'package:jitsi_meet_flutter_sdk/jitsi_meet_flutter_sdk.dart';

/// Llamadas de voz/video DENTRO de Pichangol (Jitsi embebido). Mismo servidor
/// público gratuito (meet.jit.si), pero la llamada abre en una pantalla dentro
/// de la app en vez de mandar al navegador.
///
/// Fail-safe: si el `join` nativo lanza (equipo raro, plugin no disponible), la
/// UI cae al enlace web de Jitsi.
class LlamadaService {
  static final JitsiMeet _jitsi = JitsiMeet();
  static const String servidor = 'https://meet.jit.si';

  /// Nombre de sala estable por hilo de chat (ambos caen en la MISMA).
  static String salaChat(String hilo) =>
      'PichangolChat${hilo.replaceAll(RegExp(r'[^A-Za-z0-9]'), '')}';

  /// Nombre de sala estable por grupo.
  static String salaGrupo(String grupoId) =>
      'PichangolGrupo${grupoId.replaceAll(RegExp(r'[^A-Za-z0-9]'), '')}';

  /// Enlace web de la sala (para postear en el chat y como fallback).
  static String enlace(String sala, {bool audioSolo = false}) {
    final base = '$servidor/$sala';
    return audioSolo ? '$base#config.startAudioOnly=true' : base;
  }

  /// Si un enlace es de una sala Pichangol (para enrutarlo al SDK nativo al
  /// tocarlo en el chat). Devuelve el nombre de sala o null.
  static String? salaDeEnlace(String url) {
    final m = RegExp(r'meet\.jit\.si/(Pichangol[A-Za-z0-9]+)').firstMatch(url);
    return m?.group(1);
  }

  /// Une a una sala Jitsi dentro de la app. [audioSolo] arranca sin cámara (voz).
  /// Devuelve true si abrió el SDK; false si falló (para caer al enlace web).
  static Future<bool> unir({
    required String sala,
    required bool audioSolo,
    String nombre = '',
    String email = '',
    String asunto = 'Pichangol',
  }) async {
    try {
      final opciones = JitsiMeetConferenceOptions(
        serverURL: servidor,
        room: sala,
        configOverrides: {
          'startWithVideoMuted': audioSolo,
          'startAudioOnly': audioSolo,
          'subject': asunto,
        },
        featureFlags: {
          'invite.enabled': false,
          'meeting-password.enabled': false,
          'live-streaming.enabled': false,
          'recording.enabled': false,
        },
        userInfo: JitsiMeetUserInfo(
          displayName: nombre.isEmpty ? 'Pichangol' : nombre,
          email: email,
        ),
      );
      await _jitsi.join(opciones);
      return true;
    } catch (_) {
      return false;
    }
  }
}
