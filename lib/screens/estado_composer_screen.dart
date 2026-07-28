import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../data/estados_repo.dart';
import '../services/musica_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/chip_musica.dart';
import '../widgets/dialogo_pichangol.dart';
import 'selector_musica_screen.dart';

/// Paleta de fondos para el estado de TEXTO (colores de marca + vivos).
const _fondos = <int>[
  0xFF128C7E, // lima
  0xFF008489, // teal
  0xFF14463A, // bosque
  0xFF7B61FF, // morado
  0xFFE07A3E, // naranja
  0xFFC13515, // rojo Airbnb
  0xFF2AA9E0, // azul
  0xFF222222, // charcoal
];

/// Composer de ESTADO de TEXTO (tipo WhatsApp): escribe sobre un fondo de color
/// que puedes cambiar. Al enviar, publica el estado (24 h).
class EstadoComposerScreen extends StatefulWidget {
  const EstadoComposerScreen({super.key});

  @override
  State<EstadoComposerScreen> createState() => _EstadoComposerScreenState();
}

class _EstadoComposerScreenState extends State<EstadoComposerScreen> {
  final _ctrl = TextEditingController();
  int _bgIdx = 0;
  bool _enviando = false;
  PistaMusica? _musica;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _elegirMusica() async {
    final p = await Navigator.of(context).push<PistaMusica>(
        MaterialPageRoute(builder: (_) => const SelectorMusicaScreen()));
    if (p != null && mounted) setState(() => _musica = p);
  }

  Future<void> _publicar() async {
    final t = _ctrl.text.trim();
    if (t.isEmpty || _enviando) return;
    setState(() => _enviando = true);
    final e = await appState.publicarEstadoTexto(
      t,
      _fondos[_bgIdx],
      musicaTitulo: _musica?.titulo ?? '',
      musicaArtista: _musica?.artista ?? '',
      musicaPreview: _musica?.previewUrl ?? '',
      musicaArt: _musica?.artUrl ?? '',
    );
    if (!mounted) return;
    if (e == null) {
      setState(() => _enviando = false);
      await avisarPichangol(context,
          titulo: 'No se pudo publicar',
          mensaje:
              'No pudimos publicar tu estado. Revisa tu conexión e inténtalo de nuevo.',
          icono: Icons.cloud_off);
      return;
    }
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final bg = Color(_fondos[_bgIdx]);
    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
        title: const Text('Estado',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            tooltip: 'Añadir música',
            icon: Icon(
                _musica != null ? Icons.music_note : Icons.music_note_outlined,
                color: Colors.white),
            onPressed: _elegirMusica,
          ),
          IconButton(
            tooltip: 'Cambiar color',
            icon: const Icon(Icons.palette_outlined, color: Colors.white),
            onPressed: () =>
                setState(() => _bgIdx = (_bgIdx + 1) % _fondos.length),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // width infinito (acotado por el Scaffold) para que el TextField
            // ocupe TODO el ancho; si no, con maxLines:null cada letra caía en su
            // propia línea y se veían "rayas". El scroll deja crecer con teclado.
            Expanded(
              child: SizedBox(
                width: double.infinity,
                child: SingleChildScrollView(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 48),
                  child: TextField(
                    controller: _ctrl,
                    autofocus: true,
                    textAlign: TextAlign.center,
                    maxLines: null,
                    maxLength: 280,
                    cursorColor: Colors.white,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 26,
                        fontWeight: FontWeight.w700,
                        height: 1.3),
                    decoration: const InputDecoration(
                      border: InputBorder.none,
                      counterText: '',
                      hintText: 'Escribe un estado',
                      hintStyle:
                          TextStyle(color: Colors.white70, fontSize: 24),
                    ),
                  ),
                ),
              ),
            ),
            if (_musica != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                child: ChipMusica(
                    pista: _musica!,
                    onQuitar: () => setState(() => _musica = null)),
              ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: Colors.white,
        onPressed: _enviando ? null : _publicar,
        child: _enviando
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2, color: lima))
            : const Icon(Icons.send, color: lima),
      ),
    );
  }
}

/// Composer de ESTADO de FOTO: muestra la foto elegida + pie opcional y publica.
class EstadoFotoComposerScreen extends StatefulWidget {
  const EstadoFotoComposerScreen({super.key, required this.bytes});
  final Uint8List bytes;

  @override
  State<EstadoFotoComposerScreen> createState() =>
      _EstadoFotoComposerScreenState();
}

class _EstadoFotoComposerScreenState extends State<EstadoFotoComposerScreen> {
  final _ctrl = TextEditingController();
  bool _enviando = false;
  PistaMusica? _musica;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _elegirMusica() async {
    final p = await Navigator.of(context).push<PistaMusica>(
        MaterialPageRoute(builder: (_) => const SelectorMusicaScreen()));
    if (p != null && mounted) setState(() => _musica = p);
  }

  Future<void> _publicar() async {
    if (_enviando) return;
    setState(() => _enviando = true);
    final e = await appState.publicarEstadoFoto(
      widget.bytes,
      pie: _ctrl.text.trim(),
      musicaTitulo: _musica?.titulo ?? '',
      musicaArtista: _musica?.artista ?? '',
      musicaPreview: _musica?.previewUrl ?? '',
      musicaArt: _musica?.artUrl ?? '',
    );
    if (!mounted) return;
    if (e == null) {
      setState(() => _enviando = false);
      await avisarPichangol(context,
          titulo: 'No se pudo publicar',
          mensaje: EstadosRepo.ultimoErrorFoto ??
              'No pudimos subir tu foto. Inténtalo de nuevo.',
          icono: Icons.cloud_off);
      return;
    }
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
        title: const Text('Estado',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            tooltip: 'Añadir música',
            icon: Icon(
                _musica != null ? Icons.music_note : Icons.music_note_outlined,
                color: Colors.white),
            onPressed: _elegirMusica,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Center(
                child: Image.memory(widget.bytes, fit: BoxFit.contain),
              ),
            ),
            if (_musica != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: ChipMusica(
                      pista: _musica!,
                      onQuitar: () => setState(() => _musica = null)),
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(
                        color: Colors.white12,
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: TextField(
                        controller: _ctrl,
                        maxLength: 200,
                        cursorColor: Colors.white,
                        style: const TextStyle(color: Colors.white),
                        decoration: const InputDecoration(
                          border: InputBorder.none,
                          counterText: '',
                          hintText: 'Añade un pie…',
                          hintStyle: TextStyle(color: Colors.white54),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  FloatingActionButton(
                    backgroundColor: lima,
                    onPressed: _enviando ? null : _publicar,
                    child: _enviando
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.send, color: Colors.white),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
