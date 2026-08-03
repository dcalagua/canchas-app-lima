import 'package:flutter/material.dart';

import '../models/campeonato.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/pro_gate.dart';
import '../widgets/responsive.dart';
import 'campeonato_detalle_screen.dart';
import 'crear_campeonato_screen.dart';
import 'unirse_campeonato_sheet.dart';

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
      appBar: AppBar(
        title: const Text('Campeonatos'),
        actions: [
          IconButton(
            tooltip: 'Unirme con enlace o código',
            icon: const Icon(Icons.link),
            onPressed: () => UnirseCampeonato.mostrar(context),
          ),
        ],
      ),
      floatingActionButton: ListenableBuilder(
        listenable: appState,
        builder: (context, _) => _esDueno()
            ? FloatingActionButton.extended(
                onPressed: () async {
                  // Candado Pichangol Pro: organizar un campeonato exige Pro,
                  // también para el dueño de la academia (modelo universal).
                  final ok = await exigirPro(context,
                      motivo: 'Crear campeonatos (fixture, inscripciones, '
                          'resultados) es parte de Pichangol Pro. Hazte Pro '
                          'para organizar el tuyo.');
                  if (!ok || !context.mounted) return;
                  Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) =>
                          CrearCampeonatoScreen(academiaId: academiaId)));
                },
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
            // Regla app: contenido centrado (ancho máx) en pantallas anchas.
            padding: EdgeInsets.fromLTRB(
                ladoTablet(context, 16, 900), 16, ladoTablet(context, 16, 900), 90),
            children: [
              // Tablet/landscape: campeonatos en grilla de 2-3 columnas.
              if (esTablet(context))
                LayoutBuilder(builder: (context, cons) {
                  final cols = columnasTablet(cons.maxWidth);
                  final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
                  return Wrap(
                    spacing: 14,
                    children: [
                      for (final c in lista)
                        SizedBox(
                            width: w, child: _CampeonatoCard(campeonato: c)),
                    ],
                  );
                })
              else
                for (final c in lista) _CampeonatoCard(campeonato: c),
            ],
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
