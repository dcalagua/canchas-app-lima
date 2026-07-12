import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'chat_screen.dart';

/// Bandeja de chats del PROFE: un hilo por cada cuenta de alumno-app de su
/// academia, con el último mensaje y un contador de no leídos. En vivo.
class ChatsAcademiaScreen extends StatelessWidget {
  const ChatsAcademiaScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mensajes')),
      body: MensajesRepo.disponible
          ? StreamBuilder<List<Mensaje>>(
              stream: MensajesRepo.streamAcademia(academiaId),
              builder: (context, snap) {
                final msgs = snap.data ?? const <Mensaje>[];
                return ListenableBuilder(
                  listenable: appState,
                  builder: (context, _) => _lista(context, msgs),
                );
              },
            )
          : const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text(
                    'El chat necesita conexión con el servidor. Intenta más tarde.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            ),
    );
  }

  Widget _lista(BuildContext context, List<Mensaje> msgs) {
    // Cuentas de alumno-app de esta academia (email → nombre a mostrar).
    final cuentas = <String, String>{};
    for (final a in appState.alumnosDe(academiaId)) {
      if (a.email.isEmpty) continue;
      final key = a.email.toLowerCase();
      // Nombre del titular de la cuenta: si es menor, el apoderado; si no, él.
      final nombre = a.esMenor ? a.apoderadoNombre : a.nombre;
      cuentas.putIfAbsent(key, () => nombre.isNotEmpty ? nombre : a.email);
      if (!a.esMenor && a.nombre.isNotEmpty) cuentas[key] = a.nombre;
    }
    // Incluye cuentas que sólo aparecen en mensajes (por si escribieron sin
    // figurar aún en la lista de alumnos local).
    for (final m in msgs) {
      final key = m.cuentaEmail.toLowerCase();
      if (!cuentas.containsKey(key)) {
        cuentas[key] = m.esProfe ? key : (m.autorNombre.isEmpty ? key : m.autorNombre);
      }
    }

    if (cuentas.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Text(
              'Aún no tienes alumnos que usen la app. Invítalos por correo o '
              'con tu código y podrás chatear con ellos aquí.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
      );
    }

    // Último mensaje por hilo.
    final ultimo = <String, Mensaje>{};
    for (final m in msgs) {
      ultimo[m.hilo] = m; // msgs viene ordenado ascendente → queda el más nuevo
    }

    final filas = cuentas.entries.map((e) {
      final hilo = Mensaje.hiloDe(academiaId, e.key);
      return (email: e.key, nombre: e.value, hilo: hilo, ult: ultimo[hilo]);
    }).toList()
      ..sort((a, b) {
        final ta = a.ult?.creado;
        final tb = b.ult?.creado;
        if (ta != null && tb != null) return tb.compareTo(ta);
        if (ta != null) return -1;
        if (tb != null) return 1;
        return a.nombre.toLowerCase().compareTo(b.nombre.toLowerCase());
      });

    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: filas.length,
      separatorBuilder: (_, __) =>
          Divider(height: 1, color: trazo.withOpacity(0.6)),
      itemBuilder: (_, i) {
        final f = filas[i];
        final leida = appState.chatUltimaLectura(f.hilo);
        var noLeidos = 0;
        for (final m in msgs) {
          if (m.hilo != f.hilo) continue;
          if (m.esProfe) continue; // sólo cuentan los del alumno
          if (leida == null || m.creado.isAfter(leida)) noLeidos++;
        }
        return _FilaHilo(
          nombre: f.nombre,
          preview: f.ult?.texto ?? 'Toca para escribir',
          noLeidos: noLeidos,
          onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => ChatScreen(
              academiaId: academiaId,
              cuentaEmail: f.email,
              titulo: f.nombre,
              soyProfe: true,
            ),
          )),
        );
      },
    );
  }
}

class _FilaHilo extends StatelessWidget {
  const _FilaHilo(
      {required this.nombre,
      required this.preview,
      required this.noLeidos,
      required this.onTap});
  final String nombre;
  final String preview;
  final int noLeidos;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ListTile(
      onTap: onTap,
      leading: CircleAvatar(
        backgroundColor: cs.primary.withOpacity(0.15),
        child: Text(
            nombre.isNotEmpty ? nombre.characters.first.toUpperCase() : '?',
            style: TextStyle(color: cs.primary, fontWeight: FontWeight.w800)),
      ),
      title: Text(nombre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(preview,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: textoTenue)),
      trailing: noLeidos == 0
          ? const Icon(Icons.chevron_right, color: textoTenue)
          : Container(
              padding: const EdgeInsets.all(7),
              decoration: BoxDecoration(
                  color: cs.primary, shape: BoxShape.circle),
              child: Text('$noLeidos',
                  style: TextStyle(
                      color: cs.onPrimary,
                      fontSize: 11,
                      fontWeight: FontWeight.w800)),
            ),
    );
  }
}
