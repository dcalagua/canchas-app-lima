import 'package:flutter/foundation.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_service.dart';

/// Estados de una llamada 1-a-1 (WebRTC propio, tipo WhatsApp).
enum EstadoLlamada { idle, llamando, conectando, enLlamada, finalizada }

/// Motor de llamada 1-a-1 con WebRTC propio. La UI (LlamadaScreen) lo observa.
///
/// - **Media:** cámara/mic locales + pista remota, con sus renderers.
/// - **Señalización:** canal de **Supabase Realtime (broadcast)** por llamada
///   (`llamada_<callId>`): se intercambian `ready`/`offer`/`answer`/`ice`/`bye`.
///   No escribe en la base de datos (es efímero).
/// - **ICE:** STUN de Google + TURN opcional (dart-defines `TURN_URL/USER/PASS`).
///   Sin TURN funciona en WiFi/misma red; con TURN, también en redes móviles.
///
/// Singleton: solo una llamada activa a la vez (como el teléfono).
class LlamadaWebRTC extends ChangeNotifier {
  LlamadaWebRTC._();
  static final LlamadaWebRTC instance = LlamadaWebRTC._();

  static const _turnUrl = String.fromEnvironment('TURN_URL');
  static const _turnUser = String.fromEnvironment('TURN_USER');
  static const _turnPass = String.fromEnvironment('TURN_PASS');

  final RTCVideoRenderer local = RTCVideoRenderer();
  final RTCVideoRenderer remoto = RTCVideoRenderer();

  RTCPeerConnection? _pc;
  MediaStream? _localStream;
  RealtimeChannel? _canal;

  EstadoLlamada estado = EstadoLlamada.idle;
  bool video = true;
  bool micOn = true;
  bool camOn = true;
  bool altavoz = true;
  bool _soyElQueLlama = false;
  bool _remotoListo = false;
  final List<RTCIceCandidate> _icePendientes = [];
  RTCSessionDescription? _offerGuardada;

  String nombreOtro = '';
  DateTime? conectadoEn;

  Map<String, dynamic> get _iceServers {
    final servers = <Map<String, dynamic>>[
      {'urls': 'stun:stun.l.google.com:19302'},
      {'urls': 'stun:stun1.l.google.com:19302'},
    ];
    if (_turnUrl.isNotEmpty) {
      // TURN totalmente custom (avanzado): una URL propia.
      servers.add(
          {'urls': _turnUrl, 'username': _turnUser, 'credential': _turnPass});
    } else if (_turnUser.isNotEmpty && _turnPass.isNotEmpty) {
      // TURN de Metered: el dominio es el mismo para todas las cuentas; solo
      // cambian user/credential (secrets). Se incluyen todos los endpoints para
      // máxima probabilidad de conexión (WiFi y datos móviles).
      for (final u in const [
        'turn:global.relay.metered.ca:80',
        'turn:global.relay.metered.ca:80?transport=tcp',
        'turn:global.relay.metered.ca:443',
        'turns:global.relay.metered.ca:443?transport=tcp',
      ]) {
        servers.add(
            {'urls': u, 'username': _turnUser, 'credential': _turnPass});
      }
    } else {
      // Sin credenciales: TURN público de respaldo (OpenRelay) para que igual
      // conecte en datos móviles, como el relevo que usa WhatsApp.
      for (final u in const [
        'turn:openrelay.metered.ca:80',
        'turn:openrelay.metered.ca:443',
        'turn:openrelay.metered.ca:443?transport=tcp',
      ]) {
        servers.add({
          'urls': u,
          'username': 'openrelayproject',
          'credential': 'openrelayproject',
        });
      }
    }
    return {'iceServers': servers, 'sdpSemantics': 'unified-plan'};
  }

  void _set(EstadoLlamada e) {
    estado = e;
    if (e == EstadoLlamada.enLlamada) conectadoEn ??= DateTime.now();
    notifyListeners();
  }

  /// INICIA la llamada (quien llama). Prepara media y espera a que el otro entre
  /// al canal (evento `ready`) para mandarle el `offer`.
  Future<void> iniciar({
    required String callId,
    required bool video,
    String nombreOtro = '',
  }) async {
    _soyElQueLlama = true;
    this.video = video;
    this.nombreOtro = nombreOtro;
    await _prepararMedia(video);
    await _crearPeer();
    await _abrirCanal(callId);
    // El offer se crea ya, pero se envía cuando el otro mande `ready`.
    final offer = await _pc!.createOffer({});
    await _pc!.setLocalDescription(offer);
    _offerGuardada = offer;
    _set(EstadoLlamada.llamando);
  }

  /// CONTESTA la llamada (quien recibe). Entra al canal y avisa `ready` para que
  /// el que llama le mande el `offer`.
  Future<void> contestar({
    required String callId,
    required bool video,
    String nombreOtro = '',
  }) async {
    _soyElQueLlama = false;
    this.video = video;
    this.nombreOtro = nombreOtro;
    await _prepararMedia(video);
    await _crearPeer();
    await _abrirCanal(callId);
    _set(EstadoLlamada.conectando);
    _enviar('ready', {});
  }

  Future<void> _prepararMedia(bool video) async {
    await local.initialize();
    await remoto.initialize();
    _localStream = await navigator.mediaDevices.getUserMedia({
      'audio': true,
      'video': video
          ? {'facingMode': 'user'}
          : false,
    });
    local.srcObject = _localStream;
    camOn = video;
    notifyListeners();
  }

