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
      // En PROD no inventamos cuenta: si Google falla, se trata como cancelado
      // (no crear un usuario falso). En dev/qas cae a una cuenta demo para no
      // bloquear el flujo si alguien usa el botón de Google.
      if (_entorno == 'prod') return null;
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
