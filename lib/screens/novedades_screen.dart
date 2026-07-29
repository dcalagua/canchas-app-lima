import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:video_player/video_player.dart';

import '../data/canales_repo.dart';
import '../models/canal.dart';
import '../models/estado.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart' show AnchoTablet;
import 'canal_detalle_screen.dart';
import 'canales_screen.dart';
import 'estado_composer_screen.dart';
import 'estado_viewer_screen.dart';
import 'login_google_sheet.dart';

/// NOVEDADES (tipo WhatsApp "Novedades/Estados"): pantalla dedicada donde el
/// usuario sube su historia (24 h) y ve las de sus conocidos. "Mi estado" arriba
/// + "Actualizaciones recientes" abajo. Vive como sección contextual de Mensajes.
class NovedadesScreen extends StatefulWidget {
  const NovedadesScreen({super.key});

  @override
  State<NovedadesScreen> createState() => _NovedadesScreenState();
}

class _NovedadesScreenState extends State<NovedadesScreen> {
  List<Canal> _canales = const [];
  Map<String, List<CanalPost>> _postsCanal = {};

  @override
  void initState() {
    super.initState();
    appState.cargarEstados(); // refresca al entrar (best-effort)
    _cargarCanales();
  }

  /// Canales visibles en Novedades: los que sigo + los míos, ordenados por su
  /// última publicación (como el inbox de canales de WhatsApp).
  Future<void> _cargarCanales() async {
    final email = (appState.usuario?.email ?? '').toLowerCase();
    if (email.isEmpty) return;
    final todos = await CanalesRepo.todos();
    final seguidos = await CanalesRepo.seguidosDe(email);
    final visibles = todos
        .where((c) => seguidos.contains(c.id) || c.ownerEmail == email)
        .toList();
    final posts =
        await CanalesRepo.postsAgrupados(visibles.map((c) => c.id).toList());
    visibles.sort((a, b) {
      final ta = posts[a.id]?.first.creado ?? a.creado;
      final tb = posts[b.id]?.first.creado ?? b.creado;
      return tb.compareTo(ta);
    });
    if (!mounted) return;
    setState(() {
      _canales = visibles;
      _postsCanal = posts;
    });
  }

  int _noLeidos(Canal c) {
    final email = (appState.usuario?.email ?? '').toLowerCase();
    final posts = _postsCanal[c.id] ?? const [];
    final visto = appState.canalUltimaVista(c.id);
    return posts
        .where((p) =>
            p.autorEmail.toLowerCase() != email &&
            (visto == null || p.creado.isAfter(visto)))
        .length;
  }

  static final _reEnlace = RegExp(r'(https?://|www\.)', caseSensitive: false);

  String _previewPost(CanalPost p) {
    if (p.esFoto) return '📷 Foto';
    if (p.esVideo) return '🎥 Video';
    final t = p.texto.trim();
    // Igual que WhatsApp: si el post trae un enlace, se antepone 🔗.
    if (_reEnlace.hasMatch(t)) return '🔗 $t';
    return t;
  }

  /// Hora al estilo WhatsApp para la lista de canales: hoy = hora (12:33 a. m.),
  /// ayer = "Ayer", esta semana = día abreviado, más viejo = fecha d/m/aaaa.
  String _horaCanal(DateTime t) {
    final now = DateTime.now();
    final dias = DateTime(now.year, now.month, now.day)
        .difference(DateTime(t.year, t.month, t.day))
        .inDays;
    if (dias <= 0) {
      final ampm = t.hour < 12 ? 'a. m.' : 'p. m.';
      var h12 = t.hour % 12;
      if (h12 == 0) h12 = 12;
      return '$h12:${t.minute.toString().padLeft(2, '0')} $ampm';
    }
    if (dias == 1) return 'Ayer';
    if (dias < 7) {
      const d = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
      return d[t.weekday - 1];
    }
    return '${t.day}/${t.month}/${t.year}';
  }

