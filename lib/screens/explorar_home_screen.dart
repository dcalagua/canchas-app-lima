import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../models/club.dart';
import '../widgets/club_card.dart';
import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';
import '../services/location_service.dart';
import '../utils/geo.dart';
import 'buscar_direccion_screen.dart';
import 'club_detalle_screen.dart';
import 'login_google_sheet.dart';
import 'home_shell.dart';

/// Pantalla de inicio estilo Airbnb: mapa de Google a pantalla completa con
/// barra de búsqueda flotante, filtros por deporte y un carrusel de canchas
/// sincronizado con pines de precio en el mapa.
class ExplorarHomeScreen extends StatefulWidget {
  const ExplorarHomeScreen({super.key});

  @override
  State<ExplorarHomeScreen> createState() => _ExplorarHomeScreenState();
}

class _ExplorarHomeScreenState extends State<ExplorarHomeScreen> {
  GoogleMapController? _controller;
  final PageController _pageController =
      PageController(viewportFraction: 0.88);

  Deporte? _filtro = Deporte.futbol; // por defecto: Fútbol
  bool _soloClubes = false; // pestaña "Clubes": solo clubes formales (country…)
  int _selected = 0;
  Set<Marker> _markers = {};

  LatLng? _centroBusqueda; // zona buscada por el usuario (estilo Airbnb)
  String? _labelBusqueda;
  bool _lista = true; // arranca en LISTA (categorizada); toggle a Mapa
  bool _ubicando = true; // true mientras se resuelve la ubicación inicial

  /// Clubes derivados de las canchas filtradas (un local = varias canchas).
  /// En la pestaña "Clubes" solo quedan los clubes formales (country clubs…).
  List<Club> _clubs() {
    final clubs = Club.agrupar(_filtradas());
    if (_soloClubes) return clubs.where((c) => c.esClubFormal).toList();
    return clubs;
  }

  static const double _radioKm = 20.0; // cubre corredor Ñaña–Chosica–Ricardo Palma

  List<Cancha> _filtradas() {
    // Pádel retirado del piloto: nunca aparece en el mapa ni en la lista.
    final base = appState
        .todasLasCanchas()
        .where((c) => c.deporte != Deporte.padel)
        .toList();
    // En "Clubes" no se filtra por deporte (un club puede tener varios).
    var lista = (_filtro == null || _soloClubes)
        ? base
        : base.where((c) => c.deporte == _filtro).toList();

    if (_centroBusqueda != null) {
      final centro = _centroBusqueda!;
      lista.sort((a, b) => distanciaKm(centro, a.ubicacion)
          .compareTo(distanciaKm(centro, b.ubicacion)));
      // Solo las que están de verdad cerca (radio). Si no hay ninguna, devuelve
      // vacío en vez de mostrar canchas lejanas: la UI muestra "buscando…".
      lista = lista
          .where((c) => distanciaKm(centro, c.ubicacion) <= _radioKm)
          .toList();
    }
    return lista;
  }

  int _numCanchas = 0;

  @override
  void initState() {
    super.initState();
    _numCanchas = appState.todasLasCanchas().length;
    appState.addListener(_onStateChange);
    _rebuildMarkers();
    _autoUbicar(); // autodetecta la ubicación al abrir
  }

  void _onStateChange() {
    final n = appState.todasLasCanchas().length;
    if (n != _numCanchas) {
      _numCanchas = n;
      _rebuildMarkers(); // refresca los pines al registrar una cancha nueva
    }
  }

  Future<void> _autoUbicar() async {
    if (mounted) setState(() => _ubicando = true);
    try {
      // 1) Ubicación INSTANTÁNEA con la última conocida: centra los cards en la
      //    zona del usuario de inmediato (sin esperar el GPS) y dispara la
      //    búsqueda de canchas reales cerca. Evita mostrar canchas lejanas.
      final rapida = await LocationService.ultimaConocida();
      if (rapida != null && mounted) _aplicarUbicacion(rapida);

      // 2) Fix PRECISO (puede tardar). Solo re-busca si el usuario está lejos de
      //    la posición rápida (evita una segunda llamada innecesaria).
      final precisa = await LocationService.ubicacionActual();
      if (precisa != null && mounted) {
        final reUbicar = rapida == null || distanciaKm(rapida, precisa) > 2;
        _aplicarUbicacion(precisa, descubrir: reUbicar);
      }
    } finally {
      if (mounted) setState(() => _ubicando = false);
    }
  }

