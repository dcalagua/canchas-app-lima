import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/geo.dart';
import '../utils/marcador_precio.dart';
import '../utils/moneda.dart';
import '../widgets/club_card.dart';
import 'academias_screen.dart';
import 'buscar_direccion_screen.dart';
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
  bool _soloClubes = false; // chip "Clubes": solo locales formales

  // Filtros por ATRIBUTOS del local (como los chips de Airbnb: Wifi,
  // Lavadora…): amenidades multi-selección + tipo de piso. La fila de
  // atributos REEMPLAZA a la de deportes cuando se hace una búsqueda (igual
  // que Airbnb muestra atributos en la pantalla de resultados); el chip
  // "Deportes" regresa a la fila original.
  final Set<String> _amenSel = {};
  String? _superficieSel;
  bool _mostrarAtributos = false;

  /// Amenidades que se ofrecen como chips (clave del catálogo + etiqueta +
  /// emoji). Solo atributos que el dueño marca en su cancha — data real.
  static const List<(String, String, String)> _amenChips = [
    ('techado', 'Techado', '🏠'),
    ('luces', 'Luces', '💡'),
    ('parking', 'Parking', '🅿️'),
    ('duchas', 'Duchas', '🚿'),
    ('vestuario', 'Vestuario', '👕'),
    ('wifi', 'Wi-Fi', '📶'),
    ('cafeteria', 'Cafetería', '☕'),
  ];

  late List<Club> _clubs; // locales pintados (crece con "Buscar en esta zona")
  late LatLng _centroActual; // centro de la última búsqueda
  LatLng? _cam; // a dónde movió el usuario la cámara
  bool _buscando = false; // "Buscar en esta zona" en curso
  GoogleMapController? _mapCtrl;
  String? _tituloZona; // etiqueta de la zona (cambia al buscar otra)

  // Lámina inferior con 3 niveles (como Airbnb): asomada → hasta debajo de
  // los atributos (buscador+chips visibles) → pantalla completa (los tapa).
  final _sheetCtrl = DraggableScrollableController();
  bool _sheetLlena = false; // ¿la lámina cubre toda la pantalla?
  // ¿La lámina está en el nivel MEDIO o más? Ahí se FUSIONA con la zona de
  // atributos (fondo blanco continuo, sin redondeo ni sombra — como Airbnb,
  // que se ve una sola superficie).
  bool _sheetAlta = false;

  // Pines dibujados por local: normal y seleccionado (cache global por
  // etiqueta en MarcadorPrecio; aquí referenciados por id del club).
  final Map<String, BitmapDescriptor> _pinN = {};
  final Map<String, BitmapDescriptor> _pinS = {};

  @override
  void initState() {
    super.initState();
    _filtro = widget.filtroInicial;
    _clubs = widget.clubs;
    _centroActual = widget.centro;
    _tituloZona = widget.titulo;
    _sheetCtrl.addListener(() {
      if (!_sheetCtrl.isAttached || !mounted) return;
      final s = _sheetCtrl.size;
      final llena = s > 0.95;
      final alta = s > _fraccionMedia - 0.04; // en el nivel medio o más
      if (llena != _sheetLlena || alta != _sheetAlta) {
        setState(() {
          _sheetLlena = llena;
          _sheetAlta = alta;
        });
      }
    });
    _prepararPines();
  }

  @override
  void dispose() {
    _sheetCtrl.dispose();
    super.dispose();
  }

  /// Locales visibles según deporte/clubes + atributos (amenidades y piso).
  List<Club> get _visibles => _clubs
      .where((cl) => !_soloClubes || cl.esClubFormal)
      .where((cl) =>
          _soloClubes ||
          _filtro == null ||
          cl.canchas.any((c) => c.ofrece(_filtro!)))
      .where((cl) => _amenSel.every(
          (a) => cl.canchas.any((c) => c.amenidades.contains(a))))
      .where((cl) =>
          _superficieSel == null ||
          cl.canchas.any((c) => c.superficie == _superficieSel))
      .toList();

  /// Tipos de piso presentes en los locales cargados (chips dinámicos: solo
  /// se ofrecen pisos que existen de verdad en la zona).
  List<String> get _superficiesZona {
    final vistas = <String>{};
    final out = <String>[];
    for (final cl in _clubs) {
      for (final c in cl.canchas) {
        final s = c.superficie.trim();
        if (s.isNotEmpty && vistas.add(s)) out.add(s);
      }
    }
    return out.take(6).toList();
  }

  /// PELOTA del deporte para los pines (la pelota, NO la raqueta): ⚽ 🏀 🏐 y
  /// la bola amarilla para deportes de raqueta.
  String _pelota(Deporte d) => switch (d) {
        Deporte.futbol => '⚽',
        Deporte.tenis => '🥎',
        Deporte.padel => '🥎',
        Deporte.pickleball => '🥎',
        Deporte.voley => '🏐',
        Deporte.basquet => '🏀',
        Deporte.natacion => '🏊',
      };

  /// ¿El local tiene precio conocido? (pastilla de PRECIO tipo Airbnb).
  bool _tienePrecio(Club cl) => (cl.precioDesde ?? 0) > 0;

  /// Etiqueta de la pastilla: PRECIO "desde" si se conoce (como Airbnb); si el
  /// lugar aún no tiene precio (descubierto en Google, sin reclamar), la
  /// PELOTA del deporte — con filtro activo, la del deporte BUSCADO.
  String _etiqueta(Club cl) {
    final p = cl.precioDesde;
    if (p != null && p > 0) {
      final txt = p == p.roundToDouble() ? p.round().toString() : precio(p);
      return '${cl.monedaSimbolo} $txt';
    }
    return _pelota(_filtro ?? cl.principal.deporte);
  }

  /// (Re)dibuja los pines de todos los locales. Se llama al abrir, al cambiar
  /// el chip de deporte (cambia la pelota de los sin-precio) y tras "Buscar en
  /// esta zona". MarcadorPrecio cachea por etiqueta → re-preparar es barato.
  Future<void> _prepararPines() async {
    for (final cl in _clubs) {
      final et = _etiqueta(cl);
      final esEmoji = !_tienePrecio(cl);
      _pinN[cl.id] = await MarcadorPrecio.pastilla(et, esEmoji: esEmoji);
      _pinS[cl.id] = await MarcadorPrecio.pastilla(et,
          seleccionado: true, esEmoji: esEmoji);
    }
    if (mounted) setState(() {});
  }

  /// Locales cerca de [c] con lo que la app ya conoce (cosecha + registradas).
  List<Club> _clubsCerca(LatLng c) {
    final base = appState
        .todasLasCanchas()
        .where((x) => x.deportesJugables.any((d) => d != Deporte.padel))
        .where((x) => distanciaKm(c, x.ubicacion) <= appState.radioBusquedaKm)
        .toList();
    return Club.agrupar(base);
  }

  /// Busca canchas alrededor de [c]. Cosecha-first → zonas ya cosechadas
  /// salen al instante y GRATIS; una zona nueva consulta Google una sola vez
  /// y queda cosechada para todos.
  Future<void> _buscarEn(LatLng c, {String? etiqueta}) async {
    if (_buscando) return;
    setState(() {
      _buscando = true;
      _centroActual = c;
      _sel = null;
      _mostrarAtributos = true; // resultados → chips de atributos (Airbnb)
      if (etiqueta != null) _tituloZona = etiqueta;
    });
    try {
      await appState.descubrirCanchasCerca(c);
    } catch (_) {}
    _clubs = _clubsCerca(c);
    await _prepararPines();
    if (mounted) setState(() => _buscando = false);
  }

  /// Botón "Buscar en esta zona": busca donde el usuario movió la cámara.
  Future<void> _buscarAqui() async {
    final c = _cam;
    if (c != null) await _buscarEn(c);
  }

  /// Fracción de pantalla de la lámina en su nivel MEDIO (top justo debajo
  /// de los atributos: buscador + chips quedan visibles).
  double get _fraccionMedia {
    final alto = MediaQuery.of(context).size.height;
    // status bar + buscador + 1 fila de chips (deportes O atributos). Un pelín
    // MENOS que la altura real: la lámina se mete debajo del header y el borde
    // queda escondido → fusión perfecta sin rayita (como Airbnb).
    final headerPx = MediaQuery.of(context).padding.top + 112;
    return (1 - headerPx / alto).clamp(0.45, 0.85).toDouble();
  }

  /// Buscador del mapa (como Airbnb): abre la búsqueda de zona/dirección y al
  /// elegir, mueve la cámara, busca canchas ahí (cosecha-first) y sube la
  /// lámina al nivel medio — mapa con pastillas arriba + resultados abajo,
  /// igual que la pantalla de resultados de Airbnb.
  Future<void> _abrirBusqueda() async {
    final res = await Navigator.of(context).push<ResultadoBusqueda>(
      MaterialPageRoute(builder: (_) => const BuscarDireccionScreen()),
    );
    if (res == null || !mounted) return;
    _mapCtrl?.animateCamera(CameraUpdate.newLatLngZoom(res.centro, 12));
    await _buscarEn(res.centro, etiqueta: res.etiqueta);
    if (mounted && _sheetCtrl.isAttached) {
      _sheetCtrl.animateTo(_fraccionMedia,
          duration: const Duration(milliseconds: 320), curve: Curves.easeOut);
    }
  }

  /// Cambia el chip de deporte y re-dibuja pines (los sin-precio cambian su
  /// emoji al deporte buscado; el caché hace que sea instantáneo). Elegir un
  /// deporte apaga "Clubes" (y viceversa), igual que en Explorar.
  void _cambiarFiltro(Deporte? d) {
    setState(() {
      _filtro = d;
      _soloClubes = false;
      _sel = null;
    });
    _prepararPines();
  }

  void _activarClubes() {
    setState(() {
      _soloClubes = true;
      _filtro = null;
      _sel = null;
    });
    _prepararPines();
  }

  /// ¿La cámara se alejó lo suficiente del último centro buscado como para
  /// ofrecer "Buscar en esta zona"?
  bool get _ofrecerBusqueda {
    final c = _cam;
    return c != null && !_buscando && distanciaKm(c, _centroActual) > 1.5;
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
              if (emoji.isNotEmpty) ...[
                Text(emoji, style: const TextStyle(fontSize: 15)),
                const SizedBox(width: 7),
              ],
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
              // Zoom abierto (se ve el barrio completo, como Airbnb).
              initialCameraPosition:
                  CameraPosition(target: widget.centro, zoom: 12),
              markers: _marcadores(),
              myLocationEnabled: true,
              myLocationButtonEnabled: false, // la capa de arriba manda
              onMapCreated: (c) {
                _mapCtrl = c;
                // ignore: deprecated_member_use
                c.setMapStyle(_estiloAirbnb);
              },
              onCameraMove: (pos) {
                // Sin setState: solo recordamos a dónde fue la cámara.
                _cam = pos.target;
              },
              // Al soltar la cámara decidimos si ofrecer "Buscar en esta zona".
              onCameraIdle: () => setState(() {}),
              // Tocar el mapa (fuera de un pin) cierra la mini-tarjeta.
              onTap: (_) => setState(() => _sel = null),
            ),
          ),
          // ── Capa superior estilo Airbnb: buscador + chips sobre el mapa ──
          // Con la lámina en el nivel medio, el header toma fondo BLANCO y se
          // fusiona con la lista en una sola superficie (sin línea divisoria).
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(
              color: _sheetAlta
                  ? cs.surface
                  : Colors.transparent,
              padding: const EdgeInsets.only(bottom: 12),
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
                              // Como Airbnb: abre la búsqueda de zona y al
                              // elegir, el mapa vuela ahí y busca canchas.
                              onTap: _abrirBusqueda,
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
                                            _tituloZona ?? 'Cerca de ti',
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
                    // UNA fila de chips, como Airbnb: DEPORTES normalmente;
                    // tras una búsqueda, ATRIBUTOS del local (el primer chip
                    // regresa a deportes).
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: !_mostrarAtributos
                            ? [
                                _chip('🏟️', 'Todos',
                                    activo: !_soloClubes && _filtro == null,
                                    onTap: () => _cambiarFiltro(null)),
                                _chip(emojiDeporte(Deporte.futbol), 'Fútbol',
                                    activo: _filtro == Deporte.futbol,
                                    onTap: () =>
                                        _cambiarFiltro(Deporte.futbol)),
                                _chip(emojiDeporte(Deporte.tenis), 'Tenis',
                                    activo: _filtro == Deporte.tenis,
                                    onTap: () =>
                                        _cambiarFiltro(Deporte.tenis)),
                                _chip(emojiDeporte(Deporte.basquet), 'Básquet',
                                    activo: _filtro == Deporte.basquet,
                                    onTap: () =>
                                        _cambiarFiltro(Deporte.basquet)),
                                _chip(emojiDeporte(Deporte.voley), 'Vóley',
                                    activo: _filtro == Deporte.voley,
                                    onTap: () =>
                                        _cambiarFiltro(Deporte.voley)),
                                _chip(emojiDeporte(Deporte.natacion),
                                    'Natación',
                                    activo: _filtro == Deporte.natacion,
                                    onTap: () =>
                                        _cambiarFiltro(Deporte.natacion)),
                                _chip('🏛️', 'Clubes',
                                    activo: _soloClubes,
                                    onTap: _activarClubes),
                                _chip('🎓', 'Academias',
                                    activo: false,
                                    onTap: () => Navigator.of(context).push(
                                        MaterialPageRoute(
                                            builder: (_) =>
                                                const AcademiasScreen()))),
                              ]
                            : [
                                _chip('🏟️', 'Deportes',
                                    activo: false,
                                    onTap: () => setState(
                                        () => _mostrarAtributos = false)),
                                for (final (clave, etiqueta, emoji)
                                    in _amenChips)
                                  _chip(emoji, etiqueta,
                                      activo: _amenSel.contains(clave),
                                      onTap: () => setState(() {
                                            _amenSel.contains(clave)
                                                ? _amenSel.remove(clave)
                                                : _amenSel.add(clave);
                                            _sel = null;
                                          })),
                                for (final s in _superficiesZona)
                                  _chip('', s,
                                      activo: _superficieSel == s,
                                      onTap: () => setState(() {
                                            _superficieSel =
                                                _superficieSel == s
                                                    ? null
                                                    : s;
                                            _sel = null;
                                          })),
                              ],
                      ),
                    ),
                    // Botón "Buscar en esta zona" (como Airbnb): aparece al
                    // mover el mapa lejos de la última búsqueda.
                    if (_ofrecerBusqueda || _buscando) ...[
                      const SizedBox(height: 10),
                      Material(
                        elevation: 4,
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(999),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(999),
                          onTap: _buscarAqui,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 16, vertical: 10),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (_buscando)
                                  const SizedBox(
                                    width: 15,
                                    height: 15,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2),
                                  )
                                else
                                  const Icon(Icons.refresh, size: 17),
                                const SizedBox(width: 7),
                                Text(
                                  _buscando
                                      ? 'Buscando canchas…'
                                      : 'Buscar canchas en esta zona',
                                  style: const TextStyle(
                                      fontSize: 13.5,
                                      fontWeight: FontWeight.w800),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            ),
          ),
          // Lámina arrastrable inferior (como el "Más de 1000 alojamientos"
          // de Airbnb) con 3 NIVELES: asomada → hasta DEBAJO de los atributos
          // (buscador + chips siguen visibles) → pantalla COMPLETA (recién ahí
          // los atributos desaparecen, tapados por la lámina).
          Builder(builder: (context) {
            final medio = _fraccionMedia;
            return DraggableScrollableSheet(
            controller: _sheetCtrl,
            initialChildSize: 0.11,
            minChildSize: 0.11,
            // 0.99 (no 1.0): llegar EXACTO al tope con imanes tiene un bug
            // conocido de Flutter que deja la lámina trabada al querer bajar.
            maxChildSize: 0.99,
            snap: true,
            snapSizes: [0.11, medio, 0.99],
            builder: (context, scrollCtrl) => Container(
              decoration: BoxDecoration(
                color: cs.surface,
                // Desde el nivel MEDIO pierde redondeo Y sombra: se fusiona
                // con la franja blanca de atributos en una sola superficie
                // (Airbnb no muestra ninguna línea de separación).
                borderRadius: _sheetAlta
                    ? BorderRadius.zero
                    : const BorderRadius.vertical(top: Radius.circular(24)),
                boxShadow: _sheetAlta
                    ? null
                    : const [
                        BoxShadow(color: Color(0x22000000), blurRadius: 16),
                      ],
              ),
              clipBehavior: Clip.antiAlias,
              child: ListView(
                controller: scrollCtrl,
                // Clamping: el rebote elástico se come el gesto de COLAPSAR la
                // lámina en algunos equipos (queda "trabada" arriba).
                physics: const ClampingScrollPhysics(),
                padding: EdgeInsets.fromLTRB(
                    16,
                    // A pantalla completa respeta el status bar.
                    _sheetLlena ? MediaQuery.of(context).padding.top : 0,
                    16,
                    40),
                children: [
                  // Asa + contador: también son un ESCAPE al toque — si la
                  // lámina está arriba, tocarlos la baja (además del arrastre).
                  GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () {
                      final abajo = _sheetCtrl.size <= 0.12;
                      _sheetCtrl.animateTo(abajo ? _fraccionMedia : 0.11,
                          duration: const Duration(milliseconds: 260),
                          curve: Curves.easeOut);
                    },
                    child: Column(
                      children: [
                        Center(
                          child: Container(
                            margin: const EdgeInsets.only(top: 10, bottom: 8),
                            width: 38,
                            height: 4,
                            decoration: BoxDecoration(
                              color: const Color(0xFFD9D9D9),
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                        ),
                        Center(
                          child: Text(
                            '$n ${n == 1 ? 'lugar' : 'lugares'}',
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 15.5),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  for (final cl in _visibles)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: ClubCard(
                        club: cl,
                        onTap: () => _abrirFicha(cl),
                        distanciaKm:
                            distanciaKm(widget.centro, cl.ubicacion),
                        resumenResenas: appState.resumenResenas(
                            cl.canchas.map((c) => c.id).toList()),
                      ),
                    ),
                ],
              ),
            ),
          );
          }),
          // Botón "Mapa" flotante cuando la lista está a pantalla completa
          // (como Airbnb): un toque y la lámina baja para volver al mapa.
          if (_sheetLlena)
            Positioned(
              left: 0,
              right: 0,
              bottom: 28 + MediaQuery.of(context).padding.bottom,
              child: Center(
                child: Material(
                  elevation: 6,
                  color: tinta,
                  borderRadius: BorderRadius.circular(999),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(999),
                    onTap: () => _sheetCtrl.animateTo(0.11,
                        duration: const Duration(milliseconds: 280),
                        curve: Curves.easeOut),
                    child: const Padding(
                      padding:
                          EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text('Mapa',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 14.5)),
                          SizedBox(width: 7),
                          Icon(Icons.map_outlined,
                              color: Colors.white, size: 18),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          // Mini-tarjeta del local seleccionado (estilo Airbnb).
          if (sel != null)
            Positioned(
              left: 16,
              right: 16,
              bottom: 100 + MediaQuery.of(context).padding.bottom,
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
                            // Claro (nada de bloque oscuro): tinte suave.
                            color: const Color(0xFFF1F4EE),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE4E4E4)),
                          ),
                          child: Center(
                            child: Text(
                              _pelota(_filtro ?? sel.principal.deporte),
                              style: const TextStyle(fontSize: 20),
                            ),
                          ),
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