  Future<void> _abrirCanal(Canal c) async {
    await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => CanalDetalleScreen(canal: c)));
    _cargarCanales();
  }

  Widget _filaCanal(Canal c) {
    final posts = _postsCanal[c.id] ?? const [];
    final ultima = posts.isNotEmpty ? posts.first : null;
    final noLeidos = _noLeidos(c);
    final foto = c.fotoUrl;
    return ListTile(
      onTap: () => _abrirCanal(c),
      leading: CircleAvatar(
        radius: 26,
        backgroundColor: limaSuave,
        backgroundImage:
            foto.isNotEmpty ? CachedNetworkImageProvider(foto) : null,
        child: foto.isEmpty ? const Icon(Icons.campaign, color: lima) : null,
      ),
      title: Text(c.nombre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(
          ultima != null
              ? _previewPost(ultima)
              : 'Se creó el canal "${c.nombre}"',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(color: textoTenueDe(context))),
      trailing: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(ultima != null ? _horaCanal(ultima.creado) : '',
              style: TextStyle(
                  fontSize: 11.5,
                  fontWeight: noLeidos > 0 ? FontWeight.w700 : FontWeight.w400,
                  color: noLeidos > 0 ? lima : textoTenueDe(context))),
          const SizedBox(height: 5),
          if (noLeidos > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                  color: lima, borderRadius: BorderRadius.circular(12)),
              constraints: const BoxConstraints(minWidth: 20),
              child: Text(noLeidos > 999 ? '+999' : '$noLeidos',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11.5,
                      fontWeight: FontWeight.w800)),
            )
          else
            const SizedBox(height: 18),
        ],
      ),
    );
  }

  String _hace(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'ahora';
    if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
    if (d.inHours < 24) return 'hace ${d.inHours} h';
    return 'hace ${d.inDays} d';
  }

  Future<void> _agregar() async {
    final r = await showModalBottomSheet<String>(
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
            const SizedBox(height: 8),
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 8, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Añadir a mi estado',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.text_fields, color: teal)),
              title: const Text('Escribir'),
              onTap: () => Navigator.pop(context, 'texto'),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.photo_library_outlined, color: teal)),
              title: const Text('Galería'),
              onTap: () => Navigator.pop(context, 'galeria'),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.photo_camera_outlined, color: teal)),
              title: const Text('Cámara'),
              onTap: () => Navigator.pop(context, 'camara'),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.videocam_outlined, color: teal)),
              title: const Text('Video'),
              subtitle: const Text('Hasta 30 segundos'),
              onTap: () => Navigator.pop(context, 'video'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (r == null || !mounted) return;
    if (r == 'texto') {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const EstadoComposerScreen(),
          fullscreenDialog: true));
      if (mounted) setState(() {});
      return;
    }
    if (r == 'video') {
      final XFile? vf = await ImagePicker().pickVideo(
          source: ImageSource.gallery,
          maxDuration: const Duration(seconds: 30));
      if (vf == null || !mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => EstadoVideoComposerScreen(file: vf),
          fullscreenDialog: true));
      if (mounted) setState(() {});
      return;
    }
    final XFile? f = await ImagePicker().pickImage(
        source: r == 'camara' ? ImageSource.camera : ImageSource.gallery,
        maxWidth: 1600,
        imageQuality: 82);
    if (f == null || !mounted) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoFotoComposerScreen(bytes: bytes),
        fullscreenDialog: true));
    if (mounted) setState(() {});
  }

  Future<void> _verDe(String email) async {
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => EstadoViewerScreen(autorEmail: email)));
    if (mounted) setState(() {});
  }

  Future<void> _tocarMiEstado() async {
    if (appState.misEstados.isEmpty) {
      await _agregar();
      return;
    }
    await _verDe(appState.usuario?.email ?? '');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Novedades',
            style: TextStyle(fontWeight: FontWeight.w800)),
        centerTitle: false,
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (!appState.logueado) {
            return _Aviso(
              texto: 'Inicia sesión para ver y publicar novedades.',
              accion: FilledButton.icon(
                style: FilledButton.styleFrom(backgroundColor: lima),
                onPressed: () async {
                  if (await LoginGoogleSheet.mostrar(context,
                      motivo: 'ver novedades')) {
                    setState(() {});
                  }
                },
                icon: const Icon(Icons.login),
                label: const Text('Iniciar sesión'),
              ),
            );
          }
          final autores = appState.autoresConEstado();
          final misEstados = appState.misEstados;
          final tengo = misEstados.isNotEmpty;
          return AnchoTablet(
            child: RefreshIndicator(
              onRefresh: () => appState.cargarEstados(),
              child: ListView(
                children: [
                  const SizedBox(height: 6),
                  // "Mi estado"
                  ListTile(
                    onTap: _tocarMiEstado,
                    leading: _AnilloAvatar(
                      email: appState.usuario?.email ?? '',
                      fotoUrl: appState.usuario?.fotoUrl,
                      nombre: appState.usuario?.nombre ?? '',
                      preview: tengo ? misEstados.last : null,
                      aro: tengo ? 1 : 0, // aro lima: tienes historia activa
                      mostrarMas: true,
                    ),
                    title: const Text('Mi estado',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(tengo
                        ? _hace(misEstados.last.creadoEn)
                        : 'Toca para añadir una novedad'),
                    trailing: tengo
                        ? IconButton(
                            icon: const Icon(Icons.add_circle_outline,
                                color: teal),
                            onPressed: _agregar,
                          )
                        : null,
                  ),
                  Divider(height: 8, thickness: 8, color: trazo.withOpacity(0.25)),
                  // ── Canales (difusión tipo WhatsApp Channels) ──────────────
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 8, 2),
                    child: Row(
                      children: [
                        const Text('Canales',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 17)),
                        const Spacer(),
                        TextButton(
                          onPressed: () async {
                            await Navigator.of(context).push(MaterialPageRoute(
                                builder: (_) => const CanalesScreen()));
                            _cargarCanales();
                          },
                          style: TextButton.styleFrom(
                              backgroundColor: Theme.of(context).brightness ==
                                      Brightness.dark
                                  ? const Color(0xFF2A3942)
                                  : const Color(0xFFEDEDED),
                              foregroundColor:
                                  Theme.of(context).colorScheme.onSurface,
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(20))),
                          child: const Text('Explorar'),
                        ),
                      ],
                    ),
                  ),
                  if (_canales.isEmpty)
                    ListTile(
                      onTap: () async {
                        await Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => const CanalesScreen()));
                        _cargarCanales();
                      },
                      leading: const CircleAvatar(
                          backgroundColor: limaSuave,
                          child: Icon(Icons.campaign, color: lima)),
                      title: const Text('Sigue canales',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: const Text(
                          'Mantente al día o crea el tuyo para difundir'),
                      trailing: const Icon(Icons.chevron_right),
                    )
                  else
                    for (final c in _canales) _filaCanal(c),
                  Divider(height: 8, thickness: 8, color: trazo.withOpacity(0.25)),
                  if (autores.isNotEmpty) ...[
                    const Padding(
                      padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
                      child: Text('Actualizaciones recientes',
                          style: TextStyle(
                              color: textoTenue,
                              fontWeight: FontWeight.w700,
                              fontSize: 13)),
                    ),
                    for (final e in autores)
                      ListTile(
                        onTap: () => _verDe(e),
                        leading: _AnilloAvatar(
                          email: e,
                          fotoUrl: appState.fotoDe(e),
                          nombre: appState.nombreMostrableDe(e) ?? e,
                          preview: appState.estadosDe(e).last,
                          aro: appState.autorTieneNoVisto(e) ? 1 : 2,
                        ),
                        title: Text(
                            appState.nombreMostrableDe(e) ?? e.split('@').first,
                            style:
                                const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text(_hace(appState.estadosDe(e).last.creadoEn)),
                      ),
                  ] else
                    const Padding(
                      padding: EdgeInsets.fromLTRB(24, 40, 24, 24),
                      child: Text(
                        'Aún no hay novedades de tus contactos. Cuando alguien '
                        'que conoces publique una historia, aparecerá aquí.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: textoTenue),
                      ),
                    ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          );
        },
      ),
      floatingActionButton: appState.logueado
          ? FloatingActionButton(
              backgroundColor: lima,
              onPressed: _agregar,
              child: const Icon(Icons.camera_alt, color: Colors.white),
            )
          : null,
    );
  }
}

