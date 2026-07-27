import 'package:flutter/material.dart';

/// Ícono de "Mensajes": el logo de WhatsApp a color (verde con teléfono blanco),
/// "con vida" (regla de UI Airbnb). Es una imagen (assets/icon/whatsapp.png), no
/// un glyph, para conservar los dos colores. No se apaga a gris cuando la pestaña
/// no está seleccionada —resalta como marca—; solo baja un poco de opacidad.
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan({super.key, this.size = 24, this.activo = true});
  final double size;

  /// Si false (pestaña no seleccionada), se muestra con un poco menos de opacidad.
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: activo ? 1 : 0.72,
      child: Image.asset(
        'assets/icon/whatsapp.png',
        width: size,
        height: size,
        fit: BoxFit.contain,
      ),
    );
  }
}
