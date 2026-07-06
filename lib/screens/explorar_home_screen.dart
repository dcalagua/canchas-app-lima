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
import '../widgets/marca.dart';
import '../services/location_service.dart';
import '../utils/geo.dart';
import 'buscar_direccion_screen.dart';
import 'club_detalle_screen.dart';
import 'login_google_sheet.dart';
import 'login_screen.dart';
import 'home_shell.dart';
import 'mis_reservas_screen.dart';
import 'mis_canchas_screen.dart';
import 'registrar_cancha_screen.dart';
import 'verificador_screen.dart';
import 'convocatorias_screen.dart';
import '../services/growth_service.dart';
import '../services/convocatorias_service.dart';

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
  int _selected = 0;
  Set<Marker> _markers = {};

  LatLng? _centroBusqueda; // zona buscada por el usuario (estilo Airbnb)
  String? _labelBusqueda;
  bool _lista = false; // vista lista de clubes (toggle estilo Airbnb)
  bool _ubicando = true; // true mientras se resuelve la ubicación inicial

  /// Clubes derivados de las canchas filtradas (un local = varias canchas).
  List<Club> _clubs() => Club.agrupar(_filtradas());

  static const double _radioKm = 8.0; // canchas "cercanas" a la zona buscada

  List<Cancha> _filtradas() {
    final base = appState.todasLasCanchas();
    var lista = _filtro == null
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
    final list = _filtradas();
    final markers = <Marker>{};
    for (var i = 0; i < list.length; i++) {
      final c = list[i];
      final sel = i == _selected;
      // Las reclamadas muestran su precio real; las descubiertas en Google aún
      // no tienen precio, así que mostramos un estimado por deporte con "~".
      final etiqueta = c.registrada
          ? 'S/ ${c.precioHora.toStringAsFixed(2)}'
          : '~S/ ${c.precioReferencial.toStringAsFixed(2)}';
      final icon = await _pinPrecio(etiqueta, seleccionado: sel);
      markers.add(
        Marker(
          markerId: MarkerId(c.id),
          position: c.ubicacion,
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
    final c = _filtradas()[i];
    _controller?.animateCamera(CameraUpdate.newLatLng(c.ubicacion));
    _rebuildMarkers();
  }

  void _cambiarFiltro(Deporte? f) {
    setState(() {
      _filtro = f;
      _selected = 0;
    });
    if (_pageController.hasClients) _pageController.jumpToPage(0);
    final list = _filtradas();
    if (list.isNotEmpty) {
      _controller?.animateCamera(CameraUpdate.newLatLng(list.first.ubicacion));
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

  void _abrirDetalle(Cancha cancha) {
    // Construye el club de esa cancha (un local puede tener varias) y abre su ficha.
    final clubs = Club.agrupar(appState.todasLasCanchas());
    final club = clubs.firstWhere(
      (cl) => cl.canchas.any((c) => c.id == cancha.id),
      orElse: () => Club(id: cancha.id, nombre: cancha.club, canchas: [cancha]),
    );
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ClubDetalleScreen(club: club, canchaInicial: cancha),
      ),
    );
  }

  void _abrirPanel() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            appState.sesionIniciada ? const HomeShell() : const LoginScreen(),
      ),
    );
  }

  Future<void> _abrirMisReservas() async {
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) return;
    }
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const MisReservasScreen()),
    );
  }

  void _abrirMenu() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) => _MenuSheet(
        onMisReservas: () {
          Navigator.of(sheetContext).pop();
          _abrirMisReservas();
        },
        onPanel: () {
          Navigator.of(sheetContext).pop();
          _abrirPanel();
        },
        onRegistrar: () {
          Navigator.of(sheetContext).pop();
          Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const RegistrarCanchaScreen()),
          );
        },
        onMisCanchas: () {
          Navigator.of(sheetContext).pop();
          Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const MisCanchasScreen()),
          );
        },
        onPichangas: () {
          Navigator.of(sheetContext).pop();
          final club = appState.nombreClub;
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ConvocatoriasScreen(
                clubId: ConvocatoriasService.slugClub(club),
                clubNombre: club,
              ),
            ),
          );
        },
        onVerificador: () {
          Navigator.of(sheetContext).pop();
          Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const VerificadorScreen()),
          );
        },
        onLogin: () async {
          Navigator.of(sheetContext).pop();
          await LoginGoogleSheet.mostrar(context);
        },
        onLogout: () async {
          await appState.cerrarSesionUsuario();
          if (mounted) Navigator.of(sheetContext).pop();
        },
      ),
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
                      return ListView.separated(
                        padding: const EdgeInsets.fromLTRB(18, 16, 18, 28),
                        itemCount: clubs.length + 1,
                        separatorBuilder: (_, __) => const SizedBox(height: 14),
                        itemBuilder: (context, i) {
                          if (i == 0) {
                            final nCanchas = clubs.fold<int>(
                                0, (a, c) => a + c.canchas.length);
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 2),
                              child: Text(
                                '${clubs.length} clubes · $nCanchas canchas',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(color: textoTenue),
                              ),
                            );
                          }
                          final club = clubs[i - 1];
                          return ClubCard(
                            club: club,
                            onTap: () => _abrirDetalle(club.principal),
                          );
                        },
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
                    onAvatar: _abrirMenu,
                    onBuscar: _abrirBuscar,
                    label: _labelBusqueda,
                    onClear: _limpiarBusqueda,
                  ),
                  const SizedBox(height: 10),
                  _FiltrosDeporte(
                    seleccion: _filtro,
                    onSeleccion: _cambiarFiltro,
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
                    final lista = _filtradas();
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
                      itemBuilder: (context, i) => _CanchaCard(
                        cancha: lista[i],
                        destacado: lista[i].club == SampleData.clubActivo &&
                            appState.destacadoActivo,
                        onTap: () => _abrirDetalle(lista[i]),
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
  final VoidCallback onAvatar;
  final VoidCallback onBuscar;
  final VoidCallback onClear;
  final String? label;
  const _BarraBusqueda({
    required this.onAvatar,
    required this.onBuscar,
    required this.onClear,
    this.label,
  });

  @override
  Widget build(BuildContext context) {
    final buscando = label != null;
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
                                : 'Tenis · Pádel · Fútbol · Lima',
                            style: const TextStyle(
                                color: Colors.grey, fontSize: 12),
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
        const SizedBox(width: 10),
        InkWell(
          onTap: onAvatar,
          borderRadius: BorderRadius.circular(30),
          child: Material(
            elevation: 4,
            shape: const CircleBorder(),
            color: Colors.white,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Icon(Icons.person_outline, color: verdeCancha),
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
  final ValueChanged<Deporte?> onSeleccion;
  const _FiltrosDeporte({required this.seleccion, required this.onSeleccion});

  @override
  Widget build(BuildContext context) {
    Widget chip(String texto, Deporte? valor, IconData icono) {
      final activo = seleccion == valor;
      return Padding(
        padding: const EdgeInsets.only(right: 8),
        child: GestureDetector(
          onTap: () => onSeleccion(valor),
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
                    color: activo ? Colors.white : Colors.black87,
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
            chip('Todos', null, Icons.sports),
            chip('Fútbol', Deporte.futbol, Icons.sports_soccer),
            chip('Tenis', Deporte.tenis, Icons.sports_tennis),
            chip('Pádel', Deporte.padel, Icons.sports_handball),
          ],
        ),
      ),
    );
  }
}

class _CanchaCard extends StatelessWidget {
  final Cancha cancha;
  final bool destacado;
  final VoidCallback onTap;
  const _CanchaCard(
      {required this.cancha, this.destacado = false, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = colorDeporte(cancha.deporte);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
      child: Material(
        elevation: 6,
        borderRadius: BorderRadius.circular(18),
        color: Colors.white,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              // “Foto” simulada con gradiente + ícono del deporte
              Container(
                width: 110,
                height: 130,
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  gradient: gradienteDeporte(cancha.deporte),
                ),
                child: Stack(
                  children: [
                    if (cancha.fotoUrl != null)
                      Positioned.fill(
                        child: Image.network(cancha.fotoUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) =>
                                const SizedBox.shrink()),
                      )
                    else ...[
                      const Positioned.fill(child: CourtLines(opacity: 0.5)),
                      Center(
                        child: Icon(
                          iconoDeporte(cancha.deporte),
                          color: Colors.white,
                          size: 44,
                        ),
                      ),
                    ],
                    if (!cancha.registrada)
                      Positioned(
                        top: 8,
                        left: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            '◎ En Google',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.w700),
                          ),
                        ),
                      )
                    else if (cancha.pendienteVerificacion)
                      Positioned(
                        top: 8,
                        left: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: clayOscuro,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            '⏳ Por verificar',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.w700),
                          ),
                        ),
                      )
                    else if (destacado)
                      Positioned(
                        top: 8,
                        left: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: amarillo,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            '★ Destacado',
                            style: TextStyle(
                                color: tinta,
                                fontSize: 10,
                                fontWeight: FontWeight.w800),
                          ),
                        ),
                      )
                    else if (cancha.clubFundador)
                      Positioned(
                        top: 8,
                        left: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: arena,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Text(
                            '★ Fundador',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.w700),
                          ),
                        ),
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
                    Text(
                      cancha.nombre,
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 16),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      cancha.direccion ??
                          '${cancha.club} · ${cancha.distrito.etiqueta}',
                      style: const TextStyle(color: Colors.grey, fontSize: 12),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: color,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            cancha.deporte.etiqueta,
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 11,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                        const Spacer(),
                        if (cancha.registrada)
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.baseline,
                            textBaseline: TextBaseline.alphabetic,
                            children: [
                              Text(
                                'S/ ${cancha.precioHora.toStringAsFixed(2)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 16,
                                    color: verdeCancha),
                              ),
                              const Text(' /h',
                                  style: TextStyle(
                                      color: Colors.grey, fontSize: 12)),
                            ],
                          )
                        else
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.baseline,
                            textBaseline: TextBaseline.alphabetic,
                            children: [
                              Text(
                                '~S/ ${cancha.precioReferencial.toStringAsFixed(2)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 16,
                                    color: verdeCancha),
                              ),
                              const Text(' /h ref.',
                                  style: TextStyle(
                                      color: Colors.grey, fontSize: 12)),
                            ],
                          ),
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