/// Avatar con aro de estado (0 sin aro, 1 lima=sin ver, 2 gris=visto) y badge +
/// opcional (Mi estado). El círculo muestra un PREVIEW de la historia (la foto,
/// o el color de fondo si es de texto), tipo WhatsApp; si no hay historia, cae a
/// la foto de perfil / inicial.
class _AnilloAvatar extends StatelessWidget {
  const _AnilloAvatar({
    required this.email,
    required this.fotoUrl,
    required this.nombre,
    required this.aro,
    this.preview,
    this.mostrarMas = false,
  });
  final String email;
  final String? fotoUrl;
  final String nombre;
  final int aro;
  final Estado? preview; // última historia, para la miniatura
  final bool mostrarMas;

  @override
  Widget build(BuildContext context) {
    final ini =
        (nombre.trim().isNotEmpty ? nombre.trim()[0] : '?').toUpperCase();
    final ring = aro == 1
        ? lima
        : aro == 2
            ? trazo
            : Colors.transparent;

    // Contenido del círculo: miniatura de la historia si la hay.
    Widget circulo;
    final e = preview;
    if (e != null && e.esVideo) {
      // Historia de video: primer fotograma del clip como preview (WhatsApp).
      circulo = e.fotoUrl.isNotEmpty
          ? _VideoThumb(url: e.fotoUrl)
          : const CircleAvatar(
              radius: 24,
              backgroundColor: Colors.black54,
              child: Icon(Icons.videocam, color: Colors.white, size: 22),
            );
    } else if (e != null && e.esFoto && e.fotoUrl.isNotEmpty) {
      circulo = CircleAvatar(radius: 24, backgroundImage: NetworkImage(e.fotoUrl));
    } else if (e != null && !e.esFoto) {
      // Historia de texto: círculo del color de fondo con un fragmento del texto.
      circulo = CircleAvatar(
        radius: 24,
        backgroundColor: Color(e.bg),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Text(
            e.texto,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(
                color: Colors.white, fontSize: 8, fontWeight: FontWeight.w700),
          ),
        ),
      );
    } else {
      circulo = CircleAvatar(
        radius: 24,
        backgroundColor: limaSuave,
        backgroundImage:
            (fotoUrl != null && fotoUrl!.isNotEmpty) ? NetworkImage(fotoUrl!) : null,
        child: (fotoUrl == null || fotoUrl!.isEmpty)
            ? Text(ini,
                style: const TextStyle(
                    color: teal, fontWeight: FontWeight.bold, fontSize: 18))
            : null,
      );
    }

    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(width: 2.2, color: ring),
          ),
          child: circulo,
        ),
        if (mostrarMas)
          Positioned(
            right: -1,
            bottom: -1,
            child: Container(
              decoration: BoxDecoration(
                color: lima,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 2),
              ),
              child: const Icon(Icons.add, size: 15, color: Colors.white),
            ),
          ),
      ],
    );
  }
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.texto, this.accion});
  final String texto;
  final Widget? accion;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
              if (accion != null) ...[
                const SizedBox(height: 16),
                accion!,
              ],
            ],
          ),
        ),
      );
}

