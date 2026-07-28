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
  int _sonando = -1; // índice que se está escuchando (-1 = ninguno)

  @override
  void dispose() {
    _player.dispose();
    _q.dispose();
    super.dispose();
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

  void _usar(PistaMusica p) {
    _player.stop();
    Navigator.of(context).pop(p);
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
              autofocus: true,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _buscar(),
              decoration: InputDecoration(
                hintText: 'Busca una canción o artista',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                    icon: const Icon(Icons.arrow_forward), onPressed: _buscar),
                filled: true,
                fillColor: const Color(0xFFF2F2F2),
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none),
              ),
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
