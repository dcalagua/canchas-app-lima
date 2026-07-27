import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

/// Verde WhatsApp (el mismo que se usa para los accesos de WhatsApp en el app).
const Color _verdeWhatsapp = Color(0xFF25D366);

/// Ícono de "Mensajes": el logo de WhatsApp (glyph de Font Awesome) en verde,
/// "con vida" (regla de UI Airbnb). No se apaga a gris cuando la pestaña no está
/// seleccionada —resalta como marca—; solo baja un poco de opacidad.
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan({super.key, this.size = 24, this.activo = true});
  final double size;

  /// Si false (pestaña no seleccionada), se muestra con un poco menos de opacidad.
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: activo ? 1 : 0.72,
      child: FaIcon(FontAwesomeIcons.whatsapp, color: _verdeWhatsapp, size: size),
    );
  }
}
