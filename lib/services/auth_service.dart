import 'package:google_sign_in/google_sign_in.dart';

import '../models/usuario.dart';

/// Autenticación del jugador. Hoy: Google Sign-In con fallback de demo.
///
/// Para que el login sea Gmail REAL en el APK hay que:
///  1. Crear un OAuth Client (Android + iOS) en Google Cloud / Firebase.
///  2. Registrar el SHA-1 de la firma estable (ver RELEASE_SIGNING.md).
///  3. iOS: agregar el reversed client id como URL scheme en Info.plist.
/// Mientras eso no exista, [entrarConGoogle] cae en una cuenta de demostración
/// para no bloquear el flujo de reserva.
class AuthService {
  static final GoogleSignIn _google =
      GoogleSignIn(scopes: const ['email', 'profile']);

  static const _entorno =
      String.fromEnvironment('ENTORNO', defaultValue: 'dev');

  /// Último error de Google Sign-In (para diagnóstico en la UI). Null si el
  /// último intento salió bien o fue cancelado por el usuario.
  static String? ultimoError;

  /// Devuelve el usuario, o null si el usuario canceló el login (o si Google
  /// falló; en ese caso [ultimoError] trae el detalle). NO cae a cuenta demo:
  /// el login de pruebas ahora es explícito (entrarComo), así que un fallo de
  /// Google se ve tal cual para poder diagnosticarlo.
  static Future<Usuario?> entrarConGoogle() async {
    ultimoError = null;
    try {
      final cuenta = await _google.signIn();
      if (cuenta == null) return null; // cancelado por el usuario
      return Usuario(
        nombre: cuenta.displayName ?? cuenta.email.split('@').first,
        email: cuenta.email,
        fotoUrl: cuenta.photoUrl,
      );
    } catch (e) {
      // Guarda el error real (ej. ApiException: 10 = DEVELOPER_ERROR por SHA-1/
      // paquete que no calzan) para mostrarlo en la hoja de login.
      ultimoError = e.toString();
      return null;
    }
  }

  static Future<void> salir() async {
    try {
      await _google.signOut();
    } catch (_) {}
  }
}
