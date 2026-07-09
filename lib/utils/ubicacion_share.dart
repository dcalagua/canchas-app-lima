import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';

/// Compartir / abrir la ubicación de un lugar (cancha o academia). Usa un enlace
/// de Google Maps; no requiere dependencias extra (solo url_launcher).
class UbicacionShare {
  static String enlace(LatLng p) =>
      'https://www.google.com/maps/search/?api=1&query=${p.latitude},${p.longitude}';

  /// Abre la ubicación en Google Maps / la app de mapas del teléfono.
  static Future<void> abrirMapa(LatLng p) async {
    try {
      await launchUrl(Uri.parse(enlace(p)),
          mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  /// Comparte por WhatsApp (elige el contacto): abre WhatsApp con el enlace.
  static Future<void> compartirWhatsApp(LatLng p, String titulo) async {
    final texto = '📍 $titulo\n${enlace(p)}';
    try {
      await launchUrl(
          Uri.parse('https://wa.me/?text=${Uri.encodeComponent(texto)}'),
          mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  /// Hoja con opciones para compartir/abrir la ubicación de [titulo] en [punto].
  static Future<void> menu(BuildContext context,
      {required LatLng punto, required String titulo}) {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 10),
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                  color: trazo, borderRadius: BorderRadius.circular(999)),
            ),
            const SizedBox(height: 14),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  const Icon(Icons.place, color: verdeCancha),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Compartir ubicación',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 16)),
                        Text(titulo,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                color: textoTenue, fontSize: 13)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 6),
            ListTile(
              leading: const Icon(Icons.directions, color: verdeCancha),
              title: const Text('Cómo llegar'),
              subtitle: const Text('Abre la ruta en Google Maps'),
              onTap: () {
                Navigator.pop(ctx);
                abrirMapa(punto);
              },
            ),
            ListTile(
              leading: const Icon(Icons.chat, color: verde),
              title: const Text('Enviar por WhatsApp'),
              subtitle: const Text('Comparte el punto con un contacto'),
              onTap: () {
                Navigator.pop(ctx);
                compartirWhatsApp(punto, titulo);
              },
            ),
            ListTile(
              leading: const Icon(Icons.link, color: bosque),
              title: const Text('Copiar enlace'),
              subtitle: const Text('Pégalo donde quieras'),
              onTap: () {
                Navigator.pop(ctx);
                Clipboard.setData(
                    ClipboardData(text: '$titulo\n${enlace(punto)}'));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                    content: Text('Enlace de ubicación copiado.')));
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}
