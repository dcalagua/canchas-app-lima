import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/estado.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';

/// Visor de ESTADOS / HISTORIAS a pantalla completa (tipo WhatsApp): barras de
/// progreso arriba, auto-avance, tap izquierda/derecha para retroceder/avanzar,
/// mantener presionado para pausar y deslizar hacia abajo para cerrar.
class EstadoViewerScreen extends StatefulWidget {
  const EstadoViewerScreen({super.key, required this.autorEmail});

  /// Correo del autor cuyos estados se ven (todos sus estados vigentes).
  final String autorEmail;

  @override
  State<EstadoViewerScreen> createState() => _EstadoViewerScreenState();
}

class _EstadoViewerScreenState extends State<EstadoViewerScreen>
    with SingleTickerProviderStateMixin {
  static const _duracion = Duration(seconds: 5);
  static const _duracionMusica = Duration(seconds: 15); // más tiempo si hay música
  late final AnimationController _ctrl;
  final AudioPlayer _audio = AudioPlayer();
  late List<Estado> _items;
  int _i = 0;

  bool get _esMio =>
      widget.autorEmail.toLowerCase() ==
      (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _items = appState.estadosDe(widget.autorEmail);
    _ctrl = AnimationController(vsync: this, duration: _duracion)
      ..addStatusListener((s) {
        if (s == AnimationStatus.completed) _siguiente();
      });
    if (_items.isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) Navigator.of(context).pop();
      });
    } else {
      _mostrar(0);
    }
  }

  @override
  void dispose() {
    _audio.dispose();
    _ctrl.dispose();
    super.dispose();
  }

  void _mostrar(int idx) {
    if (idx < 0 || idx >= _items.length) return;
    setState(() => _i = idx);
    final e = _items[idx];
    appState.marcarEstadoVisto(e.id);
    // Música: reproduce el preview (o corta si el estado no tiene) y da más
    // tiempo de exhibición para que la canción se escuche.
    _audio.stop();
    if (e.tieneMusica) {
      _ctrl.duration = _duracionMusica;
      try {
        _audio.play(UrlSource(e.musicaPreview));
      } catch (_) {}
    } else {
      _ctrl.duration = _duracion;
    }
    _ctrl
      ..reset()
      ..forward();
  }

  Future<void> _abrirSpotify(Estado e) async {
    _pausar();
    final q = Uri.encodeComponent('${e.musicaTitulo} ${e.musicaArtista}'.trim());
    final url = Uri.parse('https://open.spotify.com/search/$q');
    try {
      await launchUrl(url, mode: LaunchMode.externalApplication);
    } catch (_) {}
    if (mounted) _reanudar();
  }

  void _siguiente() {
    if (_i + 1 < _items.length) {
      _mostrar(_i + 1);
    } else {
      Navigator.of(context).maybePop();
    }
  }

  void _anterior() {
    if (_i - 1 >= 0) {
      _mostrar(_i - 1);
    } else {
      _ctrl
        ..reset()
        ..forward();
    }
  }

  void _pausar() {
    _ctrl.stop();
    _audio.pause();
  }

  void _reanudar() {
    if (!_ctrl.isAnimating) _ctrl.forward();
    if (_items.isNotEmpty && _items[_i].tieneMusica) _audio.resume();
  }

  String _hace(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'ahora';
    if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
    if (d.inHours < 24) return 'hace ${d.inHours} h';
    return 'hace ${d.inDays} d';
  }

  Future<void> _eliminarActual() async {
    _pausar();
    final ok = await confirmarPichangol(
      context,
      titulo: 'Eliminar estado',
      mensaje: '¿Quieres eliminar esta historia? Ya no la verá nadie.',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (!ok) {
      _reanudar();
      return;
    }
    final borrado = _items[_i];
    await appState.eliminarEstado(borrado.id);
    if (!mounted) return;
    _items = appState.estadosDe(widget.autorEmail);
    if (_items.isEmpty) {
      Navigator.of(context).maybePop();
      return;
    }
    _mostrar(_i.clamp(0, _items.length - 1));
  }

  void _verVistas() {
    _pausar();
    final e = _items[_i];
    final vistas = appState.vistasDe(e.id);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 12),
            Row(children: [
              const SizedBox(width: 18),
              const Icon(Icons.remove_red_eye_outlined, color: teal),
              const SizedBox(width: 8),
              Text('Visto por ${vistas.length}',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 16)),
            ]),
            const SizedBox(height: 8),
            if (vistas.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('Todavía nadie ha visto esta historia.',
                    style: TextStyle(color: textoTenue)),
              )
            else
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final em in vistas)
                      ListTile(
                        leading: _MiniAvatar(email: em),
                        title: Text(
                            appState.nombreMostrableDe(em) ?? em,
                            style:
                                const TextStyle(fontWeight: FontWeight.w600)),
                      ),
                  ],
                ),
              ),
            const SizedBox(height: 6),
          ],
        ),
      ),
    ).whenComplete(_reanudar);
  }

  @override
  Widget build(BuildContext context) {
    if (_items.isEmpty) {
      return const Scaffold(
          backgroundColor: Colors.black,
          body: Center(child: CircularProgressIndicator(color: Colors.white)));
    }
    final e = _items[_i];
    final foto = appState.fotoDe(widget.autorEmail);
    final nombre = _esMio
        ? 'Mi estado'
        : (appState.nombreMostrableDe(widget.autorEmail) ?? e.autorNombre);
    final ancho = MediaQuery.of(context).size.width;

    return Scaffold(
      backgroundColor: e.esFoto ? Colors.black : Color(e.bg),
      body: GestureDetector(
        onTapUp: (d) {
          if (d.localPosition.dx < ancho * 0.32) {
            _anterior();
          } else {
            _siguiente();
          }
        },
        onLongPressStart: (_) => _pausar(),
        onLongPressEnd: (_) => _reanudar(),
        onVerticalDragEnd: (d) {
          if ((d.primaryVelocity ?? 0) > 200) Navigator.of(context).maybePop();
        },
        child: Stack(
          children: [
            // Contenido
            Positioned.fill(
              child: e.esFoto
                  ? Center(
                      child: Image.network(
                        e.fotoUrl,
                        fit: BoxFit.contain,
                        loadingBuilder: (c, w, p) => p == null
                            ? w
                            : const Center(
                                child: CircularProgressIndicator(
                                    color: Colors.white)),
                        errorBuilder: (c, _, __) => const Center(
                            child: Icon(Icons.broken_image_outlined,
                                color: Colors.white54, size: 48)),
                      ),
                    )
                  : Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Text(
                          e.texto,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 26,
                            fontWeight: FontWeight.w700,
                            height: 1.3,
                          ),
                        ),
                      ),
                    ),
            ),
            // Pie de foto
            if (e.esFoto && e.texto.isNotEmpty)
              Positioned(
                left: 0,
                right: 0,
                bottom: _esMio ? 84 : 32,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                  child: Text(e.texto,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 17,
                          fontWeight: FontWeight.w600)),
                ),
              ),
            // Barras de progreso + cabecera
            SafeArea(
              child: Column(
                children: [
                  Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    child: Row(
                      children: [
                        for (var k = 0; k < _items.length; k++)
                          Expanded(
                            child: Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 2),
                              child: _Barra(
                                controller: _ctrl,
                                estado: k < _i
                                    ? 1
                                    : k > _i
                                        ? 0
                                        : 2, // 0 vacía, 1 llena, 2 animando
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    child: Row(
                      children: [
                        CircleAvatar(
                          radius: 18,
                          backgroundColor: Colors.white24,
                          backgroundImage:
                              (foto != null && foto.isNotEmpty)
                                  ? NetworkImage(foto)
                                  : null,
                          child: (foto == null || foto.isEmpty)
                              ? Text(
                                  (nombre.isNotEmpty ? nombre[0] : '?')
                                      .toUpperCase(),
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.bold))
                              : null,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(nombre,
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w700)),
                              Text(_hace(e.creadoEn),
                                  style: const TextStyle(
                                      color: Colors.white70, fontSize: 12)),
                            ],
                          ),
                        ),
                        if (_esMio)
                          IconButton(
                            icon: const Icon(Icons.delete_outline,
                                color: Colors.white),
                            onPressed: _eliminarActual,
                          ),
                        IconButton(
                          icon: const Icon(Icons.close, color: Colors.white),
                          onPressed: () => Navigator.of(context).maybePop(),
                        ),
                      ],
                    ),
                  ),
                  // Sticker de música (si la historia trae canción).
                  if (e.tieneMusica)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(12, 2, 12, 0),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: _MusicaSticker(
                            estado: e, onSpotify: () => _abrirSpotify(e)),
                      ),
                    ),
                ],
              ),
            ),
            // "Visto por N" (solo mis estados), abajo
            if (_esMio)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: SafeArea(
                  child: InkWell(
                    onTap: _verVistas,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.remove_red_eye,
                              color: Colors.white, size: 18),
                          const SizedBox(width: 6),
                          Text('Visto por ${appState.vistasCount(e.id)}',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Una barra de progreso segmentada. [estado]: 0 vacía, 1 llena, 2 = animando
/// con el controller.
class _Barra extends StatelessWidget {
  const _Barra({required this.controller, required this.estado});
  final AnimationController controller;
  final int estado;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(3),
      child: SizedBox(
        height: 3,
        child: estado == 2
            ? AnimatedBuilder(
                animation: controller,
                builder: (_, __) => LinearProgressIndicator(
                  value: controller.value,
                  backgroundColor: Colors.white30,
                  valueColor: const AlwaysStoppedAnimation(Colors.white),
                ),
              )
            : Container(color: estado == 1 ? Colors.white : Colors.white30),
      ),
    );
  }
}

