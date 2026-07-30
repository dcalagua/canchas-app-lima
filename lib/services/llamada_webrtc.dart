import 'dart:async';

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

  /// Logger de diagnóstico (lo setea LlamadaService para escribir al mismo
  /// registro que se ve en Ajustes → Zona de pruebas).
  static void Function(String)? registrar;
  void _diag(String m) {
    try {
      registrar?.call('WRTC $m');
    } catch (_) {}
  }

  static const _turnUrl = String.fromEnvironment('TURN_URL');
  static const _turnUser = String.fromEnvironment('TURN_USER');
  static const _turnPass = String.fromEnvironment('TURN_PASS');

  final RTCVideoRenderer local = RTCVideoRenderer();
  final RTCVideoRenderer remoto = RTCVideoRenderer();

  RTCPeerConnection? _pc;
  MediaStream? _localStream;
  RealtimeChannel? _canal;
  String _callId = ''; // sala de la llamada (para cancelar en el otro por push)
  Timer? _timeoutConexion; // corta si nunca engancha (rechazo perdido/no contesta)

  /// Lo setea PushService: cuando el que LLAMA cuelga ANTES de conectar, apaga el
  /// timbre del que RECIBE (que aún no está suscrito al canal) por push. (room,
  /// correo del destino).
  static Future<void> Function(String room, String emailDestino)?
      alCancelarEntranteRemota;

  EstadoLlamada estado = EstadoLlamada.idle;

  /// ¿Hay una llamada en curso (para mostrar la barra "volver a la llamada")?
  bool get activa =>
      estado == EstadoLlamada.llamando ||
      estado == EstadoLlamada.conectando ||
      estado == EstadoLlamada.enLlamada;

  /// La LlamadaScreen la pone en true mientras está montada; así la barra de
  /// "volver a la llamada" solo aparece cuando NO estás viendo la pantalla grande.
  static bool pantallaVisible = false;

  bool video = true;
  bool micOn = true;
  bool camOn = true;
  bool altavoz = true;
  bool _soyElQueLlama = false;
  bool _remotoListo = false; // ya fijamos la descripción remota
  bool _suscrito = false; // el canal de señalización está SUBSCRIBED
  bool _otroPresente = false; // el otro ya entró (podemos mandarle cosas)
  bool _ofertaEnviada = false; // el que llama ya mandó su offer
  final List<RTCIceCandidate> _icePendientes = []; // ICE ENTRANTE en espera
  final List<Map<String, dynamic>> _iceSalientes = []; // ICE SALIENTE en cola
  RTCSessionDescription? _offerGuardada;

  String nombreOtro = '';
  String fotoOtro = ''; // foto del contacto (para la pantalla y la barra)
  String emailOtro = ''; // correo del contacto (para el historial / rellamar)
  DateTime? conectadoEn;

  /// Aviso al TERMINAR una llamada, con su resumen (para el historial). Lo setea
  /// LlamadaService. data: nombre, foto, email, saliente, conectada, duracionSeg, video.
  static void Function(Map<String, dynamic>)? alTerminar;

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
    return {
      'iceServers': servers,
      'sdpSemantics': 'unified-plan',
      // Pre-recolecta algunos candidatos para enganchar un poco más rápido.
      'iceCandidatePoolSize': 2,
    };
  }

  void _set(EstadoLlamada e) {
    estado = e;
    if (e == EstadoLlamada.enLlamada) {
      conectadoEn ??= DateTime.now();
      _timeoutConexion?.cancel(); // ya enganchó: no cortar
    }
    notifyListeners();
  }

  /// Red de seguridad: si nunca engancha (rechazo perdido, no contesta, señal
  /// mala) corta a los 45 s con "no contestó", como el timeout de WhatsApp.
  void _armarTimeoutConexion() {
    _timeoutConexion?.cancel();
    _timeoutConexion = Timer(const Duration(seconds: 45), () {
      if (estado != EstadoLlamada.enLlamada &&
          estado != EstadoLlamada.finalizada) {
        _diag('timeout: nunca conectó → finalizar');
        finalizar(avisar: true);
      }
    });
  }

  /// INICIA la llamada (quien llama). Prepara media y espera a que el otro entre
  /// al canal (evento `ready`) para mandarle el `offer`.
  Future<void> iniciar({
    required String callId,
    required bool video,
    String nombreOtro = '',
    String fotoOtro = '',
    String emailOtro = '',
  }) async {
    if (_pc != null) {
      _diag('iniciar IGNORADO (ya hay llamada activa)');
      return; // evita doble arranque (crea 2 conexiones/canales)
    }
    _soyElQueLlama = true;
    _callId = callId;
    this.video = video;
    this.nombreOtro = nombreOtro;
    this.fotoOtro = fotoOtro;
    this.emailOtro = emailOtro;
    _diag('iniciar sala=$callId');
    await _prepararMedia(video);
    await _crearPeer();
    await _abrirCanal(callId);
    // El offer se crea ya, pero se envía cuando el otro mande `ready`.
    final offer = await _pc!.createOffer({});
    await _pc!.setLocalDescription(offer);
    _offerGuardada = offer;
    _set(EstadoLlamada.llamando);
    _armarTimeoutConexion();
  }

  /// CONTESTA la llamada (quien recibe). Entra al canal y avisa `ready` para que
  /// el que llama le mande el `offer`.
  Future<void> contestar({
    required String callId,
    required bool video,
    String nombreOtro = '',
    String fotoOtro = '',
    String emailOtro = '',
  }) async {
    if (_pc != null) {
      _diag('contestar IGNORADO (ya hay llamada activa)');
      return; // evita doble arranque (crea 2 conexiones/canales)
    }
    _soyElQueLlama = false;
    _callId = callId;
    this.video = video;
    this.nombreOtro = nombreOtro;
    this.fotoOtro = fotoOtro;
    this.emailOtro = emailOtro;
    _diag('contestar sala=$callId');
    await _prepararMedia(video);
    await _crearPeer();
    _set(EstadoLlamada.conectando);
    _armarTimeoutConexion();
    // El `ready` se manda cuando el canal esté SUBSCRIBED (dentro de _abrirCanal),
    // con reintentos — no antes, o se perdería.
    await _abrirCanal(callId);
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
      final msg = {
        't': 'ice',
        'candidate': c.candidate,
        'sdpMid': c.sdpMid,
        'sdpMLineIndex': c.sdpMLineIndex,
      };
      // Solo se manda cuando el canal está listo Y el otro ya entró; si no, se
      // encola y se vacía cuando ambos ocurran (evita perder candidatos).
      if (_suscrito && _otroPresente) {
        _crudo(msg);
      } else {
        _iceSalientes.add(msg);
      }
    };
    pc.onTrack = (RTCTrackEvent e) {
      _diag('onTrack ${e.track.kind}');
      if (e.streams.isNotEmpty) {
        remoto.srcObject = e.streams[0];
        notifyListeners();
      }
    };
    pc.onConnectionState = (RTCPeerConnectionState s) {
      _diag('conn=$s');
      if (s == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
        _set(EstadoLlamada.enLlamada);
        // Ruta de audio al altavoz para que se oiga (sin pegarse el teléfono).
        try {
          Helper.setSpeakerphoneOn(altavoz);
        } catch (_) {}
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
    // OJO: subscribe() es asíncrono. NO se puede mandar señalización hasta estar
    // SUBSCRIBED, o los mensajes se pierden (era el bug de "ambos en Llamando").
    canal.subscribe((status, [error]) {
      _diag('subscribe status=$status');
      if (status == RealtimeSubscribeStatus.subscribed) {
        _suscrito = true;
        // Vacía lo que se acumuló antes de estar suscrito.
        _vaciarIceSalientes();
        // Quien CONTESTA anuncia su presencia (con reintentos) para que el que
        // llama le mande el offer, aunque el otro se haya suscrito un poco después.
        if (!_soyElQueLlama) _anunciarReady();
      }
    });
  }

  /// Anuncia `ready` varias veces hasta que el otro responda con el offer (o ya
  /// esté en llamada). Cubre la carrera de que el que llama se suscriba tarde.
  Future<void> _anunciarReady() async {
    for (var i = 0; i < 5; i++) {
      if (_remotoListo || estado == EstadoLlamada.enLlamada) return;
      _diag('envio ready #$i');
      _crudo({'t': 'ready'});
      await Future.delayed(const Duration(milliseconds: 700));
    }
  }

  /// Envía un mensaje de señalización YA (asume canal suscrito).
  void _crudo(Map<String, dynamic> msg) {
    _canal?.sendBroadcastMessage(event: 'signal', payload: msg);
  }

  void _vaciarIceSalientes() {
    if (!_suscrito || !_otroPresente) return;
    for (final m in _iceSalientes) {
      _crudo(m);
    }
    _iceSalientes.clear();
  }

  Future<void> _alRecibir(Map<String, dynamic> p) async {
    final t = (p['t'] ?? '').toString();
    _diag('recibo $t');
    final pc = _pc;
    if (pc == null) return;
    switch (t) {
      case 'ready': // el otro entró: quien llama manda el offer
        if (!_soyElQueLlama) return;
        _otroPresente = true;
        _vaciarIceSalientes();
        // Reenvía el offer con CADA `ready` mientras no llegue el answer (el que
        // contesta reintenta `ready` varias veces): si un offer se perdió, el
        // siguiente ready lo reintenta. Idempotente en el otro lado.
        if (_offerGuardada != null && !_remotoListo) {
          _ofertaEnviada = true;
          _diag('envio offer');
          // OJO: la clave 'type' la usa Supabase en su sobre de broadcast y
          // pisaba la nuestra → usamos 'sdpType' para el tipo del SDP.
          _crudo({
            't': 'offer',
            'sdp': _offerGuardada!.sdp,
            'sdpType': _offerGuardada!.type,
          });
        }
        break;
      case 'offer': // solo quien contesta: fija el remoto y responde
        if (_soyElQueLlama) return;
        if (_remotoListo) return; // ya procesamos el offer (llegó duplicado)
        // Marca ANTES del primer await: A reenvía varios offers y llegan casi
        // juntos; sin esta guarda síncrona se procesaban en paralelo y
        // `setRemoteDescription` chocaba (glare) → nunca se creaba el answer.
        _remotoListo = true;
        _otroPresente = true;
        try {
          await pc.setRemoteDescription(RTCSessionDescription(
              p['sdp']?.toString(), p['sdpType']?.toString()));
          await _vaciarIce();
          final answer = await pc.createAnswer({});
          await pc.setLocalDescription(answer);
          _diag('envio answer');
          _crudo({'t': 'answer', 'sdp': answer.sdp, 'sdpType': answer.type});
          _vaciarIceSalientes(); // ahora sí, manda los candidatos en cola
        } catch (e) {
          _diag('ERROR offer: $e');
          _remotoListo = false; // deja reintentar con el próximo offer
        }
        break;
      case 'answer': // solo quien llama: fija el remoto
        if (!_soyElQueLlama) return;
        if (_remotoListo) return; // answer duplicado
        _remotoListo = true; // guarda síncrona (igual que el offer)
        try {
          await pc.setRemoteDescription(RTCSessionDescription(
              p['sdp']?.toString(), p['sdpType']?.toString()));
          await _vaciarIce();
        } catch (e) {
          _diag('ERROR answer: $e');
          _remotoListo = false;
        }
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

  /// Rechaza una llamada ENTRANTE sin arrancar el motor: abre el canal de
  /// señalización, avisa `bye` al que llama (para que se le corte el "Llamando")
  /// y cierra el canal. Se usa cuando el usuario RECHAZA desde la entrante in-app
  /// (donde todavía no arrancamos WebRTC). No toca el estado del motor.
  static Future<void> rechazarRemoto(String callId) async {
    void log(String m) {
      try {
        registrar?.call('WRTC $m');
      } catch (_) {}
    }

    try {
      final canal = SupabaseService.client.channel('llamada_$callId');
      final listo = Completer<void>();
      canal.subscribe((status, [error]) {
        log('rechazo subscribe=$status');
        if (status == RealtimeSubscribeStatus.subscribed &&
            !listo.isCompleted) {
          listo.complete();
        }
      });
      // Espera a estar SUBSCRIBED (el socket puede estar frío tras el push).
      try {
        await listo.future.timeout(const Duration(seconds: 5));
      } catch (_) {
        log('rechazo: no suscribió a tiempo');
      }
      // Manda el bye varias veces (idempotente en el otro lado) para no perderlo.
      for (var i = 0; i < 3; i++) {
        try {
          canal.sendBroadcastMessage(event: 'signal', payload: {'t': 'bye'});
          log('rechazo envio bye #$i');
        } catch (e) {
          log('rechazo ERROR bye: $e');
        }
        await Future.delayed(const Duration(milliseconds: 400));
      }
      try {
        await canal.unsubscribe();
      } catch (_) {}
    } catch (e) {
      log('rechazo ERROR: $e');
    }
  }

  /// Cuelga: avisa al otro (si [avisar]) y limpia todo.
  Future<void> finalizar({bool avisar = true}) async {
    if (estado == EstadoLlamada.finalizada) return;
    _timeoutConexion?.cancel();
    _timeoutConexion = null;
    if (avisar && _suscrito) _crudo({'t': 'bye'});
    // Si YO llamo y cuelgo ANTES de conectar (no contestó / cancelé), el que
    // recibe aún NO está suscrito al canal → el `bye` no le llega. Le mandamos
    // un push de cancelación para apagarle el timbre (como WhatsApp).
    if (avisar &&
        _soyElQueLlama &&
        conectadoEn == null &&
        _callId.isNotEmpty &&
        emailOtro.isNotEmpty) {
      // Fire-and-forget: no bloquea el colgado ni el cierre de la pantalla.
      _diag('cancelar entrante remota → $emailOtro (room=$_callId)');
      try {
        alCancelarEntranteRemota?.call(_callId, emailOtro);
      } catch (_) {}
    }
    // Registra la llamada en el historial (solo si el motor llegó a arrancar,
    // es decir hubo intento de llamada/contestar).
    if (nombreOtro.isNotEmpty || emailOtro.isNotEmpty) {
      try {
        alTerminar?.call({
          'nombre': nombreOtro,
          'foto': fotoOtro,
          'email': emailOtro,
          'saliente': _soyElQueLlama,
          'conectada': conectadoEn != null,
          'duracionSeg': conectadoEn != null
              ? DateTime.now().difference(conectadoEn!).inSeconds
              : 0,
          'video': video,
        });
      } catch (_) {}
    }
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
    _iceSalientes.clear();
    _offerGuardada = null;
    _remotoListo = false;
    _suscrito = false;
    _otroPresente = false;
    _ofertaEnviada = false;
    conectadoEn = null;
    nombreOtro = '';
    fotoOtro = '';
    emailOtro = '';
    _callId = '';
    notifyListeners();
  }
}
