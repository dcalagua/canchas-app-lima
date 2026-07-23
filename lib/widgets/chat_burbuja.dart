import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

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
    // Ícono "asistente" (robot) importado de FontAwesome: más carácter que una
    // burbuja simple y distinto a WhatsApp. La punta amarilla (la "o" pelota de
    // Pichang·o·l) le da identidad de marca.
    final icono = SizedBox(
      width: 30,
      height: 26,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          const FaIcon(FontAwesomeIcons.robot, size: 22, color: Colors.white),
          Positioned(
            top: -3,
            right: 1,
            child: Container(
              width: 6,
              height: 6,
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