/// Sticker de música en el visor: carátula + título/artista + "Spotify".
class _MusicaSticker extends StatelessWidget {
  const _MusicaSticker({required this.estado, required this.onSpotify});
  final Estado estado;
  final VoidCallback onSpotify;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(6, 5, 10, 5),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.4),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: estado.musicaArt.isNotEmpty
                ? Image.network(estado.musicaArt,
                    width: 26,
                    height: 26,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const Icon(Icons.music_note,
                        color: Colors.white, size: 20))
                : const Icon(Icons.music_note, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              '${estado.musicaTitulo} · ${estado.musicaArtista}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                  fontSize: 12),
            ),
          ),
          const SizedBox(width: 8),
          InkWell(
            onTap: onSpotify,
            child: const Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.play_circle_fill, color: Color(0xFF1DB954), size: 18),
              SizedBox(width: 3),
              Text('Spotify',
                  style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      fontSize: 12)),
            ]),
          ),
        ],
      ),
    );
  }
}

class _MiniAvatar extends StatelessWidget {
  const _MiniAvatar({required this.email});
  final String email;
  @override
  Widget build(BuildContext context) {
    final foto = appState.fotoDe(email);
    final nombre = appState.nombreMostrableDe(email) ?? email;
    return CircleAvatar(
      radius: 18,
      backgroundColor: limaSuave,
      backgroundImage:
          (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
      child: (foto == null || foto.isEmpty)
          ? Text((nombre.isNotEmpty ? nombre[0] : '?').toUpperCase(),
              style: const TextStyle(
                  color: teal, fontWeight: FontWeight.bold))
          : null,
    );
  }
}
