import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import '../models/estado.dart';
import '../services/historia_share.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import 'chat_screen.dart';

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
  static const _maxVideo = Duration(seconds: 30); // tope de exhibición del clip
  late final AnimationController _ctrl;
  final AudioPlayer _audio = AudioPlayer();
  final TextEditingController _respuesta = TextEditingController();
  final FocusNode _focoResp = FocusNode();
  late List<Estado> _items;
  int _i = 0;
  VideoPlayerController? _video; // solo cuando el estado actual es video

  bool get _esMio =>
      widget.autorEmail.toLowerCase() ==
      (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _items = appState.estadosDe(widget.autorEmail);
    // Al escribir una respuesta, pausa el auto-avance (y reanuda al salir).
    _focoResp.addListener(() {
      if (_focoResp.hasFocus) {
        _pausar();
      } else {
        _reanudar();
      }
    });
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
    _video?.dispose();
    _respuesta.dispose();
    _focoResp.dispose();
    _ctrl.dispose();
    super.dispose();
  }

  /// Envía una respuesta (texto o emoji) a la historia como mensaje directo,
  /// CITANDO la historia (miniatura si es foto) para que se vea como WhatsApp.
  Future<void> _enviarResp(String txt) async {
    final t = txt.trim();
    if (t.isEmpty) return;
    _respuesta.clear();
    _focoResp.unfocus();
    final e = _items[_i];
    final autorNombre =
        appState.nombreMostrableDe(widget.autorEmail) ?? e.autorNombre;
    final String respTexto;
    if (e.esFoto) {
      respTexto = e.texto.isNotEmpty ? e.texto : '📷 Foto';
    } else if (e.esVideo) {
      respTexto = e.texto.isNotEmpty ? e.texto : '🎥 Video';
    } else {
      respTexto = e.texto;
    }
    final ok = await appState.enviarMensajeDirecto(
      widget.autorEmail,
      t,
      respAutor: autorNombre,
      respTexto: respTexto,
      respMedia: e.esFoto ? e.fotoUrl : '', // el video no tiene miniatura
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(ok ? 'Respuesta enviada' : 'No se pudo enviar'),
      duration: const Duration(milliseconds: 1200),
    ));
    _reanudar();
  }

  Future<void> _accionMenu(String v) async {
    switch (v) {
      case 'vistas':
        _verVistas();
        break;
      case 'compartir':
        await _compartir();
        break;
      case 'eliminar':
        await _eliminarActual();
        break;
      case 'mensaje':
        _pausar();
        await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => ChatScreen(
                  academiaId: '',
                  cuentaEmail: widget.autorEmail,
                  titulo: appState.nombreMostrableDe(widget.autorEmail) ??
                      _items[_i].autorNombre,
                  soyProfe: false,
                  tipo: 'directo',
                )));
        if (mounted) _reanudar();
        break;
      case 'silenciar':
        await appState.alternarOcultarEstados(widget.autorEmail);
        if (mounted) Navigator.of(context).maybePop();
        break;
      case 'reportar':
        _pausar();
        await avisarPichangol(context,
            titulo: 'Gracias',
            mensaje:
                'Recibimos tu reporte de esta historia. Nuestro equipo la revisará.',
            icono: Icons.flag_outlined);
        if (mounted) _reanudar();
        break;
    }
  }

  /// Prepara el controlador del video device-first: (1) MI historia → archivo
  /// local; (2) ajena ya cacheada → archivo de caché; (3) no cacheada → streaming
  /// y baja a caché para la próxima. Guarda contra cambios de historia (idx).
  Future<void> _prepararVideo(Estado e, int idx) async {
    VideoPlayerController vc;
    final local = appState.videoLocalDe(e.fotoUrl);
    if (local != null && File(local).existsSync()) {
      vc = VideoPlayerController.file(File(local));
    } else {
      File? cache;
      try {
        final info = await DefaultCacheManager().getFileFromCache(e.fotoUrl);
        if (info != null && await info.file.exists()) cache = info.file;
      } catch (_) {}
      if (!mounted || _i != idx) return; // cambió de historia mientras tanto
      if (cache != null) {
        vc = VideoPlayerController.file(cache);
      } else {
        vc = VideoPlayerController.networkUrl(Uri.parse(e.fotoUrl));
        // Baja a caché en segundo plano para verla al instante la próxima vez.
        unawaited(DefaultCacheManager()
            .downloadFile(e.fotoUrl)
            .then((_) {})
            .catchError((_) {}));
      }
    }
    if (!mounted || _i != idx) {
      vc.dispose();
      return;
    }
    _video?.dispose();
    _video = vc;
    vc.initialize().then((_) {
      if (!mounted || _video != vc) return;
      var dur = vc.value.duration;
      if (dur > _maxVideo) dur = _maxVideo;
      if (dur.inMilliseconds < 500) dur = const Duration(seconds: 5);
      _ctrl.duration = dur;
      vc
        ..setLooping(false)
        ..play();
      _ctrl
        ..reset()
        ..forward();
      setState(() {});
    }).catchError((_) {
      // Si el video no carga, no bloquear la historia: pasa al siguiente.
      if (mounted && _video == vc) _ctrl.duration = _duracion;
    });
  }

  void _mostrar(int idx) {
    if (idx < 0 || idx >= _items.length) return;
    setState(() => _i = idx);
    final e = _items[idx];
    appState.marcarEstadoVisto(e.id);
    _audio.stop();
    // Al cambiar de estado, suelta cualquier video del estado anterior.
    _video?.dispose();
    _video = null;

    if (e.esVideo) {
      // VIDEO: la barra la maneja la duración real del clip (tope 30 s). No se
      // reproduce la música (el video trae su propio audio). Device-first: MI
      // historia se reproduce desde el archivo LOCAL; las ajenas, desde la caché
      // en disco (o streaming la 1ª vez, bajando a caché para la próxima).
      _ctrl
        ..reset()
        ..stop();
      _prepararVideo(e, idx);
      return;
    }

    // FOTO / TEXTO: música opcional (más tiempo de exhibición si hay canción).
    if (e.tieneMusica) {
      _ctrl.duration = _duracionMusica;
      try {
        _audio.play(UrlSource(e.musicaPreview)).then((_) {
          // Arranca desde el fragmento elegido por el autor (recorte).
          if (e.musicaInicioMs > 0) {
            _audio.seek(Duration(milliseconds: e.musicaInicioMs));
          }
        });
      } catch (_) {}
    } else {
      _ctrl.duration = _duracion;
    }
    _ctrl
      ..reset()
      ..forward();
  }

  /// Abre un enlace de una historia (texto o pie) en el navegador. Pausa el
  /// auto-avance mientras el usuario sale y lo reanuda al volver.
  Future<void> _abrirEnlace(String url) async {
    _pausar();
    var u = url.trim();
    if (!u.startsWith('http://') && !u.startsWith('https://')) u = 'https://$u';
    final uri = Uri.tryParse(u);
    if (uri != null) {
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (_) {}
    }
    if (mounted) _reanudar();
  }

  bool _compartiendo = false;

  /// Comparte la historia actual a la hoja del sistema (Instagram, Facebook,
  /// WhatsApp…). Foto/video: descarga el archivo y lo comparte; texto: comparte
  /// el texto. Pausa el auto-avance mientras se abre la hoja.
  /// Descarga la foto/video de la historia a un archivo temporal; devuelve la
  /// ruta local (o null si falla). Reutilizado por compartir general y directo.
  Future<String?> _guardarMediaTemp(Estado e) async {
    if (!e.esFoto && !e.esVideo) return null;
    final resp = await http.get(Uri.parse(e.fotoUrl));
    if (resp.statusCode != 200) return null;
    final dir = await getTemporaryDirectory();
    final ext = e.esVideo ? 'mp4' : 'jpg';
    final ruta = '${dir.path}/pichangol_historia_'
        '${DateTime.now().millisecondsSinceEpoch}.$ext';
    await File(ruta).writeAsBytes(resp.bodyBytes);
    return ruta;
  }

  /// Compartir GENERAL (hoja del sistema): IG, FB, WhatsApp, etc.
  Future<void> _compartir() async {
    if (_compartiendo) return;
    _pausar();
    final e = _items[_i];
    setState(() => _compartiendo = true);
    try {
      if (e.esFoto || e.esVideo) {
        final ruta = await _guardarMediaTemp(e);
        if (ruta == null) throw Exception('descarga');
        await Share.shareXFiles(
          [XFile(ruta, mimeType: e.esVideo ? 'video/mp4' : 'image/jpeg')],
          text: e.texto.isNotEmpty ? e.texto : null,
        );
      } else {
        await Share.share(
          e.texto.isNotEmpty ? e.texto : 'Mira mi novedad en Pichangol',
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo compartir. Inténtalo de nuevo.')));
      }
    } finally {
      if (mounted) setState(() => _compartiendo = false);
      if (mounted) _reanudar();
    }
  }

  /// Compartir DIRECTO a la Historia de [red] ('instagram'|'facebook'). Si no
  /// hay media, no está configurado el App ID, o la app no está instalada, cae a
  /// la hoja de compartir general (con el archivo listo).
  Future<void> _compartirRed(String red) async {
    if (_compartiendo) return;
    final e = _items[_i];
    if ((!e.esFoto && !e.esVideo) || !HistoriaShare.configurado) {
      await _compartir();
      return;
    }
    _pausar();
    setState(() => _compartiendo = true);
    try {
      final ruta = await _guardarMediaTemp(e);
      if (ruta == null) throw Exception('descarga');
      final ok = red == 'instagram'
          ? await HistoriaShare.instagram(ruta, video: e.esVideo)
          : await HistoriaShare.facebook(ruta, video: e.esVideo);
      if (!ok) {
        // App no instalada / falló → hoja de compartir con el archivo.
        await Share.shareXFiles(
          [XFile(ruta, mimeType: e.esVideo ? 'video/mp4' : 'image/jpeg')],
          text: e.texto.isNotEmpty ? e.texto : null,
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo compartir. Inténtalo de nuevo.')));
      }
    } finally {
      if (mounted) setState(() => _compartiendo = false);
      if (mounted) _reanudar();
    }
  }

  /// Abre la canción: el enlace EXACTO en Apple Music si lo hay; si no, la
  /// búsqueda en Spotify (fallback).
  Future<void> _abrirCancion(Estado e) async {
    _pausar();
    Uri? url;
    if (e.musicaTrackUrl.isNotEmpty) {
      url = Uri.tryParse(e.musicaTrackUrl);
    }
    url ??= Uri.parse('https://open.spotify.com/search/'
        '${Uri.encodeComponent('${e.musicaTitulo} ${e.musicaArtista}'.trim())}');
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
    _video?.pause();
  }

  void _reanudar() {
    if (!_ctrl.isAnimating) _ctrl.forward();
    if (_items.isNotEmpty && _items[_i].tieneMusica && !_items[_i].esVideo) {
      _audio.resume();
    }
    _video?.play();
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
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF202C33)
          : Colors.white,
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
      body: Column(
        children: [
          Expanded(
            child: GestureDetector(
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
              child: e.esVideo
                  ? Center(
                      child: (_video != null && _video!.value.isInitialized)
                          ? AspectRatio(
                              aspectRatio: _video!.value.aspectRatio,
                              child: VideoPlayer(_video!),
                            )
                          : const CircularProgressIndicator(
                              color: Colors.white),
                    )
                  : e.esFoto
                      ? Center(
                          child: CachedNetworkImage(
                            imageUrl: e.fotoUrl,
                            fit: BoxFit.contain,
                            placeholder: (c, u) => const Center(
                                child: CircularProgressIndicator(
                                    color: Colors.white)),
                            errorWidget: (c, u, e) => const Center(
                                child: Icon(Icons.broken_image_outlined,
                                    color: Colors.white54, size: 48)),
                          ),
                        )
                      : Center(
                          child: Padding(
                            padding: const EdgeInsets.all(32),
                            child: _TextoConLinks(
                              texto: e.texto,
                              onLink: _abrirEnlace,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 26,
                                fontWeight: FontWeight.w700,
                                height: 1.3,
                              ),
                              align: TextAlign.center,
                            ),
                          ),
                        ),
            ),
            // Pie de foto/video (con links tappables)
            if ((e.esFoto || e.esVideo) && e.texto.isNotEmpty)
              Positioned(
                left: 0,
                right: 0,
                bottom: _esMio ? 84 : 32,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                  child: _TextoConLinks(
                    texto: e.texto,
                    onLink: _abrirEnlace,
                    align: TextAlign.center,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            // Botones dedicados de compartir (tipo WhatsApp): Facebook + Instagram
            // abajo a la derecha, solo en MIS historias.
            if (_esMio)
              Positioned(
                right: 14,
                bottom: 26,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _BotonRed(
                      icono: FontAwesomeIcons.facebookF,
                      color: const Color(0xFF1877F2),
                      tooltip: 'Compartir en Facebook',
                      onTap: () => _compartirRed('facebook'),
                    ),
                    const SizedBox(width: 12),
                    _BotonRed(
                      icono: FontAwesomeIcons.instagram,
                      color: const Color(0xFFE1306C),
                      tooltip: 'Compartir en Instagram',
                      onTap: () => _compartirRed('instagram'),
                    ),
                  ],
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
                        // Compartir la historia (Instagram, Facebook, WhatsApp…).
                        IconButton(
                          tooltip: 'Compartir',
                          icon: _compartiendo
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2, color: Colors.white))
                              : const Icon(Icons.ios_share,
                                  color: Colors.white),
                          onPressed: _compartiendo ? null : _compartir,
                        ),
                        // Menú ⋮ SIEMPRE presente (tal cual WhatsApp): en MI
                        // estado da Ver quién lo vio / Eliminar; en el ajeno da
                        // Mensaje / Silenciar / Reportar.
                        PopupMenuButton<String>(
                          icon: const Icon(Icons.more_vert,
                              color: Colors.white),
                          onOpened: _pausar,
                          onCanceled: _reanudar,
                          onSelected: _accionMenu,
                          itemBuilder: (_) => _esMio
                              ? const [
                                  PopupMenuItem(
                                      value: 'vistas',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: Icon(
                                              Icons.remove_red_eye_outlined),
                                          title: Text('Ver quién lo vio'))),
                                  PopupMenuItem(
                                      value: 'compartir',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: Icon(Icons.ios_share),
                                          title: Text('Compartir'))),
                                  PopupMenuItem(
                                      value: 'eliminar',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: Icon(Icons.delete_outline),
                                          title: Text('Eliminar'))),
                                ]
                              : [
                                  const PopupMenuItem(
                                      value: 'mensaje',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading:
                                              Icon(Icons.chat_bubble_outline),
                                          title: Text('Mensaje'))),
                                  PopupMenuItem(
                                      value: 'silenciar',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: const Icon(
                                              Icons.notifications_off_outlined),
                                          title: Text(appState.estadosOcultosDe(
                                                  widget.autorEmail)
                                              ? 'Mostrar historias'
                                              : 'Silenciar historias'))),
                                  const PopupMenuItem(
                                      value: 'reportar',
                                      child: ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: Icon(Icons.flag_outlined),
                                          title: Text('Reportar'))),
                                ],
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
                            estado: e, onAbrir: () => _abrirCancion(e)),
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
          ),
          if (!_esMio && appState.logueado) _barraResponder(),
        ],
      ),
    );
  }

  /// Barra inferior tipo WhatsApp para responder la historia: reacciones rápidas
  /// + campo de texto + corazón. Envía un mensaje directo al autor.
  Widget _barraResponder() {
    return SafeArea(
      top: false,
      child: Container(
        color: Colors.black.withOpacity(0.85),
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                for (final em in const ['😍', '😂', '😮', '👏', '🔥', '⚽'])
                  InkWell(
                    onTap: () => _enviarResp(em),
                    borderRadius: BorderRadius.circular(20),
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: Text(em, style: const TextStyle(fontSize: 26)),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white54),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: TextField(
                      controller: _respuesta,
                      focusNode: _focoResp,
                      style: const TextStyle(color: Colors.white),
                      cursorColor: Colors.white,
                      textInputAction: TextInputAction.send,
                      onSubmitted: _enviarResp,
                      decoration: const InputDecoration(
                        filled: false,
                        border: InputBorder.none,
                        hintText: 'Responder…',
                        hintStyle: TextStyle(color: Colors.white70),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.favorite, color: Colors.white),
                  onPressed: () => _enviarResp('❤️'),
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: Colors.white),
                  onPressed: () => _enviarResp(_respuesta.text),
                ),
              ],
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

/// Sticker de música en el visor: carátula + ecualizador animado + título/artista
/// + botón para abrir la canción (Apple Music exacto o Spotify).
class _MusicaSticker extends StatelessWidget {
  const _MusicaSticker({required this.estado, required this.onAbrir});
  final Estado estado;
  final VoidCallback onAbrir;

  @override
  Widget build(BuildContext context) {
    final apple = estado.musicaTrackUrl.isNotEmpty;
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
          const SizedBox(width: 7),
          const _Ecualizador(),
          const SizedBox(width: 7),
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
            onTap: onAbrir,
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(apple ? Icons.music_note : Icons.play_circle_fill,
                  color: apple
                      ? const Color(0xFFFC3C44)
                      : const Color(0xFF1DB954),
                  size: 18),
              const SizedBox(width: 3),
              Text(apple ? 'Apple Music' : 'Spotify',
                  style: const TextStyle(
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

/// Ecualizador animado (3 barritas) que da la sensación de "sonando".
class _Ecualizador extends StatefulWidget {
  const _Ecualizador();
  @override
  State<_Ecualizador> createState() => _EcualizadorState();
}

class _EcualizadorState extends State<_Ecualizador>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  @override
  void initState() {
    super.initState();
    _c = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 700))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 16,
      height: 16,
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, __) {
          double alto(double fase) {
            final v = (0.4 + 0.6 * ((_c.value + fase) % 1.0));
            return 4 + v * 10;
          }

          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final f in [0.0, 0.33, 0.66])
                Container(
                    width: 3,
                    height: alto(f),
                    decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(2))),
            ],
          );
        },
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

