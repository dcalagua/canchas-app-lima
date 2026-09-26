import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../services/location_service.dart';
import '../theme.dart';

/// Lo que devuelve [UbicacionScreen] al chat: el punto elegido y, si es en vivo,
/// la duración. `envivo == null` → ubicación estática (un solo envío).
class ResultadoUbicacion {
  const ResultadoUbicacion(this.pos, this.envivo);
  final LatLng pos;
  final Duration? envivo;
}

/// Pantalla de "Ubicación" estilo WhatsApp: un mapa con tu posición y dos
/// opciones — **Enviar tu ubicación actual** o **Compartir en tiempo real**.
/// Puedes tocar el mapa para ajustar el punto a enviar (la de tiempo real
/// siempre te sigue a ti, no al punto).
class UbicacionScreen extends StatefulWidget {
  const UbicacionScreen({super.key});

  @override
  State<UbicacionScreen> createState() => _UbicacionScreenState();
}

class _UbicacionScreenState extends State<UbicacionScreen> {
  static const LatLng _limaDefault = LatLng(-12.0464, -77.0428);

  GoogleMapController? _map;
  LatLng? _yo; // mi GPS real
  LatLng? _elegido; // punto a enviar (arranca en mi GPS; se mueve al tocar)
  bool _cargando = true;
  bool _movido = false; // ¿el usuario ajustó el pin?

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final p = await LocationService.ubicacionPrecisa();
    if (!mounted) return;
    setState(() {
      _yo = p;
      _elegido = p;
      _cargando = false;
    });
    if (p != null) {
      _map?.animateCamera(CameraUpdate.newLatLngZoom(p, 16));
    }
  }

  void _recentrar() {
    final y = _yo;
    if (y == null) return;
    setState(() {
      _elegido = y;
      _movido = false;
    });
    _map?.animateCamera(CameraUpdate.newLatLngZoom(y, 16));
  }

  void _enviarActual() {
    final pos = _elegido ?? _yo;
    if (pos == null) return;
    Navigator.of(context).pop(ResultadoUbicacion(pos, null));
  }

  Future<void> _enVivo() async {
    final pos = _yo ?? _elegido;
    if (pos == null) return;
    final dur = await _elegirDuracion();
    if (dur == null || !mounted) return;
    Navigator.of(context).pop(ResultadoUbicacion(pos, dur));
  }

  Future<Duration?> _elegirDuracion() {
    const opciones = <(String, Duration)>[
      ('15 minutos', Duration(minutes: 15)),
      ('1 hora', Duration(hours: 1)),
      ('8 horas', Duration(hours: 8)),
    ];
    return showModalBottomSheet<Duration>(
      context: context,
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF202C33)
          : Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('¿Por cuánto tiempo?',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
              ),
            ),
            for (final (etiqueta, dur) in opciones)
              ListTile(
                leading: const Icon(Icons.access_time, color: teal),
                title: Text('Durante $etiqueta'),
                onTap: () => Navigator.of(context).pop(dur),
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final centro = _elegido ?? _yo ?? _limaDefault;
    return Scaffold(
      appBar: AppBar(title: const Text('Ubicación')),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                GoogleMap(
                  initialCameraPosition: CameraPosition(
                    target: centro,
                    zoom: _yo == null ? 11 : 16,
                  ),
                  onMapCreated: (c) {
                    _map = c;
                    final y = _yo;
                    if (y != null) {
                      c.moveCamera(CameraUpdate.newLatLngZoom(y, 16));
                    }
                  },
                  myLocationEnabled: true,
                  myLocationButtonEnabled: false,
                  zoomControlsEnabled: false,
                  onTap: (p) => setState(() {
                    _elegido = p;
                    _movido = true;
                  }),
                  markers: _elegido == null
                      ? const {}
                      : {
                          Marker(
                            markerId: const MarkerId('elegido'),
                            position: _elegido!,
                            draggable: true,
                            onDragEnd: (p) => setState(() {
                              _elegido = p;
                              _movido = true;
                            }),
                          ),
                        },
                ),
                if (_cargando)
                  const Center(child: CircularProgressIndicator()),
                Positioned(
                  right: 16,
                  bottom: 16,
                  child: FloatingActionButton.small(
                    heroTag: 'fab_mi_ubic',
                    backgroundColor: cs.surface,
                    foregroundColor: teal,
                    onPressed: _recentrar,
                    child: const Icon(Icons.my_location),
                  ),
                ),
              ],
            ),
          ),
          Material(
            color: cs.surface,
            elevation: 8,
            child: SafeArea(
              top: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ListTile(
                    leading: const CircleAvatar(
                        backgroundColor: teal,
                        child: Icon(Icons.near_me, color: Colors.white)),
                    title: Text(_movido
                        ? 'Enviar la ubicación seleccionada'
                        : 'Enviar tu ubicación actual'),
                    subtitle: Text(
                      _cargando
                          ? 'Obteniendo tu ubicación…'
                          : (_elegido == null
                              ? 'Activa el permiso de ubicación'
                              : '${_elegido!.latitude.toStringAsFixed(5)}, '
                                  '${_elegido!.longitude.toStringAsFixed(5)}'),
                    ),
                    onTap: _elegido == null ? null : _enviarActual,
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const CircleAvatar(
                        backgroundColor: Color(0xFF2ECC71),
                        child: Icon(Icons.my_location, color: Colors.white)),
                    title: const Text('Compartir ubicación en tiempo real'),
                    subtitle: const Text('Se mueve contigo (15 min · 1 h · 8 h)'),
                    onTap: _yo == null ? null : _enVivo,
                  ),
                  const SizedBox(height: 4),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