/// Preview circular del PRIMER FOTOGRAMA de un video (para el aro de Novedades).
/// Usa video_player (ya presente): carga el clip, lo silencia y salta a ~100 ms
/// para mostrar un fotograma con contenido (evita el negro del frame 0). Mientras
/// carga, muestra un círculo con ícono de cámara. Libera el controlador al salir.
class _VideoThumb extends StatefulWidget {
  const _VideoThumb({required this.url, this.radio = 24});
  final String url;
  final double radio;

  @override
  State<_VideoThumb> createState() => _VideoThumbState();
}

class _VideoThumbState extends State<_VideoThumb> {
  VideoPlayerController? _c;

  @override
  void initState() {
    super.initState();
    final c = VideoPlayerController.networkUrl(Uri.parse(widget.url));
    _c = c;
    c.initialize().then((_) async {
      if (!mounted) return;
      await c.setVolume(0);
      await c.seekTo(const Duration(milliseconds: 100));
      if (mounted) setState(() {});
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.radio * 2;
    final c = _c;
    if (c == null || !c.value.isInitialized) {
      return CircleAvatar(
        radius: widget.radio,
        backgroundColor: Colors.black54,
        child: Icon(Icons.videocam, color: Colors.white, size: widget.radio),
      );
    }
    return ClipOval(
      child: SizedBox(
        width: d,
        height: d,
        child: FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: c.value.size.width,
            height: c.value.size.height,
            child: VideoPlayer(c),
          ),
        ),
      ),
    );
  }
}
