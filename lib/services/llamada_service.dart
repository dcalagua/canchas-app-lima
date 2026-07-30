import 'dart:convert';

import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import 'llamada_webrtc.dart';

/// Llamadas de Pichangol. La 1-a-1 va camino a WebRTC propio (UI tipo WhatsApp);
/// mientras se construye esa pantalla, `unir()` abre la sala por enlace. La
/// grupal se queda por enlace de Jitsi (grupo con WebRTC puro necesita un SFU).
class LlamadaService {
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

  /// Abre la sala de la llamada. [audioSolo] = voz. TRANSITORIO: mientras se
  /// construye la pantalla WebRTC propia, abre la sala por enlace (navegador/
  /// Jitsi). Devuelve true si abrió; false si falló.
  static Future<bool> unir({
    required String sala,
    required bool audioSolo,
    String nombre = '',
    String email = '',
    String asunto = 'Pichangol',
  }) async {
    try {
      await launchUrl(Uri.parse(enlace(sala, audioSolo: audioSolo)),
          mode: LaunchMode.externalApplication);
      return true;
    } catch (_) {
      return false;
    }
  }

  // ── Fase 2: llamada ENTRANTE con tono (CallKit / Android) ──────────────────
  static bool _escuchando = false;

  /// Lo setea main.dart (que conoce las pantallas): abre la LlamadaScreen para
  /// CONTESTAR cuando el usuario acepta la llamada entrante. (room, video, nombre)
  static void Function(String room, bool video, String nombre)? alContestar;

  // La llamada entrante se guarda en DISCO (SharedPreferences) al sonar, para
  // poder recuperarla al contestar aunque el push haya corrido en otro proceso
  // (isolate de background) — así no dependemos del `extra` de CallKit.
  static const _kPendiente = 'llamada_entrante_json';

  static Future<void> _guardarPendiente(
      String room, bool video, String caller) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(_kPendiente,
          jsonEncode({'room': room, 'video': video, 'caller': caller}));
    } catch (_) {}
  }

  static Future<(String, bool, String)?> _leerPendiente() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload(); // ver lo que escribió el isolate de background
      final raw = p.getString(_kPendiente);
      if (raw == null) return null;
      final m = jsonDecode(raw) as Map<String, dynamic>;
      final room = (m['room'] ?? '').toString();
      if (room.isEmpty) return null;
      return (room, m['video'] == true, (m['caller'] ?? '').toString());
    } catch (_) {
      return null;
    }
  }

  static Future<void> _limpiarPendiente() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.remove(_kPendiente);
    } catch (_) {}
  }

  /// Muestra la pantalla de llamada entrante (suena aunque la app esté cerrada).
  /// La dispara el push de llamada (data). Al aceptar entra a la sala.
  static Future<void> mostrarEntrante({
    required String room,
    required String caller,
    required bool video,
  }) async {
    if (room.isEmpty) return;
    await _guardarPendiente(room, video, caller); // para recuperar al contestar
    final params = CallKitParams(
      id: room,
      nameCaller: caller.isEmpty ? 'Pichangol' : caller,
      appName: 'Pichangol',
      type: video ? 1 : 0, // 0 = voz, 1 = video
      extra: <String, dynamic>{
        'room': room,
        'video': video,
        'caller': caller,
      },
      android: const AndroidParams(
        isCustomNotification: true,
        isShowLogo: false,
        // Muestra la pantalla de llamada ENTRANTE a pantalla completa (también
        // con el teléfono bloqueado/en reposo), como WhatsApp.
        isShowFullLockedScreen: true,
        isShowCallID: true,
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
        // Rechazar o colgar desde la pantalla nativa → termina la llamada
        // (avisa al otro por WebRTC si estaba conectada).
        if (tipo.contains('actionCallDecline') ||
            tipo.contains('actionCallEnded')) {
          await _limpiarPendiente();
          await LlamadaWebRTC.instance.finalizar();
          return;
        }
        if (!tipo.contains('actionCallAccept')) return;
        // Preferimos la pendiente guardada en disco (confiable entre procesos);
        // si no, caemos al extra del evento.
        final datos = await _leerPendiente() ?? _extraDe(evt);
        if (datos != null) {
          // Abre la pantalla de llamada WebRTC para CONTESTAR (lo hace main.dart).
          alContestar?.call(datos.$1, datos.$2, datos.$3);
        }
      });
    } catch (_) {}
  }

  /// Lee (room, video, nombre) del `extra` de un evento/llamada de CallKit.
  static (String, bool, String)? _extraDe(dynamic evt) {
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
    if (room.isEmpty) return null;
    final video = extra?['video'] == true || extra?['video'] == 'true';
    final nombre = ((extra?['caller']) ?? '').toString();
    return (room, video, nombre);
  }

  /// Al ARRANCAR la app (p. ej. cuando se contestó con la app cerrada y arrancó
  /// de cero), si hay una llamada activa abre su pantalla usando la pendiente
  /// guardada en disco.
  static Future<void> revisarLlamadaAlArrancar() async {
    try {
      final calls = await FlutterCallkitIncoming.activeCalls();
      if (calls is List && calls.isNotEmpty) {
        final datos = await _leerPendiente();
        if (datos != null) alContestar?.call(datos.$1, datos.$2, datos.$3);
      }
    } catch (_) {}
  }
}
