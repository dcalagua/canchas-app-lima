import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'llamada_service.dart';
import 'llamada_webrtc.dart';
import 'supabase_service.dart';

/// Handler de mensajes en SEGUNDO PLANO / app cerrada. Debe ser una función de
/// nivel superior con este pragma (Firebase la ejecuta en un isolate aparte).
/// No necesita lógica: el sistema ya muestra la notificación (`notification`
/// del payload). El TAP se maneja en `onMessageOpenedApp` / `getInitialMessage`.
@pragma('vm:entry-point')
Future<void> pushBackgroundHandler(RemoteMessage message) async {
  // Otro dispositivo de mi cuenta ya atendió/rechazó → apaga el timbre aquí.
  if (message.data['tipo'] == 'cancelar_llamada') {
    await LlamadaService.cancelarEntrante((message.data['room'] ?? '').toString());
    return;
  }
  // Llamada entrante (app en segundo plano / cerrada): muestra la pantalla que
  // suena (CallKit). El resto de mensajes ya los pinta el sistema.
  if (message.data['tipo'] == 'llamada') {
    final hilo = (message.data['hilo'] ?? '').toString();
    await LlamadaService.mostrarEntrante(
      room: LlamadaService.salaChat(hilo),
      caller: (message.data['caller'] ?? '').toString(),
      video: (message.data['video'] ?? '') == 'true',
      hilo: hilo,
    );
  }
}

/// Notificaciones push del chat (Etapa B, FCM). TODO es **fail-safe**: si el APK
/// no trae la configuración de Firebase (google-services.json) o falla algo, el
/// push queda DESACTIVADO (`disponible == false`) y la app sigue igual —el chat
/// en vivo (Etapa A, Supabase Realtime) no depende de esto.
///
/// Flujo: `init()` una vez al arrancar → tras el login, `registrarParaUsuario`
/// obtiene el token del dispositivo y lo guarda en `pichangol_push_tokens`
/// (asociado al correo). El envío del push lo hace la Edge Function `push-mensaje`
/// cuando entra un mensaje nuevo.
///
/// Recepción:
///  - **App abierta (foreground):** el sistema NO pinta la notificación; aquí un
///    listener muestra un aviso IN-APP (estilo WhatsApp) —salvo que ya estés en
///    ese chat—. Al tocarlo, abre el chat.
///  - **App en segundo plano / cerrada:** el sistema pinta la notificación; al
///    TOCARLA, `onMessageOpenedApp`/`getInitialMessage` abren el chat.
class PushService {
  static bool _ok = false;
  static bool get disponible => _ok;

  static String? _token;
  static String? get token => _token;
  static String _email = '';
  static StreamSubscription<String>? _tokenSub;
  static bool _listenersListos = false;

  /// Navegador global: permite abrir el chat desde una notificación (fuera del
  /// árbol de widgets normal). Se conecta al `MaterialApp` en main.dart.
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  /// Callback que abre el chat de un `hilo` (lo define main.dart, que sí conoce
  /// las pantallas). Así este servicio no importa la capa de UI.
  static void Function(String hilo)? alAbrirChat;

  /// Callback que abre la pantalla de RESERVAS del dueño (al tocar el push de
  /// "Nueva reserva"). Lo define main.dart.
  static void Function()? alAbrirReservas;

  /// Callback que abre "Mis canchas" (al tocar el push "tu cancha fue
  /// aprobada"). Lo define main.dart.
  static void Function()? alAbrirMisCanchas;

  /// Callback que abre "Mi bodega" en la pestaña Pedidos (al tocar el push de
  /// un pedido, siendo DUEÑO). Lo define main.dart.
  static void Function()? alAbrirBodegaDueno;

  /// Callback que abre la pantalla de pedidos del CLIENTE en la bodega del
  /// local [duenoEmail] (al tocar el push confirmado/entregado/anotado).
  /// Lo define main.dart.
  static void Function(String duenoEmail)? alAbrirBodegaCliente;

