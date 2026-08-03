import 'package:flutter/material.dart';

import 'icono_chat_pichan.dart';

/// Barra de navegación INFERIOR con SCROLL horizontal: íconos con color por
/// sección + etiqueta en UNA línea. Cuando hay varias secciones, la barra se
/// DESLIZA en vez de apretar/partir los textos (ej. "Cancha\ns"). La usan el
/// panel del DUEÑO (home_shell) y la ACADEMIA (academia_shell) en móvil.
class BarraNavScroll extends StatelessWidget {
  const BarraNavScroll({
    super.key,
    required this.iconos,
    required this.etiquetas,
    required this.colores,
    required this.iMensajes,
    required this.activo,
    required this.onTap,
  });

  final List<IconData> iconos;
  final List<String> etiquetas;
  final List<Color> colores;

  /// Índice de la pestaña "Mensajes" (usa el ícono de chat de marca). -1 si no hay.
  final int iMensajes;
  final int activo;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surface,
      elevation: 8,
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 64,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: Row(
              children: [
                for (var i = 0; i < iconos.length; i++) _item(context, i),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _item(BuildContext context, int i) {
    final sel = activo == i;
    final color = colores[i];
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => onTap(i),
      borderRadius: BorderRadius.circular(14),
      child: SizedBox(
        width: 76,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            i == iMensajes
                ? IconoChatPichan(activo: sel)
                : Icon(iconos[i], color: color, size: 25),
            const SizedBox(height: 3),
            Text(
              etiquetas[i],
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: sel ? FontWeight.w800 : FontWeight.w500,
                color: sel ? cs.onSurface : cs.onSurface.withOpacity(0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
