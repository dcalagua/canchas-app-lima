import 'package:flutter/material.dart';

/// Verde WhatsApp (el mismo que se usa para los accesos de WhatsApp en el app).
const Color _verdeWhatsapp = Color(0xFF25D366);

/// Ícono de "Mensajes" estilo WhatsApp, "con vida" (regla de UI): una burbuja de
/// chat SIEMPRE verde WhatsApp con una "P" de Pichangol calada en blanco al
/// centro (como el "B" de WhatsApp Business). A diferencia de un ícono plano, no
/// se apaga a gris cuando no está seleccionado —resalta como marca—; solo baja un
/// poco de opacidad para indicar el estado no seleccionado.
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan({super.key, this.size = 24, this.activo = true});
  final double size;

  /// Si false (pestaña no seleccionada), se muestra con un poco menos de opacidad.
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: activo ? 1 : 0.72,
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Icon(Icons.chat_bubble, size: size, color: _verdeWhatsapp),
            // La burbuja tiene la colita abajo → subo la "P" para centrarla en el
            // cuerpo (centrado óptico) y la calo en blanco.
            Padding(
              padding: EdgeInsets.only(bottom: size * 0.12),
              child: Text(
                'P',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: size * 0.52,
                  height: 1,
                  fontWeight: FontWeight.w900,
                  color: Colors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
