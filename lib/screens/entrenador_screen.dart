import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/entrenador_service.dart';
import 'encuadre_asistido_screen.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/candado_pro.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/ilustracion_pichangol.dart';

/// ENTRENADOR VIRTUAL 🎾 — graba tu golpe y un coach IA te dice qué mejorar.
///
/// Flujo: eliges deporte y golpe (por SELECCIÓN, regla del app) → grabas o
/// eliges un clip corto (≤20 s) → "Analizar" sube el video y pide el informe
/// al backend. Si activaste "Tips en mi reloj", las correcciones llegan como
/// notificaciones cortas que el teléfono espeja al smartwatch emparejado.
/// El historial ("Mis análisis") vive en la nube y pinta device-first.
class EntrenadorScreen extends StatefulWidget {
  const EntrenadorScreen({super.key});

  @override
  State<EntrenadorScreen> createState() => _EntrenadorScreenState();
}

class _EntrenadorScreenState extends State<EntrenadorScreen> {
  String _deporte = 'tenis';
  String _golpe = 'Saque';
  bool _tipsReloj = false;
  bool _analizando = false;
  Map<String, dynamic>? _informe; // el último informe recibido
  int _tipsEnviados = 0;
  List<Map<String, dynamic>> _historial = const [];

  static const _golpes = <String, List<String>>{
    'tenis': ['Saque', 'Derecha', 'Revés', 'Volea', 'Smash'],
    'padel': ['Saque', 'Bandeja', 'Víbora', 'Volea', 'Globo', 'Remate'],
    'pickleball': ['Saque', 'Dink', 'Volea', 'Tercer tiro'],
    'futbol': ['Penal', 'Tiro libre', 'Definición', 'Centro'],
    'voley': ['Saque', 'Remate', 'Recepción', 'Bloqueo'],
    'basquet': ['Tiro libre', 'Triple', 'Bandeja', 'Entrada'],
  };
  static const _nombres = <String, String>{
    'tenis': '🎾 Tenis', 'padel': '🎾 Pádel', 'pickleball': '🏓 Pickleball',
    'futbol': '⚽ Fútbol', 'voley': '🏐 Vóley', 'basquet': '🏀 Básquet',
  };

  String get _email => (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _cargarHistorial();
  }

  Future<void> _cargarHistorial() async {
    final h = await EntrenadorService.historial(_email);
    if (mounted) setState(() => _historial = h);
  }

