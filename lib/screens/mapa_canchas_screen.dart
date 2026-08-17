import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/club.dart';
import '../theme.dart';
import '../utils/marcador_precio.dart';
import '../utils/moneda.dart';
import 'club_detalle_screen.dart';

/// Mapa de canchas estilo Airbnb: pines-pastilla con el PRECIO (blancos; el
/// seleccionado se invierte a charcoal), lugares sin precio como pastilla-punto,
/// y estilo visual del mapa suave (crema + agua celeste, sin POIs de Google).
/// Tocar un pin muestra una mini-tarjeta abajo; de ahí se abre la ficha.
/// COSTO: el Maps SDK nativo de Android es GRATIS e ilimitado — abrir este
/// mapa no consume cuota de Google (las canchas ya vienen de la cosecha).
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

/// Estilo visual tipo Airbnb: base crema, agua celeste, calles blancas,
/// parques verdes suaves y CERO negocios/transporte de Google (el mapa es el
/// escenario; los protagonistas son nuestros pines).
const String _estiloAirbnb = '''
[
  {"elementType":"geometry","stylers":[{"color":"#F6F4EF"}]},
  {"elementType":"labels.text.fill","stylers":[{"color":"#8A8A85"}]},
  {"elementType":"labels.text.stroke","stylers":[{"color":"#FFFFFF"}]},
  {"featureType":"administrative","elementType":"geometry","stylers":[{"visibility":"off"}]},
  {"featureType":"poi","stylers":[{"visibility":"off"}]},
  {"featureType":"poi.park","elementType":"geometry","stylers":[{"visibility":"on"},{"color":"#DDEBD9"}]},
  {"featureType":"transit","stylers":[{"visibility":"off"}]},
  {"featureType":"road","elementType":"geometry","stylers":[{"color":"#FFFFFF"}]},
  {"featureType":"road","elementType":"geometry.stroke","stylers":[{"visibility":"off"}]},
  {"featureType":"road","elementType":"labels.icon","stylers":[{"visibility":"off"}]},
  {"featureType":"road.highway","elementType":"geometry","stylers":[{"color":"#FBEBC8"}]},
  {"featureType":"landscape.man_made","elementType":"geometry","stylers":[{"color":"#F1EDE5"}]},
  {"featureType":"water","elementType":"geometry","stylers":[{"color":"#C4E2F0"}]},
  {"featureType":"water","elementType":"labels.text.fill","stylers":[{"color":"#89AFC4"}]}
]
''';

class _MapaCanchasScreenState extends State<MapaCanchasScreen> {
  Club? _sel; // local tocado (mini-tarjeta inferior + pin invertido)

  // Pines dibujados por local: normal y seleccionado (cacheados por etiqueta
  // en MarcadorPrecio; aquí solo se referencian por id del club).
  final Map<String, BitmapDescriptor> _pinN = {};
  final Map<String, BitmapDescriptor> _pinS = {};

  @override
  void initState() {
    super.initState();
    _prepararPines();
  }

  /// Etiqueta de la pastilla: el precio "desde" si es reservable; vacía para
  /// descubiertas (pastilla-punto, como los sin-precio de Airbnb).
  String _etiqueta(Club cl) {
    final p = cl.precioDesde;
    if (!cl.verificada || p == null || p <= 0) return '';
    // Sin decimales cuando es entero (S/ 60); con 2 si no (S/ 62.50).
    final txt = p == p.roundToDouble() ? p.round().toString() : precio(p);
    return '${cl.monedaSimbolo} $txt';
  }

  Future<void> _prepararPines() async {
    for (final cl in widget.clubs) {
      final et = _etiqueta(cl);
      _pinN[cl.id] = await MarcadorPrecio.pastilla(et);
      _pinS[cl.id] = await MarcadorPrecio.pastilla(et, seleccionado: true);
    }
    if (mounted) setState(() {});
  }

  Set<Marker> _marcadores() => {
        for (final cl in widget.clubs)
          Marker(
            markerId: MarkerId(cl.id),
            position: cl.ubicacion,
            icon: (_sel?.id == cl.id ? _pinS[cl.id] : _pinN[cl.id]) ??
                BitmapDescriptor.defaultMarker,
            anchor: const Offset(0.5, 0.5),
            // El seleccionado por encima de los demás (como Airbnb).
            zIndex: _sel?.id == cl.id ? 2 : 1,
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
              // ignore: deprecated_member_use
              onMapCreated: (c) => c.setMapStyle(_estiloAirbnb),
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