  /// Invoca la Edge Function `push-reserva` para avisar al DUEÑO de la cancha
  /// que entró una reserva (push dedicado, fuera del chat). Se pasa SOLO el id
  /// (o el del grupo si son varias horas); el servidor deriva destinatario y
  /// texto. Best-effort: si la función no está desplegada, no rompe nada.
  static Future<void> avisarReserva(
      {String reservaId = '', String grupoId = ''}) async {
    if (!SupabaseService.disponible) return;
    if (reservaId.isEmpty && grupoId.isEmpty) return;
    try {
      await SupabaseService.client.functions.invoke('push-reserva', body: {
        if (grupoId.isNotEmpty)
          'grupo_id': grupoId
        else
          'reserva_id': reservaId,
      });
    } catch (_) {}
  }

  /// Contador que sube cuando llega un push de PEDIDO DE BODEGA en foreground:
  /// la pestaña Pedidos de Mi bodega lo escucha y se refresca sola (estilo
  /// WhatsApp, igual que nuevaReserva con el panel de Reservas).
  static final ValueNotifier<int> nuevoPedidoBodega = ValueNotifier<int>(0);

  /// Contador que se incrementa cada vez que llega un push de CHAT en foreground.
  /// La bandeja (inbox) lo escucha para refrescarse SOLA al instante, sin tener
  /// que reabrir ni hacer pull-to-refresh (estilo WhatsApp).
  static final ValueNotifier<int> nuevoMensaje = ValueNotifier<int>(0);

  /// Igual pero para RESERVAS: sube cuando llega un push de "Nueva reserva". El
  /// panel de Reservas del dueño lo escucha y se refresca SOLO al instante.
  static final ValueNotifier<int> nuevaReserva = ValueNotifier<int>(0);

