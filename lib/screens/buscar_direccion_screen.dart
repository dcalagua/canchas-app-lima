import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('¿Dónde quieres jugar?')),
      body: Padding(
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
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14)),
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
