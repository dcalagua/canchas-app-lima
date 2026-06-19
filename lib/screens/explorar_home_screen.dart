import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../brand.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'cancha_detalle_screen.dart';
import 'login_google_sheet.dart';
import 'login_screen.dart';
import 'home_shell.dart';
import 'mis_reservas_screen.dart';

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

  Deporte? _filtro; // null = todos
  int _selected = 0;
  Set<Marker> _markers = {};

  List<Cancha> _filtradas() {
    if (_filtro == null) return SampleData.canchas;
    return SampleData.canchas.where((c) => c.deporte == _filtro).toList();
  }

  @override
  void initState() {
    super.initState();
    _rebuildMarkers();
  }

  @override
  void dispose() {
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
      final icon = await _pinPrecio('S/ ${c.precioHora}', seleccionado: sel);
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

  void _abrirDetalle(Cancha cancha) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => CanchaDetalleScreen(cancha: cancha)),
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
    final canchas = _filtradas();
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
            onMapCreated: (c) => _controller = c,
            padding: const EdgeInsets.only(bottom: 180, top: 120),
          ),

          // Barra de búsqueda + filtros (overlay superior)
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Column(
                children: [
                  _BarraBusqueda(onAvatar: _abrirMenu),
                  const SizedBox(height: 10),
                  _FiltrosDeporte(
                    seleccion: _filtro,
                    onSeleccion: _cambiarFiltro,
                  ),
                ],
              ),
            ),
          ),

          // Carrusel de canchas (overlay inferior)
          Align(
            alignment: Alignment.bottomCenter,
            child: SafeArea(
              child: SizedBox(
                height: 168,
                child: PageView.builder(
                  controller: _pageController,
                  itemCount: canchas.length,
                  onPageChanged: _onPage,
                  itemBuilder: (context, i) => _CanchaCard(
                    cancha: canchas[i],
                    onTap: () => _abrirDetalle(canchas[i]),
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
  const _BarraBusqueda({required this.onAvatar});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Material(
            elevation: 4,
            borderRadius: BorderRadius.circular(30),
            color: Colors.white,
            child: const Padding(
              padding: EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              child: Row(
                children: [
                  Icon(Icons.search, color: coral),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          kBrandTaglineShort,
                          style: TextStyle(
                              fontWeight: FontWeight.w700, fontSize: 15),
                        ),
                        Text(
                          'Tenis · Pádel · Lima',
                          style: TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ],
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
  final VoidCallback onTap;
  const _CanchaCard({required this.cancha, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colorDeporte = cancha.deporte == Deporte.padel ? azulPadel : verdeCancha;
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
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [colorDeporte, colorDeporte.withOpacity(0.6)],
                  ),
                ),
                child: Stack(
                  children: [
                    Center(
                      child: Icon(
                        cancha.deporte == Deporte.padel
                            ? Icons.sports_handball
                            : Icons.sports_tennis,
                        color: Colors.white,
                        size: 44,
                      ),
                    ),
                    if (cancha.clubFundador)
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
                            color: colorDeporte,
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
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.baseline,
                          textBaseline: TextBaseline.alphabetic,
                          children: [
                            Text(
                              'S/ ${cancha.precioHora}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 16,
                                  color: verdeCancha),
                            ),
                            const Text(' /h',
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
  final Future<void> Function() onLogin;
  final Future<void> Function() onLogout;
  const _MenuSheet({
    required this.onMisReservas,
    required this.onPanel,
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
                leading: const Icon(Icons.storefront, color: verdeCancha),
                title: const Text('Soy dueño de cancha'),
                subtitle: const Text('Panel del club'),
                onTap: onPanel,
              ),
              const Divider(),
              if (u == null)
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: coral),
                  onPressed: onLogin,
                  icon: const Icon(Icons.login),
                  label: const Text('Iniciar sesión con Google'),
                )
              else
                TextButton.icon(
                  onPressed: onLogout,
                  icon: const Icon(Icons.logout, color: Colors.redAccent),
                  label: const Text('Cerrar sesión',
                      style: TextStyle(color: Colors.redAccent)),
                ),
            ],
          ),
        );
      },
    );
  }
}
