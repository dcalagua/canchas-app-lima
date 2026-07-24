import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'supabase_service.dart';

/// Handler de mensajes en SEGUNDO PLANO / app cerrada. Debe ser una función de
/// nivel superior con este pragma (Firebase la ejecuta en un isolate aparte).
/// No necesita lógica: el sistema ya muestra la notificación (`notification`
/// del payload). Aquí sólo se deja el gancho.
@pragma('vm:entry-point')
Future<void> pushBackgroundHandler(RemoteMessage message) async {
  // Sin lógica: la notificación la pinta el sistema. (Si luego se quiere
  // navegar a un chat concreto, se lee message.data aquí / en onMessageOpenedApp.)
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
class PushService {
  static bool _ok = false;
  static bool get disponible => _ok;

  static String? _token;
  static String _email = '';

  /// Inicializa Firebase + messaging. Fail-safe: sin config → queda desactivado.
  static Future<void> init() async {
    if (_ok) return;
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(pushBackgroundHandler);
      _ok = true;
    } catch (_) {
      _ok = false; // sin google-services.json / sin Firebase: push off
    }
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
      // El token puede rotar: lo re-guardamos cuando cambie.
      fm.onTokenRefresh.listen((t) {
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
      // Evita NOTIFICACIONES DOBLES: el token FCM rota (reinstalar/actualizar) y
      // el viejo queda en la tabla, así que el push saldría 2 veces al MISMO
      // dispositivo. Borra los tokens ANTERIORES de esta cuenta en esta
      // plataforma (una cuenta usa un dispositivo activo por plataforma).
      await SupabaseService.client
          .from('pichangol_push_tokens')
          .delete()
          .eq('email', email)
          .eq('plataforma', plataforma)
          .neq('token', token);
    } catch (_) {}
  }

  /// Al cerrar sesión: borra el token de ESTE dispositivo para dejar de recibir
  /// push de la cuenta anterior. Fail-safe.
  static Future<void> olvidar() async {
    final t = _token;
    _email = '';
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