  Future<void> _crearPeer() async {
    final pc = await createPeerConnection(_iceServers);
    _pc = pc;
    for (final track in _localStream!.getTracks()) {
      await pc.addTrack(track, _localStream!);
    }
    pc.onIceCandidate = (RTCIceCandidate c) {
      _enviar('ice', {
        'candidate': c.candidate,
        'sdpMid': c.sdpMid,
        'sdpMLineIndex': c.sdpMLineIndex,
      });
    };
    pc.onTrack = (RTCTrackEvent e) {
      if (e.streams.isNotEmpty) {
        remoto.srcObject = e.streams[0];
        notifyListeners();
      }
    };
    pc.onConnectionState = (RTCPeerConnectionState s) {
      if (s == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
        _set(EstadoLlamada.enLlamada);
      } else if (s == RTCPeerConnectionState.RTCPeerConnectionStateFailed ||
          s == RTCPeerConnectionState.RTCPeerConnectionStateClosed ||
          s == RTCPeerConnectionState.RTCPeerConnectionStateDisconnected) {
        if (estado != EstadoLlamada.finalizada) finalizar(avisar: false);
      }
    };
  }

  Future<void> _abrirCanal(String callId) async {
    // Canal por defecto: broadcast NO se reenvía a uno mismo (self=false), así
    // solo recibimos lo que manda el otro. Igual guardamos por rol más abajo.
    final canal = SupabaseService.client.channel('llamada_$callId');
    _canal = canal;
    canal.onBroadcast(
      event: 'signal',
      callback: (payload) => _alRecibir(payload),
    );
    canal.subscribe();
  }

  void _enviar(String tipo, Map<String, dynamic> data) {
    _canal?.sendBroadcastMessage(
        event: 'signal', payload: {'t': tipo, ...data});
  }

  Future<void> _alRecibir(Map<String, dynamic> p) async {
    final t = (p['t'] ?? '').toString();
    final pc = _pc;
    if (pc == null) return;
    switch (t) {
      case 'ready': // el otro entró: quien llama manda el offer
        if (!_soyElQueLlama) return;
        if (_offerGuardada != null) {
          _enviar('offer',
              {'sdp': _offerGuardada!.sdp, 'type': _offerGuardada!.type});
        }
        break;
      case 'offer': // solo quien contesta: fija el remoto y responde
        if (_soyElQueLlama) return;
        await pc.setRemoteDescription(
            RTCSessionDescription(p['sdp']?.toString(), p['type']?.toString()));
        _remotoListo = true;
        await _vaciarIce();
        final answer = await pc.createAnswer({});
        await pc.setLocalDescription(answer);
        _enviar('answer', {'sdp': answer.sdp, 'type': answer.type});
        break;
      case 'answer': // solo quien llama: fija el remoto
        if (!_soyElQueLlama) return;
        await pc.setRemoteDescription(
            RTCSessionDescription(p['sdp']?.toString(), p['type']?.toString()));
        _remotoListo = true;
        await _vaciarIce();
        break;
      case 'ice':
        final c = RTCIceCandidate(p['candidate']?.toString(),
            p['sdpMid']?.toString(), (p['sdpMLineIndex'] as num?)?.toInt());
        if (_remotoListo) {
          try {
            await pc.addCandidate(c);
          } catch (_) {}
        } else {
          _icePendientes.add(c); // llegó antes del remoto: se guarda
        }
        break;
      case 'bye':
        finalizar(avisar: false);
        break;
    }
  }

  Future<void> _vaciarIce() async {
    for (final c in _icePendientes) {
      try {
        await _pc?.addCandidate(c);
      } catch (_) {}
    }
    _icePendientes.clear();
  }

  // ── Controles de la llamada ────────────────────────────────────────────────
  void alternarMic() {
    micOn = !micOn;
    _localStream?.getAudioTracks().forEach((t) => t.enabled = micOn);
    notifyListeners();
  }

  void alternarCam() {
    camOn = !camOn;
    _localStream?.getVideoTracks().forEach((t) => t.enabled = camOn);
    notifyListeners();
  }

  Future<void> voltearCamara() async {
    final v = _localStream?.getVideoTracks();
    if (v != null && v.isNotEmpty) {
      await Helper.switchCamera(v.first);
    }
  }

  Future<void> alternarAltavoz() async {
    altavoz = !altavoz;
    try {
      await Helper.setSpeakerphoneOn(altavoz);
    } catch (_) {}
    notifyListeners();
  }

  /// Cuelga: avisa al otro (si [avisar]) y limpia todo.
  Future<void> finalizar({bool avisar = true}) async {
    if (estado == EstadoLlamada.finalizada) return;
    if (avisar) _enviar('bye', {});
    _set(EstadoLlamada.finalizada);
    // Cierra la pantalla nativa de CallKit (la notificación "Llamada en curso").
    try {
      await FlutterCallkitIncoming.endAllCalls();
    } catch (_) {}
    try {
      await _pc?.close();
    } catch (_) {}
    _pc = null;
    try {
      for (final t in _localStream?.getTracks() ?? const []) {
        await t.stop();
      }
      await _localStream?.dispose();
    } catch (_) {}
    _localStream = null;
    try {
      await _canal?.unsubscribe();
    } catch (_) {}
    _canal = null;
    local.srcObject = null;
    remoto.srcObject = null;
    _icePendientes.clear();
    _offerGuardada = null;
    _remotoListo = false;
    conectadoEn = null;
    notifyListeners();
  }
}
