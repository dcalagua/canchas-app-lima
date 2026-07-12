import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/redes.dart';
import 'academia_detalle_screen.dart';
import 'login_google_sheet.dart';

/// Directorio público de academias (Fase 1): el jugador ve las academias, su
/// deporte, dónde entrenan y sus planes. Al tocar una entra a la ficha, donde
/// ve el feed de fotos, se matricula (pago simulado) y sigue sus redes.
class AcademiasScreen extends StatelessWidget {
  const AcademiasScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Academias')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final academias = appState.academias;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _UnirmeConCodigo(),
              const SizedBox(height: 16),
              if (academias.isEmpty)
                const Padding(
                  padding: EdgeInsets.fromLTRB(8, 24, 8, 8),
                  child: Text(
                      'Todavía no hay academias publicadas. ¿Tienes una? Créala desde tu Perfil.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: textoTenue)),
                )
              else
                for (final a in academias) _TarjetaAcademia(academia: a),
            ],
          );
        },
      ),
    );
  }
}

/// Tarjeta-CTA para que un alumno se una a la academia de su profe con el
/// CÓDIGO que este le pasó (estilo "unirse a una clase" de Google Classroom).
class _UnirmeConCodigo extends StatelessWidget {
  const _UnirmeConCodigo();

  Future<void> _abrir(BuildContext context) async {
    // Unirse requiere sesión (queda como alumno-app con su perfil real).
    if (appState.usuario == null) {
      await LoginGoogleSheet.mostrar(context);
      if (appState.usuario == null) return; // canceló el login
    }
    if (!context.mounted) return;
    final ctrl = TextEditingController();
    final res = await showDialog<({bool ok, String mensaje})>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Unirme a una academia'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
                'Ingresa el código de 6 caracteres que te dio tu profesor.'),
            const SizedBox(height: 14),
            TextField(
              controller: ctrl,
              autofocus: true,
              textCapitalization: TextCapitalization.characters,
              textAlign: TextAlign.center,
              maxLength: 8,
              style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 4),
              decoration: const InputDecoration(
                hintText: 'RAQ4X2',
                counterText: '',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(dctx).pop(),
              child: const Text('Cancelar')),
          FilledButton(
            onPressed: () =>
                Navigator.of(dctx).pop(appState.matricularConCodigo(ctrl.text)),
            child: const Text('Unirme'),
          ),
        ],
      ),
    );
    if (res != null && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(res.mensaje),
        backgroundColor: res.ok ? bosque : null,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surface,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => _abrir(context),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: lima.withOpacity(0.7)),
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                    color: lima.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12)),
                child: Icon(Icons.qr_code_2, color: cs.primary),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('¿Tu profe te dio un código?',
                        style: t.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text('Únete a su academia y sigue tus clases y pagos.',
                        style: t.bodySmall?.copyWith(color: textoTenue)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: cs.primary),
            ],
          ),
        ),
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
    final cs = Theme.of(context).colorScheme;
    double? desde;
    for (final p in academia.planes) {
      final v = p.precioMes;
      if (desde == null || v < desde) desde = v;
    }
    final portada = academia.fotos.isNotEmpty ? academia.fotos.first : null;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
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
                                color: cs.primary, fontWeight: FontWeight.w800))
                      else
                        const SizedBox.shrink(),
                      Text('Ver y matricularme',
                          style: t.labelLarge?.copyWith(
                              color: cs.primary, fontWeight: FontWeight.w800)),
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
