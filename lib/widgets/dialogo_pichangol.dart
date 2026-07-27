import 'package:flutter/material.dart';

import '../theme.dart';

/// Popup ESTÁNDAR del app (regla de UI/UX): TODOS los diálogos de confirmación y
/// avisos usan este formato — tarjeta blanca redondeada (radio 24), ícono opcional
/// en burbuja, título en charcoal, mensaje tenue y botones consistentes (primario
/// relleno lima, o rojo si es destructivo; secundario de texto). No usar
/// `AlertDialog` suelto en pantallas nuevas: usar `confirmarPichangol`,
/// `avisarPichangol` o `DialogoPichangol`.
class DialogoPichangol extends StatelessWidget {
  const DialogoPichangol({
    super.key,
    required this.titulo,
    this.mensaje,
    this.contenido,
    this.icono,
    this.destructivo = false,
    required this.acciones,
  });

  final String titulo;
  final String? mensaje;

  /// Contenido personalizado (si se necesita más que un mensaje de texto).
  final Widget? contenido;
  final IconData? icono;
  final bool destructivo;
  final List<Widget> acciones;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final acento = destructivo ? clayOscuro : lima;
    return Dialog(
      backgroundColor: cs.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      insetPadding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(22, 24, 22, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (icono != null) ...[
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                    color: acento.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(14)),
                child: Icon(icono, color: acento, size: 26),
              ),
              const SizedBox(height: 14),
            ],
            Text(titulo,
                style: TextStyle(
                    color: cs.onSurface,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                    height: 1.2)),
            if (mensaje != null) ...[
              const SizedBox(height: 8),
              Text(mensaje!,
                  style: TextStyle(
                      color: textoTenueDe(context),
                      fontSize: 14,
                      height: 1.35)),
            ],
            if (contenido != null) ...[
              const SizedBox(height: 12),
              contenido!,
            ],
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                for (final a in acciones) ...[
                  a,
                  if (a != acciones.last) const SizedBox(width: 8),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Confirmación estándar (Sí/No). Devuelve true si el usuario confirma.
/// Ej.: `if (await confirmarPichangol(context, titulo: '...', destructivo: true)) {...}`
Future<bool> confirmarPichangol(
  BuildContext context, {
  required String titulo,
  String? mensaje,
  String textoConfirmar = 'Aceptar',
  String textoCancelar = 'Cancelar',
  bool destructivo = false,
  IconData? icono,
}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => DialogoPichangol(
      titulo: titulo,
      mensaje: mensaje,
      icono: icono,
      destructivo: destructivo,
      acciones: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          style: TextButton.styleFrom(foregroundColor: textoTenueDe(ctx)),
          child: Text(textoCancelar),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          style: FilledButton.styleFrom(
            backgroundColor: destructivo ? clayOscuro : lima,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12)),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          ),
          child: Text(textoConfirmar,
              style: const TextStyle(fontWeight: FontWeight.w800)),
        ),
      ],
    ),
  );
  return r ?? false;
}

/// Aviso estándar (un solo botón "Entendido"). Para informar, no preguntar.
Future<void> avisarPichangol(
  BuildContext context, {
  required String titulo,
  String? mensaje,
  String textoBoton = 'Entendido',
  IconData? icono,
}) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => DialogoPichangol(
      titulo: titulo,
      mensaje: mensaje,
      icono: icono,
      acciones: [
        FilledButton(
          onPressed: () => Navigator.pop(ctx),
          style: FilledButton.styleFrom(
            backgroundColor: lima,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12)),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          ),
          child: Text(textoBoton,
              style: const TextStyle(fontWeight: FontWeight.w800)),
        ),
      ],
    ),
  );
}
