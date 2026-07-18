import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';

import '../data/canchas_repo.dart';
import '../services/growth_service.dart';
import '../services/location_service.dart';
import '../theme.dart';
import 'validar_reclamo_screen.dart';

/// Mini-app del VERIFICADOR: cola de visitas (priorizada por demanda), captura de
/// fotos GEO del sitio + ubicación + firma → confirma la cancha por carril físico.
/// Las fotos son del ESTABLECIMIENTO (no documentos personales).
class VerificadorScreen extends StatefulWidget {
  const VerificadorScreen({super.key});

  @override
  State<VerificadorScreen> createState() => _VerificadorScreenState();
}

class _VerificadorScreenState extends State<VerificadorScreen> {
  // Cola por CERCANÍA al verificador — sin listas de zonas clavadas a Lima. La
  // app pide al backend las visitas dentro de un radio alrededor de tu GPS, así
  // en Juliaca ves Juliaca, en La Paz ves La Paz, en Ecuador ves Ecuador.
  static const List<double?> _radios = [25, 50, 100, null]; // km; null = todas
  double? _radioKm = 50; // por defecto: 50 km a la redonda
  LatLng? _pos; // ubicación actual del verificador
  bool _cargando = false;
  List<Map<String, dynamic>> _visitas = [];

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    // Ubica al verificador para pedir la cola por cercanía. Fail-safe: si no hay
    // GPS, se pide sin filtro (todas) y se avisa arriba que active la ubicación.
    _pos ??= await LocationService.ubicacionActual();
    final v = await GrowthService.visitas(
      lat: _pos?.latitude,
      lng: _pos?.longitude,
      radioKm: _pos != null ? _radioKm : null,
    );
    if (!mounted) return;
    setState(() {
      _visitas = v;
      _cargando = false;
    });
  }

  /// Etiqueta legible de un radio: 25 → "25 km", null → "Todas".
  String _lblRadio(double? r) => r == null ? 'Todas' : '${r.toStringAsFixed(0)} km';

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Verificador')),
      body: Column(
        children: [
          if (!GrowthService.disponible)
            const Padding(
              padding: EdgeInsets.all(18),
              child: Text(
                  'El servicio de verificación no está configurado en esta build.'),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Visitas pendientes',
                    style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                Text(
                    _pos == null
                        ? 'Cerca de ti · la más pedida primero.'
                        : 'Cerca de ti (${_lblRadio(_radioKm)}) · la más pedida primero.',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(
                          builder: (_) => const ValidarReclamoScreen()),
                    ),
                    icon: const Icon(Icons.pin_drop),
                    label: const Text('Validar reclamo por código'),
                  ),
                ),
                if (_pos == null && !_cargando) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Activa la ubicación para ver solo las canchas cercanas a ti.',
                    style: t.bodySmall?.copyWith(
                        color: clayOscuro, fontWeight: FontWeight.w600),
                  ),
                ],
                const SizedBox(height: 12),
                // Radio de cercanía (reemplaza las zonas fijas de Lima).
                SizedBox(
                  height: 38,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: [
                      for (final r in _radios)
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: ChoiceChip(
                            label: Text(_lblRadio(r)),
                            selected: _radioKm == r,
                            // Seleccionado = verde WhatsApp (marca), no negro.
                            selectedColor: lima,
                            checkmarkColor: Colors.white,
                            labelStyle: TextStyle(
                                color: _radioKm == r
                                    ? Colors.white
                                    : cs.onSurface,
                                fontWeight: FontWeight.w700),
                            onSelected: (_) {
                              setState(() => _radioKm = r);
                              _cargar();
                            },
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _cargar,
              child: _cargando
                  ? const Center(child: CircularProgressIndicator())
                  : _visitas.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          Center(
                              child: Text(
                                  'No hay visitas pendientes cerca de ti.')),
                        ])
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(18, 6, 18, 24),
                          itemCount: _visitas.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 10),
                          itemBuilder: (_, i) => _VisitaCard(
                            visita: _visitas[i],
                            onTap: () => _abrirCaptura(_visitas[i]),
                          ),
                        ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _abrirCaptura(Map<String, dynamic> visita) async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => _CapturaScreen(visita: visita)),
    );
    if (ok == true) _cargar();
  }
}

/// Formatea la distancia del verificador a la visita: "a 380 m" / "a 2.4 km".
String _distancia(dynamic metros) {
  final m = (metros as num).toDouble();
  if (m < 1000) return 'a ${m.round()} m';
  return 'a ${(m / 1000).toStringAsFixed(1)} km';
}