class _MenuSheet extends StatelessWidget {
  final VoidCallback onMisReservas;
  final VoidCallback onPanel;
  final VoidCallback onRegistrar;
  final VoidCallback onMisCanchas;
  final VoidCallback onVerificador;
  final VoidCallback onPichangas;
  final Future<void> Function() onLogin;
  final Future<void> Function() onLogout;
  const _MenuSheet({
    required this.onMisReservas,
    required this.onPanel,
    required this.onRegistrar,
    required this.onMisCanchas,
    required this.onVerificador,
    required this.onPichangas,
    required this.onLogin,
    required this.onLogout,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final u = appState.usuario;
        return Container(
          decoration: const BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 44,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.black12,
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Center(child: PichangolWordmark(fontSize: 24)),
              const SizedBox(height: 2),
              Center(
                child: Text(kBrandEslogan,
                    style: TextStyle(
                        color: textoTenue, fontWeight: FontWeight.w600)),
              ),
              const SizedBox(height: 18),
              // Cabecera de perfil
              Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: verdeClaro,
                    backgroundImage: (u?.fotoUrl != null)
                        ? NetworkImage(u!.fotoUrl!)
                        : null,
                    child: (u?.fotoUrl == null)
                        ? const Icon(Icons.person, color: Colors.white)
                        : null,
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          u?.nombre ?? 'Invitado',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 17),
                        ),
                        Text(
                          u?.email ?? 'Inicia sesión para reservar',
                          style: TextStyle(color: Colors.grey[600], fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              // Login PROMINENTE arriba cuando no hay sesión (antes estaba al
              // fondo del menú y no se encontraba).
              if (u == null) ...[
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: verdeCancha,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: onLogin,
                    icon: const Icon(Icons.login),
                    label: const Text('Iniciar sesión con Google'),
                  ),
                ),
              ],
              const SizedBox(height: 10),
              const Divider(),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.event_available, color: verdeCancha),
                title: const Text('Mis reservas'),
                onTap: onMisReservas,
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.groups, color: verdeCancha),
                title: const Text('Pichangas'),
                subtitle: const Text('Anótate a las convocatorias del club'),
                onTap: onPichangas,
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.storefront, color: verdeCancha),
                title: const Text('Soy dueño de cancha'),
                subtitle: const Text('Panel del club'),
                onTap: onPanel,
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.add_a_photo, color: verdeCancha),
                title: const Text('Registrar mi cancha'),
                subtitle: const Text('La IA detecta el deporte por foto'),
                onTap: onRegistrar,
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.sports_soccer, color: verdeCancha),
                title: const Text('Mis canchas'),
                subtitle: const Text('Edita precio, fotos y ubicación'),
                onTap: onMisCanchas,
              ),
              if (GrowthService.disponible)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.verified_user, color: verdeCancha),
                  title: const Text('Verificador'),
                  subtitle: const Text('Visitas: foto, GPS y firma'),
                  onTap: onVerificador,
                ),
              if (u != null) ...[
                const Divider(),
                TextButton.icon(
                  onPressed: onLogout,
                  icon: const Icon(Icons.logout, color: Colors.redAccent),
                  label: const Text('Cerrar sesión',
                      style: TextStyle(color: Colors.redAccent)),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}
