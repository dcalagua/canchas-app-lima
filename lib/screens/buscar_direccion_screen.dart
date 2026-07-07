import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../services/location_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Resultado de la búsqueda: centro geográfico + etiqueta para mostrar.
class ResultadoBusqueda {
  final LatLng centro;
  final String etiqueta;
  const ResultadoBusqueda(this.centro, this.etiqueta);
}

/// Búsqueda por dirección/zona (estilo Airbnb). Geocodifica el texto y devuelve
/// un [ResultadoBusqueda] por Navigator.pop. También ofrece distritos rápidos.
class BuscarDireccionScreen extends StatefulWidget {
  const BuscarDireccionScreen({super.key});

  @override
  State<BuscarDireccionScreen> createState() => _BuscarDireccionScreenState();
}

class _BuscarDireccionScreenState extends State<BuscarDireccionScreen> {
  final _ctrl = TextEditingController();
  bool _buscando = false;
  String? _error;
  late double _radioKm = appState.radioBusquedaKm; // radio de búsqueda (km)

  static const _distritos = <String, LatLng>{
    'San Borja': LatLng(-12.108, -76.999),
    'Surco': LatLng(-12.135, -76.992),
    'La Molina': LatLng(-12.079, -76.948),
    'Miraflores': LatLng(-12.121, -77.029),
    'San Isidro': LatLng(-12.097, -77.036),
  };

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _buscar() async {
    final q = _ctrl.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _buscando = true;
      _error = null;
    });
    try {
      final locs = await locationFromAddress('$q, Lima, Perú');
      if (locs.isEmpty) {
        setState(() {
          _buscando = false;
          _error = 'No encontré esa dirección. Prueba con otra o elige un distrito.';
        });
        return;
      }
      final l = locs.first;
      if (!mounted) return;
      Navigator.of(context)
          .pop(ResultadoBusqueda(LatLng(l.latitude, l.longitude), q));
    } catch (_) {
      setState(() {
        _buscando = false;
        _error = 'No pude buscar esa dirección. Prueba con un distrito.';
      });
    }
  }

  Future<void> _usarMiUbicacion() async {
    setState(() {
      _buscando = true;
      _error = null;
    });
    final pos = await LocationService.ubicacionActual();
    if (!mounted) return;
    if (pos == null) {
      setState(() {
        _buscando = false;
        _error = 'No pude obtener tu ubicación. Activa el GPS y los permisos.';
      });
      return;
    }
    Navigator.of(context).pop(ResultadoBusqueda(pos, 'Tu ubicación'));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('¿Dónde quieres jugar?')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _buscar(),
              decoration: InputDecoration(
                hintText: 'Dirección, avenida o distrito',
                prefixIcon: const Icon(Icons.search, color: coral),
                suffixIcon: _buscando
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2)),
                      )
                    : IconButton(
                        icon: const Icon(Icons.arrow_forward, color: verdeCancha),
                        onPressed: _buscar,
                      ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(_error!, style: const TextStyle(color: coralOscuro)),
            ],
            const SizedBox(height: 16),
            Material(
              color: const Color(0xFFEAF6EF),
              borderRadius: BorderRadius.circular(14),
              child: InkWell(
                borderRadius: BorderRadius.circular(14),
                onTap: _usarMiUbicacion,
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                  child: Row(
                    children: [
                      Icon(Icons.my_location, color: verdeCancha),
                      SizedBox(width: 12),
                      Text('Usar mi ubicación actual',
                          style: TextStyle(
                              fontWeight: FontWeight.w600, color: verdeOscuro)),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 22),
            Text('¿Hasta qué distancia?',
                style: Theme.of(context)
                    .textTheme
                    .titleSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 2),
            const Text('Muestra canchas dentro de este radio de tu ubicación.',
                style: TextStyle(color: textoTenue, fontSize: 12)),
            Row(
              children: [
                const Icon(Icons.social_distance, size: 20, color: verdeCancha),
                const SizedBox(width: 8),
                Text('${_radioKm.round()} km',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 20)),
              ],
            ),
            Slider(
              value: _radioKm,
              min: AppState.radioMinKm,
              max: AppState.radioMaxKm,
              divisions: (AppState.radioMaxKm - AppState.radioMinKm).round(),
              label: '${_radioKm.round()} km',
              activeColor: verdeCancha,
              onChanged: (v) => setState(() {
                _radioKm = v;
                appState.setRadioBusqueda(v);
              }),
            ),
            Wrap(
              spacing: 8,
              children: [
                for (final p in const [5.0, 10.0, 20.0, 30.0])
                  ChoiceChip(
                    label: Text('${p.round()} km'),
                    selected: _radioKm.round() == p.round(),
                    selectedColor: limaSuave,
                    onSelected: (_) => setState(() {
                      _radioKm = p;
                      appState.setRadioBusqueda(p);
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 22),
            Text('Distritos populares',
                style: Theme.of(context)
                    .textTheme
                    .titleSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final e in _distritos.entries)
                  ActionChip(
                    avatar: const Icon(Icons.place, size: 18, color: verdeCancha),
                    label: Text(e.key),
                    onPressed: () => Navigator.of(context)
                        .pop(ResultadoBusqueda(e.value, e.key)),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
