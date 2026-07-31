import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import '../data/canales_repo.dart';
import '../data/reacciones_repo.dart';
import '../models/canal.dart';
import '../services/link_preview_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'community_manager_screen.dart';
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
    _seedDesdeCache(); // device-first: pinta lo último conocido al instante
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

  /// Device-first: pinta al instante los posts cacheados de este canal (los que
  /// ya vio en Novedades) para que abrir el canal no muestre spinner. Luego
  /// [_cargar] refresca desde Supabase en segundo plano.
  Future<void> _seedDesdeCache() async {
    final cache = await appState.leerCanalesCache();
    final posts = cache?.posts[_canal.id];
    if (posts != null && posts.isNotEmpty && mounted && _posts.isEmpty) {
      setState(() {
        _posts = posts;
        _cargando = false;
      });
    }
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
    // REGLA de la app: acción que demora → preload de marca (nunca spinner pelado).
    final ok = await conPreload(context, () => CanalesRepo.publicar(post),
        texto: 'Publicando…');
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
    Uint8List bytes;
    if (video) {
      final vf = await picker.pickVideo(
          source: ImageSource.gallery,
          maxDuration: const Duration(seconds: 60));
      if (vf == null) return;
      bytes = await vf.readAsBytes();
    } else {
      final f = await picker.pickImage(
          source: ImageSource.gallery, maxWidth: 1600, imageQuality: 85);
      if (f == null) return;
      bytes = await f.readAsBytes();
    }
    if (!mounted) return;
    // Estilo WhatsApp: primero se ve la media y se le pone descripción; recién
    // al tocar enviar se publica. Devuelve el caption (o null si canceló).
    final caption = await Navigator.of(context).push<String>(MaterialPageRoute(
        builder: (_) => _PreviewMediaCanal(bytes: bytes, video: video)));
    if (caption == null || !mounted) return;
    setState(() => _publicando = true);
    await _subirYPublicar(bytes,
        tipo: video ? 'video' : 'foto', video: video, texto: caption);
  }

  Future<void> _subirYPublicar(Uint8List bytes,
      {required String tipo,
      required bool video,
      required String texto}) async {
    final u = appState.usuario!;
    final id = 'cp_${DateTime.now().microsecondsSinceEpoch}';
    final ext = video ? 'mp4' : 'jpg';
    // REGLA de la app: acción que demora → preload de marca (nunca spinner pelado).
    final post = await conPreload<CanalPost?>(context, () async {
      final url = await CanalesRepo.subirMedia('${_canal.id}/$id.$ext', bytes,
          video: video);
      if (url == null) return null;
      // Device-first: guarda el video en un archivo local para reproducir MI
      // post al instante (sin re-bajar de la nube), como WhatsApp.
      if (video) {
        try {
          final dir = await getTemporaryDirectory();
          final f = File('${dir.path}/$id.mp4');
          await f.writeAsBytes(bytes);
          appState.recordarVideoLocal(url, f.path);
        } catch (_) {}
      }
      final p = CanalPost(
        id: id,
        canalId: _canal.id,
        autorEmail: u.email,
        autorNombre: u.nombre,
        tipo: tipo,
        texto: texto.trim(),
        mediaUrl: url,
        creado: DateTime.now(),
      );
      final ok = await CanalesRepo.publicar(p);
      return ok ? p : null;
    }, texto: 'Publicando…');
    if (!mounted) return;
    if (post == null) {
      setState(() => _publicando = false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo subir. Revisa el bucket "canales".')));
      return;
    }
    setState(() {
      _publicando = false;
      _posts = [post, ..._posts];
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

  /// Community manager con IA: la IA redacta novedades y, si el dueño las
  /// publica, vuelven aquí para mostrarse al instante en el feed.
  Future<void> _generarConIa() async {
    final publicados = await Navigator.of(context).push<List<CanalPost>>(
        MaterialPageRoute(
            builder: (_) => CommunityManagerScreen(canal: _canal)));
    if (publicados != null && publicados.isNotEmpty && mounted) {
      setState(() => _posts = [...publicados, ..._posts]);
    }
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
              tooltip: 'Generar con IA',
              icon: const Icon(Icons.auto_awesome),
              onPressed: _generarConIa,
            ),
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
                                child: Column(
                                  children: [
                                    Text(
                                        _soyDueno
                                            ? 'Aún no publicas nada. Escribe abajo tu primera novedad o deja que la IA la redacte.'
                                            : 'Este canal todavía no tiene publicaciones.',
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                            color: textoTenueDe(context))),
                                    if (_soyDueno) ...[
                                      const SizedBox(height: 16),
                                      FilledButton.icon(
                                        style: FilledButton.styleFrom(
                                            backgroundColor: lima),
                                        onPressed: _generarConIa,
                                        icon: const Icon(Icons.auto_awesome,
                                            size: 18),
                                        label: const Text('Generar con IA',
                                            style: TextStyle(
                                                fontWeight: FontWeight.w800)),
                                      ),
                                    ],
                                  ],
                                ),
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
          // Tarjeta de previsualización del enlace (Open Graph), tipo WhatsApp.
          // Solo si el post no trae ya foto/video propio (para no duplicar imagen).
          if (!p.tieneMedia && _primerEnlace(p.texto) != null) ...[
            const SizedBox(height: 8),
            _LinkPreview(
              url: _primerEnlace(p.texto)!,
              onTap: _abrirEnlace,
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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Preview del enlace mientras escribes (estilo WhatsApp): aparece
            // arriba del compositor y se publica junto con la descripción.
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: _texto,
              builder: (_, val, __) {
                final url = _primerEnlace(val.text);
                if (url == null) return const SizedBox.shrink();
                return Padding(
                  padding: const EdgeInsets.fromLTRB(6, 4, 6, 6),
                  child: _LinkPreview(url: url, onTap: _abrirEnlace),
                );
              },
            ),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                IconButton(
                  tooltip: 'Foto',
                  icon:
                      Icon(Icons.image_outlined, color: textoTenueDe(context)),
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
    _preparar();
  }

  /// Device-first: MI post → archivo local; ajeno cacheado → archivo de caché;
  /// no cacheado → streaming y baja a caché para la próxima (como WhatsApp).
  Future<void> _preparar() async {
    VideoPlayerController c;
    final local = appState.videoLocalDe(widget.url);
    if (local != null && File(local).existsSync()) {
      c = VideoPlayerController.file(File(local));
    } else {
      File? cache;
      try {
        final info = await DefaultCacheManager().getFileFromCache(widget.url);
        if (info != null && await info.file.exists()) cache = info.file;
      } catch (_) {}
      if (!mounted) return;
      if (cache != null) {
        c = VideoPlayerController.file(cache);
      } else {
        c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
        unawaited(DefaultCacheManager()
            .downloadFile(widget.url)
            .then((_) {})
            .catchError((_) {}));
      }
    }
    if (!mounted) {
      c.dispose();
      return;
    }
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

/// Previsualización de una foto/video antes de publicarlo en el canal (estilo
/// WhatsApp): se ve la media, se le pone una descripción y recién al enviar se
/// publica. Devuelve el caption (posiblemente vacío) al enviar, o null si vuelve.
class _PreviewMediaCanal extends StatefulWidget {
  const _PreviewMediaCanal({required this.bytes, required this.video});
  final Uint8List bytes;
  final bool video;

  @override
  State<_PreviewMediaCanal> createState() => _PreviewMediaCanalState();
}

class _PreviewMediaCanalState extends State<_PreviewMediaCanal> {
  final _caption = TextEditingController();

  @override
  void dispose() {
    _caption.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Text(widget.video ? 'Video' : 'Foto',
            style: const TextStyle(fontWeight: FontWeight.w700)),
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: widget.video
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        Icon(Icons.play_circle_fill,
                            color: Colors.white70, size: 72),
                        SizedBox(height: 12),
                        Text('Video listo para publicar',
                            style: TextStyle(color: Colors.white70)),
                      ],
                    )
                  : InteractiveViewer(
                      child: Image.memory(widget.bytes, fit: BoxFit.contain),
                    ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                          color: const Color(0xFF1F2C34),
                          borderRadius: BorderRadius.circular(24)),
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: TextField(
                        controller: _caption,
                        autofocus: true,
                        minLines: 1,
                        maxLines: 4,
                        style: const TextStyle(color: Colors.white),
                        cursorColor: lima,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: const InputDecoration(
                          hintText: 'Añade una descripción…',
                          hintStyle: TextStyle(color: Colors.white54),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () =>
                        Navigator.of(context).pop(_caption.text.trim()),
                    child: const CircleAvatar(
                      radius: 26,
                      backgroundColor: lima,
                      child: Icon(Icons.send, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

final _reEnlacePost = RegExp(
  r'((https?:\/\/|www\.)[^\s]+|[a-zA-Z0-9.-]+\.(com|net|org|pe|app|io|co|gg|me)(\/[^\s]*)?)',
  caseSensitive: false,
);

/// Primer enlace del texto (normalizado a https), o null si no hay.
String? _primerEnlace(String texto) {
  final m = _reEnlacePost.firstMatch(texto);
  if (m == null) return null;
  var u = m.group(0)!;
  if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'https://$u';
  return u;
}

/// Tarjeta de previsualización de un enlace (Open Graph) al estilo WhatsApp:
/// imagen + título + descripción + dominio. Carga los metadatos del backend; si
/// no hay preview, no muestra nada (colapsa).
class _LinkPreview extends StatefulWidget {
  const _LinkPreview({required this.url, required this.onTap});
  final String url;
  final void Function(String url) onTap;

  @override
  State<_LinkPreview> createState() => _LinkPreviewState();
}

class _LinkPreviewState extends State<_LinkPreview> {
  PreviewEnlace? _p;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void didUpdateWidget(_LinkPreview old) {
    super.didUpdateWidget(old);
    if (old.url != widget.url) _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final p = await LinkPreviewService.obtener(widget.url);
    if (!mounted) return;
    setState(() {
      _p = p;
      _cargando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final fondo = oscuro ? const Color(0xFF17242B) : const Color(0xFFF5F6F6);

    if (_cargando) {
      // Esqueleto discreto mientras baja los metadatos.
      return Container(
        height: 68,
        decoration: BoxDecoration(
            color: fondo, borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          children: [
            const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(width: 12),
            Expanded(
              child: Text(_primerEnlace(widget.url) ?? widget.url,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      color: textoTenueDe(context), fontSize: 12.5)),
            ),
          ],
        ),
      );
    }

    final p = _p;
    if (p == null) return const SizedBox.shrink();

    return InkWell(
      onTap: () => widget.onTap(p.url),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: trazo.withOpacity(oscuro ? 0.25 : 0.7)),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (p.imagen.isNotEmpty)
              CachedNetworkImage(
                imageUrl: p.imagen,
                width: double.infinity,
                height: 172,
                fit: BoxFit.cover,
                placeholder: (c, u) =>
                    Container(height: 172, color: Colors.black12),
                errorWidget: (c, u, e) => const SizedBox.shrink(),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (p.titulo.isNotEmpty)
                    Text(p.titulo,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            color: cs.onSurface,
                            fontWeight: FontWeight.w800,
                            fontSize: 14.5,
                            height: 1.25)),
                  if (p.descripcion.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(p.descripcion,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            color: textoTenueDe(context),
                            fontSize: 12.8,
                            height: 1.3)),
                  ],
                  if (p.dominio.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(Icons.link, size: 15, color: textoTenueDe(context)),
                        const SizedBox(width: 5),
                        Flexible(
                          child: Text(p.dominio,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  color: textoTenueDe(context), fontSize: 12.5)),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