class _VisitaCard extends StatelessWidget {
  const _VisitaCard({required this.visita, required this.onTap});
  final Map<String, dynamic> visita;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: trazo),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Cancha ${visita['cancha_id']}',
                        style: t.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text('${visita['estado']} · ${visita['motivo'] ?? ''}',
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                    if (visita['distancia_m'] != null) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Icon(Icons.directions_walk,
                              size: 14, color: bosque),
                          const SizedBox(width: 3),
                          Text(_distancia(visita['distancia_m']),
                              style: t.bodySmall?.copyWith(
                                  color: bosque, fontWeight: FontWeight.w700)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(10)),
                child: Column(
                  children: [
                    Text('${visita['demanda'] ?? 0}',
                        style: t.titleMedium?.copyWith(
                            color: bosque, fontWeight: FontWeight.w900)),
                    const Text('pedidos',
                        style: TextStyle(color: bosque, fontSize: 10)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CapturaScreen extends StatefulWidget {
  const _CapturaScreen({required this.visita});
  final Map<String, dynamic> visita;

  @override
  State<_CapturaScreen> createState() => _CapturaScreenState();
}

class _CapturaScreenState extends State<_CapturaScreen> {
  final _firma = TextEditingController();
  final List<Uint8List> _fotos = [];
  bool _enviando = false;
  String? _msg;

  @override
  void dispose() {
    _firma.dispose();
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

  Future<void> _confirmar() async {
    if (_fotos.isEmpty) {
      setState(() => _msg = 'Toma al menos una foto del sitio.');
      return;
    }
    if (_firma.text.trim().isEmpty) {
      setState(() => _msg = 'Firma con tu nombre.');
      return;
    }
    setState(() {
      _enviando = true;
      _msg = null;
    });

    // Ubicación del sitio (GPS).
    final pos = await LocationService.ubicacionActual();
    if (pos == null) {
      setState(() {
        _enviando = false;
        _msg = 'No pude obtener tu ubicación. Activa el GPS y reintenta.';
      });
      return;
    }

    // Sube las fotos del sitio a Storage y manda sus URLs.
    final ts = DateTime.now().millisecondsSinceEpoch;
    final urls = <String>[];
    for (var i = 0; i < _fotos.length; i++) {
      final url = await CanchasRepo.subirFoto('verif', _fotos[i],
          sufijo: '${widget.visita['id']}_${i}_$ts');
      if (url != null) urls.add(url);
    }

    final r = await GrowthService.captura(
      vfId: (widget.visita['id'] as num).toInt(),
      fotosGeoUrls: urls,
      latSitio: pos.latitude,
      lngSitio: pos.longitude,
      firma: _firma.text.trim(),
      observaciones: 'Verificado en sitio (${_fotos.length} fotos).',
    );
    if (!mounted) return;
    setState(() => _enviando = false);

    if (r == null) {
      setState(() => _msg = 'No se pudo enviar. Revisa tu conexión.');
      return;
    }
    if (r['ok'] == true) {
      Navigator.of(context).pop(true);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: lima,
        content: Text(
            '✅ ${r['insignia'] ?? 'Cancha verificada'} · coincide (${r['distancia_m'] ?? '—'} m)',
            style: const TextStyle(color: Colors.white)),
      ));
    } else if (r['estado'] == 'rechazada') {
      setState(() => _msg =
          '❌ La ubicación no coincide (${r['distancia_m']} m). Acércate al sitio.');
    } else {
      setState(() => _msg = 'No se pudo: ${r['error'] ?? 'error'}');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar:
          AppBar(title: Text('Verificar cancha ${widget.visita['cancha_id']}')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Text(
              'Zona ${widget.visita['zona'] ?? ''} · demanda ${widget.visita['demanda'] ?? 0}',
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _enviando ? null : _tomarFoto,
            icon: const Icon(Icons.photo_camera),
            label: const Text('Tomar foto del sitio'),
          ),
          const SizedBox(height: 12),
          if (_fotos.isNotEmpty)
            SizedBox(
              height: 90,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _fotos.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (_, i) => ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.memory(_fotos[i],
                      width: 90, height: 90, fit: BoxFit.cover),
                ),
              ),
            ),
          const SizedBox(height: 16),
          TextField(
            controller: _firma,
            decoration: const InputDecoration(
              labelText: 'Firma (tu nombre)',
            ),
          ),
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!,
                style: const TextStyle(
                    color: clayOscuro, fontWeight: FontWeight.w600)),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _enviando ? null : _confirmar,
              icon: _enviando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.verified),
              label: Text(_enviando ? 'Enviando…' : 'Confirmar y firmar'),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            'Las fotos son del establecimiento, no documentos personales. No se piden DNI ni recibos.',
            style: t.bodySmall
                ?.copyWith(color: textoTenue, fontStyle: FontStyle.italic),
          ),
        ],
      ),
    );
  }
}
