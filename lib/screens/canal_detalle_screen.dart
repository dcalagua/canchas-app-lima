import 'dart:typed_data';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import '../data/canales_repo.dart';
import '../data/reacciones_repo.dart';
import '../models/canal.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'editar_canal_screen.dart';

/// Feed de un CANAL (tipo WhatsApp Channels): cabecera con foto/nombre/seguidores,
/// botón de seguir, y las publicaciones. Si soy el dueño, puedo publicar
/// (texto + foto/video), editar el canal y borrar publicaciones.
class CanalDetalleScreen extends StatefulWidget {
  const CanalDetalleScreen({super.key, required this.canal});
  final Canal canal;

  @override
  State<CanalDetalleScreen> createState() => _CanalDetalleScreenState();
}

class _CanalDetalleScreenState extends State<CanalDetalleScreen> {
  late Canal _canal;
  List<CanalPost> _posts = const [];
  bool _cargando = true;
  bool _sigo = false;
  bool _publicando = false;
  final _texto = TextEditingController();

  // reacciones: postId → {correo: emoji}
  final Map<String, Map<String, String>> _reacciones = {};

  String get _yo => (appState.usuario?.email ?? '').toLowerCase();
  bool get _soyDueno => _canal.ownerEmail.toLowerCase() == _yo;
  String get _hiloReacc => 'canal_${_canal.id}';

