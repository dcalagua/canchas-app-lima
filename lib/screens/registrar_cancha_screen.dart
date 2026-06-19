import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../models/models.dart';
import '../services/sport_detector.dart';
import '../state/app_state.dart';
import '../theme.dart';

class RegistrarCanchaScreen extends StatefulWidget {
  const RegistrarCanchaScreen({super.key});

  @override
  State<RegistrarCanchaScreen> createState() => _RegistrarCanchaScreenState();
}

class _RegistrarCanchaScreenState extends State<RegistrarCanchaScreen> {
  static const _centros = {
    Distrito.sanBorja: LatLng(-12.108, -76.999),
    Distrito.surco: LatLng(-12.135, -76.992),
    Distrito.laMolina: LatLng(-12.079, -76.948),
  };

  final _nombre = TextEditingController();
  final _precio = TextEditingController(text: '120');
  Distrito _distrito = Distrito.sanBorja;
  Deporte _deporte = Deporte.futbol;

  Uint8List? _foto;
  bool _analizando = false;
  DeteccionDeporte? _deteccion;

  @override
  void dispose() {
    _nombre.dispose();
    _precio.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final XFile? file = await ImagePicker()
        .pickImage(source: ImageSource.gallery, maxWidth: 1024);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() {
      _foto = bytes;
      _analizando = true;
      _deteccion = null;
    });
    final det = await SportDetector.detectar(bytes);
    if (!mounted) return;
    setState(() {
      _analizando = false;
      _deteccion = det;
      _deporte = det.deporte; // la IA preselecciona el deporte
    });
  }

  void _publicar() {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ponle un nombre a la cancha.')),
      );
      return;
    }
    final precio = int.tryParse(_precio.text.trim()) ?? 100;
    final base = _centros[_distrito]!;
    final rnd = Random();
    final ubic = LatLng(
      base.latitude + (rnd.nextDouble() - 0.5) * 0.012,
      base.longitude + (rnd.nextDouble() - 0.5) * 0.012,
    );
    appState.agregarCancha(Cancha(
      id: 'u${DateTime.now().millisecondsSinceEpoch}',
      nombre: nombre,
      club: appState.nombreClub,
      distrito: _distrito,
      deporte: _deporte,
      precioHora: precio,
      ubicacion: ubic,
      clubFundador: false,
      digitalizada: true,
    ));
    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          backgroundColor: verdeCancha,
          content: Text('✅ "$nombre" publicada en el mapa.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Registrar cancha')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _ZonaFoto(
            foto: _foto,
            onTap: _elegirFoto,
          ),
          const SizedBox(height: 12),
          if (_analizando)
            Row(
              children: const [
                SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2)),
                SizedBox(width: 10),
                Text('Analizando la foto con IA…'),
              ],
            )
          else if (_deteccion != null)
            _ResultadoIA(deteccion: _deteccion!),
          const SizedBox(height: 20),
          TextField(
            controller: _nombre,
            decoration: const InputDecoration(
              labelText: 'Nombre de la cancha',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 14),
          DropdownButtonFormField<Deporte>(
            value: _deporte,
            decoration: const InputDecoration(
                labelText: 'Deporte', border: OutlineInputBorder()),
            items: [
              for (final d in Deporte.values)
                DropdownMenuItem(value: d, child: Text(d.etiqueta)),
            ],
            onChanged: (v) => setState(() => _deporte = v ?? _deporte),
          ),
          const SizedBox(height: 14),
          DropdownButtonFormField<Distrito>(
            value: _distrito,
            decoration: const InputDecoration(
                labelText: 'Distrito', border: OutlineInputBorder()),
            items: [
              for (final d in _centros.keys)
                DropdownMenuItem(value: d, child: Text(d.etiqueta)),
            ],
            onChanged: (v) => setState(() => _distrito = v ?? _distrito),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _precio,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Precio por hora (S/)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: coral,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
              onPressed: _publicar,
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Publicar cancha'),
            ),
          ),
        ],
      ),
    );
  }
}

class _ZonaFoto extends StatelessWidget {
  final Uint8List? foto;
  final VoidCallback onTap;
  const _ZonaFoto({required this.foto, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 180,
        decoration: BoxDecoration(
          color: const Color(0xFFEAF6EF),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: verdeClaro),
        ),
        clipBehavior: Clip.antiAlias,
        child: foto == null
            ? Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  Icon(Icons.add_a_photo, color: verdeCancha, size: 40),
                  SizedBox(height: 8),
                  Text('Sube una foto de la cancha',
                      style: TextStyle(
                          color: verdeOscuro, fontWeight: FontWeight.w600)),
                  Text('la IA detectará el deporte',
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                ],
              )
            : Image.memory(foto!, fit: BoxFit.cover, width: double.infinity),
      ),
    );
  }
}

class _ResultadoIA extends StatelessWidget {
  final DeteccionDeporte deteccion;
  const _ResultadoIA({required this.deteccion});

  @override
  Widget build(BuildContext context) {
    final pct = (deteccion.confianza * 100).round();
    final color = colorDeporte(deteccion.deporte);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color),
      ),
      child: Row(
        children: [
          Icon(Icons.auto_awesome, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'IA detectó: ${deteccion.deporte.etiqueta}  ·  $pct% de confianza',
              style: TextStyle(fontWeight: FontWeight.w600, color: color),
            ),
          ),
        ],
      ),
    );
  }
}
