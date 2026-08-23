import 'package:flutter/material.dart';

/// Globo flotante de CHAT interno (siempre a la mano). Con identidad Pichangol:
/// - Si hay una imagen ([logoUrl]: LOGO de la academia o FOTO de la cancha) →
///   la usa como avatar → se siente personal.
/// - Si NO hay imagen (o falla la carga) → la MASCOTA de la marca: el pin de
///   Pichangol (el de la pestaña Mensajes, decisión del director) sobre blanco.
/// En AMBOS casos lleva la insignia verde de chat (matiz "WhatsApp") para que
/// se lea como "aquí se chatea", no como un botón cualquiera.
/// Se usa como `floatingActionButton` en las fichas (academia, cancha/club).
class ChatBurbuja extends StatelessWidget {
  const ChatBurbuja({
    super.key,
    required this.onTap,
    this.logoUrl,
  });

  final VoidCallback onTap;

  /// Logo de la academia/cancha. Si viene (y carga), reemplaza al pin.
  final String? logoUrl;

  // Verde WhatsApp oficial: da el "matiz de chat" a la insignia sobre el logo.
  static const _verdeWa = Color(0xFF25D366);

  // Fallback de marca: el pin de Pichangol (la "o" pelota) sobre blanco —
  // el mismo asset de la pestaña Mensajes, nada de robots genéricos.
  Widget _pichangolContenido() => Container(
        color: Colors.white,
        alignment: Alignment.center,
        child: Image.asset(
          'assets/brand/logo_pin.png',
          width: 32,
          height: 32,
          filterQuality: FilterQuality.medium,
        ),
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
          // Círculo tappable con sombra (estilo FAB). Fondo blanco en ambos
          // casos (logo o pin de marca) para que la elevación renderice.
          Material(
            elevation: 4,
            shape: const CircleBorder(),
            clipBehavior: Clip.antiAlias,
            color: Colors.white,
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
                        // Si el logo no carga, cae al pin de Pichangol.
                        errorBuilder: (_, __, ___) => _pichangolContenido(),
                      )
                    : _pichangolContenido(),
              ),
            ),
          ),
          // Insignia de chat (matiz WhatsApp) SIEMPRE: deja claro que este
          // globo es para chatear, con logo del local o con el pin de marca.
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
