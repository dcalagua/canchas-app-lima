import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/club.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import 'club_detalle_screen.dart';

/// Mapa de canchas (estilo Airbnb): pines de los locales que salen en la lista
/// de Explorar. Tocar un pin muestra una mini-tarjeta abajo; de ahí se abre la
/// ficha. COSTO: el Maps SDK nativo de Android es GRATIS e ilimitado — abrir
/// este mapa no consume cuota de Google (las canchas ya vienen de la cosecha).
class MapaCanchasScreen extends StatefulWidget {
  const MapaCanchasScreen(
      {super.key, required this.clubs, required this.centro});

  /// Locales a pintar (los mismos de la lista, ya filtrados por deporte/zona).
  final List<Club> clubs;

  /// Centro de la búsqueda (ubicación del usuario o zona buscada).
  final LatLng centro;

  @override
  State<MapaCanchasScreen> createState() => _MapaCanchasScreenState();
}

class _MapaCanchasScreenState extends State<MapaCanchasScreen> {
  Club? _sel; // local tocado (mini-tarjeta inferior)

  Set<Marker> _marcadores() => {
        for (final cl in widget.clubs)
          Marker(
            markerId: MarkerId(cl.id),
            position: cl.ubicacion,
            // Verde = reservable en Pichangol; rojo = descubierta en Google
            // (reclamable). Mismo lenguaje que la lista.
            icon: BitmapDescriptor.defaultMarkerWithHue(cl.verificada
                ? BitmapDescriptor.hueGreen
                : BitmapDescriptor.hueRed),
            onTap: () => setState(() => _sel = cl),
          ),
      };

  void _abrirFicha(Club cl) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ClubDetalleScreen(club: cl),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final sel = _sel;
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: GoogleMap(
              initialCameraPosition:
                  CameraPosition(target: widget.centro, zoom: 13.5),
              markers: _marcadores(),
              myLocationEnabled: true,
              myLocationButtonEnabled: true,
              // Tocar el mapa (fuera de un pin) cierra la mini-tarjeta.
              onTap: (_) => setState(() => _sel = null),
            ),
          ),
          // Botón volver flotante (el mapa va a pantalla completa, sin AppBar).
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            left: 16,
            child: Material(
              elevation: 4,
              shape: const CircleBorder(),
              color: cs.surface,
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: () => Navigator.of(context).pop(),
                child: const Padding(
                  padding: EdgeInsets.all(10),
                  child: Icon(Icons.arrow_back, size: 22),
                ),
              ),
            ),
          ),
          // Mini-tarjeta del local seleccionado (estilo Airbnb).
          if (sel != null)
            Positioned(
              left: 16,
              right: 16,
              bottom: 24 + MediaQuery.of(context).padding.bottom,
              child: Material(
                elevation: 8,
                borderRadius: BorderRadius.circular(18),
                color: cs.surface,
                child: InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: () => _abrirFicha(sel),
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            gradient: gradienteDeporte(sel.principal.deporte),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.sports_soccer,
                              color: Colors.white, size: 22),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(sel.nombre,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 15)),
                              const SizedBox(height: 2),
                              Text(
                                sel.verificada
                                    ? (sel.precioDesde != null
                                        ? 'Desde ${sel.monedaSimbolo} '
                                            '${precio(sel.precioDesde!)} /h · toca para reservar'
                                        : 'Reservable · toca para ver')
                                    : 'En Google · toca para ver y reclamar',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontSize: 12.5,
                                    fontWeight: FontWeight.w600,
                                    color: textoTenueDe(context)),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        const Icon(Icons.chevron_right),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
