import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/redes.dart';
import 'academia_detalle_screen.dart';

/// Directorio público de academias (Fase 1): el jugador ve las academias, su
/// deporte, dónde entrenan y sus planes. Al tocar una entra a la ficha, donde
/// ve el feed de fotos, se matricula (pago simulado) y sigue sus redes.
class AcademiasScreen extends StatelessWidget {
  const AcademiasScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: papel,
      appBar: AppBar(title: const Text('Academias')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final academias = appState.academias;
          if (academias.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text(
                    'Todavía no hay academias publicadas. ¿Tienes una? Créala desde tu Perfil.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [for (final a in academias) _TarjetaAcademia(academia: a)],
          );
        },
      ),
    );
  }
}

class _TarjetaAcademia extends StatelessWidget {
  const _TarjetaAcademia({required this.academia});
  final Academia academia;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    double? desde;
    for (final p in academia.planes) {
      final v = p.precioMes;
      if (desde == null || v < desde) desde = v;
    }
    final portada = academia.fotos.isNotEmpty ? academia.fotos.first : null;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 5)),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => AcademiaDetalleScreen(academiaId: academia.id))),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Portada del feed (si el profe subió fotos).
            if (portada != null)
              AspectRatio(
                aspectRatio: 16 / 9,
                child: Image.network(portada, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) =>
                        Container(color: limaSuave)),
              ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      CircleAvatar(
                        radius: 22,
                        backgroundColor: colorDeporte(academia.deporte),
                        backgroundImage: (academia.logoUrl != null &&
                                academia.logoUrl!.isNotEmpty)
                            ? NetworkImage(academia.logoUrl!)
                            : null,
                        child: (academia.logoUrl != null &&
                                academia.logoUrl!.isNotEmpty)
                            ? null
                            : Icon(iconoDeporte(academia.deporte),
                                color: Colors.white),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(academia.nombre,
                                style: t.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800)),
                            Text(
                                '${academia.deporte.etiqueta}'
                                '${academia.sedeClub.isNotEmpty ? ' · ${academia.sedeClub}' : ''}',
                                style:
                                    t.bodySmall?.copyWith(color: textoTenue)),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: textoTenue),
                    ],
                  ),
                  if (academia.redes.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        for (final e in academia.redes.entries)
                          if (urlRed(e.key, e.value) != null)
                            RedBadge(
                                clave: e.key, valor: e.value, size: 34),
                      ],
                    ),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      if (desde != null)
                        Text('desde S/ ${desde.toStringAsFixed(2)}',
                            style: t.titleSmall?.copyWith(
                                color: bosque, fontWeight: FontWeight.w800))
                      else
                        const SizedBox.shrink(),
                      Text('Ver y matricularme',
                          style: t.labelLarge?.copyWith(
                              color: bosque, fontWeight: FontWeight.w800)),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
