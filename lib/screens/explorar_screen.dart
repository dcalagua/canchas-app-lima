import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../theme.dart';

class ExplorarScreen extends StatelessWidget {
  const ExplorarScreen({super.key});

  Set<Marker> _marcadores() {
    return SampleData.canchas.map((c) {
      final hue = c.deporte == Deporte.padel
          ? BitmapDescriptor.hueAzure
          : BitmapDescriptor.hueGreen;
      final fundador = c.clubFundador ? ' · Club Fundador' : '';
      return Marker(
        markerId: MarkerId(c.id),
        position: c.ubicacion,
        icon: BitmapDescriptor.defaultMarkerWithHue(hue),
        infoWindow: InfoWindow(
          title: '${c.nombre} · S/ ${c.precioHora}/h',
          snippet: '${c.club} · ${c.deporte.etiqueta} · ${c.distrito.etiqueta}$fundador',
        ),
      );
    }).toSet();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Explorar canchas')),
      body: Stack(
        children: [
          GoogleMap(
            initialCameraPosition: const CameraPosition(
              target: SampleData.centroPiloto,
              zoom: 12.5,
            ),
            markers: _marcadores(),
            myLocationButtonEnabled: false,
            zoomControlsEnabled: false,
          ),
          const Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: EdgeInsets.all(16),
              child: _Leyenda(),
            ),
          ),
        ],
      ),
    );
  }
}

class _Leyenda extends StatelessWidget {
  const _Leyenda();

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 4,
      borderRadius: BorderRadius.circular(12),
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Zona piloto: San Borja · Surco · La Molina',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
            ),
            const SizedBox(height: 6),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: const [
                _Punto(azulPadel, 'Pádel'),
                SizedBox(width: 16),
                _Punto(verdeCancha, 'Tenis'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Punto extends StatelessWidget {
  final Color color;
  final String texto;
  const _Punto(this.color, this.texto);

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(texto, style: const TextStyle(fontSize: 11)),
      ],
    );
  }
}