  /// Aplica una ubicación: centra el mapa, reordena los cards a lo cercano y
  /// (opcionalmente) descubre canchas reales alrededor.
  void _aplicarUbicacion(LatLng pos, {bool descubrir = true}) {
    setState(() {
      _centroBusqueda = pos;
      _labelBusqueda = 'Tu ubicación';
      _selected = 0;
    });
    if (_pageController.hasClients) _pageController.jumpToPage(0);
    _controller?.animateCamera(CameraUpdate.newLatLngZoom(pos, 13.5));
    _rebuildMarkers();
    if (descubrir) appState.descubrirCanchasCerca(pos); // canchas reales (Places)
  }

  @override
  void dispose() {
    appState.removeListener(_onStateChange);
    _pageController.dispose();
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _rebuildMarkers() async {
    // Un pin por LOCAL (club), no por cancha: un local con varias canchas es un
    // solo punto en el mapa; adentro se elige la cancha.
    final clubs = _clubs();
    final markers = <Marker>{};
    for (var i = 0; i < clubs.length; i++) {
      final cl = clubs[i];
      final sel = i == _selected;
      // Precio "desde" del local; si aún no tiene precio (solo Google), estima.
      final precio = cl.precioDesde;
      final etiqueta = precio != null
          ? 'S/ ${precio.toStringAsFixed(2)}'
          : '~S/ ${cl.principal.precioReferencial.toStringAsFixed(2)}';
      final icon = await _pinPrecio(etiqueta, seleccionado: sel);
      markers.add(
        Marker(
          markerId: MarkerId(cl.id),
          position: cl.ubicacion,
          icon: icon,
          zIndex: sel ? 2 : 1,
          onTap: () => _pageController.animateToPage(
            i,
            duration: const Duration(milliseconds: 350),
            curve: Curves.easeOut,
          ),
        ),
      );
    }
    if (_centroBusqueda != null) {
      markers.add(
        Marker(
          markerId: const MarkerId('_busqueda'),
          position: _centroBusqueda!,
          icon: BitmapDescriptor.defaultMarkerWithHue(
              BitmapDescriptor.hueRose),
          infoWindow: InfoWindow(title: _labelBusqueda ?? 'Tu zona'),
          zIndex: 0,
        ),
      );
    }
    if (mounted) setState(() => _markers = markers);
  }

  /// Dibuja un pin con forma de “píldora de precio” (estilo Airbnb).
  Future<BitmapDescriptor> _pinPrecio(String texto,
      {required bool seleccionado}) async {
    const ratio = 3.0;
    final colorTexto = seleccionado ? Colors.white : verdeCancha;
    final colorFondo = seleccionado ? verdeCancha : Colors.white;

    final tp = TextPainter(
      text: TextSpan(
        text: texto,
        style: TextStyle(
          fontSize: 13 * ratio,
          fontWeight: FontWeight.w700,
          color: colorTexto,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();

    final hPad = 12.0 * ratio;
    final vPad = 7.0 * ratio;
    final w = tp.width + hPad * 2;
    final h = tp.height + vPad * 2;

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    final rrect = RRect.fromRectAndRadius(
      Rect.fromLTWH(0, 0, w, h),
      Radius.circular(h / 2),
    );
    // sombra
    canvas.drawRRect(
      rrect.shift(const Offset(0, 3)),
      Paint()
        ..color = Colors.black26
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4),
    );
    // relleno
    canvas.drawRRect(rrect, Paint()..color = colorFondo);
    // borde
    canvas.drawRRect(
      rrect,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5 * ratio
        ..color = verdeCancha,
    );
    tp.paint(canvas, Offset(hPad, vPad));

    final img = await recorder
        .endRecording()
        .toImage(w.ceil(), h.ceil());
    final bytes = await img.toByteData(format: ui.ImageByteFormat.png);
    return BitmapDescriptor.fromBytes(bytes!.buffer.asUint8List());
  }

  void _onPage(int i) {
    setState(() => _selected = i);
    final clubs = _clubs();
    if (i < clubs.length) {
      _controller?.animateCamera(CameraUpdate.newLatLng(clubs[i].ubicacion));
    }
    _rebuildMarkers();
  }

  void _cambiarFiltro(Deporte? f) {
    setState(() {
      _filtro = f;
      _soloClubes = false; // elegir un deporte sale de la pestaña "Clubes"
      _selected = 0;
    });
    _reencuadrar();
  }

  /// Activa la pestaña "Clubes": solo clubes formales (country clubs, etc.).
  void _activarClubes() {
    setState(() {
      _soloClubes = true;
      _selected = 0;
    });
    _reencuadrar();
  }

  void _reencuadrar() {
    if (_pageController.hasClients) _pageController.jumpToPage(0);
    final clubs = _clubs();
    if (clubs.isNotEmpty) {
      _controller?.animateCamera(CameraUpdate.newLatLng(clubs.first.ubicacion));
    }
    _rebuildMarkers();
  }

  Future<void> _abrirBuscar() async {
    final res = await Navigator.of(context).push<ResultadoBusqueda>(
      MaterialPageRoute(builder: (_) => const BuscarDireccionScreen()),
    );
    if (res == null || !mounted) return;
    setState(() {
      _centroBusqueda = res.centro;
      _labelBusqueda = res.etiqueta;
      _selected = 0;
    });
    if (_pageController.hasClients) _pageController.jumpToPage(0);
    _controller?.animateCamera(CameraUpdate.newLatLngZoom(res.centro, 13.5));
    _rebuildMarkers();
    appState.descubrirCanchasCerca(res.centro); // canchas reales cerca de la zona
  }

  void _limpiarBusqueda() {
    setState(() {
      _centroBusqueda = null;
      _labelBusqueda = null;
      _selected = 0;
    });
    if (_pageController.hasClients) _pageController.jumpToPage(0);
    _controller?.animateCamera(
        CameraUpdate.newLatLngZoom(SampleData.centroPiloto, 12.5));
    _rebuildMarkers();
  }

  /// Abre un LOCAL desde su card. Si el usuario es su DUEÑO, va directo a su
  /// panel (Mis canchas); si no, a la ficha pública para reservar.
  ///
  /// IMPORTANTE: la ficha recibe el club TAL CUAL viene del card, con sus
  /// canchas YA FILTRADAS por el deporte elegido (el card se arma desde
  /// `_clubs()` = `Club.agrupar(_filtradas())`). Así, si buscas FÚTBOL y abres
  /// Machuca, "Elige la cancha" muestra solo sus canchas de fútbol; si buscas
  /// TENIS, solo la de tenis. Con filtro "Todos" se ven todas.
  void _abrirClub(Club club) {
    final email = appState.usuario?.email ?? '';
    final esMio = email.isNotEmpty && club.canchas.any((c) => c.dueno == email);
    if (esMio) {
      _abrirPanel(); // panel del dueño (Mis canchas)
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            ClubDetalleScreen(club: club, canchaInicial: club.principal),
      ),
    );
  }

  /// Abre el Panel del Dueño unificado (Mis canchas · Agenda · Reservas ·
  /// Reportes · Cuenta). Requiere sesión de Google porque "Mis canchas" trabaja
  /// sobre las canchas del dueño (dueno == tu correo).
  Future<void> _abrirPanel() async {
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) return;
    }
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const HomeShell()),
    );
  }


  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          GoogleMap(
            initialCameraPosition: const CameraPosition(
              target: SampleData.centroPiloto,
              zoom: 12.5,
            ),
            markers: _markers,
            myLocationButtonEnabled: false,
            zoomControlsEnabled: false,
            mapToolbarEnabled: false,
            onMapCreated: (c) {
              _controller = c;
              if (_centroBusqueda != null) {
                c.animateCamera(
                    CameraUpdate.newLatLngZoom(_centroBusqueda!, 13.5));
              }
            },
            padding: const EdgeInsets.only(bottom: 180, top: 120),
          ),

          // Vista LISTA de clubes (overlay sobre el mapa)
          if (_lista)
            Positioned.fill(
              top: 0,
              child: Padding(
                padding: const EdgeInsets.only(top: 160),
                child: Container(
                  color: papel,
                  child: ListenableBuilder(
                    listenable: appState,
                    builder: (context, _) {
                      final clubs = _clubs();
                      if (clubs.isEmpty) {
                        return Center(
                          child: Padding(
                            padding: const EdgeInsets.all(32),
                            child: Text(
                              'No hay canchas cerca. Mueve el mapa o busca otra '
                              'zona.',
                              textAlign: TextAlign.center,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(color: textoTenue),
                            ),
                          ),
                        );
                      }
                      // Clasificar: CLUBES = locales formales (country clubs,
                      // varios deportes, fundador). El resto, por su deporte.
                      final clubesFormales = <Club>[];
                      final porDeporte = <Deporte, List<Club>>{};
                      for (final cl in clubs) {
                        if (cl.esClubFormal) {
                          clubesFormales.add(cl);
                        } else {
                          porDeporte
                              .putIfAbsent(cl.principal.deporte, () => [])
                              .add(cl);
                        }
                      }
                      final nCanchas = clubs.fold<int>(
                          0, (a, c) => a + c.canchas.length);
                      final hijos = <Widget>[
                        Text(
                          '${clubs.length} ${clubs.length == 1 ? 'lugar' : 'lugares'} · $nCanchas canchas',
                          style: Theme.of(context)
                              .textTheme
                              .bodyMedium
                              ?.copyWith(color: textoTenue),
                        ),
                      ];
                      Widget card(Club cl) => Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: ClubCard(
                                club: cl, onTap: () => _abrirClub(cl)),
                          );
                      for (final d in deportesActivos) {
                        final lista = porDeporte[d] ?? const <Club>[];
                        if (lista.isEmpty) continue;
                        hijos.add(_SeccionHeader(
                            d.etiqueta, lista.length, colorDeporte(d),
                            iconoDeporte(d)));
                        hijos.addAll(lista.map(card));
                      }
                      if (clubesFormales.isNotEmpty) {
                        hijos.add(_SeccionHeader('Clubes',
                            clubesFormales.length, bosque, Icons.apartment));
                        hijos.addAll(clubesFormales.map(card));
                      }
                      return ListView(
                        padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
                        children: hijos,
                      );
                    },
                  ),
                ),
              ),
            ),

          // Barra de búsqueda + filtros (overlay superior)
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Column(
                children: [
                  _BarraBusqueda(
                    onBuscar: _abrirBuscar,
                    label: _labelBusqueda,
                    onClear: _limpiarBusqueda,
                  ),
                  const SizedBox(height: 10),
                  _FiltrosDeporte(
                    seleccion: _filtro,
                    soloClubes: _soloClubes,
                    onSeleccion: _cambiarFiltro,
                    onClubes: _activarClubes,
                  ),
                  // Feedback mientras la app trae canchas reales cerca (Places).
                  ListenableBuilder(
                    listenable: appState,
                    builder: (_, __) => appState.descubriendo
                        ? const Padding(
                            padding: EdgeInsets.only(top: 10),
                            child: _BuscandoCerca(),
                          )
                        : const SizedBox.shrink(),
                  ),
                ],
              ),
            ),
          ),

          // Botón "mi ubicación" (sobre el carrusel)
          if (!_lista)
            Positioned(
            right: 16,
            bottom: 188,
            child: Material(
              elevation: 4,
              shape: const CircleBorder(),
              color: Colors.white,
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: _autoUbicar,
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: Icon(Icons.my_location, color: verdeCancha),
                ),
              ),
            ),
          ),

          // Carrusel de canchas (overlay inferior). ListenableBuilder para que
          // el badge "Destacado" reaccione al saldo del club.
          if (!_lista)
            Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              child: SizedBox(
                height: 168,
                child: ListenableBuilder(
                  listenable: appState,
                  builder: (context, _) {
                    // Mientras se resuelve la ubicación: skeleton desde el primer
                    // frame (evita el parpadeo de canchas lejanas con el GPS).
                    if (_centroBusqueda == null && _ubicando) {
                      return const _CarruselSkeleton();
                    }
                    final lista = _clubs(); // un card por LOCAL
                    // Con ubicación pero sin canchas cerca: si seguimos buscando,
                    // skeleton; si ya terminó, mensaje claro.
                    if (lista.isEmpty) {
                      return appState.descubriendo
                          ? const _CarruselSkeleton()
                          : const _SinCanchasCerca();
                    }
                    return PageView.builder(
                      controller: _pageController,
                      itemCount: lista.length,
                      onPageChanged: _onPage,
                      itemBuilder: (context, i) => _LocalCarruselCard(
                        club: lista[i],
                        onTap: () => _abrirClub(lista[i]),
                      ),
                    );
                  },
                ),
              ),
            ),
          ),

          // Toggle Mapa ⇄ Lista (píldora centrada, estilo Airbnb)
          Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.only(bottom: _lista ? 16 : 184),
                child: Material(
                  color: tinta,
                  borderRadius: BorderRadius.circular(999),
                  elevation: 6,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(999),
                    onTap: () => setState(() => _lista = !_lista),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 12),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(_lista ? Icons.map : Icons.view_list,
                              color: lima, size: 18),
                          const SizedBox(width: 8),
                          Text(_lista ? 'Mapa' : 'Lista',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700)),
                        ],
                      ),
                    ),
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

