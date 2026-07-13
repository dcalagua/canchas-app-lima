import 'package:flutter/material.dart';

import '../models/academia.dart';
import '../models/invitacion.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/redes.dart';
import '../widgets/responsive.dart';
import 'academia_detalle_screen.dart';
import 'login_google_sheet.dart';
import '../utils/moneda.dart';

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
          // Destacadas primero (más saldo = más visibilidad), luego el resto.
          final academias = [...appState.academias]
            ..sort((a, b) => appState
                .nivelDestacadoAcademia(b)
                .compareTo(appState.nivelDestacadoAcademia(a)));
          // Métrica de impacto: impresión por cada academia destacada mostrada.
          final destacadasVistas = [
            for (final a in academias)
              if (appState.esDestacadaAcademia(a)) a.id
          ];
          if (destacadasVistas.isNotEmpty) {
            PagosService.registrarVistasUnaVez(destacadasVistas);
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _MisInvitaciones(),
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
              else if (esTablet(context))
                // Tablet/landscape: academias en grilla de 2-3 columnas.
                LayoutBuilder(builder: (context, cons) {
                  final cols = columnasTablet(cons.maxWidth);
                  final w = (cons.maxWidth - 14 * (cols - 1)) / cols;
                  return Wrap(
                    spacing: 14,
                    children: [
                      for (final a in academias)
                        SizedBox(
                          width: w,
                          child: _TarjetaAcademia(
                              academia: a,
                              nivelDestacado:
                                  appState.nivelDestacadoAcademia(a)),
                        ),
                    ],
                  );
                })
              else
                for (final a in academias)
                  _TarjetaAcademia(
                      academia: a,
                      nivelDestacado: appState.nivelDestacadoAcademia(a)),
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
    // Unirse requiere sesión (la cuenta es siempre de un adulto).
    if (appState.usuario == null) {
      await LoginGoogleSheet.mostrar(context);
      if (appState.usuario == null) return; // canceló el login
    }
    if (!context.mounted) return;
    final codigo = TextEditingController();
    final nombreNino = TextEditingController();
    final edad = TextEditingController();
    final waApoderado = TextEditingController();
    var paraHijo = false;
    var consiente = false;
    String? error; // validación DENTRO del popup

    final res = await showDialog<({bool ok, String mensaje})>(
      context: context,
      builder: (dctx) => StatefulBuilder(
        builder: (dctx, setSB) => AlertDialog(
          title: const Text('Unirme a una academia'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Ingresa el código de 6 caracteres del profesor.'),
                const SizedBox(height: 12),
                TextField(
                  controller: codigo,
                  autofocus: true,
                  textCapitalization: TextCapitalization.characters,
                  textAlign: TextAlign.center,
                  maxLength: 8,
                  style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 4),
                  decoration:
                      const InputDecoration(hintText: 'RAQ4X2', counterText: ''),
                ),
                const SizedBox(height: 8),
                const Text('¿Quién va a entrenar?',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text('Yo')),
                        selected: !paraHijo,
                        onSelected: (_) => setSB(() => paraHijo = false),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: ChoiceChip(
                        label: const Center(child: Text('Mi hijo(a)')),
                        selected: paraHijo,
                        onSelected: (_) => setSB(() => paraHijo = true),
                      ),
                    ),
                  ],
                ),
                if (paraHijo) ...[
                  const SizedBox(height: 10),
                  TextField(
                    controller: nombreNino,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                        labelText: 'Nombre del alumno (niño/a)'),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: edad,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                              labelText: 'Edad (opcional)'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: waApoderado,
                          keyboardType: TextInputType.phone,
                          decoration: const InputDecoration(
                              labelText: 'Tu WhatsApp', prefixText: '+51 '),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    controlAffinity: ListTileControlAffinity.leading,
                    dense: true,
                    value: consiente,
                    onChanged: (v) => setSB(() => consiente = v ?? false),
                    title: const Text(
                        'Soy el apoderado y autorizo el registro del menor.',
                        style: TextStyle(fontSize: 12)),
                  ),
                ],
                if (error != null) ...[
                  const SizedBox(height: 10),
                  Text(error!,
                      style: const TextStyle(
                          color: Colors.redAccent,
                          fontSize: 12.5,
                          fontWeight: FontWeight.w600)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(dctx).pop(),
                child: const Text('Cancelar')),
            FilledButton(
              onPressed: () {
                // Validación DENTRO del popup: muestra el error y NO cierra.
                if (paraHijo && nombreNino.text.trim().isEmpty) {
                  setSB(() => error = 'Escribe el nombre del alumno.');
                  return;
                }
                if (paraHijo && !consiente) {
                  setSB(() => error =
                      'Marca la casilla: confirma que eres el apoderado.');
                  return;
                }
                final r = appState.matricularConCodigo(
                  codigo.text,
                  nombreAlumno: paraHijo ? nombreNino.text : null,
                  edad: paraHijo ? int.tryParse(edad.text.trim()) : null,
                  apoderadoWhatsapp: paraHijo ? waApoderado.text : null,
                );
                // Código inválido / no encontrado → error inline, sigue abierto.
                if (!r.ok) {
                  setSB(() => error = r.mensaje);
                  return;
                }
                Navigator.of(dctx).pop(r);
              },
              child: const Text('Unirme'),
            ),
          ],
        ),
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
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
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