  /// Grabar con la CÁMARA PROPIA (encuadre asistido): la guía en vivo acomoda
  /// el ángulo/distancia y auto-graba con cuenta 3-2-1. El clip nace en el
  /// espacio privado del app — nunca toca la galería del teléfono — y aquí se
  /// borra apenas queda en memoria.
  Future<void> _grabarAsistido() async {
    if (_analizando) return;
    final String? ruta = await Navigator.push<String>(
      context,
      MaterialPageRoute(
          builder: (_) =>
              EncuadreAsistidoScreen(deporte: _deporte, golpe: _golpe)),
    );
    if (ruta == null || !mounted) return;
    final f = File(ruta);
    final Uint8List bytes;
    try {
      bytes = await f.readAsBytes();
    } catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo leer el video. Graba de nuevo.')));
      return;
    }
    try {
      await f.delete();
    } catch (_) {}
    if (!mounted) return;
    await _procesarClip(bytes);
  }

  /// Elegir un clip ya grabado de la galería (el original del usuario NO se
  /// toca; solo se borra la copia temporal que image_picker deja en caché).
  Future<void> _grabar(ImageSource origen) async {
    if (_analizando) return;
    final XFile? clip = await ImagePicker().pickVideo(
        source: origen, maxDuration: const Duration(seconds: 20));
    if (clip == null || !mounted) return;
    final bytes = await clip.readAsBytes();
    try {
      await File(clip.path).delete();
    } catch (_) {}
    if (!mounted) return;
    await _procesarClip(bytes);
  }

  /// Sube el clip (ya en memoria) y pide el informe al coach. El video en la
  /// nube lo borra el backend apenas el informe sale.
  Future<void> _procesarClip(Uint8List bytes) async {
    if (bytes.length > 40 * 1024 * 1024) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('El video pesa demasiado. Graba 15–20 segundos.')));
      return;
    }
    setState(() {
      _analizando = true;
      _informe = null;
      _tipsEnviados = 0;
    });
    // Paso 1: sube el clip al bucket.
    final id = 'ent_${DateTime.now().millisecondsSinceEpoch}';
    final url = await EntrenadorService.subirVideo(id, bytes);
    if (!mounted) return;
    if (url == null) {
      setState(() => _analizando = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(EntrenadorService.ultimoError ??
              'No se pudo subir el video.')));
      return;
    }
    // Paso 2: el coach lo analiza — 1 a 2 minutos como máximo.
    final r = await EntrenadorService.analizar(
      email: _email,
      deporte: _deporte,
      golpe: _golpe,
      videoUrl: url,
      tipsReloj: _tipsReloj,
    );
    if (!mounted) return;
    setState(() => _analizando = false);
    final error = r['error']?.toString();
    if (error == 'requiere_pro') {
      await exigirPro(context, funcion: 'El entrenador virtual');
      return;
    }
    if (error == 'limite_mensual') {
      await avisarPichangol(
        context,
        titulo: 'Llegaste a tu tope del mes',
        mensaje: 'Ya usaste todos tus análisis de este mes. El contador se '
            'reinicia el día 1. ¡Practica los drills mientras tanto!',
        icono: Icons.hourglass_bottom,
      );
      return;
    }
    if (error != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error)));
      return;
    }
    setState(() {
      _informe = (r['informe'] as Map?)?.cast<String, dynamic>();
      _tipsEnviados = (r['tips_reloj_enviados'] as num?)?.toInt() ?? 0;
    });
    _cargarHistorial();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final golpes = _golpes[_deporte] ?? const ['Saque'];
    return Scaffold(
      appBar: AppBar(title: const Text('Entrenador virtual')),
      body: AnchoLectura(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
          children: [
            // Cabecera cálida: qué es esto.
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: limaSuave,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: lima),
              ),
              child: const Text(
                '🎥 Graba SOLO el golpe: un clip de 5–10 s. La cámara de '
                'Pichangol te guía sola al ángulo perfecto ("retrocede unos '
                'pasos", "gírate de costado") y graba con cuenta 3-2-1. El '
                'coach te dirá qué haces bien, qué corregir y qué practicar. '
                'Los videos se borran solos después del análisis.',
                style: TextStyle(fontSize: 13.5, height: 1.35),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Deporte',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final d in _golpes.keys)
                  ChoiceChip(
                    label: Text(_nombres[d] ?? d),
                    selected: _deporte == d,
                    onSelected: (_) => setState(() {
                      _deporte = d;
                      _golpe = (_golpes[d] ?? const ['Saque']).first;
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            const Text('¿Qué golpe quieres mejorar?',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final g in golpes)
                  ChoiceChip(
                    label: Text(g),
                    selected: _golpe == g,
                    onSelected: (_) => setState(() => _golpe = g),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            // Tips al RELOJ: notificaciones cortas que el teléfono espeja al
            // smartwatch emparejado (sin app de reloj). Sin reloj, quedan en
            // el informe igual.
            Container(
              decoration: BoxDecoration(
                color: cs.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: trazo),
              ),
              child: SwitchListTile(
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                title: const Text('⌚ Tips en mi reloj',
                    style:
                        TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
                subtitle: const Text(
                    'Las correcciones te llegan como notificaciones cortas '
                    '("Lanza la pelota más arriba"): si tienes un smartwatch '
                    'emparejado, te vibran en la muñeca mientras sigues en '
                    'cancha.',
                    style: TextStyle(fontSize: 12, height: 1.3)),
                value: _tipsReloj,
                onChanged: (v) => setState(() => _tipsReloj = v),
              ),
            ),
            const SizedBox(height: 14),
            if (_analizando)
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: cs.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: trazo),
                ),
                child: const Column(
                  children: [
                    CircularProgressIndicator(color: bosque),
                    SizedBox(height: 12),
                    Text('Tu entrenador está viendo tu video… 👀',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                    Text('Esto toma alrededor de un minuto.',
                        style: TextStyle(color: textoTenue, fontSize: 12.5)),
                  ],
                ),
              )
            else
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          padding: const EdgeInsets.symmetric(vertical: 14)),
                      onPressed: _grabarAsistido,
                      icon: const Icon(Icons.videocam),
                      label: const Text('Grabar mi golpe',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ),
                  const SizedBox(width: 10),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 14)),
                    onPressed: () => _grabar(ImageSource.gallery),
                    icon: const Icon(Icons.video_library_outlined, size: 18),
                    label: const Text('Galería'),
                  ),
                ],
              ),
            if (_informe != null) ...[
              const SizedBox(height: 18),
              _InformeCoach(informe: _informe!, tipsEnviados: _tipsEnviados),
            ],
            const SizedBox(height: 22),
            const Text('Mis análisis',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 8),
            if (_historial.isEmpty && _informe == null)
              const VacioPichangol(
                clave: 'entrenador_vacio',
                emoji: '🎾',
                mensaje: 'Aún no tienes análisis. Graba tu primer golpe y '
                    'mira lo que tu coach te dice.',
                size: 110,
              ),
            for (final h in _historial)
              _HistorialCard(analisis: h),
          ],
        ),
      ),
    );
  }
}

