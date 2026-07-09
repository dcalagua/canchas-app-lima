import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/academia.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/ubicacion_share.dart';

/// Ícono de cada red social (mismo catálogo que el editor de academia).
const _iconoRed = <String, IconData>{
  'instagram': FontAwesomeIcons.instagram,
  'facebook': FontAwesomeIcons.facebook,
  'tiktok': FontAwesomeIcons.tiktok,
  'youtube': FontAwesomeIcons.youtube,
  'web': FontAwesomeIcons.globe,
};

/// Convierte el usuario/enlace guardado en una URL abrible.
Uri? _urlRed(String clave, String valor) {
  final v = valor.trim();
  if (v.isEmpty) return null;
  if (v.startsWith('http://') || v.startsWith('https://')) return Uri.tryParse(v);
  final u = v.startsWith('@') ? v.substring(1) : v;
  switch (clave) {
    case 'instagram':
      return Uri.parse('https://instagram.com/$u');
    case 'facebook':
      return Uri.parse('https://facebook.com/$u');
    case 'tiktok':
      return Uri.parse('https://tiktok.com/@$u');
    case 'youtube':
      return Uri.parse('https://youtube.com/@$u');
    default:
      return Uri.tryParse(v.contains('.') ? 'https://$v' : v);
  }
}

/// Directorio público de academias (Fase 1, opción "libre"): el jugador ve las
/// academias, su deporte, dónde entrenan ahora y sus planes; contacta por
/// WhatsApp. La reserva/pago online es Fase 2.
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
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 5)),
        ],
      ),
      child: Padding(
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
                          style: t.bodySmall?.copyWith(color: textoTenue)),
                    ],
                  ),
                ),
              ],
            ),
            if (academia.descripcion.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(academia.descripcion,
                  style: t.bodyMedium?.copyWith(color: tinta)),
            ],
            if (academia.redes.isNotEmpty) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  for (final e in academia.redes.entries)
                    if (_urlRed(e.key, e.value) != null)
                      Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: IconButton(
                          tooltip: e.key,
                          visualDensity: VisualDensity.compact,
                          constraints:
                              const BoxConstraints.tightFor(width: 36, height: 36),
                          padding: EdgeInsets.zero,
                          icon: FaIcon(_iconoRed[e.key] ?? FontAwesomeIcons.globe,
                              size: 18, color: bosque),
                          onPressed: () => launchUrl(_urlRed(e.key, e.value)!,
                              mode: LaunchMode.externalApplication),
                        ),
                      ),
                ],
              ),
            ],
            if (academia.planes.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final p in academia.planes.take(4))
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 4),
                      decoration: BoxDecoration(
                          color: limaSuave,
                          borderRadius: BorderRadius.circular(999)),
                      child: Text(
                          p.tipo == TipoPlan.porClase
                              ? '${p.nombre} S/${p.precioMes.toStringAsFixed(0)}'
                              : '${p.nombre} S/${p.precioMes.toStringAsFixed(0)}/mes',
                          style: const TextStyle(
                              color: bosque,
                              fontSize: 11,
                              fontWeight: FontWeight.w700)),
                    ),
                ],
              ),
            ],
            if (desde != null) ...[
              const SizedBox(height: 12),
              Text('desde S/ ${desde.toStringAsFixed(2)}',
                  style: t.titleSmall
                      ?.copyWith(color: bosque, fontWeight: FontWeight.w800)),
            ],
            const SizedBox(height: 14),
            Row(
              children: [
                if (academia.sedeUbicacion != null) ...[
                  Expanded(
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: bosque,
                        side: const BorderSide(color: bosque, width: 1.4),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                      onPressed: () => UbicacionShare.menu(context,
                          punto: academia.sedeUbicacion!,
                          titulo: academia.nombre),
                      icon: const Icon(Icons.share_location, size: 20),
                      label: const Text('Ubicación'),
                    ),
                  ),
                  const SizedBox(width: 10),
                ],
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: verde,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    onPressed: academia.whatsapp.isEmpty
                        ? null
                        : () => WhatsAppLink.abrir(
                            academia.whatsapp,
                            'Hola, vi ${academia.nombre} en Pichangol y quiero info de las clases.'),
                    icon: const Icon(Icons.chat, size: 18),
                    label: const Text('Contactar'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
