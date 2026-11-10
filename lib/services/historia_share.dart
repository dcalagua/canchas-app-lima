import 'package:flutter/services.dart';

/// Compartir una historia DIRECTO a la Historia de Instagram/Facebook (1 toque,
/// como WhatsApp), vía el intent nativo "Add to Story" (MainActivity expone el
/// MethodChannel `pichangol/share_story`). Requiere el Facebook App ID
/// (dart-define `FACEBOOK_APP_ID`) para la atribución que exige Meta.
///
/// Solo Android. En iOS o si no está configurado / la app no está instalada,
/// [instagram]/[facebook] devuelven false y la UI cae a la hoja de compartir.
class HistoriaShare {
  static const _canal = MethodChannel('pichangol/share_story');
  static const _appId = String.fromEnvironment('FACEBOOK_APP_ID');

  static bool get configurado => _appId.isNotEmpty;

  /// Publica el archivo [rutaLocal] (foto o video) directo a la Historia de IG.
  static Future<bool> instagram(String rutaLocal, {bool video = false}) =>
      _compartir('instagram', rutaLocal, video);

  /// Publica el archivo [rutaLocal] directo a la Historia de Facebook.
  static Future<bool> facebook(String rutaLocal, {bool video = false}) =>
      _compartir('facebook', rutaLocal, video);

  static Future<bool> _compartir(String red, String ruta, bool video) async {
    if (!configurado || ruta.isEmpty) return false;
    try {
      final ok = await _canal.invokeMethod<bool>(
          red, {'path': ruta, 'video': video, 'appId': _appId});
      return ok ?? false;
    } catch (_) {
      return false; // iOS / sin app / error → la UI cae a la hoja de compartir
    }
  }
}
