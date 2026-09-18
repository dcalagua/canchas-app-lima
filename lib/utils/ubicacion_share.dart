import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';
import 'compartir_pichangol.dart';

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
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        final acento = Theme.of(ctx).colorScheme.primary;
        return SafeArea(
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
                    Icon(Icons.place, color: acento),
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
              // Interno primero: compartir dentro de Pichangol (chat de PCG).
              ListTile(
                leading: const CircleAvatar(
                    radius: 14,
                    backgroundColor: Color(0xFF25D366),
                    child: Text('P',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            fontSize: 13))),
                title: const Text('Compartir en Pichangol'),
                subtitle: const Text('Envíalo a un chat de la app'),
                onTap: () {
                  Navigator.pop(ctx);
                  CompartirPichangol.compartir(context,
                      texto: '$titulo\n${enlace(punto)}');
                },
              ),
              ListTile(
                leading: Icon(Icons.directions, color: acento),
                title: const Text('Cómo llegar'),
                subtitle: const Text('Abre la ruta en Google Maps'),
                onTap: () {
                  Navigator.pop(ctx);
                  abrirMapa(punto);
                },
              ),
              ListTile(
                leading: Icon(Icons.chat, color: acento),
                title: const Text('Enviar por WhatsApp'),
                subtitle: const Text('Comparte el punto con un contacto'),
                onTap: () {
                  Navigator.pop(ctx);
                  compartirWhatsApp(punto, titulo);
                },
              ),
              ListTile(
                leading: Icon(Icons.link, color: acento),
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
        );
      },
    );
  }
}
