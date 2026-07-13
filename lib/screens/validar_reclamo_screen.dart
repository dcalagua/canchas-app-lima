import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../services/location_service.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Validación EN SITIO de un reclamo por el motorizado: ingresa el CÓDIGO que le
/// dieron y, estando en el local, manda su GPS (y fotos del sitio). El servidor
/// exige que la ubicación coincida con la de la cancha; si coincide, la activa
/// con el sello "verificada en persona".
class ValidarReclamoScreen extends StatefulWidget {
  const ValidarReclamoScreen({super.key});

  @override
  State<ValidarReclamoScreen> createState() => _ValidarReclamoScreenState();
}

class _ValidarReclamoScreenState extends State<ValidarReclamoScreen> {
  final _codigo = TextEditingController();
  final List<Uint8List> _fotos = [];
  bool _enviando = false;
  String? _msg;
  bool _ok = false;

  @override
  void dispose() {
    _codigo.dispose();
    super.dispose();
  }

  Future<void> _tomarFoto() async {
    final XFile? f = await ImagePicker()
        .pickImage(source: ImageSource.camera, maxWidth: 1280);
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() => _fotos.add(bytes));
  }

  Future<void> _validar() async {
    final cod = _codigo.text.trim();
    if (cod.length < 4) {
      setState(() => _msg = 'Ingresa el código del reclamo.');
      return;
    }
    setState(() {
      _enviando = true;
      _msg = null;
      _ok = false;
    });

    final pos = await LocationService.ubicacionActual();
    if (pos == null) {
      setState(() {
        _enviando = false;
        _msg = 'No pude obtener tu ubicación. Activa el GPS y reintenta.';
      });
      return;
    }

    // Sube las fotos del sitio (si hay) y manda sus URLs.
    final ts = DateTime.now().millisecondsSinceEpoch;
    final urls = <String>[];
    for (var i = 0; i < _fotos.length; i++) {
      final url = await CanchasRepo.subirFoto('validacion', _fotos[i],
          sufijo: '${cod}_${i}_$ts');
      if (url != null) urls.add(url);
    }

    final r = await PropiedadService.validarReclamo(
      codigo: cod,
      lat: pos.latitude,
      lng: pos.longitude,
      validador: appState.usuario?.email ?? 'motorizado',
      fotosUrls: urls,
    );
    if (!mounted) return;
    setState(() => _enviando = false);

    if (r == null) {
      setState(() => _msg = 'No se pudo enviar. Revisa tu conexión.');
      return;
    }
    if (r['ok'] == true && r['estado'] == 'activada') {
      setState(() {
        _ok = true;
        _msg = '✅ Validada y activada. La cancha quedó verificada en persona.';
      });
    } else if (r['ok'] == true && r['estado'] == 'validada_pendiente_admin') {
      setState(() {
        _ok = true;
        _msg = '✅ Validada. Falta que el admin la active.';
      });
    } else if (r['error'] == 'ubicacion_no_coincide') {
      setState(() => _msg =
          '❌ No estás en el sitio (${r['distancia_m']} m de la cancha). Acércate al local.');
    } else if (r['error'] == 'codigo_invalido') {
      setState(() => _msg =
          '❌ Código inválido o el reclamo no está listo para validar.');
    } else {
      setState(() => _msg = 'No se pudo: ${r['error'] ?? 'error'}');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Validar por código')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Text('Validación en sitio',
              style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text(
              'Ingresa el código del reclamo estando EN el local. Tu GPS debe '
              'coincidir con la ubicación de la cancha.',
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 18),
          TextField(
            controller: _codigo,
            keyboardType: TextInputType.number,
            maxLength: 6,
            decoration: const InputDecoration(
              labelText: 'Código del reclamo',
              prefixIcon: Icon(Icons.pin),
            ),
          ),
          const SizedBox(height: 6),
          FilledButton.icon(
            onPressed: _enviando ? null : _tomarFoto,
            icon: const Icon(Icons.photo_camera),
            label: const Text('Tomar foto del sitio (opcional)'),
          ),
          if (_fotos.isNotEmpty) ...[
            const SizedBox(height: 12),
            SizedBox(
              height: 86,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _fotos.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (_, i) => ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.memory(_fotos[i],
                      width: 86, height: 86, fit: BoxFit.cover),
                ),
              ),
            ),
          ],
          if (_msg != null) ...[
            const SizedBox(height: 16),
            Text(_msg!,
                style: TextStyle(
                    color: _ok ? cs.primary : clayOscuro,
                    fontWeight: FontWeight.w700)),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _enviando || _ok ? null : _validar,
              icon: _enviando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.where_to_vote),
              label: Text(_enviando ? 'Validando…' : 'Validar aquí'),
            ),
          ),
        ],
      ),
    );
  }
}
