import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../state/app_state.dart';
import 'dialogo_pichangol.dart';

/// Candado de PICHANGOL PRO (regla del director): las herramientas avanzadas
/// del dueño — reserva manual y bloqueo de horas — son parte de la suscripción.
///
/// Devuelve true si puede usar la función. Si no es Pro, muestra el diálogo
/// Pichangol con CTA "Hazte Pro" (abre la pantalla de suscripción) y devuelve
/// el estado REAL al volver: si activó Pro ahí mismo, entra de una.
Future<bool> exigirPro(BuildContext context, {required String funcion}) async {
  if (appState.proActivo) return true;
  final ir = await confirmarPichangol(
    context,
    titulo: 'Función de Pichangol Pro',
    mensaje: '$funcion es parte de Pichangol Pro, la suscripción para dueños '
        'que administran su negocio desde la app. Actívala y desbloquea esta '
        'y todas las herramientas Pro.',
    textoConfirmar: 'Hazte Pro',
    textoCancelar: 'Ahora no',
    icono: Icons.workspace_premium,
  );
  if (ir && context.mounted) {
    await Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const HazteProScreen()));
    return appState.proActivo; // si se suscribió, pasa sin repetir el diálogo
  }
  return false;
}
