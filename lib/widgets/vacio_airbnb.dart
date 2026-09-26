import 'package:flutter/material.dart';

import '../theme.dart';

/// Estado VACÍO estilo Airbnb — REGLA de UI para todas las secciones del modo
/// anfitrión (y donde aplique en el jugador): objeto/ícono "flotante" centrado
/// con sombra suave, título GRANDE y amable, subtítulo tenue y botón pill gris
/// (como "Completa tu anuncio" de Airbnb). Nada de íconos planos chiquitos ni
/// botones de color chillón en un vacío.
class VacioAirbnb extends StatelessWidget {
  const VacioAirbnb({
    super.key,
    required this.icono,
    required this.titulo,
    required this.mensaje,
    this.colorIcono,
    this.textoBoton,
    this.onBoton,
  });

  final IconData icono;
  final String titulo;
  final String mensaje;

  /// Color del ícono flotante (por sección, "con vida"). Default: lima.
  final Color? colorIcono;

  /// CTA opcional (pill gris estilo Airbnb). Sin texto = sin botón.
  final String? textoBoton;
  final VoidCallback? onBoton;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(28, 32, 28, 40),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // "Objeto" flotante: tarjeta blanca con sombra suave y el ícono
              // de la sección en color (equivale a la ilustración 3D de Airbnb).
              Container(
                width: 104,
                height: 104,
                decoration: BoxDecoration(
                  color: cs.surface,
                  borderRadius: BorderRadius.circular(26),
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x1A000000),
                        blurRadius: 26,
                        offset: Offset(0, 12)),
                    BoxShadow(
                        color: Color(0x0D000000),
                        blurRadius: 6,
                        offset: Offset(0, 2)),
                  ],
                ),
                child: Icon(icono, size: 52, color: colorIcono ?? lima),
              ),
              const SizedBox(height: 30),
              Text(
                titulo,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    height: 1.12,
                    color: cs.onSurface),
              ),
              const SizedBox(height: 10),
              Text(
                mensaje,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 15.5,
                    height: 1.4,
                    color: textoTenueDe(context)),
              ),
              if (textoBoton != null) ...[
                const SizedBox(height: 26),
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFFF0F0F0),
                    foregroundColor: cs.onSurface,
                    elevation: 0,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 28, vertical: 15),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(999)),
                  ),
                  onPressed: onBoton,
                  child: Text(textoBoton!,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 15.5)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
