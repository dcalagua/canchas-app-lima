import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'campeonato_detalle_screen.dart';
import 'crear_campeonato_screen.dart';

/// Lista de campeonatos de una academia. El profe (dueño) puede crear; cualquiera
/// puede abrir un campeonato para ver llaves/tabla.
class CampeonatosScreen extends StatelessWidget {
  const CampeonatosScreen({super.key, required this.academiaId});
  final String academiaId;

  bool _esDueno() {
    final u = appState.usuario;
    if (u == null) return false;
    for (final a in appState.academias) {
      if (a.id == academiaId) {
        return a.dueno.toLowerCase() == u.email.toLowerCase();
      }
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Campeonatos')),
      floatingActionButton: ListenableBuilder(
        listenable: appState,
        builder: (context, _) => _esDueno()
            ? FloatingActionButton.extended(
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) =>
                        CrearCampeonatoScreen(academiaId: academiaId))),
                icon: const Icon(Icons.add),
                label: const Text('Nuevo'),
              )
            : const SizedBox.shrink(),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final lista = appState.campeonatosDe(academiaId);
          if (lista.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.emoji_events_outlined,
                        size: 64,
                        color: Theme.of(context).colorScheme.primary),
                    const SizedBox(height: 12),
                    const Text('Aún no hay campeonatos',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 18)),
                    const SizedBox(height: 6),
                    Text(
                        _esDueno()
                            ? 'Crea uno: arma la llave o la liga, carga resultados y compártelo.'
                            : 'Esta academia todavía no publicó campeonatos.',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: textoTenue)),
                  ],
                ),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 90),
            children: [for (final c in lista) _CampeonatoCard(campeonato: c)],
          );
        },
      ),
    );
  }
}

class _CampeonatoCard extends StatelessWidget {
  const _CampeonatoCard({required this.campeonato});
  final Campeonato campeonato;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: CircleAvatar(
          backgroundColor: colorDeporte(campeonato.deporte),
          child: Icon(iconoDeporte(campeonato.deporte), color: Colors.white),
        ),
        title: Text(campeonato.nombre,
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        subtitle: Text(
            '${campeonato.formato.etiqueta} · '
            '${campeonato.participantes.length} inscritos'
            '${campeonato.categoria.isNotEmpty ? ' · ${campeonato.categoria}' : ''}',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
        trailing: const Icon(Icons.chevron_right, color: textoTenue),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) =>
                CampeonatoDetalleScreen(campeonatoId: campeonato.id))),
      ),
    );
  }
}
