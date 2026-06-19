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

  /// Devuelve el usuario, o null si el usuario canceló el login.
  static Future<Usuario?> entrarConGoogle() async {
    try {
      final cuenta = await _google.signIn();
      if (cuenta == null) return null; // cancelado por el usuario
      return Usuario(
        nombre: cuenta.displayName ?? cuenta.email.split('@').first,
        email: cuenta.email,
        fotoUrl: cuenta.photoUrl,
      );
    } catch (_) {
      // OAuth aún no configurado en este build: cuenta demo para probar el flujo.
      return const Usuario(
        nombre: 'Jugador Pichangol',
        email: 'jugador@gmail.com',
        fotoUrl: null,
      );
    }
  }

  static Future<void> salir() async {
    try {
      await _google.signOut();
    } catch (_) {}
  }
}
