import 'package:flutter/material.dart';

import '../theme.dart';

/// Globo flotante de CHAT interno (siempre a la mano, estilo "burbuja" de
/// WhatsApp pero con identidad Pichangol: verde de marca + burbuja de diálogo,
/// no el teléfono de WhatsApp). Se usa como `floatingActionButton` en las fichas
/// (academia, cancha/club) para escribirle al profe / al dueño sin hacer scroll.
class ChatBurbuja extends StatelessWidget {
  const ChatBurbuja({
    super.key,
    required this.onTap,
    this.etiqueta = 'Chat',
    this.heroTag,
  });

  final VoidCallback onTap;

  /// Texto corto junto al ícono (ej. "Chat", "Escríbenos"). Si es vacío, queda
  /// como globo circular sin texto.
  final String etiqueta;
  final Object? heroTag;

  @override
  Widget build(BuildContext context) {
    final icono = Container(
      width: 26,
      height: 26,
      alignment: Alignment.center,
      child: Stack(
        alignment: Alignment.center,
        children: [
          const Icon(Icons.chat_bubble_rounded, size: 26, color: Colors.white),
          // Punto lima/amarillo = guiño a la "o" pelota de Pichang·o·l: distingue
          // la burbuja de la de WhatsApp.
          Positioned(
            bottom: 8,
            child: Container(
              width: 5,
              height: 5,
              decoration: const BoxDecoration(
                  color: Color(0xFFF2C94C), shape: BoxShape.circle),
            ),
          ),
        ],
      ),
    );

    if (etiqueta.trim().isEmpty) {
      return FloatingActionButton(
        heroTag: heroTag,
        onPressed: onTap,
        backgroundColor: lima,
        foregroundColor: Colors.white,
        elevation: 4,
        child: icono,
      );
    }
    return FloatingActionButton.extended(
      heroTag: heroTag,
      onPressed: onTap,
      backgroundColor: lima,
      foregroundColor: Colors.white,
      elevation: 4,
      icon: icono,
      label: Text(etiqueta,
          style: const TextStyle(fontWeight: FontWeight.w800)),
    );
  }
}