  /// Inicializa Firebase + messaging. Fail-safe: sin config → queda desactivado.
  static Future<void> init() async {
    if (_ok) return;
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(pushBackgroundHandler);
      _configurarListeners();
      LlamadaService.escucharEventos(); // botones de la llamada entrante
      // Al contestar en ESTE equipo, apaga el timbre en los otros de mi cuenta.
      LlamadaService.alAtender = cancelarLlamadaEnOtros;
      // Si YO cuelgo antes de que contesten, apaga el timbre del que RECIBE.
      LlamadaWebRTC.alCancelarEntranteRemota = cancelarLlamadaAlDestino;
      _ok = true;
    } catch (_) {
      _ok = false; // sin google-services.json / sin Firebase: push off
    }
  }

  /// Listeners de recepción: foreground (aviso in-app) y tap (abrir chat).
  static void _configurarListeners() {
    if (_listenersListos) return;
    _listenersListos = true;
    // Mensaje con la app ABIERTA: muestra el aviso in-app (el sistema no lo pinta).
    FirebaseMessaging.onMessage.listen(_enForeground);
    // Tap en la notificación del sistema con la app en segundo plano.
    FirebaseMessaging.onMessageOpenedApp.listen((m) => _abrir(m.data));
    // Tap que ABRIÓ la app estando cerrada: se procesa cuando el navegador ya
    // está montado (tras el primer frame).
    FirebaseMessaging.instance.getInitialMessage().then((m) {
      if (m == null) return;
      WidgetsBinding.instance.addPostFrameCallback((_) => _abrir(m.data));
    });
  }

  static void _abrir(Map<String, dynamic> data) {
    // Push de reserva → abre la pantalla de Reservas del dueño.
    if (data['tipo'] == 'reserva') {
      alAbrirReservas?.call();
      return;
    }
    // Push "tu cancha fue aprobada" → refresca propiedades y abre Mis canchas.
    if (data['tipo'] == 'reclamo_aprobado') {
      appState.sincronizarPropiedades();
      alAbrirMisCanchas?.call();
      return;
    }
    // Push de PEDIDO DE BODEGA → abre la pantalla del rol correcto: el CLIENTE
    // va a sus pedidos del local (data trae el correo del dueño = el local);
    // el DUEÑO va a Mi bodega, pestaña Pedidos. Avisos viejos sin 'destino'
    // caen por el correo del dueño si viaja.
    if (data['tipo'] == 'bodega_pedido') {
      final destino = (data['destino'] ?? '').toString();
      final dueno = (data['dueno'] ?? '').toString();
      if (destino == 'cliente' || dueno.isNotEmpty) {
        alAbrirBodegaCliente?.call(dueno);
      } else {
        alAbrirBodegaDueno?.call();
      }
      return;
    }
    final hilo = (data['hilo'] ?? '').toString();
    if (hilo.isNotEmpty) alAbrirChat?.call(hilo);
  }

  /// Aviso IN-APP cuando llega un mensaje con la app abierta. No se muestra si ya
  /// estás dentro de ese chat (ahí el mensaje llega solo por Realtime).
  static void _enForeground(RemoteMessage m) {
    // Otro dispositivo de mi cuenta atendió/rechazó → apaga el timbre aquí.
    if (m.data['tipo'] == 'cancelar_llamada') {
      LlamadaService.cancelarEntrante((m.data['room'] ?? '').toString());
      return;
    }
    // Llamada entrante con la app ABIERTA: además de la notificación de CallKit
    // (que pone el timbre), abre la pantalla ENTRANTE a PANTALLA COMPLETA
    // dentro de la app (Contestar/Rechazar), como WhatsApp cuando estás con la
    // app al frente. `revisarEntranteAlFrente` ya trae todos los candados
    // (no duplica si CallKit atendió, si hay llamada en curso, etc.).
    if (m.data['tipo'] == 'llamada') {
      final hilo = (m.data['hilo'] ?? '').toString();
      () async {
        await LlamadaService.mostrarEntrante(
          room: LlamadaService.salaChat(hilo),
          caller: (m.data['caller'] ?? '').toString(),
          video: (m.data['video'] ?? '') == 'true',
          hilo: hilo,
        );
        await LlamadaService.revisarEntranteAlFrente();
      }();
      return;
    }
    // Push de RESERVA con la app abierta: sonido + banner que abre Reservas, y
    // avisa al panel de Reservas para que se REFRESQUE solo (estilo WhatsApp).
    if (m.data['tipo'] == 'reserva') {
      final n = m.notification;
      // Refresco GLOBAL: baja la reserva nueva pase lo que pase (aunque estés en
      // otra pantalla), y avisa al panel de Reservas por si está abierto.
      appState.cargarReservasRemotas();
      nuevaReserva.value++;
      try {
        _sonidoPush.play(AssetSource('sonidos/pichan.mp3'));
      } catch (_) {}
      _mostrarBanner((n?.title ?? 'Nueva reserva').trim(), (n?.body ?? '').trim(),
          onTap: () => alAbrirReservas?.call());
      return;
    }
    // Push "tu cancha fue aprobada" con la app abierta: refresca propiedades (se
    // cae el cartel "pendiente" y se habilitan reservas) + sonido + banner.
    if (m.data['tipo'] == 'reclamo_aprobado') {
      final n = m.notification;
      appState.sincronizarPropiedades();
      try {
        _sonidoPush.play(AssetSource('sonidos/pichan.mp3'));
      } catch (_) {}
      _mostrarBanner((n?.title ?? '¡Cancha aprobada!').trim(),
          (n?.body ?? '').trim(), onTap: () => alAbrirMisCanchas?.call());
      return;
    }
    final hilo = (m.data['hilo'] ?? '').toString();
    // AVISOS GENÉRICOS sin hilo de chat (pedido de bodega, retos, academia,
    // puntos, recargas…): con la app ABIERTA el sistema NO los pinta y antes
    // se DESCARTABAN en silencio (bug reportado por el director: el pedido no
    // "llegó" porque el dueño tenía la app al frente). Sonido + banner in-app,
    // igual que reservas/chat.
    if (hilo.isEmpty) {
      final n = m.notification;
      final t = (n?.title ?? '').trim();
      final c = (n?.body ?? '').trim();
      if (t.isEmpty && c.isEmpty) return; // data-only: nada que pintar
      // Pedido de bodega: avisa al panel para que se refresque solo.
      final esBodega = m.data['tipo'] == 'bodega_pedido';
      if (esBodega) nuevoPedidoBodega.value++;
      try {
        _sonidoPush.play(AssetSource('sonidos/pichan.mp3'));
      } catch (_) {}
      // El banner in-app también navega al tocarlo (igual que la notificación
      // del sistema): pedidos de bodega van a su pantalla.
      _mostrarBanner(t.isEmpty ? 'Pichangol' : t, c,
          onTap: esBodega ? () => _abrir(m.data) : null);
      return;
    }
    // Avisa a la bandeja para que se refresque sola (aunque el chat esté abierto
    // o silenciado): así el mensaje "se siembra" al toque, sin reabrir.
    nuevoMensaje.value++;
    if (hilo == appState.hiloChatAbierto) return;
    // Chat silenciado (campanita): no molestamos con el aviso in-app.
    if (appState.chatSilenciado(hilo)) return;
    final n = m.notification;
    final titulo = (n?.title ?? '').trim().isNotEmpty ? n!.title! : 'Nuevo mensaje';
    final cuerpo = (n?.body ?? '').trim();
    // Si es el AVISO de una llamada (📹 Videollamada / 📞 Llamada de voz) o hay
    // una llamada sonando/en curso de este hilo, NO reproducimos el "Pichan" de
    // chat: la llamada ya tiene su propio timbre (evita el "pichan" tardío que se
    // oía al rechazar).
    final esAvisoLlamada = cuerpo.contains('Videollamada') ||
        cuerpo.contains('Llamada de voz') ||
        LlamadaService.esLlamadaReciente(hilo) ||
        LlamadaWebRTC.instance.activa;
    if (esAvisoLlamada) return;
    // Sonido "Pichan" (estilo Yape) con la app abierta (el sistema no lo pinta).
    try {
      _sonidoPush.play(AssetSource('sonidos/pichan.mp3'));
    } catch (_) {}
    _mostrarBanner(titulo, cuerpo, hilo: hilo);
  }

  /// Reproductor del sonido "Pichan" para avisos con la app en foreground.
  static final AudioPlayer _sonidoPush = AudioPlayer();

  /// Tarjeta flotante superior tipo WhatsApp (heads-up): tarjeta BLANCA con la
  /// foto del remitente + nombre + preview. Tocable (abre el chat), auto-oculta.
  static void _mostrarBanner(String titulo, String cuerpo,
      {String hilo = '', VoidCallback? onTap}) {
    final overlay = navigatorKey.currentState?.overlay;
    if (overlay == null) return;
    // Foto del remitente (deducida del hilo directo).
    String otroEmail = '';
    if (hilo.startsWith('directo_')) {
      final partes = hilo.substring('directo_'.length).split('|');
      final yo = (appState.usuario?.email ?? '').trim().toLowerCase();
      if (partes.length == 2) {
        otroEmail = partes[0] == yo ? partes[1] : partes[0];
      }
    }
    final foto = otroEmail.isNotEmpty ? (appState.fotoDe(otroEmail) ?? '') : '';
    final inicial =
        titulo.trim().isNotEmpty ? titulo.trim()[0].toUpperCase() : '?';

    late OverlayEntry entry;
    var cerrado = false;
    void cerrar() {
      if (cerrado) return;
      cerrado = true;
      entry.remove();
    }

    entry = OverlayEntry(
      builder: (context) => Positioned(
        top: MediaQuery.of(context).padding.top + 8,
        left: 10,
        right: 10,
        child: Material(
          color: Colors.transparent,
          child: GestureDetector(
            onTap: () {
              cerrar();
              if (onTap != null) {
                onTap();
              } else if (hilo.isNotEmpty) {
                alAbrirChat?.call(hilo);
              }
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                boxShadow: const [
                  BoxShadow(
                      color: Color(0x22000000),
                      blurRadius: 14,
                      offset: Offset(0, 4)),
                ],
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: limaSuave,
                    backgroundImage: foto.isNotEmpty ? NetworkImage(foto) : null,
                    child: foto.isEmpty
                        ? Text(inicial,
                            style: const TextStyle(
                                color: bosque, fontWeight: FontWeight.w800))
                        : null,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(titulo,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                color: Color(0xFF111111),
                                fontWeight: FontWeight.w800,
                                fontSize: 14.5)),
                        if (cuerpo.isNotEmpty)
                          Text(cuerpo,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: Colors.black54, fontSize: 13)),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right, color: Colors.black26),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    overlay.insert(entry);
    Future.delayed(const Duration(seconds: 5), cerrar);
  }

  /// Pide permiso de notificaciones, obtiene el token FCM y lo guarda para
  /// [email]. Llamar tras el login (y al restaurar sesión). Idempotente.
  static Future<void> registrarParaUsuario(String? email) async {
    final e = (email ?? '').trim().toLowerCase();
    if (!_ok || e.isEmpty) return;
    _email = e;
    try {
      final fm = FirebaseMessaging.instance;
      await fm.requestPermission(); // Android 13+ / iOS piden permiso explícito
      final token = await fm.getToken();
      if (token != null && token.isNotEmpty) {
        _token = token;
        await _guardarToken(e, token);
      }
      // El token puede rotar: lo re-guardamos cuando cambie. Cancela la
      // suscripción anterior para no acumular listeners al re-registrar.
      _tokenSub?.cancel();
      _tokenSub = fm.onTokenRefresh.listen((t) {
        _token = t;
        _guardarToken(_email, t);
      });
    } catch (_) {
      // permiso denegado / sin red: no rompe nada
    }
  }

  /// Al contestar/rechazar una llamada en ESTE equipo, avisa al backend para que
  /// apague el timbre en los OTROS dispositivos de la misma cuenta ("contestada
  /// en otro dispositivo", estilo WhatsApp). Fail-safe: si la Edge Function no
  /// está desplegada, no rompe nada.
  static Future<void> cancelarLlamadaEnOtros(String room) async {
    if (room.isEmpty || _email.isEmpty || !SupabaseService.disponible) return;
    try {
      await SupabaseService.client.functions.invoke('cancelar-llamada', body: {
        'room': room,
        'email': _email,
        'excluir_token': _token ?? '',
      });
    } catch (_) {}
  }

  /// El que LLAMA colgó antes de que el otro conteste: manda un push de
  /// cancelación al DESTINO ([emailDestino]) para apagarle el timbre (aún no está
  /// suscrito al canal WebRTC, así que el `bye` no le llega). Misma Edge Function.
  static Future<void> cancelarLlamadaAlDestino(
      String room, String emailDestino) async {
    final dest = emailDestino.trim().toLowerCase();
    if (room.isEmpty || dest.isEmpty || !SupabaseService.disponible) return;
    try {
      await SupabaseService.client.functions.invoke('cancelar-llamada', body: {
        'room': room,
        'email': dest,
        'excluir_token': '',
      });
    } catch (_) {}
  }

  static Future<void> _guardarToken(String email, String token) async {
    if (!SupabaseService.disponible) return;
    final plataforma =
        defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
    try {
      await SupabaseService.client.from('pichangol_push_tokens').upsert({
        'token': token,
        'email': email,
        'plataforma': plataforma,
        'actualizado': DateTime.now().toUtc().toIso8601String(),
      }, onConflict: 'token');
      // Un token pertenece a UN dispositivo: si estaba asociado a otra cuenta
      // (se cambió de sesión en este equipo), el upsert por 'token' lo reasigna.
      // No borramos otros tokens de la misma cuenta para permitir multi-dispositivo
      // (cel + tablet): la Edge Function deduplica por token al enviar.
    } catch (_) {}
  }

  /// Al cerrar sesión: borra el token de ESTE dispositivo para dejar de recibir
  /// push de la cuenta anterior. Fail-safe.
  static Future<void> olvidar() async {
    final t = _token;
    _email = '';
    _tokenSub?.cancel();
    _tokenSub = null;
    if (t == null || !SupabaseService.disponible) return;
    try {
      await SupabaseService.client
          .from('pichangol_push_tokens')
          .delete()
          .eq('token', t);
    } catch (_) {}
    _token = null;
  }
}