  @override
  void initState() {
    super.initState();
    _canal = widget.canal;
    _cargar();
    // Reacciones en vivo de todo el canal.
    ReaccionesRepo.stream(_hiloReacc).listen((rows) {
      final m = <String, Map<String, String>>{};
      for (final r in rows) {
        final mid = (r['mensaje_id'] ?? '').toString();
        final em = (r['email'] ?? '').toString().toLowerCase();
        final emoji = (r['emoji'] ?? '').toString();
        if (mid.isEmpty || em.isEmpty || emoji.isEmpty) continue;
        (m[mid] ??= <String, String>{})[em] = emoji;
      }
      if (mounted) {
        setState(() {
          _reacciones
            ..clear()
            ..addAll(m);
        });
      }
    });
  }

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    final seguidos = await CanalesRepo.seguidosDe(_yo);
    final posts = await CanalesRepo.posts(_canal.id);
    await appState.cargarPerfiles([_canal.ownerEmail]);
    // Marca el canal como visto hasta el post más nuevo → limpia el badge.
    if (posts.isNotEmpty) {
      appState.marcarCanalVisto(_canal.id, posts.first.creado);
    } else {
      appState.marcarCanalVisto(_canal.id, DateTime.now());
    }
    if (!mounted) return;
    setState(() {
      _sigo = seguidos.contains(_canal.id);
      _posts = posts;
      _cargando = false;
    });
  }

  Future<void> _seguirAlternar() async {
    final antes = _sigo;
    setState(() => _sigo = !antes);
    final ok = antes
        ? await CanalesRepo.dejar(_canal.id, _yo)
        : await CanalesRepo.seguir(_canal.id, _yo);
    if (!ok && mounted) setState(() => _sigo = antes);
    if (mounted) {
      setState(() => _canal = _canal.copyWith(
          seguidores: (_canal.seguidores + (antes ? -1 : 1)).clamp(0, 1 << 30)));
    }
  }

  Future<void> _publicarTexto() async {
    final t = _texto.text.trim();
    final u = appState.usuario;
    if (t.isEmpty || u == null || _publicando) return;
    setState(() => _publicando = true);
    final post = CanalPost(
      id: 'cp_${DateTime.now().microsecondsSinceEpoch}',
      canalId: _canal.id,
      autorEmail: u.email,
      autorNombre: u.nombre,
      tipo: 'texto',
      texto: t,
      creado: DateTime.now(),
    );
    final ok = await CanalesRepo.publicar(post);
    if (!mounted) return;
    setState(() {
      _publicando = false;
      if (ok) {
        _texto.clear();
        _posts = [post, ..._posts];
      }
    });
  }

  Future<void> _publicarMedia({required bool video}) async {
    final u = appState.usuario;
    if (u == null || _publicando) return;
    final picker = ImagePicker();
    if (video) {
      final vf = await picker.pickVideo(
          source: ImageSource.gallery,
          maxDuration: const Duration(seconds: 60));
      if (vf == null) return;
      setState(() => _publicando = true);
      final bytes = await vf.readAsBytes();
      await _subirYPublicar(bytes, tipo: 'video', video: true);
    } else {
      final f = await picker.pickImage(
          source: ImageSource.gallery, maxWidth: 1600, imageQuality: 85);
      if (f == null) return;
      setState(() => _publicando = true);
      final bytes = await f.readAsBytes();
      await _subirYPublicar(bytes, tipo: 'foto', video: false);
    }
  }

  Future<void> _subirYPublicar(Uint8List bytes,
      {required String tipo, required bool video}) async {
    final u = appState.usuario!;
    final id = 'cp_${DateTime.now().microsecondsSinceEpoch}';
    final ext = video ? 'mp4' : 'jpg';
    final url =
        await CanalesRepo.subirMedia('${_canal.id}/$id.$ext', bytes, video: video);
    if (url == null) {
      if (mounted) {
        setState(() => _publicando = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo subir. Revisa el bucket "canales".')));
      }
      return;
    }
    final post = CanalPost(
      id: id,
      canalId: _canal.id,
      autorEmail: u.email,
      autorNombre: u.nombre,
      tipo: tipo,
      texto: _texto.text.trim(),
      mediaUrl: url,
      creado: DateTime.now(),
    );
    final ok = await CanalesRepo.publicar(post);
    if (!mounted) return;
    setState(() {
      _publicando = false;
      if (ok) {
        _texto.clear();
        _posts = [post, ..._posts];
      }
    });
  }

  Future<void> _borrarPost(CanalPost p) async {
    final ok = await confirmarPichangol(context,
        titulo: 'Eliminar publicación',
        mensaje: '¿Quieres eliminar esta publicación del canal?',
        textoConfirmar: 'Eliminar',
        destructivo: true,
        icono: Icons.delete_outline);
    if (!ok) return;
    final hecho = await CanalesRepo.eliminarPost(p.id);
    if (hecho && mounted) {
      setState(() => _posts = _posts.where((x) => x.id != p.id).toList());
    }
  }

  Future<void> _editarCanal() async {
    final r = await Navigator.of(context).push<Canal>(MaterialPageRoute(
        builder: (_) => EditarCanalScreen(canal: _canal)));
    if (r != null && mounted) setState(() => _canal = r);
  }

  void _reaccionar(CanalPost p, String emoji) {
    final actual = _reacciones[p.id]?[_yo];
    ReaccionesRepo.alternar(_hiloReacc, p.id, _yo, emoji, emojiActual: actual);
  }

  Future<void> _abrirEnlace(String url) async {
    var u = url.trim();
    if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'https://$u';
    final uri = Uri.tryParse(u);
    if (uri != null) {
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (_) {}
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(_canal.nombre,
            style: const TextStyle(fontWeight: FontWeight.w800)),
        actions: [
          if (_soyDueno)
            IconButton(
              tooltip: 'Editar canal',
              icon: const Icon(Icons.edit_outlined),
              onPressed: _editarCanal,
            ),
        ],
      ),
      body: _cargando
          ? const CargandoPichangol()
          : AnchoTablet(
              maxWidth: 720,
              child: Column(
                children: [
                  Expanded(
                    child: RefreshIndicator(
                      onRefresh: _cargar,
                      child: ListView(
                        padding: const EdgeInsets.only(bottom: 16),
                        children: [
                          _cabecera(cs),
                          if (_posts.isEmpty)
                            Padding(
                              padding: const EdgeInsets.all(40),
                              child: Center(
                                child: Text(
                                    _soyDueno
                                        ? 'Aún no publicas nada. Escribe abajo tu primera novedad.'
                                        : 'Este canal todavía no tiene publicaciones.',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                        color: textoTenueDe(context))),
                              ),
                            )
                          else
                            for (final p in _posts) _tarjetaPost(p, cs),
                        ],
                      ),
                    ),
                  ),
                  if (_soyDueno) _composer(cs),
                ],
              ),
            ),
    );
  }

  Widget _cabecera(ColorScheme cs) {
    final foto = _canal.fotoUrl;
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
      child: Column(
        children: [
          CircleAvatar(
            radius: 46,
            backgroundColor: limaSuave,
            backgroundImage:
                foto.isNotEmpty ? CachedNetworkImageProvider(foto) : null,
            child: foto.isEmpty
                ? const Icon(Icons.campaign, color: lima, size: 42)
                : null,
          ),
          const SizedBox(height: 12),
          Text(_canal.nombre,
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 21,
                  fontWeight: FontWeight.w800,
                  color: cs.onSurface)),
          const SizedBox(height: 4),
          Text('${_canal.seguidores} seguidores',
              style: TextStyle(color: textoTenueDe(context), fontSize: 13.5)),
          if (_canal.descripcion.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(_canal.descripcion,
                textAlign: TextAlign.center,
                style: TextStyle(color: cs.onSurface, fontSize: 14.5)),
          ],
          const SizedBox(height: 14),
          if (_soyDueno)
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                  color: limaSuave, borderRadius: BorderRadius.circular(20)),
              child: const Text('Eres el administrador',
                  style: TextStyle(
                      color: lima, fontWeight: FontWeight.w700, fontSize: 13)),
            )
          else
            SizedBox(
              width: 200,
              child: _sigo
                  ? OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                          foregroundColor: textoTenueDe(context),
                          side: BorderSide(color: trazo),
                          minimumSize: const Size.fromHeight(44)),
                      onPressed: _seguirAlternar,
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text('Siguiendo'),
                    )
                  : FilledButton.icon(
                      style: FilledButton.styleFrom(
                          backgroundColor: lima,
                          minimumSize: const Size.fromHeight(44)),
                      onPressed: _seguirAlternar,
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('Seguir'),
                    ),
            ),
          const SizedBox(height: 6),
          Divider(color: trazo.withOpacity(0.4)),
        ],
      ),
    );
  }

  Widget _tarjetaPost(CanalPost p, ColorScheme cs) {
    final reacc = _reacciones[p.id] ?? const {};
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 6, 12, 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).brightness == Brightness.dark
            ? const Color(0xFF1F2C34)
            : Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 8,
              offset: const Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (p.esFoto)
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: CachedNetworkImage(
                imageUrl: p.mediaUrl,
                width: double.infinity,
                fit: BoxFit.cover,
                placeholder: (c, u) => const SizedBox(
                    height: 180,
                    child: Center(child: CircularProgressIndicator())),
                errorWidget: (c, u, e) => const SizedBox(
                    height: 100,
                    child: Icon(Icons.broken_image_outlined)),
              ),
            ),
          if (p.esVideo)
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: _PostVideo(url: p.mediaUrl),
            ),
          if (p.texto.isNotEmpty) ...[
            if (p.tieneMedia) const SizedBox(height: 8),
            _TextoConLinks(
              texto: p.texto,
              onLink: _abrirEnlace,
              style: TextStyle(fontSize: 15, color: cs.onSurface, height: 1.35),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              Text(_hace(p.creado),
                  style:
                      TextStyle(color: textoTenueDe(context), fontSize: 11.5)),
              const Spacer(),
              // Reacciones existentes (emoji + total).
              if (reacc.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Text(
                      '${reacc.values.toSet().take(3).join()} ${reacc.length}',
                      style: const TextStyle(fontSize: 13)),
                ),
              InkWell(
                onTap: () => _elegirReaccion(p),
                borderRadius: BorderRadius.circular(20),
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: Icon(
                      reacc.containsKey(_yo)
                          ? Icons.emoji_emotions
                          : Icons.emoji_emotions_outlined,
                      size: 20,
                      color: reacc.containsKey(_yo)
                          ? amarillo
                          : textoTenueDe(context)),
                ),
              ),
              if (_soyDueno)
                InkWell(
                  onTap: () => _borrarPost(p),
                  borderRadius: BorderRadius.circular(20),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Icon(Icons.delete_outline,
                        size: 20, color: textoTenueDe(context)),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  void _elegirReaccion(CanalPost p) {
    const emojis = ['👍', '❤️', '😂', '😮', '😢', '🙏', '🔥', '⚽'];
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Wrap(
            alignment: WrapAlignment.center,
            spacing: 8,
            children: [
              for (final e in emojis)
                InkWell(
                  onTap: () {
                    Navigator.pop(context);
                    _reaccionar(p, e);
                  },
                  borderRadius: BorderRadius.circular(30),
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: Text(e, style: const TextStyle(fontSize: 30)),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _composer(ColorScheme cs) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
        decoration: BoxDecoration(
          color: cs.surface,
          border: Border(top: BorderSide(color: trazo.withOpacity(0.4))),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            IconButton(
              tooltip: 'Foto',
              icon: Icon(Icons.image_outlined, color: textoTenueDe(context)),
              onPressed:
                  _publicando ? null : () => _publicarMedia(video: false),
            ),
            IconButton(
              tooltip: 'Video',
              icon: Icon(Icons.videocam_outlined, color: textoTenueDe(context)),
              onPressed:
                  _publicando ? null : () => _publicarMedia(video: true),
            ),
            Expanded(
              child: TextField(
                controller: _texto,
                minLines: 1,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  hintText: 'Escribe una novedad…',
                  isDense: true,
                ),
              ),
            ),
            const SizedBox(width: 6),
            _publicando
                ? const Padding(
                    padding: EdgeInsets.all(10),
                    child: SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2)),
                  )
                : IconButton(
                    icon: const CircleAvatar(
                        radius: 20,
                        backgroundColor: lima,
                        child: Icon(Icons.send, color: Colors.white, size: 20)),
                    onPressed: _publicarTexto,
                  ),
          ],
        ),
      ),
    );
  }

  String _hace(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'ahora';
    if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
    if (d.inHours < 24) return 'hace ${d.inHours} h';
    if (d.inDays < 7) return 'hace ${d.inDays} d';
    return '${t.day}/${t.month}/${t.year}';
  }
}

