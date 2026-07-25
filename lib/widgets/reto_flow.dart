import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../screens/login_google_sheet.dart';
import '../services/avisos_service.dart';
import '../services/retos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Retos que se están enviando AHORA (clave = correo del retado). Es la guardia
/// anti doble-clic: mientras un reto a ese jugador está en vuelo, se ignora
/// cualquier tap repetido (así un usuario ansioso no crea 3 retos iguales).
final Set<String> _retosEnVuelo = {};

/// Envía un reto con PRELOAD bloqueante y guardia anti doble-clic. Un solo reto
/// por click, aunque el usuario toque varias veces. Punto único usado por el
/// ranking, jugadores disponibles y el buscador de jugadores.
Future<void> enviarRetoConGuardia(
  BuildContext context, {
  required String deporte,
  required String retadoEmail,
  required String retadoNombre,
  String zona = '',
}) async {
  final email = retadoEmail.toLowerCase().trim();
  if (email.isEmpty) return;
  if (_retosEnVuelo.contains(email)) return; // ya se está enviando a este
  if (!await LoginGoogleSheet.mostrar(context, motivo: 'retar a un jugador')) {
    return;
  }
  if (!context.mounted) return;
  final u = appState.usuario;
  if (u == null) return;
  if (email == u.email.toLowerCase().trim()) {
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No puedes retarte a ti mismo.')));
    return;
  }
  final nombre = retadoNombre.trim().isNotEmpty ? retadoNombre.trim() : 'Jugador';

  _retosEnVuelo.add(email);
  // Preload bloqueante: además de mostrar "Enviando…", su barrera impide un
  // segundo tap sobre el botón que quedó debajo.
  showDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => const _RetandoDialog(),
  );

  Map<String, dynamic>? resp;
  try {
    resp = await RetosService.crear(
      retadorEmail: u.email,
      retadorNombre: u.nombre,
      retadoEmail: email,
      retadoNombre: nombre,
      deporte: deporte,
      zona: zona,
    );
  } finally {
    _retosEnVuelo.remove(email);
    if (context.mounted) Navigator.of(context, rootNavigator: true).pop();
  }
  if (!context.mounted) return;

  // Tope semanal del free → ofrecer Pro.
  if (resp != null && resp['error'] == 'limite_retos_free') {
    await _ofrecerPro(context, resp['limite']);
    return;
  }
  final ok = resp != null && resp['ok'] == true;
  if (ok) {
    AvisosService.retoRecibido(
        retadoEmail: email, retadorNombre: u.nombre, deporte: deporte);
  }
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    backgroundColor: ok ? bosque : null,
    content: Text(ok
        ? 'Reto enviado a $nombre. Coordinen la cancha y repórtenlo en "Mis retos".'
        : 'No se pudo enviar el reto. Reintenta.'),
  ));
}

Future<void> _ofrecerPro(BuildContext context, dynamic limite) async {
  final n = (limite is num) ? limite.toInt() : 3;
  final ir = await showDialog<bool>(
    context: context,
    builder: (dctx) => AlertDialog(
      title: const Text('Llegaste a tu límite de retos'),
      content: Text(
          'Los jugadores sin Pichangol Pro pueden enviar $n retos por semana. '
          'Hazte Pro y reta sin límites.'),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(dctx, false),
            child: const Text('Ahora no')),
        FilledButton(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () => Navigator.pop(dctx, true),
            child: const Text('Ver Pro')),
      ],
    ),
  );
  if (ir == true && context.mounted) {
    Navigator.of(context)
        .push(MaterialPageRoute(builder: (_) => const HazteProScreen()));
  }
}

/// Preload "Enviando reto…" (caja centrada, estilo del app).
class _RetandoDialog extends StatelessWidget {
  const _RetandoDialog();
  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape:
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 28, vertical: 26),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 46,
              height: 46,
              child: CircularProgressIndicator(strokeWidth: 3, color: lima),
            ),
            SizedBox(height: 16),
            Text('Enviando reto…',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            SizedBox(height: 4),
            Text('Un momento',
                style: TextStyle(color: textoTenue, fontSize: 12.5)),
          ],
        ),
      ),
    );
  }
}
