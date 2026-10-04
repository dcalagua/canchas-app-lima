import 'package:flutter/material.dart';

/// Ícono de la pestaña MENSAJES en las barras/rails.
///
/// Decisión del director (sep-2026): va un ícono de chat NORMAL, del mismo
/// lenguaje que Explorar/Partidos/Reservas (línea cuando no está seleccionado,
/// relleno cuando sí). Nada de logo ni burbuja de marca: la pestaña se lee
/// como "mensajes" de un vistazo y no compite con el logo de Pichangol.
/// (Historial: llevó el pin de PCG → se revirtió; luego la burbuja con la "P"
/// de Pichan → también se revirtió. Este es el definitivo.)
///
/// Si no se pasa [color], hereda el del `IconTheme` (así en la barra inferior
/// se pinta igual que las demás pestañas); los rails/barras "con vida" le pasan
/// el color de su sección, como a los otros íconos.
class IconoMensajesLogo extends StatelessWidget {
  const IconoMensajesLogo(
      {super.key, this.size = 25, this.activo = true, this.color});
  final double size;
  final bool activo;
  final Color? color;

  @override
  Widget build(BuildContext context) =>
      IconoChatPichan(size: size, activo: activo, color: color);
}

/// Mismo ícono, nombre histórico (lo usan varias barras).
class IconoChatPichan extends StatelessWidget {
  const IconoChatPichan(
      {super.key, this.size = 25, this.activo = true, this.color});
  final double size;

  /// Seleccionado → versión rellena; si no, la de línea.
  final bool activo;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Icon(
      activo ? Icons.chat_bubble : Icons.chat_bubble_outline,
      size: size,
      color: color,
    );
  }
}
