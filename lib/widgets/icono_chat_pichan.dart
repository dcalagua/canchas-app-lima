import 'package:flutter/material.dart';

/// Ícono de "Mensajes" estilo WhatsApp: una burbuja de chat con una "P" de
/// Pichangol calada en el centro (como el "B" de WhatsApp Business). La "P" usa
/// el color de fondo para verse "recortada" sobre la burbuja, así se ve bien
/// tanto seleccionada (burbuja verde) como sin seleccionar (burbuja gris). La
/// burbuja toma el color del IconTheme, así respeta el estado del NavigationBar.
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan({super.key, this.size = 24});
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = IconTheme.of(context).color ??
        Theme.of(context).colorScheme.onSurface;
    // La "P" se cala con el color de fondo (blanco en claro) sobre la burbuja.
    final calado = Theme.of(context).scaffoldBackgroundColor;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Icon(Icons.chat_bubble, size: size, color: color),
          // La burbuja tiene la colita abajo → subo la "P" para centrarla en el
          // cuerpo de la burbuja (centrado óptico, no geométrico).
          Padding(
            padding: EdgeInsets.only(bottom: size * 0.12),
            child: Text(
              'P',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: size * 0.52,
                height: 1,
                fontWeight: FontWeight.w900,
                color: calado,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
