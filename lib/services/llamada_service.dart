import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/llamada_historial.dart';
import '../widgets/dialogo_pichangol.dart';
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
  static void Function(String room, bool video, String nombre, String hilo)?
      alContestar;

  static bool _abriendo = false;

  // ── Registro de diagnóstico (se ve en Ajustes → Zona de pruebas) ───────────
  static const _kRegistro = 'llamada_registro';
  static String _hhmmss() {
    final n = DateTime.now();
    String d(int x) => x.toString().padLeft(2, '0');
    return '${d(n.hour)}:${d(n.minute)}:${d(n.second)}';
  }

  static void _log(String m) {
    final linea = '${_hhmmss()}  $m';
    // Persistimos (SharedPreferences) para verlo aunque el evento haya corrido
    // en el isolate de background.
    () async {
      try {
        final p = await SharedPreferences.getInstance();
        await p.reload();
        final l = p.getStringList(_kRegistro) ?? <String>[];
        l.add(linea);
        while (l.length > 40) {
          l.removeAt(0);
        }
        await p.setStringList(_kRegistro, l);
      } catch (_) {}
    }();
  }

  /// Lee el registro de diagnóstico de llamadas (para mostrarlo en Ajustes).
  static Future<List<String>> leerRegistro() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload();
      return p.getStringList(_kRegistro) ?? const [];
    } catch (_) {
      return const [];
    }
  }

  static Future<void> limpiarRegistro() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.remove(_kRegistro);
    } catch (_) {}
  }

  /// Punto ÚNICO para abrir la pantalla de llamada al contestar. Es idempotente
  /// y seguro de llamar desde varios lados (evento CallKit, arranque de la app,
  /// y `resumed` del ciclo de vida) — solo abre una vez.
  ///
  /// **Clave:** abre SOLO si la llamada pendiente está marcada como ACEPTADA
  /// (el usuario tocó "Contestar"). NO se usa `activeCalls()` para decidir,
  /// porque CallKit cuenta como "activa" también la llamada que apenas SUENA —
  /// eso hacía que se auto-contestara al volver la app al frente.
  static Future<void> _intentarContestar({bool desdeAceptar = false}) async {
    if (alContestar == null || _abriendo) {
      _log('intentar: skip (alContestar=${alContestar != null} abriendo=$_abriendo)');
      return;
    }
    // ¿El motor ya está ocupado con esta llamada? Entonces la pantalla ya se
    // abrió (o se está abriendo): no dupliques.
    final est = LlamadaWebRTC.instance.estado;
    if (est == EstadoLlamada.llamando ||
        est == EstadoLlamada.conectando ||
        est == EstadoLlamada.enLlamada) {
      _log('intentar: skip (motor ocupado: $est)');
      return;
    }
    final ciclo = WidgetsBinding.instance.lifecycleState;
    // Si venimos del RESUME/arranque (no del botón "Contestar"), solo abrimos con
    // la app al frente. Si venimos de ACEPTAR, abrimos igual (la app se está
    // trayendo al frente); la pantalla maneja el error si el mic no está listo.
    if (!desdeAceptar &&
        (ciclo == AppLifecycleState.paused ||
            ciclo == AppLifecycleState.hidden ||
            ciclo == AppLifecycleState.detached)) {
      _log('intentar: diferir (ciclo=$ciclo, no desdeAceptar)');
      return;
    }
    _abriendo = true;
    try {
      // SOLO si el usuario tocó "Contestar" (no si apenas está sonando).
      final acc = await _pendienteAceptada();
      if (!acc) {
        _log('intentar: skip (no aceptada aún)');
        return;
      }
      final datos = await _leerPendiente();
      if (datos == null) {
        _log('intentar: skip (sin pendiente)');
        return;
      }
      await _limpiarPendiente(); // ya la vamos a atender: no reabrir de nuevo
      _log('intentar: ABRIENDO pantalla (ciclo=$ciclo, desdeAceptar=$desdeAceptar)');
      alContestar?.call(datos.$1, datos.$2, datos.$3, datos.$4);
    } finally {
      _abriendo = false;
    }
  }

  /// Se llama desde el ciclo de vida de la app (`AppLifecycleState.resumed`):
  /// cuando el usuario toca "Contestar", Android trae la app al frente → aquí
  /// abrimos la pantalla completa **si ya estaba marcada como aceptada**.
  static Future<void> revisarLlamadaResumida() {
    _log('resume');
    return _intentarContestar();
  }

  // La llamada entrante se guarda en DISCO (SharedPreferences) al sonar, para
  // poder recuperarla al contestar aunque el push haya corrido en otro proceso
  // (isolate de background) — así no dependemos del `extra` de CallKit.
  static const _kPendiente = 'llamada_entrante_json';

  // Ventana de frescura de la llamada pendiente. Como abrir la pantalla ya está
  // blindado por el estado del motor y por la marca "aceptada", esta ventana
  // solo evita revivir una pendiente muy vieja que quedó olvidada.
  static const int _pendienteMaxSegundos = 300;

  static Future<void> _guardarPendiente(
      String room, bool video, String caller, String hilo) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(
          _kPendiente,
          jsonEncode({
            'room': room,
            'video': video,
            'caller': caller,
            'hilo': hilo,
            'ts': DateTime.now().millisecondsSinceEpoch,
          }));
    } catch (_) {}
  }

  static Future<(String, bool, String, String)?> _leerPendiente() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload(); // ver lo que escribió el isolate de background
      final raw = p.getString(_kPendiente);
      if (raw == null) return null;
      final m = jsonDecode(raw) as Map<String, dynamic>;
      final room = (m['room'] ?? '').toString();
      if (room.isEmpty) return null;
      // Descarta una pendiente vieja (p. ej. llamada perdida hace rato).
      final ts = (m['ts'] as num?)?.toInt();
      if (ts != null) {
        final edad = DateTime.now().millisecondsSinceEpoch - ts;
        if (edad > _pendienteMaxSegundos * 1000) return null;
      }
      return (
        room,
        m['video'] == true,
        (m['caller'] ?? '').toString(),
        (m['hilo'] ?? '').toString(),
      );
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

  /// Marca la llamada pendiente como ACEPTADA (el usuario tocó "Contestar").
  /// Si por lo que sea el disco no tenía la pendiente, la crea desde [respaldo]
  /// (el `extra` del evento de CallKit).
  static Future<void> _marcarAceptada(
      {(String, bool, String, String)? respaldo}) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload();
      final raw = p.getString(_kPendiente);
      Map<String, dynamic> m;
      if (raw != null) {
        m = jsonDecode(raw) as Map<String, dynamic>;
      } else if (respaldo != null) {
        m = {
          'room': respaldo.$1,
          'video': respaldo.$2,
          'caller': respaldo.$3,
          'hilo': respaldo.$4,
          'ts': DateTime.now().millisecondsSinceEpoch,
        };
      } else {
        return;
      }
      m['aceptada'] = true;
      await p.setString(_kPendiente, jsonEncode(m));
      _log('marcada ACEPTADA');
    } catch (_) {}
  }

  /// ¿La pendiente ya está marcada como aceptada por el usuario?
  static Future<bool> _pendienteAceptada() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload();
      final raw = p.getString(_kPendiente);
      if (raw == null) return false;
      final m = jsonDecode(raw) as Map<String, dynamic>;
      return m['aceptada'] == true;
    } catch (_) {
      return false;
    }
  }

  /// Muestra la pantalla de llamada entrante (suena aunque la app esté cerrada).
  /// La dispara el push de llamada (data). Al aceptar entra a la sala.
  // Dedup de entrantes duplicadas (FCM puede reentregar el mismo push, o llegar
  // por 2 vías): recordamos la última sala y cuándo se mostró.
  static String _ultEntranteRoom = '';
  static int _ultEntranteTs = 0;
  static const int _dedupEntranteMs = 45000; // 45 s

  static Future<void> mostrarEntrante({
    required String room,
    required String caller,
    required bool video,
    String hilo = '',
  }) async {
    if (room.isEmpty) return;
    // Ya hay una llamada en curso → no muestres otra entrante (evita duplicar).
    if (LlamadaWebRTC.instance.activa) {
      _log('mostrarEntrante IGNORADO (llamada en curso)');
      return;
    }
    // Misma sala mostrada hace poco (ráfaga de pushes duplicados) → ignora.
    final ahora = DateTime.now().millisecondsSinceEpoch;
    if (room == _ultEntranteRoom && ahora - _ultEntranteTs < _dedupEntranteMs) {
      _log('mostrarEntrante IGNORADO (entrante duplicada)');
      return;
    }
    _ultEntranteRoom = room;
    _ultEntranteTs = ahora;
    _log('mostrarEntrante room=$room');
    // hilo: para recuperar la foto del que llama al contestar.
    await _guardarPendiente(room, video, caller, hilo);
    final params = CallKitParams(
      id: room,
      nameCaller: caller.isEmpty ? 'Pichangol' : caller,
      appName: 'Pichangol',
      type: video ? 1 : 0, // 0 = voz, 1 = video
      extra: <String, dynamic>{
        'room': room,
        'video': video,
        'caller': caller,
        'hilo': hilo,
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

  /// Notificación de "llamada en curso" para el que LLAMA (saliente): así, al
  /// minimizar TODA la app, la llamada sigue visible en la barra de notificación
  /// (y tocarla vuelve a la pantalla). Se limpia al colgar (finalizar →
  /// endAllCalls). En quien contesta, esa notificación ya la crea el entrante.
  static Future<void> marcarLlamadaSaliente({
    required String room,
    required String caller,
    required bool video,
  }) async {
    if (room.isEmpty) return;
    try {
      await FlutterCallkitIncoming.startCall(CallKitParams(
        id: room,
        nameCaller: caller.isEmpty ? 'Pichangol' : caller,
        appName: 'Pichangol',
        type: video ? 1 : 0,
        extra: <String, dynamic>{'room': room, 'video': video, 'caller': caller},
        android: const AndroidParams(
          isCustomNotification: true,
          isShowLogo: false,
          backgroundColor: '#14463A',
          actionColor: '#128C7E',
          textColor: '#ffffff',
        ),
      ));
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
    LlamadaWebRTC.registrar = _log; // señalización WebRTC → mismo registro
    LlamadaWebRTC.alTerminar = registrarHistorial; // guarda cada llamada
    try {
      FlutterCallkitIncoming.onEvent.listen((dynamic evt) async {
        if (evt == null) return;
        // Lee el tipo del evento de forma robusta entre versiones del plugin:
        // las versiones nuevas exponen `eventName` (String, p. ej.
        // "...ACTION_CALL_ACCEPT"); las viejas, `event` (enum Event).
        String tipo = '';
        try {
          final en = evt.eventName;
          if (en != null) tipo = en.toString();
        } catch (_) {}
        if (tipo.isEmpty) {
          try {
            tipo = evt.event.toString();
          } catch (_) {}
        }
        _log('evt: ${tipo.isEmpty ? '(sin tipo)' : tipo}');
        final t = tipo.toLowerCase();
        // Rechazar/colgar desde la pantalla nativa → termina la llamada.
        if (t.contains('decline') || t.contains('ended')) {
          await _limpiarPendiente();
          await LlamadaWebRTC.instance.finalizar();
          return;
        }
        // Timeout: llamada entrante PERDIDA → al historial y limpia la pendiente.
        if (t.contains('timeout')) {
          final datos = await _leerPendiente();
          if (datos != null) {
            await registrarHistorial({
              'nombre': datos.$3,
              'email': '',
              'saliente': false,
              'conectada': false,
              'duracionSeg': 0,
              'video': datos.$2,
            });
          }
          await _limpiarPendiente();
          return;
        }
        if (!t.contains('accept')) return;
        // El usuario tocó "Contestar": marca la pendiente como ACEPTADA y abre la
        // pantalla (aunque la app se esté trayendo al frente en ese momento).
        await _marcarAceptada(respaldo: _extraDe(evt));
        await _intentarContestar(desdeAceptar: true);
      });
    } catch (_) {}
  }

  /// Lee (room, video, nombre, hilo) del `extra` de un evento/llamada de CallKit.
  static (String, bool, String, String)? _extraDe(dynamic evt) {
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
    final hilo = ((extra?['hilo']) ?? '').toString();
    return (room, video, nombre, hilo);
  }

  /// Al ARRANCAR la app (p. ej. cuando se contestó con la app cerrada y arrancó
  /// de cero), si hay una llamada activa abre su pantalla usando la pendiente
  /// guardada en disco.
  static Future<void> revisarLlamadaAlArrancar() => _intentarContestar();

  // ── Permiso de pantalla completa (Android 14+) ─────────────────────────────
  static const _kPidioFullScreen = 'perm_full_screen_llamada';

  /// En **Android 14+** la llamada entrante NO se muestra a pantalla completa
  /// (como WhatsApp) hasta que el usuario concede un permiso especial. Lo
  /// pedimos UNA sola vez, con un diálogo Pichangol, al entrar a la app. En
  /// Android < 14 / iOS `canUseFullScreenIntent` devuelve true y no molestamos.
  static Future<void> pedirPermisoPantallaCompleta(BuildContext context) async {
    try {
      final puede = await FlutterCallkitIncoming.canUseFullScreenIntent();
      if (puede) return;
      final p = await SharedPreferences.getInstance();
      if (p.getBool(_kPidioFullScreen) == true) return;
      await p.setBool(_kPidioFullScreen, true);
      if (!context.mounted) return;
      final ok = await confirmarPichangol(
        context,
        titulo: 'Llamadas en pantalla completa',
        mensaje: 'Para ver las llamadas de Pichangol a pantalla completa (como '
            'WhatsApp), incluso con el teléfono bloqueado, activa '
            '"Notificaciones a pantalla completa" para Pichangol.',
        textoConfirmar: 'Activar',
        textoCancelar: 'Ahora no',
        icono: Icons.phone_in_talk,
      );
      if (ok) {
        await FlutterCallkitIncoming.requestFullIntentPermission();
      }
    } catch (_) {}
  }

  // ── Diagnóstico (Zona de pruebas) ──────────────────────────────────────────

  /// ¿Este equipo permite mostrar la llamada a pantalla completa? (Android 14+).
  static Future<bool> puedePantallaCompleta() async {
    try {
      return await FlutterCallkitIncoming.canUseFullScreenIntent();
    } catch (_) {
      return true; // Android < 14 / iOS: se asume permitido
    }
  }

  /// Abre los ajustes del sistema para conceder el permiso de pantalla completa.
  static Future<void> abrirAjustesPantallaCompleta() async {
    try {
      await FlutterCallkitIncoming.requestFullIntentPermission();
    } catch (_) {}
  }

  /// Simula una llamada entrante LOCAL (sin push ni otro teléfono) para ver si
  /// la pantalla completa aparece en ESTE equipo. [delaySeg] da tiempo a bloquear
  /// la pantalla y probar el caso "teléfono en reposo".
  static Future<void> simularEntrante({int delaySeg = 0}) async {
    if (delaySeg > 0) await Future.delayed(Duration(seconds: delaySeg));
    await mostrarEntrante(
      room: 'PichangolPrueba',
      caller: 'Prueba Pichangol',
      video: false,
    );
  }

  // ── Historial de llamadas (registro estilo WhatsApp) ───────────────────────
  static const _kHistorial = 'llamadas_historial';

  /// Guarda una llamada en el historial local (más reciente primero, tope 100).
  static Future<void> registrarHistorial(Map<String, dynamic> data) async {
    try {
      final entrada = LlamadaHistorial(
        nombre: (data['nombre'] ?? '').toString(),
        foto: (data['foto'] ?? '').toString(),
        email: (data['email'] ?? '').toString(),
        saliente: data['saliente'] == true,
        conectada: data['conectada'] == true,
        duracionSeg: (data['duracionSeg'] as num?)?.toInt() ?? 0,
        video: data['video'] == true,
        cuando: DateTime.now(),
      );
      final p = await SharedPreferences.getInstance();
      await p.reload();
      final l = p.getStringList(_kHistorial) ?? <String>[];
      l.insert(0, jsonEncode(entrada.toJson()));
      while (l.length > 100) {
        l.removeLast();
      }
      await p.setStringList(_kHistorial, l);
    } catch (_) {}
  }

  /// Lee el historial de llamadas (más reciente primero).
  static Future<List<LlamadaHistorial>> leerHistorial() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.reload();
      final l = p.getStringList(_kHistorial) ?? const [];
      return l
          .map((s) =>
              LlamadaHistorial.fromJson(jsonDecode(s) as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  /// Borra todo el historial de llamadas.
  static Future<void> limpiarHistorial() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.remove(_kHistorial);
    } catch (_) {}
  }
}
