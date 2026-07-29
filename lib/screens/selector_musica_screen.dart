import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import '../services/musica_service.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

/// Buscador de música para una historia: escribe, escucha el preview de 30 s y
/// elige. Devuelve la [PistaMusica] seleccionada (o null si cancela).
class SelectorMusicaScreen extends StatefulWidget {
  const SelectorMusicaScreen({super.key});

  @override
  State<SelectorMusicaScreen> createState() => _SelectorMusicaScreenState();
}

class _SelectorMusicaScreenState extends State<SelectorMusicaScreen> {
  final _q = TextEditingController();
  final _player = AudioPlayer();
  List<PistaMusica> _res = const [];
  bool _cargando = false;
  bool _destacadas = true; // mostrando el top (aún no buscó)
  int _sonando = -1; // índice que se está escuchando (-1 = ninguno)

  @override
  void initState() {
    super.initState();
    _cargarDestacadas();
  }

  @override
  void dispose() {
    _player.dispose();
    _q.dispose();
    super.dispose();
  }

  Future<void> _cargarDestacadas() async {
    setState(() => _cargando = true);
    final r = await MusicaService.destacadas();
    if (!mounted) return;
    setState(() {
      _res = r;
      _destacadas = true;
      _cargando = false;
    });
  }

  Future<void> _buscar() async {
    final q = _q.text.trim();
    if (q.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _cargando = true);
    final r = await MusicaService.buscar(q);
    if (!mounted) return;
    setState(() {
      _res = r;
      _destacadas = false;
      _cargando = false;
    });
  }

  Future<void> _preview(int i) async {
    if (_sonando == i) {
      await _player.stop();
      if (mounted) setState(() => _sonando = -1);
      return;
    }
    await _player.stop();
    setState(() => _sonando = i);
    try {
      await _player.play(UrlSource(_res[i].previewUrl));
    } catch (_) {}
  }

