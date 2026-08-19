import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../theme.dart';

/// Globo flotante de CHAT interno (siempre a la mano). Con identidad Pichangol:
/// - Si hay una imagen ([logoUrl]: LOGO de la academia o FOTO de la cancha) →
///   la usa como avatar con una insignia verde de chat (matiz "WhatsApp") → se
///   siente personal.
/// - Si NO hay imagen (o falla la carga) → un robot (asistente), verde de marca,
///   con la puntita amarilla (la "o" pelota de Pichang·o·l).
/// Se usa como `floatingActionButton` en las fichas (academia, cancha/club).
class ChatBurbuja extends StatelessWidget {
  const ChatBurbuja({
    super.key,
    required this.onTap,
    this.logoUrl,
  });

  final VoidCallback onTap;

  /// Logo de la academia/cancha. Si viene (y carga), reemplaza al robot.
  final String? logoUrl;

  // Verde WhatsApp oficial: da el "matiz de chat" a la insignia sobre el logo.
  static const _verdeWa = Color(0xFF25D366);

  // Contenido del robot (sin fondo: el fondo lima lo pone el Material).
  Widget _robotContenido() => Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.center,
        children: [
          const FaIcon(FontAwesomeIcons.robot, size: 24, color: Colors.white),
          Positioned(
            top: 8,
            right: 12,
            child: Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(
                  color: Color(0xFFD9B45A), shape: BoxShape.circle),
            ),
          ),
        ],
      );

  @override
  Widget build(BuildContext context) {
    final tieneLogo = (logoUrl ?? '').trim().isNotEmpty;

    return SizedBox(
      width: 60,
      height: 60,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // Círculo tappable con sombra (estilo FAB). El fondo va en el Material
          // (blanco si hay logo, lima si es robot) para que la elevación renderice.
          Material(
            elevation: 4,
            shape: const CircleBorder(),
            clipBehavior: Clip.antiAlias,
            color: tieneLogo ? Colors.white : lima,
            child: InkWell(
              onTap: onTap,
              customBorder: const CircleBorder(),
              child: SizedBox(
                width: 56,
                height: 56,
                child: tieneLogo
                    ? Image.network(
                        logoUrl!.trim(),
                        fit: BoxFit.cover,
                        // Si el logo no carga, cae al robot sobre fondo lima.
                        errorBuilder: (_, __, ___) => Container(
                            color: lima,
                            alignment: Alignment.center,
                            child: _robotContenido()),
                      )
                    : _robotContenido(),
              ),
            ),
          ),
          // Insignia de chat (matiz WhatsApp) SOLO cuando hay logo: deja claro
          // que el avatar es un botón para chatear.
          if (tieneLogo)
            Positioned(
              right: -1,
              bottom: -1,
              child: Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  color: _verdeWa,
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 2),
                ),
                alignment: Alignment.center,
                child: const Icon(Icons.chat_bubble_rounded,
                    size: 10, color: Colors.white),
              ),
            ),
        ],
      ),
    );
  }
}
