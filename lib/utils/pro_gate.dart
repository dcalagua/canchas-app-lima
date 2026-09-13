import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../state/app_state.dart';
import '../widgets/dialogo_pichangol.dart';

/// Candado Pichangol Pro reutilizable: si el usuario NO es Pro, muestra el
/// diálogo con CTA "Hazte Pro" (→ pantalla de suscripción) y devuelve si quedó
/// Pro. Devuelve true de inmediato si ya es Pro. [motivo] describe la feature.
Future<bool> exigirPro(BuildContext context, {required String motivo}) async {
  if (appState.proActivo) return true;
  final ir = await confirmarPichangol(
    context,
    titulo: 'Es Pichangol Pro',
    mensaje: motivo,
    textoConfirmar: 'Hazte Pro',
    icono: Icons.workspace_premium,
  );
  if (ir != true || !context.mounted) return false;
  await Navigator.of(context)
      .push(MaterialPageRoute(builder: (_) => const HazteProScreen()));
  return context.mounted && appState.proActivo;
}