/// Invitaciones pendientes dirigidas al usuario (por correo): "te invitaron a
/// tal academia". Un toque las acepta y lo matricula como alumno-app.
class _MisInvitaciones extends StatelessWidget {
  const _MisInvitaciones();

  @override
  Widget build(BuildContext context) {
    final invs = appState.misInvitacionesPendientes();
    if (invs.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        for (final inv in invs) _TarjetaInvitacionRecibida(inv: inv),
      ],
    );
  }
}

class _TarjetaInvitacionRecibida extends StatelessWidget {
  const _TarjetaInvitacionRecibida({required this.inv});
  final Invitacion inv;

  Future<void> _aceptar(BuildContext context) async {
    final res = appState.aceptarInvitacion(inv);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(res.mensaje), backgroundColor: res.ok ? bosque : null));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: lima.withOpacity(0.9), width: 1.4),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                    color: lima.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12)),
                child: Icon(Icons.mark_email_unread_outlined, color: cs.primary),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Te invitaron a ${inv.academiaNombre}',
                        style: t.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text('Acepta para ver tus clases y pagos.',
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              TextButton(
                onPressed: () => appState.rechazarInvitacion(inv),
                child: const Text('Ahora no'),
              ),
              const Spacer(),
              FilledButton.icon(
                onPressed: () => _aceptar(context),
                icon: const Icon(Icons.check, size: 18),
                label: const Text('Aceptar'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TarjetaAcademia extends StatelessWidget {
  const _TarjetaAcademia({required this.academia, this.nivelDestacado = 0});
  final Academia academia;

  /// Nivel de destacado (0 = no; 1 bronce, 2 plata, 3 oro). Su dueño puso
  /// saldo → badge con medalla + va arriba en la lista.
  final int nivelDestacado;

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
                            if (nivelDestacado > 0)
                              Container(
                                margin: const EdgeInsets.only(bottom: 3),
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 2),
                                decoration: BoxDecoration(
                                    color: lima,
                                    borderRadius: BorderRadius.circular(999)),
                                child: Text(
                                    '${medallaDestacado(nivelDestacado)} DESTACADO',
                                    style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 10,
                                        fontWeight: FontWeight.w800)),
                              ),
                            Text(academia.nombre,
                                style: t.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800)),
                            Text(
                                '${academia.deporte.etiqueta}'
                                '${academia.sedeClub.isNotEmpty ? ' · ${academia.sedeClub}' : ''}',
                                style:
                                    t.bodySmall?.copyWith(color: textoTenueDe(context))),
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
                        Text('desde $monedaSimbolo ${desde.toStringAsFixed(2)}',
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
