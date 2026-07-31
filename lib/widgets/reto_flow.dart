import 'dart:async';

import 'package:flutter/material.dart';

import '../screens/hazte_pro_screen.dart';
import '../screens/login_google_sheet.dart';
import '../services/avisos_service.dart';
import '../services/retos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'dialogo_pichangol.dart';
import 'cargando_pichangol.dart';

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
    // Chat del partido: abre el hilo directo con el rival con un mensaje inicial
    // para coordinar la cancha (y le llega el push). Best-effort.
    unawaited(appState.enviarMensajeDirecto(email,
        '⚔️ Te reté en Pichangol ($deporte). Coordinemos cancha y horario.'));
  }
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    backgroundColor: ok ? bosque : null,
    content: Text(ok
        ? 'Reto enviado a $nombre. Coordinen la cancha y repórtenlo en "Mis retos".'
        : 'No se pudo enviar el reto. Reintenta.'),
  ));
}

/// Envía un reto de DOBLES (2v2): yo + [companero] retamos a [rival1]+[rival2].
/// Mismo preload/guardia que singles. Los 4 correos deben ser distintos.
Future<void> enviarRetoDoblesConGuardia(
  BuildContext context, {
  required String deporte,
  required String companeroEmail,
  required String companeroNombre,
  required String rival1Email,
  required String rival1Nombre,
  required String rival2Email,
  required String rival2Nombre,
  String zona = '',
}) async {
  final u = appState.usuario;
  if (u == null) {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'retar en dobles')) {
      return;
    }
  }
  if (!context.mounted) return;
  final yo = (appState.usuario?.email ?? '').toLowerCase().trim();
  final comp = companeroEmail.toLowerCase().trim();
  final r1 = rival1Email.toLowerCase().trim();
  final r2 = rival2Email.toLowerCase().trim();
  final cuatro = {yo, comp, r1, r2};
  if (yo.isEmpty || comp.isEmpty || r1.isEmpty || r2.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Elige a tu compañero y a los dos rivales.')));
    return;
  }
  if (cuatro.length != 4) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Los cuatro jugadores deben ser distintos.')));
    return;
  }
  final clave = 'dobles:$r1|$r2';
  if (_retosEnVuelo.contains(clave)) return;
  _retosEnVuelo.add(clave);
  showDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => const _RetandoDialog(),
  );

  Map<String, dynamic>? resp;
  try {
    resp = await RetosService.crear(
      retadorEmail: appState.usuario!.email,
      retadorNombre: appState.usuario!.nombre,
      retadoEmail: rival1Email,
      retadoNombre: rival1Nombre.trim().isNotEmpty ? rival1Nombre.trim() : 'Rival',
      deporte: deporte,
      zona: zona,
      modalidad: 'dobles',
      retador2Email: companeroEmail,
      retador2Nombre:
          companeroNombre.trim().isNotEmpty ? companeroNombre.trim() : 'Compañero',
      retado2Email: rival2Email,
      retado2Nombre:
          rival2Nombre.trim().isNotEmpty ? rival2Nombre.trim() : 'Rival 2',
    );
  } finally {
    _retosEnVuelo.remove(clave);
    if (context.mounted) Navigator.of(context, rootNavigator: true).pop();
  }
  if (!context.mounted) return;

  if (resp != null && resp['error'] == 'limite_retos_free') {
    await _ofrecerPro(context, resp['limite']);
    return;
  }
  final ok = resp != null && resp['ok'] == true;
  if (ok) {
    // Avisa a los rivales (ambos) y al compañero.
    for (final e in [r1, r2]) {
      AvisosService.retoRecibido(
          retadoEmail: e, retadorNombre: appState.usuario!.nombre, deporte: deporte);
    }
  }
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    backgroundColor: ok ? bosque : null,
    content: Text(ok
        ? 'Reto de dobles enviado. Coordinen y repórtenlo en "Mis retos".'
        : (resp != null && resp['error'] == 'jugadores_repetidos'
            ? 'Los cuatro jugadores deben ser distintos.'
            : 'No se pudo enviar el reto. Reintenta.')),
  ));
}

Future<void> _ofrecerPro(BuildContext context, dynamic limite) async {
  final n = (limite is num) ? limite.toInt() : 3;
  final ir = await confirmarPichangol(
    context,
    titulo: 'Llegaste a tu límite de retos',
    mensaje: 'Los jugadores sin Pichangol Pro pueden enviar $n retos por semana. '
        'Hazte Pro y reta sin límites.',
    textoConfirmar: 'Ver Pro',
    textoCancelar: 'Ahora no',
    icono: Icons.workspace_premium,
  );
  if (ir && context.mounted) {
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
        child: CargandoPichangol(texto: 'Enviando reto…'),
      ),
    );
  }
}
