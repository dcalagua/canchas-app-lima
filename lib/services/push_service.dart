import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../theme.dart';
import 'supabase_service.dart';

/// Handler de mensajes en SEGUNDO PLANO / app cerrada. Debe ser una función de
/// nivel superior con este pragma (Firebase la ejecuta en un isolate aparte).
/// No necesita lógica: el sistema ya muestra la notificación (`notification`
/// del payload). El TAP se maneja en `onMessageOpenedApp` / `getInitialMessage`.
@pragma('vm:entry-point')
Future<void> pushBackgroundHandler(RemoteMessage message) async {}

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

  /// Inicializa Firebase + messaging. Fail-safe: sin config → queda desactivado.
  static Future<void> init() async {
    if (_ok) return;
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(pushBackgroundHandler);
      _configurarListeners();
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
    final hilo = (data['hilo'] ?? '').toString();
    if (hilo.isNotEmpty) alAbrirChat?.call(hilo);
  }

  /// Aviso IN-APP cuando llega un mensaje con la app abierta. No se muestra si ya
  /// estás dentro de ese chat (ahí el mensaje llega solo por Realtime).
  static void _enForeground(RemoteMessage m) {
    final hilo = (m.data['hilo'] ?? '').toString();
    if (hilo.isEmpty || hilo == appState.hiloChatAbierto) return;
    final n = m.notification;
    final titulo = (n?.title ?? '').trim().isNotEmpty ? n!.title! : 'Nuevo mensaje';
    final cuerpo = (n?.body ?? '').trim();
    _mostrarBanner(titulo, cuerpo, hilo);
  }

  /// Tarjeta flotante superior (estilo heads-up), tocable, auto-oculta a los 5 s.
  static void _mostrarBanner(String titulo, String cuerpo, String hilo) {
    final overlay = navigatorKey.currentState?.overlay;
    if (overlay == null) return;
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
              alAbrirChat?.call(hilo);
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: bosque,
                borderRadius: BorderRadius.circular(16),
                boxShadow: const [
                  BoxShadow(
                      color: Color(0x33000000), blurRadius: 12, offset: Offset(0, 4)),
                ],
              ),
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 18,
                    backgroundColor: Colors.white24,
                    child: Icon(Icons.chat_bubble, color: Colors.white, size: 18),
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
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                                fontSize: 14.5)),
                        if (cuerpo.isNotEmpty)
                          Text(cuerpo,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: Colors.white70, fontSize: 13)),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white70, size: 18),
                    onPressed: cerrar,
                  ),
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
