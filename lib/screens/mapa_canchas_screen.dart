import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../theme.dart';
import '../utils/marcador_precio.dart';
import '../utils/moneda.dart';
import 'club_detalle_screen.dart';

/// Mapa de canchas estilo Airbnb:
///  - Arriba: buscador flotante (zona actual) + chips de filtro por deporte,
///    flotando SOBRE el mapa (misma capa que Airbnb).
///  - Pines-pastilla con el PRECIO para las reservables (el seleccionado se
///    invierte a charcoal); las descubiertas sin precio llevan su EMOJI de
///    deporte en la pastilla (⚽ 🎾), no un punto vacío.
///  - Tocar un pin abre una mini-tarjeta abajo; de ahí, la ficha.
/// COSTO: el Maps SDK nativo es GRATIS e ilimitado — abrir el mapa no gasta
/// cuota de Google (las canchas ya vienen de la cosecha).
class MapaCanchasScreen extends StatefulWidget {
  const MapaCanchasScreen({
    super.key,
    required this.clubs,
    required this.centro,
    this.titulo,
    this.filtroInicial,
  });

  /// Locales cerca de la zona (SIN filtrar por deporte: los chips del mapa
  /// filtran aquí mismo).
  final List<Club> clubs;

  /// Centro de la búsqueda (ubicación del usuario o zona buscada).
  final LatLng centro;

  /// Etiqueta de la zona para el buscador flotante ("Urb Santa María…").
  final String? titulo;

  /// Deporte que venía filtrado en la lista (se respeta al abrir).
  final Deporte? filtroInicial;

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
  Deporte? _filtro; // chip de deporte activo (null = todos)

  // Pines dibujados por local: normal y seleccionado (cache global por
  // etiqueta en MarcadorPrecio; aquí referenciados por id del club).
  final Map<String, BitmapDescriptor> _pinN = {};
  final Map<String, BitmapDescriptor> _pinS = {};

  @override
  void initState() {
    super.initState();
    _filtro = widget.filtroInicial;
    _prepararPines();
  }

  /// Locales visibles según el chip de deporte activo.
  List<Club> get _visibles => _filtro == null
      ? widget.clubs
      : widget.clubs
          .where((cl) => cl.canchas.any((c) => c.ofrece(_filtro!)))
          .toList();

  /// Etiqueta de la pastilla: precio "desde" si es reservable; si no, el emoji
  /// del deporte (así una zona sin precios igual se ve viva, no puntos vacíos).
  String _etiqueta(Club cl) {
    final p = cl.precioDesde;
    if (cl.verificada && p != null && p > 0) {
      final txt = p == p.roundToDouble() ? p.round().toString() : precio(p);
      return '${cl.monedaSimbolo} $txt';
    }
    return emojiDeporte(cl.principal.deporte);
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
        for (final cl in _visibles)
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

  /// Chip estilo Airbnb (pastilla blanca, seleccionado = relleno gris plomo).
  Widget _chip(String emoji, String texto,
      {required bool activo, required VoidCallback onTap}) {
    return Padding(
      padding: const EdgeInsets.only(right: 10),
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: activo ? const Color(0xFFEBEBEB) : Colors.white,
            borderRadius: BorderRadius.circular(30),
            border: Border.all(
              color:
                  activo ? const Color(0xFFD6D6D6) : const Color(0xFFE4E4E4),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.08),
                blurRadius: 6,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(emoji, style: const TextStyle(fontSize: 15)),
              const SizedBox(width: 7),
              Text(texto,
                  style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: activo ? FontWeight.w800 : FontWeight.w600,
                      color: tinta)),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final sel = _sel;
    final n = _visibles.length;
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: GoogleMap(
              initialCameraPosition:
                  CameraPosition(target: widget.centro, zoom: 13.5),
              markers: _marcadores(),
              myLocationEnabled: true,
              myLocationButtonEnabled: false, // la capa de arriba manda
              // ignore: deprecated_member_use
              onMapCreated: (c) => c.setMapStyle(_estiloAirbnb),
              // Tocar el mapa (fuera de un pin) cierra la mini-tarjeta.
              onTap: (_) => setState(() => _sel = null),
            ),
          ),
          // ── Capa superior estilo Airbnb: buscador + chips sobre el mapa ──
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Material(
                          elevation: 4,
                          shape: const CircleBorder(),
                          color: cs.surface,
                          child: InkWell(
                            customBorder: const CircleBorder(),
                            onTap: () => Navigator.of(context).pop(),
                            child: const Padding(
                              padding: EdgeInsets.all(11),
                              child: Icon(Icons.arrow_back, size: 21),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Material(
                            elevation: 4,
                            borderRadius: BorderRadius.circular(30),
                            color: cs.surface,
                            child: InkWell(
                              borderRadius: BorderRadius.circular(30),
                              // El buscador vive en la lista: volver la abre.
                              onTap: () => Navigator.of(context).pop(),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 16, vertical: 9),
                                child: Row(
                                  children: [
                                    Icon(Icons.search,
                                        size: 20, color: cs.primary),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            widget.titulo ?? 'Cerca de ti',
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: const TextStyle(
                                                fontWeight: FontWeight.w800,
                                                fontSize: 14.5),
                                          ),
                                          Text(
                                            '$n ${n == 1 ? 'lugar' : 'lugares'} en el mapa',
                                            style: TextStyle(
                                                fontSize: 11.5,
                                                fontWeight: FontWeight.w600,
                                                color: textoTenueDe(context)),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: [
                          _chip('🏟️', 'Todos',
                              activo: _filtro == null,
                              onTap: () => setState(() => _filtro = null)),
                          _chip(emojiDeporte(Deporte.futbol), 'Fútbol',
                              activo: _filtro == Deporte.futbol,
                              onTap: () =>
                                  setState(() => _filtro = Deporte.futbol)),
                          _chip(emojiDeporte(Deporte.tenis), 'Tenis',
                              activo: _filtro == Deporte.tenis,
                              onTap: () =>
                                  setState(() => _filtro = Deporte.tenis)),
                          _chip(emojiDeporte(Deporte.basquet), 'Básquet',
                              activo: _filtro == Deporte.basquet,
                              onTap: () =>
                                  setState(() => _filtro = Deporte.basquet)),
                          _chip(emojiDeporte(Deporte.voley), 'Vóley',
                              activo: _filtro == Deporte.voley,
                              onTap: () =>
                                  setState(() => _filtro = Deporte.voley)),
                        ],
                      ),
                    ),
                  ],
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
