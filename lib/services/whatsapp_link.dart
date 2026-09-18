import 'package:url_launcher/url_launcher.dart';

import '../config/pais.dart';

/// Abre WhatsApp con un mensaje prellenado (deep link `wa.me`). Fase 1: el
/// recordatorio de cobro lo dispara el profe con un toque, sin backend. En
/// Fase 2 se puede automatizar con el adapter de Twilio del backend.
class WhatsAppLink {
  static Future<bool> abrir(String telefono, String mensaje) async {
    final tel = _normalizar(telefono);
    if (tel.isEmpty) return false;
    final uri = Uri.parse(
        'https://wa.me/$tel?text=${Uri.encodeComponent(mensaje)}');
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }

  /// Comparte un mensaje SIN destinatario fijo: abre WhatsApp para que el
  /// usuario elija a quién enviárselo (útil para pasar el código de la
  /// academia a un alumno).
  static Future<bool> compartir(String mensaje) async {
    final uri =
        Uri.parse('https://wa.me/?text=${Uri.encodeComponent(mensaje)}');
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }

  /// Normaliza a formato internacional según el **país activo**. Si el número
  /// viene como celular local (largo exacto del país: 9 en PE/EC, 8 en BO), le
  /// antepone el código internacional (+51 / +591 / +593). Si trae más dígitos,
  /// se asume que ya incluye el código de país y se respeta.
  static String _normalizar(String t) {
    var d = t.replaceAll(RegExp(r'[^0-9]'), '');
    if (d.length == paisActual.telLongitud) d = '${paisActual.codigoTel}$d';
    return d;
  }
}