/// El informe del coach: resumen, fortalezas ✅, correcciones 🎯 y drills 🏋️.
class _InformeCoach extends StatelessWidget {
  const _InformeCoach({required this.informe, this.tipsEnviados = 0});

  final Map<String, dynamic> informe;
  final int tipsEnviados;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final encuadreOk = informe['encuadre_ok'] != false;
    final fortalezas = (informe['fortalezas'] as List?) ?? const [];
    final correcciones = (informe['correcciones'] as List?) ?? const [];
    final drills = (informe['drills'] as List?) ?? const [];
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 3)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('🧑‍🏫 Tu entrenador dice',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          const SizedBox(height: 6),
          Text(informe['resumen']?.toString() ?? '',
              style: const TextStyle(fontSize: 13.5, height: 1.4)),
          if (!encuadreOk) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFFFF6E5),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                  '📐 Para un mejor análisis: grábate de costado, cuerpo '
                  'completo, a 3–5 metros.',
                  style: TextStyle(fontSize: 12.5)),
            ),
          ],
          if (tipsEnviados > 0) ...[
            const SizedBox(height: 10),
            Text('⌚ $tipsEnviados tips enviados a tus notificaciones '
                '(míralos en tu reloj).',
                style: const TextStyle(
                    color: bosque,
                    fontWeight: FontWeight.w700,
                    fontSize: 12.5)),
          ],
          if (fortalezas.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('Lo que ya haces bien',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
            const SizedBox(height: 4),
            for (final f in fortalezas)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text('✅ $f', style: const TextStyle(fontSize: 13)),
              ),
          ],
          if (correcciones.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('Para mejorar',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
            const SizedBox(height: 4),
            for (final c in correcciones)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('🎯 ${(c as Map)['titulo'] ?? ''}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 13.5)),
                    Text(c['detalle']?.toString() ?? '',
                        style: const TextStyle(
                            fontSize: 12.5, color: textoTenue, height: 1.35)),
                  ],
                ),
              ),
          ],
          if (drills.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('Tu tarea para la próxima sesión',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
            const SizedBox(height: 4),
            for (final d in drills)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text('🏋️ $d', style: const TextStyle(fontSize: 13)),
              ),
          ],
        ],
      ),
    );
  }
}

/// Tarjeta compacta del historial; al tocar, expande el informe completo.
class _HistorialCard extends StatelessWidget {
  const _HistorialCard({required this.analisis});

  final Map<String, dynamic> analisis;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final informe =
        (analisis['informe'] as Map?)?.cast<String, dynamic>() ?? const {};
    final creado = DateTime.tryParse(analisis['creado']?.toString() ?? '');
    // Fecha Y HORA de la grabación (pedido del director): "mié 25 ago · 21:15".
    final local = creado?.toLocal();
    final fecha = local == null
        ? ''
        : '${AppState.fechaBonita(local.toIso8601String())} · '
            '${local.hour.toString().padLeft(2, '0')}:'
            '${local.minute.toString().padLeft(2, '0')}';
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          title: Text(
              '${analisis['golpe'] ?? ''} · ${analisis['deporte'] ?? ''}',
              style: const TextStyle(
                  fontWeight: FontWeight.w700, fontSize: 14)),
          subtitle: Text(fecha,
              style: const TextStyle(color: textoTenue, fontSize: 12)),
          children: [_InformeCoach(informe: informe)],
        ),
      ),
    );
  }
}
