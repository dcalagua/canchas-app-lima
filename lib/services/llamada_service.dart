import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:jitsi_meet_flutter_sdk/jitsi_meet_flutter_sdk.dart';

import '../state/app_state.dart';

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

  // ── Fase 2: llamada ENTRANTE con tono (CallKit / Android) ──────────────────
  static bool _escuchando = false;

  /// Muestra la pantalla de llamada entrante (suena aunque la app esté cerrada).
  /// La dispara el push de llamada (data). Al aceptar entra a la sala.
  static Future<void> mostrarEntrante({
    required String room,
    required String caller,
    required bool video,
  }) async {
    if (room.isEmpty) return;
    final params = CallKitParams(
      id: room,
      nameCaller: caller.isEmpty ? 'Pichangol' : caller,
      appName: 'Pichangol',
      type: video ? 1 : 0, // 0 = voz, 1 = video
      extra: <String, dynamic>{'room': room, 'video': video},
      android: const AndroidParams(
        isCustomNotification: true,
        ringtonePath: 'system_ringtone_default',
        backgroundColor: '#14463A',
        actionColor: '#128C7E',
        textColor: '#ffffff',
        textAccept: 'Contestar',
        textDecline: 'Rechazar',
      ),
    );
    try {
      await FlutterCallkitIncoming.showCallkitIncoming(params);
    } catch (_) {}
  }

  /// Escucha los botones de la pantalla de llamada entrante. Al **contestar**,
  /// une a la sala Jitsi; rechazar/colgar no hace nada. Se registra una vez.
  ///
  /// Se usa acceso dinámico al evento para no depender de los nombres exactos de
  /// la API del plugin (cambian entre versiones): comparamos el evento por texto
  /// y leemos el `extra` desde `body['extra']` o `extra`, lo que exista.
  static void escucharEventos() {
    if (_escuchando) return;
    _escuchando = true;
    try {
      FlutterCallkitIncoming.onEvent.listen((dynamic evt) async {
        if (evt == null) return;
        String tipo;
        try {
          tipo = evt.event.toString();
        } catch (_) {
          return;
        }
        if (!tipo.contains('actionCallAccept')) return;
        Map? extra;
        try {
          final b = evt.body;
          if (b is Map) extra = b['extra'] as Map?;
        } catch (_) {}
        if (extra == null) {
          try {
            final e = evt.extra;
            if (e is Map) extra = e;
          } catch (_) {}
        }
        final room = ((extra?['room']) ?? '').toString();
        final video =
            extra?['video'] == true || extra?['video'] == 'true';
        if (room.isNotEmpty) {
          final u = appState.usuario;
          await unir(
              sala: room,
              audioSolo: !video,
              nombre: u?.nombre ?? '',
              email: u?.email ?? '');
        }
      });
    } catch (_) {}
  }
}