/// Video de una publicación: se reproduce en línea al tocar (silenciado por
/// defecto, con toque para pausar). Libera el controlador al salir.
class _PostVideo extends StatefulWidget {
  const _PostVideo({required this.url});
  final String url;

  @override
  State<_PostVideo> createState() => _PostVideoState();
}

class _PostVideoState extends State<_PostVideo> {
  VideoPlayerController? _c;
  bool _muted = true;

  @override
  void initState() {
    super.initState();
    final c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
    _c = c;
    c.initialize().then((_) {
      if (!mounted) return;
      c.setVolume(0);
      setState(() {});
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    if (c == null || !c.value.isInitialized) {
      return const SizedBox(
          height: 200, child: Center(child: CircularProgressIndicator()));
    }
    return GestureDetector(
      onTap: () => setState(() => c.value.isPlaying ? c.pause() : c.play()),
      child: Stack(
        alignment: Alignment.center,
        children: [
          AspectRatio(aspectRatio: c.value.aspectRatio, child: VideoPlayer(c)),
          if (!c.value.isPlaying)
            const CircleAvatar(
                radius: 26,
                backgroundColor: Colors.black45,
                child: Icon(Icons.play_arrow, color: Colors.white, size: 34)),
          Positioned(
            right: 8,
            bottom: 8,
            child: InkWell(
              onTap: () {
                setState(() {
                  _muted = !_muted;
                  c.setVolume(_muted ? 0 : 1);
                });
              },
              child: CircleAvatar(
                radius: 16,
                backgroundColor: Colors.black45,
                child: Icon(_muted ? Icons.volume_off : Icons.volume_up,
                    color: Colors.white, size: 18),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Texto con enlaces tappables (URLs → abren el navegador). Gestiona sus propios
/// TapGestureRecognizer.
class _TextoConLinks extends StatefulWidget {
  const _TextoConLinks(
      {required this.texto, required this.onLink, required this.style});
  final String texto;
  final void Function(String url) onLink;
  final TextStyle style;

  @override
  State<_TextoConLinks> createState() => _TextoConLinksState();
}

class _TextoConLinksState extends State<_TextoConLinks> {
  static final _re = RegExp(
    r'((https?:\/\/|www\.)[^\s]+|[a-zA-Z0-9.-]+\.(com|net|org|pe|app|io|co|gg|me)(\/[^\s]*)?)',
    caseSensitive: false,
  );
  final List<TapGestureRecognizer> _recs = [];

  @override
  void dispose() {
    for (final r in _recs) {
      r.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    for (final r in _recs) {
      r.dispose();
    }
    _recs.clear();
    final t = widget.texto;
    final spans = <InlineSpan>[];
    var last = 0;
    for (final m in _re.allMatches(t)) {
      if (m.start > last) spans.add(TextSpan(text: t.substring(last, m.start)));
      final url = m.group(0)!;
      final rec = TapGestureRecognizer()..onTap = () => widget.onLink(url);
      _recs.add(rec);
      spans.add(TextSpan(
        text: url,
        style: const TextStyle(
            color: lima,
            decoration: TextDecoration.underline,
            fontWeight: FontWeight.w700),
        recognizer: rec,
      ));
      last = m.end;
    }
    if (last < t.length) spans.add(TextSpan(text: t.substring(last)));
    return Text.rich(TextSpan(style: widget.style, children: spans));
  }
}
