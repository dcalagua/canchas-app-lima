import 'package:flutter/material.dart';

import '../theme.dart';
import 'marca.dart';

/// Loader de marca (mini-splash) para los estados de PRELOAD: en vez de un
/// spinner pelado, muestra la pelota de Pichangol rebotando + el wordmark +
/// "Cargando…", igual que el splash inicial. Reutilizable en cualquier pantalla.
class CargandoPichangol extends StatefulWidget {
  const CargandoPichangol({
    super.key,
    this.texto = 'Cargando…',
    this.conMarca = true,
  });

  /// Texto bajo la pelota (p. ej. "Cargando tus canchas…").
  final String texto;

  /// Muestra el wordmark "Pichangol" (en espacios chicos se puede ocultar).
  final bool conMarca;

  @override
  State<CargandoPichangol> createState() => _CargandoPichangolState();
}

class _CargandoPichangolState extends State<CargandoPichangol>
    with SingleTickerProviderStateMixin {
  late final AnimationController _rebote = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 560))
    ..repeat(reverse: true);

  @override
  void dispose() {
    _rebote.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Pelota lima que rebota (como en el splash).
          AnimatedBuilder(
            animation: _rebote,
            builder: (context, child) {
              final dy = -10 * Curves.easeInOut.transform(_rebote.value);
              return Transform.translate(offset: Offset(0, dy), child: child);
            },
            child: Container(
              width: 74,
              height: 74,
              decoration: const BoxDecoration(
                color: lima,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                      color: Color(0x33000000),
                      blurRadius: 14,
                      offset: Offset(0, 8)),
                ],
              ),
              child: const Icon(Icons.sports_soccer,
                  color: Colors.white, size: 38),
            ),
          ),
          if (widget.conMarca) ...[
            const SizedBox(height: 18),
            const PichangolWordmark(fontSize: 26),
          ],
          const SizedBox(height: 12),
          Text(widget.texto,
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: textoTenueDe(context),
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
        ],
      ),
    );
  }
}