/// Botón circular oscuro (tipo WhatsApp) con el ícono de una red, para compartir
/// la historia. Abre la hoja del sistema con la foto/video (IG/FB de primeros).
class _BotonRed extends StatelessWidget {
  const _BotonRed(
      {required this.icono,
      required this.color,
      required this.tooltip,
      required this.onTap});
  final IconData icono;
  final Color color;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.black.withOpacity(0.55),
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(13),
            child: FaIcon(icono, color: color, size: 22),
          ),
        ),
      ),
    );
  }
}

/// Texto de una historia con los ENLACES detectados como tappables (tipo
/// WhatsApp: "compartir link"). Toca un link → [onLink] lo abre. Gestiona sus
/// propios TapGestureRecognizer (los libera al desmontar).
class _TextoConLinks extends StatefulWidget {
  const _TextoConLinks({
    required this.texto,
    required this.onLink,
    required this.style,
    this.align = TextAlign.start,
  });
  final String texto;
  final void Function(String url) onLink;
  final TextStyle style;
  final TextAlign align;

  @override
  State<_TextoConLinks> createState() => _TextoConLinksState();
}

class _TextoConLinksState extends State<_TextoConLinks> {
  // Detecta http(s)://..., www.algo... y dominios sueltos (algo.com/...).
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
    final spans = <InlineSpan>[];
    final t = widget.texto;
    var last = 0;
    for (final m in _re.allMatches(t)) {
      if (m.start > last) {
        spans.add(TextSpan(text: t.substring(last, m.start)));
      }
      final url = m.group(0)!;
      final rec = TapGestureRecognizer()..onTap = () => widget.onLink(url);
      _recs.add(rec);
      spans.add(TextSpan(
        text: url,
        style: const TextStyle(
            decoration: TextDecoration.underline,
            fontWeight: FontWeight.w800),
        recognizer: rec,
      ));
      last = m.end;
    }
    if (last < t.length) spans.add(TextSpan(text: t.substring(last)));
    return Text.rich(
      TextSpan(style: widget.style, children: spans),
      textAlign: widget.align,
    );
  }
}