class _BarraBusqueda extends StatelessWidget {
  final VoidCallback onBuscar;
  final VoidCallback onClear;
  final String? label;
  const _BarraBusqueda({
    required this.onBuscar,
    required this.onClear,
    this.label,
  });

  @override
  Widget build(BuildContext context) {
    final buscando = label != null;
    // El acceso al perfil vive en la pestaña "Perfil" de la barra inferior;
    // por eso el buscador ya no lleva avatar (se evita el doble acceso).
    return Row(
      children: [
        Expanded(
          child: Material(
            elevation: 4,
            borderRadius: BorderRadius.circular(30),
            color: Colors.white,
            child: InkWell(
              onTap: onBuscar,
              borderRadius: BorderRadius.circular(30),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                child: Row(
                  children: [
                    const Icon(Icons.search, color: coral),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            buscando ? label! : kBrandTaglineShort,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 15),
                          ),
                          Text(
                            buscando
                                ? 'Canchas cerca de tu zona'
                                : 'Fútbol · Tenis · Clubes · Lima',
                            style: const TextStyle(
                                color: textoTenue, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    if (buscando)
                      GestureDetector(
                        onTap: onClear,
                        child: const Icon(Icons.close, color: Colors.grey),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Píldora de "cargando" mientras se traen canchas reales cerca del usuario.
/// Da feedback claro (estilo Airbnb) para que la espera no confunda.
class _BuscandoCerca extends StatelessWidget {
  const _BuscandoCerca();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(999),
          boxShadow: const [
            BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 2)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: const [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: verdeCancha),
            ),
            SizedBox(width: 10),
            Text('Buscando canchas cerca de ti…',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

/// Tarjetas "fantasma" mientras se cargan las canchas cercanas (percepción de
/// rapidez estilo Airbnb), en vez de mostrar canchas lejanas o un hueco vacío.
class _CarruselSkeleton extends StatelessWidget {
  const _CarruselSkeleton();

  Widget _bloque(double w, double h, {double radius = 8}) => Container(
        width: w,
        height: h,
        decoration: BoxDecoration(
            color: const Color(0xFFEDEAE2),
            borderRadius: BorderRadius.circular(radius)),
      );

  @override
  Widget build(BuildContext context) {
    final ancho = MediaQuery.of(context).size.width * 0.82;
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: 3,
      separatorBuilder: (_, __) => const SizedBox(width: 12),
      itemBuilder: (_, __) => Container(
        width: ancho,
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          boxShadow: const [
            BoxShadow(color: Colors.black12, blurRadius: 10, offset: Offset(0, 4)),
          ],
        ),
        child: Row(
          children: [
            _bloque(86, 86, radius: 14),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _bloque(double.infinity, 14),
                  const SizedBox(height: 8),
                  _bloque(140, 12),
                  const SizedBox(height: 14),
                  _bloque(90, 20, radius: 999),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mensaje cuando ya se terminó de buscar y no hay canchas en el radio cercano.
class _SinCanchasCerca extends StatelessWidget {
  const _SinCanchasCerca();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(18),
          boxShadow: const [
            BoxShadow(color: Colors.black12, blurRadius: 10, offset: Offset(0, 4)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.location_off, color: textoTenue),
            SizedBox(width: 10),
            Flexible(
              child: Text(
                'No encontramos canchas cerca de ti. Mueve el mapa o busca otra zona.',
                style: TextStyle(color: tinta, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FiltrosDeporte extends StatelessWidget {
  final Deporte? seleccion;
  final bool soloClubes;
  final ValueChanged<Deporte?> onSeleccion;
  final VoidCallback onClubes;
  const _FiltrosDeporte({
    required this.seleccion,
    required this.soloClubes,
    required this.onSeleccion,
    required this.onClubes,
  });

  @override
  Widget build(BuildContext context) {
    Widget chip(String texto, IconData icono,
        {required bool activo, required VoidCallback onTap}) {
      return Padding(
        padding: const EdgeInsets.only(right: 8),
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            decoration: BoxDecoration(
              color: activo ? verdeCancha : Colors.white,
              borderRadius: BorderRadius.circular(30),
              boxShadow: const [
                BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2)),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icono,
                    size: 16, color: activo ? Colors.white : verdeCancha),
                const SizedBox(width: 6),
                Text(
                  texto,
                  style: TextStyle(
                    color: activo ? Colors.white : tinta,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Align(
      alignment: Alignment.centerLeft,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            chip('Todos', Icons.sports,
                activo: !soloClubes && seleccion == null,
                onTap: () => onSeleccion(null)),
            chip('Fútbol', Icons.sports_soccer,
                activo: !soloClubes && seleccion == Deporte.futbol,
                onTap: () => onSeleccion(Deporte.futbol)),
            chip('Tenis', Icons.sports_tennis,
                activo: !soloClubes && seleccion == Deporte.tenis,
                onTap: () => onSeleccion(Deporte.tenis)),
            chip('Clubes', Icons.apartment,
                activo: soloClubes, onTap: onClubes),
          ],
        ),
      ),
    );
  }
}

/// Tarjeta de LOCAL para el carrusel del mapa (un local = varias canchas).
/// Muestra el nombre del local, sus deportes y el precio "desde"; al tocar abre
/// la ficha del local donde se elige la cancha.
class _LocalCarruselCard extends StatelessWidget {
  final Club club;
  final VoidCallback onTap;
  const _LocalCarruselCard({required this.club, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final principal = club.principal;
    final desc = !club.registrada;
    final precio = club.precioDesde;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
      child: Material(
        elevation: 6,
        borderRadius: BorderRadius.circular(20),
        color: Colors.white,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(20),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Row(
              children: [
                // "Foto" del local: gradiente del deporte principal + líneas.
                Container(
                  width: 110,
                  height: 130,
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    gradient: gradienteDeporte(principal.deporte),
                  ),
                  child: Stack(
                    children: [
                      if (principal.fotoUrl != null)
                        Positioned.fill(
                          child: Image.network(principal.fotoUrl!,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) =>
                                  const SizedBox.shrink()),
                        )
                      else
                        const Positioned.fill(child: CourtLines(opacity: 0.5)),
                      if (desc)
                        const Positioned(
                          top: 8,
                          left: 8,
                          child: _MiniBadge('◎ En Google',
                              bg: Colors.black54, fg: Colors.white),
                        )
                      else if (club.clubFundador)
                        const Positioned(
                          top: 8,
                          left: 8,
                          child: _MiniBadge('★ Fundador',
                              bg: arena, fg: Colors.white),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(club.nombre,
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 16),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis),
                          ),
                          if (club.verificada) ...[
                            const SizedBox(width: 6),
                            const Icon(Icons.verified, size: 16, color: verde),
                          ],
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        club.direccion ??
                            '${club.barrio} · ${club.canchas.length} ${club.canchas.length == 1 ? 'cancha' : 'canchas'}',
                        style: const TextStyle(color: textoTenue, fontSize: 12),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 9),
                      Row(
                        children: [
                          for (final d in club.deportes.take(4)) ...[
                            Container(
                              width: 9,
                              height: 9,
                              decoration: BoxDecoration(
                                  color: colorDeporte(d),
                                  borderRadius: BorderRadius.circular(2)),
                            ),
                            const SizedBox(width: 5),
                          ],
                          const Spacer(),
                          if (precio != null)
                            Text.rich(
                              TextSpan(children: [
                                const TextSpan(
                                    text: 'desde ',
                                    style: TextStyle(
                                        color: textoTenue, fontSize: 12)),
                                TextSpan(
                                    text: 'S/ ${precio.toStringAsFixed(2)}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.bold,
                                        fontSize: 16,
                                        color: verdeCancha)),
                              ]),
                            )
                          else
                            Text(
                                '~S/ ${principal.precioReferencial.toStringAsFixed(2)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 15,
                                    color: verdeCancha)),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MiniBadge extends StatelessWidget {
  const _MiniBadge(this.texto, {required this.bg, required this.fg});
  final String texto;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(texto,
          style: TextStyle(
              color: fg, fontSize: 10, fontWeight: FontWeight.w700)),
    );
  }
}

/// Encabezado de sección de la lista (por deporte o "Clubes"): ícono + título +
/// contador.
class _SeccionHeader extends StatelessWidget {
  const _SeccionHeader(this.titulo, this.n, this.color, this.icono);
  final String titulo;
  final int n;
  final Color color;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 20, bottom: 2),
      child: Row(
        children: [
          Icon(icono, size: 20, color: color),
          const SizedBox(width: 8),
          Text(titulo,
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(999)),
            child: Text('$n',
                style: TextStyle(
                    color: color, fontWeight: FontWeight.w700, fontSize: 12)),
          ),
        ],
      ),
    );
  }
}