  Future<void> _usar(PistaMusica p) async {
    await _player.stop();
    if (mounted) setState(() => _sonando = -1);
    if (!mounted) return;
    // Paso 2: elegir el fragmento (qué ~15 s suenan en la historia).
    final elegido = await Navigator.of(context).push<PistaMusica>(
        MaterialPageRoute(builder: (_) => RecorteMusicaScreen(pista: p)));
    if (elegido != null && mounted) Navigator.of(context).pop(elegido);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Añadir música',
            style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
            child: TextField(
              controller: _q,
              // Sin autofocus: así se ven las canciones destacadas sin que el
              // teclado las tape apenas entras.
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _buscar(),
              decoration: InputDecoration(
                hintText: 'Busca una canción o artista',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                    icon: const Icon(Icons.arrow_forward), onPressed: _buscar),
                filled: true,
                fillColor: Theme.of(context).brightness == Brightness.dark
                    ? const Color(0xFF1F2C34)
                    : const Color(0xFFF2F2F2),
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none),
              ),
            ),
          ),
          if (!_cargando && _res.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 2, 18, 6),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(_destacadas ? 'Destacadas' : 'Resultados',
                    style: const TextStyle(
                        color: textoTenue,
                        fontWeight: FontWeight.w700,
                        fontSize: 13)),
              ),
            ),
          Expanded(
            child: _cargando
                ? const CargandoPichangol()
                : _res.isEmpty
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.all(28),
                          child: Text(
                            'Busca tu canción y escucha un preview de 30 s antes '
                            'de añadirla a tu historia.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: textoTenue),
                          ),
                        ),
                      )
                    : ListView.separated(
                        itemCount: _res.length,
                        separatorBuilder: (_, __) =>
                            Divider(height: 1, color: trazo.withOpacity(0.5)),
                        itemBuilder: (_, i) {
                          final p = _res[i];
                          final sonando = _sonando == i;
                          return ListTile(
                            onTap: () => _preview(i),
                            leading: Stack(
                              alignment: Alignment.center,
                              children: [
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: p.artUrl.isNotEmpty
                                      ? Image.network(p.artUrl,
                                          width: 48,
                                          height: 48,
                                          fit: BoxFit.cover,
                                          errorBuilder: (_, __, ___) =>
                                              const _ArtVacia())
                                      : const _ArtVacia(),
                                ),
                                Icon(
                                  sonando
                                      ? Icons.pause_circle_filled
                                      : Icons.play_circle_fill,
                                  color: Colors.white,
                                  size: 26,
                                ),
                              ],
                            ),
                            title: Text(p.titulo,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600)),
                            subtitle: Text(p.artista,
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                            trailing: FilledButton(
                              style: FilledButton.styleFrom(
                                  backgroundColor: lima,
                                  visualDensity: VisualDensity.compact),
                              onPressed: () => _usar(p),
                              child: const Text('Usar'),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _ArtVacia extends StatelessWidget {
  const _ArtVacia();
  @override
  Widget build(BuildContext context) => Container(
        width: 48,
        height: 48,
        color: limaSuave,
        child: const Icon(Icons.music_note, color: teal),
      );
}

/// Paso 2 de "Añadir música": elige QUÉ fragmento (~15 s) de la canción suena en
/// la historia (estilo Instagram/WhatsApp). Reproduce en bucle el fragmento
/// elegido mientras arrastras. Devuelve la [PistaMusica] con `inicioMs`.
class RecorteMusicaScreen extends StatefulWidget {
  const RecorteMusicaScreen({super.key, required this.pista});
  final PistaMusica pista;

  @override
  State<RecorteMusicaScreen> createState() => _RecorteMusicaScreenState();
}

class _RecorteMusicaScreenState extends State<RecorteMusicaScreen> {
  static const _ventanaMs = 15000; // lo que dura la música en la historia
  final _player = AudioPlayer();
  int _inicioMs = 0;
  int _durMs = 30000; // duración del preview (se corrige al cargar)
  bool _listo = false;

  int get _maxInicio => (_durMs - _ventanaMs).clamp(0, _durMs);

  @override
  void initState() {
    super.initState();
    _player.onDurationChanged.listen((d) {
      if (d.inMilliseconds > 1000 && mounted) {
        setState(() => _durMs = d.inMilliseconds);
      }
    });
    // Bucle del fragmento: al pasar el final de la ventana, vuelve al inicio.
    _player.onPositionChanged.listen((pos) {
      if (!mounted) return;
      if (pos.inMilliseconds >= _inicioMs + _ventanaMs ||
          pos.inMilliseconds < _inicioMs - 500) {
        _player.seek(Duration(milliseconds: _inicioMs));
      }
    });
    _arrancar();
  }

  Future<void> _arrancar() async {
    try {
      await _player.play(UrlSource(widget.pista.previewUrl));
      await _player.seek(Duration(milliseconds: _inicioMs));
      if (mounted) setState(() => _listo = true);
    } catch (_) {
      if (mounted) setState(() => _listo = true);
    }
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  void _mover(double v) {
    _inicioMs = v.round();
    _player.seek(Duration(milliseconds: _inicioMs));
    setState(() {});
  }

  String _fmt(int ms) {
    final s = ms ~/ 1000;
    return '0:${(s % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.pista;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Elegir fragmento',
            style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: p.artUrl.isNotEmpty
                  ? Image.network(p.artUrl,
                      width: 180,
                      height: 180,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const _ArtVacia())
                  : Container(
                      width: 180,
                      height: 180,
                      color: limaSuave,
                      child: const Icon(Icons.music_note, color: teal, size: 60)),
            ),
            const SizedBox(height: 16),
            Text(p.titulo,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            Text(p.artista,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: textoTenueDe(context))),
            const Spacer(),
            if (!_listo)
              const Padding(
                padding: EdgeInsets.only(bottom: 12),
                child: Text('Cargando preview…',
                    style: TextStyle(color: textoTenue)),
              ),
            // Barra de recorte: la ventana de 15 s dentro del preview.
            Row(
              children: [
                Text(_fmt(_inicioMs),
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(width: 8),
                Expanded(
                  child: Icon(Icons.graphic_eq, color: lima.withOpacity(0.7)),
                ),
                const SizedBox(width: 8),
                Text('~${_ventanaMs ~/ 1000}s',
                    style: TextStyle(color: textoTenueDe(context))),
              ],
            ),
            Slider(
              value: _inicioMs.toDouble().clamp(0, _maxInicio.toDouble()),
              min: 0,
              max: _maxInicio.toDouble() <= 0 ? 1 : _maxInicio.toDouble(),
              activeColor: lima,
              onChanged: _maxInicio <= 0 ? null : _mover,
            ),
            Text('Arrastra para elegir desde dónde suena en tu historia',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenueDe(context), fontSize: 12.5)),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    minimumSize: const Size.fromHeight(50)),
                onPressed: () {
                  _player.stop();
                  Navigator.of(context).pop(p.copyWith(inicioMs: _inicioMs));
                },
                icon: const Icon(Icons.check),
                label: const Text('Usar este fragmento',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
