import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

// ── Paleta estilo WhatsApp (theme-aware) ─────────────────────────────────────
// Se calcula según el brillo del tema. Fondo del chat, burbujas y barra imitan
// la app de WhatsApp sobre la marca Pichangol (verde bosque/lima).
class _WA {
  final bool dark;
  const _WA(this.dark);

  Color get appBar => dark ? const Color(0xFF1F2C34) : const Color(0xFF008069);
  Color get fondo => dark ? const Color(0xFF0B141A) : const Color(0xFFECE5DD);
  Color get burbujaMia => dark ? const Color(0xFF005C4B) : const Color(0xFFD9FDD3);
  Color get burbujaOtro => dark ? const Color(0xFF202C33) : Colors.white;
  Color get textoMio => dark ? const Color(0xFFE9EDEF) : const Color(0xFF111B21);
  Color get textoOtro => dark ? const Color(0xFFE9EDEF) : const Color(0xFF111B21);
  Color get hora => dark ? Colors.white54 : Colors.black38;
  Color get barra => dark ? const Color(0xFF111B21) : const Color(0xFFF0F2F5);
  Color get pill => dark ? const Color(0xFF1F2C34) : Colors.white;
  Color get pillTexto => dark ? const Color(0xFFE9EDEF) : const Color(0xFF111B21);
  Color get send => const Color(0xFF00A884);
}

/// Conversación 1:1 profe ↔ alumno de una academia (Etapa A: Realtime, sin
/// push). Se usa igual desde el lado del profe ([soyProfe] = true) que del
/// alumno ([soyProfe] = false); [cuentaEmail] identifica el lado alumno.
class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.academiaId,
    required this.cuentaEmail,
    required this.titulo,
    required this.soyProfe,
    this.tipo = 'academia',
    this.refId = '',
    this.embebido = false,
    this.fotoInicial,
  });

  final String academiaId;
  final String cuentaEmail; // otra parte en 1:1 (alumno/jugador)
  final String titulo; // nombre de la contraparte (o de la academia)
  final bool soyProfe; // true = soy el anfitrión (profe/dueño)
  final String tipo; // 'academia' | 'cancha' | 'grupo'
  final String refId; // canchaId/grupoId cuando no es academia
  // Cuando se muestra dentro de un panel (master-detail en tablet), no lleva
  // flecha de "volver" (no hay ruta que cerrar: el menú lateral sigue visible).
  final bool embebido;

  /// Si se pasa (p. ej. desde la cámara del inbox), al abrir el chat se envía
  /// esta foto automáticamente.
  final Uint8List? fotoInicial;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _texto = TextEditingController();
  final _scroll = ScrollController();
  final _focus = FocusNode();
  bool _enviando = false;
  bool _emojis = false; // panel de emojis abierto
  String _ultimoVisto = ''; // id del último mensaje ya procesado

  String get _refId =>
      widget.refId.isNotEmpty ? widget.refId : widget.academiaId;

  String get _hilo {
    switch (widget.tipo) {
      case 'cancha':
        return Mensaje.hiloCancha(_refId, widget.cuentaEmail);
      case 'grupo':
        return Mensaje.hiloGrupo(_refId);
      case 'directo':
        return Mensaje.hiloDirecto(
            appState.usuario?.email ?? '', widget.cuentaEmail);
      default:
        return Mensaje.hiloDe(widget.academiaId, widget.cuentaEmail);
    }
  }

  void _toggleEmojis() {
    setState(() => _emojis = !_emojis);
    if (_emojis) {
      _focus.unfocus(); // esconde el teclado (como WhatsApp)
    } else {
      _focus.requestFocus();
    }
  }

  /// Inserta el emoji en la posición del cursor.
  void _insertarEmoji(String e) {
    final sel = _texto.selection;
    final base = _texto.text;
    final start = sel.start >= 0 ? sel.start : base.length;
    final end = sel.end >= 0 ? sel.end : base.length;
    final nuevo = base.replaceRange(start, end, e);
    _texto.value = TextEditingValue(
      text: nuevo,
      selection: TextSelection.collapsed(offset: start + e.length),
    );
  }

  // Stream creado UNA sola vez: si se recreara en cada build (p. ej. al enviar,
  // que hace setState), el StreamBuilder volvería al spinner y la pantalla
  // parpadearía. Por eso es un campo late, no una llamada dentro de build().
  late final Stream<List<Mensaje>> _stream = MensajesRepo.streamHilo(_hilo);

  @override
  void initState() {
    super.initState();
    // Al abrir el teclado, cierra el panel de emojis (no ambos a la vez).
    _focus.addListener(() {
      if (_focus.hasFocus && _emojis) setState(() => _emojis = false);
    });
    // Chat de cancha, lado dueño: carga si el jugador está verificado (insignia).
    if (widget.tipo == 'cancha' &&
        widget.soyProfe &&
        widget.cuentaEmail.isNotEmpty) {
      appState.sincronizarVerificados([widget.cuentaEmail]).then((_) {
        if (mounted) setState(() {});
      });
    }
    // Si la contraparte es una PERSONA (correo), trae su perfil para mostrar
    // su nombre + foto en vez del correo.
    if (_contraparteEmail.isNotEmpty) {
      appState.cargarPerfiles([_contraparteEmail]).then((_) {
        if (mounted) setState(() {});
      });
    }
    // Este es el chat visible ahora: mientras esté abierto, los mensajes de este
    // hilo no disparan el aviso de push (llegan solos por Realtime).
    appState.hiloChatAbierto = _hilo;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      appState.marcarChatLeido(_hilo);
      // Foto tomada desde la cámara del inbox → se envía al abrir el chat.
      if (widget.fotoInicial != null) _enviarBytes(widget.fotoInicial!);
    });
  }

  /// Correo de la CONTRAPARTE persona (a quien le muestro nombre+foto). En un
  /// chat DIRECTO siempre es la otra persona; cuando soy el profe/dueño, es
  /// `cuentaEmail` (el alumno/jugador). En grupos no aplica.
  String get _contraparteEmail {
    if (widget.tipo == 'directo') return widget.cuentaEmail;
    return (widget.soyProfe && widget.tipo != 'grupo') ? widget.cuentaEmail : '';
  }

  /// ¿Muestro la insignia de "verificado" en la cabecera? Solo cuando soy el
  /// dueño y el jugador (la contraparte) está verificado.
  bool get _contraparteVerificada =>
      widget.tipo == 'cancha' &&
      widget.soyProfe &&
      appState.estaVerificado(widget.cuentaEmail);

  @override
  void dispose() {
    appState.marcarChatLeido(_hilo);
    // Deja de ser el chat visible (solo si sigo siendo yo el abierto).
    if (appState.hiloChatAbierto == _hilo) appState.hiloChatAbierto = '';
    _texto.dispose();
    _scroll.dispose();
    _focus.dispose();
    _rec.dispose();
    super.dispose();
  }

  Future<void> _enviar() async {
    final txt = _texto.text.trim();
    final u = appState.usuario;
    if (txt.isEmpty || u == null || _enviando) return;
    setState(() => _enviando = true);
    final msg = Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
      hilo: _hilo,
      tipo: widget.tipo,
      refId: _refId,
      academiaId: widget.academiaId,
      cuentaEmail: widget.cuentaEmail,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: widget.soyProfe,
      texto: txt,
      creado: DateTime.now(),
    );
    final ok = await MensajesRepo.enviar(msg);
    if (!mounted) return;
    setState(() => _enviando = false);
    if (ok) {
      _texto.clear();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
  }

  /// Adjunta/toma una foto y la envía como mensaje con imagen.
  Future<void> _enviarFoto(ImageSource source) async {
    if (_enviando) return;
    try {
      final XFile? file = await ImagePicker()
          .pickImage(source: source, maxWidth: 1600, imageQuality: 80);
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      await _enviarBytes(bytes);
    } catch (_) {
      // ignora: fail-safe
    }
  }

  /// Sube y envía una imagen (bytes) como mensaje con foto en este hilo. Se usa
  /// tanto desde el chat (galería/cámara) como al abrir con una foto inicial
  /// (cámara del inbox).
  Future<void> _enviarBytes(Uint8List bytes) async {
    final u = appState.usuario;
    if (u == null || _enviando) return;
    setState(() => _enviando = true);
    try {
      final url = await MensajesRepo.subirFoto(_hilo, bytes);
      if (url == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo subir la foto. Revisa tu conexión.')));
        return;
      }
      final msg = Mensaje(
        id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
        hilo: _hilo,
        tipo: widget.tipo,
        refId: _refId,
        academiaId: widget.academiaId,
        cuentaEmail: widget.cuentaEmail,
        autorEmail: u.email,
        autorNombre: u.nombre,
        esProfe: widget.soyProfe,
        texto: '📷 Foto',
        mediaUrl: url,
        creado: DateTime.now(),
      );
      await MensajesRepo.enviar(msg);
    } catch (_) {
      // ignora: fail-safe
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  // ── Notas de voz ──────────────────────────────────────────────────────────
  final AudioRecorder _rec = AudioRecorder();
  bool _grabando = false;

  /// Inicia o detiene la grabación de una nota de voz. Al detener, la sube y la
  /// envía como mensaje de audio.
  Future<void> _toggleGrabacion() async {
    if (_grabando) {
      String? ruta;
      try {
        ruta = await _rec.stop();
      } catch (_) {}
      if (mounted) setState(() => _grabando = false);
      if (ruta != null) await _enviarAudio(ruta);
      return;
    }
    // Empezar: pide permiso de micrófono.
    try {
      if (!await _rec.hasPermission()) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Activa el permiso de micrófono para grabar.')));
        }
        return;
      }
      final dir = await getTemporaryDirectory();
      final ruta =
          '${dir.path}/nota_${DateTime.now().microsecondsSinceEpoch}.m4a';
      await _rec.start(const RecordConfig(encoder: AudioEncoder.aacLc),
          path: ruta);
      if (mounted) setState(() => _grabando = true);
    } catch (_) {
      if (mounted) setState(() => _grabando = false);
    }
  }

  Future<void> _enviarAudio(String ruta) async {
    final u = appState.usuario;
    if (u == null) return;
    setState(() => _enviando = true);
    try {
      final bytes = await File(ruta).readAsBytes();
      if (bytes.isEmpty) return;
      final url = await MensajesRepo.subirAudio(_hilo, bytes);
      if (url == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo enviar la nota de voz.')));
        return;
      }
      final msg = Mensaje(
        id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
        hilo: _hilo,
        tipo: widget.tipo,
        refId: _refId,
        academiaId: widget.academiaId,
        cuentaEmail: widget.cuentaEmail,
        autorEmail: u.email,
        autorNombre: u.nombre,
        esProfe: widget.soyProfe,
        texto: '🎤 Nota de voz',
        mediaUrl: url,
        creado: DateTime.now(),
      );
      await MensajesRepo.enviar(msg);
    } catch (_) {
      // fail-safe
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  void _alFinal() {
    if (!_scroll.hasClients) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final wa = _WA(Theme.of(context).brightness == Brightness.dark);
    // Nombre y foto a mostrar: si la contraparte es una persona con perfil, se
    // usa su nombre + foto; si no, el título recibido (nombre de academia/grupo).
    final nombrePerfil = _contraparteEmail.isEmpty
        ? null
        : appState.nombreMostrableDe(_contraparteEmail);
    final fotoPerfil = _contraparteEmail.isEmpty
        ? null
        : appState.fotoDe(_contraparteEmail);
    // Recado (estado tipo WhatsApp) de la contraparte, si lo puso.
    final recado = _contraparteEmail.isEmpty
        ? null
        : appState.recadoDe(_contraparteEmail);
    final tituloMostrar =
        (nombrePerfil != null && nombrePerfil.isNotEmpty)
            ? nombrePerfil
            : widget.titulo;
    final inicial = tituloMostrar.trim().isNotEmpty
        ? tituloMostrar.characters.first.toUpperCase()
        : '?';
    return Scaffold(
      backgroundColor: wa.fondo,
      appBar: AppBar(
        backgroundColor: wa.appBar,
        foregroundColor: Colors.white,
        automaticallyImplyLeading: !widget.embebido,
        titleSpacing: 0,
        title: Row(
          children: [
            CircleAvatar(
              radius: 17,
              backgroundColor: Colors.white24,
              backgroundImage: (fotoPerfil != null && fotoPerfil.isNotEmpty)
                  ? NetworkImage(fotoPerfil)
                  : null,
              child: (fotoPerfil != null && fotoPerfil.isNotEmpty)
                  ? null
                  : Text(inicial,
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 10),
            Flexible(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(tituloMostrar,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  if (recado != null && recado.isNotEmpty)
                    Text(recado,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 11.5)),
                ],
              ),
            ),
            if (_contraparteVerificada)
              const Padding(
                padding: EdgeInsets.only(left: 6),
                child: Icon(Icons.verified, size: 18, color: Colors.white),
              ),
          ],
        ),
        actions: [
          // Si la contraparte compartió su celular, botón "Contactar por WhatsApp".
          if (_contraparteEmail.isNotEmpty &&
              appState.celularDe(_contraparteEmail) != null)
            IconButton(
              tooltip: 'Contactar por WhatsApp',
              icon: const FaIcon(FontAwesomeIcons.whatsapp,
                  color: Color(0xFF25D366)),
              onPressed: () => WhatsAppLink.abrir(
                  appState.celularDe(_contraparteEmail)!,
                  'Hola, te escribo desde Pichangol.'),
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: MensajesRepo.disponible
                ? StreamBuilder<List<Mensaje>>(
                    stream: _stream,
                    builder: (context, snap) {
                      if (snap.connectionState == ConnectionState.waiting) {
                        return const CargandoPichangol();
                      }
                      final msgs = snap.data ?? const <Mensaje>[];
                      // Solo reaccionar cuando LLEGA un mensaje nuevo (no en cada
                      // rebuild): marca leído + baja al final una vez.
                      final ultimo = msgs.isNotEmpty ? msgs.last.id : '';
                      if (ultimo.isNotEmpty && ultimo != _ultimoVisto) {
                        _ultimoVisto = ultimo;
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (mounted) appState.marcarChatLeido(_hilo);
                        });
                        _alFinal();
                      }
                      if (msgs.isEmpty) return const _Vacio();
                      return ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.fromLTRB(10, 12, 10, 12),
                        itemCount: msgs.length,
                        itemBuilder: (_, i) {
                          final m = msgs[i];
                          final esGrupo = widget.tipo == 'grupo';
                          final mio = esGrupo
                              ? m.autorEmail.toLowerCase() ==
                                  (appState.usuario?.email ?? '').toLowerCase()
                              : m.esProfe == widget.soyProfe;
                          return _Burbuja(
                              mensaje: m,
                              mio: mio,
                              wa: wa,
                              mostrarAutor: esGrupo && !mio);
                        },
                      );
                    },
                  )
                : const _SinBackend(),
          ),
          _Barra(
            controller: _texto,
            focus: _focus,
            enviando: _enviando,
            onEnviar: _enviar,
            emojisAbiertos: _emojis,
            onToggleEmojis: _toggleEmojis,
            onGaleria: () => _enviarFoto(ImageSource.gallery),
            onCamara: () => _enviarFoto(ImageSource.camera),
            grabando: _grabando,
            onMic: _toggleGrabacion,
            wa: wa,
          ),
          if (_emojis) _EmojiPanel(onSelect: _insertarEmoji, wa: wa),
        ],
      ),
    );
  }
}

class _Burbuja extends StatelessWidget {
  const _Burbuja(
      {required this.mensaje,
      required this.mio,
      required this.wa,
      this.mostrarAutor = false});
  final Mensaje mensaje;
  final bool mio;
  final _WA wa;
  final bool mostrarAutor; // en grupos: nombre del autor sobre el mensaje

  @override
  Widget build(BuildContext context) {
    final hora = TimeOfDay.fromDateTime(mensaje.creado);
    final hh = hora.hour.toString().padLeft(2, '0');
    final mm = hora.minute.toString().padLeft(2, '0');
    return Align(
      alignment: mio ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints:
            BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.80),
        margin: const EdgeInsets.symmetric(vertical: 3, horizontal: 2),
        padding: const EdgeInsets.fromLTRB(10, 7, 10, 6),
        decoration: BoxDecoration(
          color: mio ? wa.burbujaMia : wa.burbujaOtro,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(12),
            topRight: const Radius.circular(12),
            bottomLeft: Radius.circular(mio ? 12 : 3),
            bottomRight: Radius.circular(mio ? 3 : 12),
          ),
          boxShadow: [
            BoxShadow(
                color: Colors.black.withOpacity(0.12),
                blurRadius: 1,
                offset: const Offset(0, 1)),
          ],
        ),
        // Wrap: el texto fluye y la hora se acomoda al final, estilo WhatsApp.
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (mostrarAutor && mensaje.autorNombre.trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(mensaje.autorNombre,
                    style: TextStyle(
                        color: wa.send,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700)),
              ),
            if (mensaje.esAudio)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: _BurbujaAudio(url: mensaje.mediaUrl, mio: mio, wa: wa),
              )
            else if (mensaje.tieneFoto)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: GestureDetector(
                  // Toca la foto → visor a pantalla completa (ampliar + descargar).
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      fullscreenDialog: true,
                      builder: (_) => _VisorFoto(url: mensaje.mediaUrl))),
                  child: Hero(
                    tag: mensaje.mediaUrl,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.network(
                        mensaje.mediaUrl,
                        width: 220,
                        fit: BoxFit.cover,
                        loadingBuilder: (c, child, prog) => prog == null
                            ? child
                            : const SizedBox(
                                width: 220,
                                height: 150,
                                child: Center(
                                    child: CircularProgressIndicator())),
                        errorBuilder: (c, e, s) => const SizedBox(
                            width: 220,
                            height: 90,
                            child: Icon(Icons.broken_image_outlined, size: 32)),
                      ),
                    ),
                  ),
                ),
              ),
            Wrap(
          alignment: WrapAlignment.end,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: [
            if (mensaje.texto.isNotEmpty &&
                !(mensaje.tieneFoto && mensaje.texto == '📷 Foto') &&
                !(mensaje.esAudio && mensaje.texto == '🎤 Nota de voz'))
              Text(mensaje.texto,
                  style: TextStyle(
                      color: mio ? wa.textoMio : wa.textoOtro, fontSize: 15.5)),
            const SizedBox(width: 8),
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('$hh:$mm',
                      style: TextStyle(fontSize: 10.5, color: wa.hora)),
                  if (mio) ...[
                    const SizedBox(width: 3),
                    Icon(Icons.done_all,
                        size: 14,
                        color: wa.dark
                            ? const Color(0xFF53BDEB)
                            : const Color(0xFF34B7F1)),
                  ],
                ],
              ),
            ),
          ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Punto rojo (indicador de grabación en curso).
class _PuntoGrabando extends StatelessWidget {
  const _PuntoGrabando();
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 11,
      height: 11,
      decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
    );
  }
}

/// Burbuja de NOTA DE VOZ: botón play/pausa + barra + duración. Reproduce la URL
/// del audio con audioplayers. Cada burbuja tiene su propio reproductor.
class _BurbujaAudio extends StatefulWidget {
  const _BurbujaAudio({required this.url, required this.mio, required this.wa});
  final String url;
  final bool mio;
  final _WA wa;

  @override
  State<_BurbujaAudio> createState() => _BurbujaAudioState();
}

class _BurbujaAudioState extends State<_BurbujaAudio> {
  final AudioPlayer _player = AudioPlayer();
  bool _sonando = false;
  Duration _total = Duration.zero;
  Duration _pos = Duration.zero;

  @override
  void initState() {
    super.initState();
    _player.onDurationChanged.listen((d) {
      if (mounted) setState(() => _total = d);
    });
    _player.onPositionChanged.listen((p) {
      if (mounted) setState(() => _pos = p);
    });
    _player.onPlayerComplete.listen((_) {
      if (mounted) setState(() {
            _sonando = false;
            _pos = Duration.zero;
          });
    });
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _toggle() async {
    try {
      if (_sonando) {
        await _player.pause();
        if (mounted) setState(() => _sonando = false);
      } else {
        await _player.play(UrlSource(widget.url));
        if (mounted) setState(() => _sonando = true);
      }
    } catch (_) {}
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString();
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.mio ? widget.wa.textoMio : widget.wa.textoOtro;
    final frac = _total.inMilliseconds == 0
        ? 0.0
        : (_pos.inMilliseconds / _total.inMilliseconds).clamp(0.0, 1.0);
    final mostrar = _sonando || _pos > Duration.zero ? _pos : _total;
    return SizedBox(
      width: 210,
      child: Row(
        children: [
          GestureDetector(
            onTap: _toggle,
            child: Icon(_sonando ? Icons.pause_circle_filled : Icons.play_circle_fill,
                size: 34, color: widget.wa.send),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: frac,
                    minHeight: 4,
                    backgroundColor: color.withOpacity(0.2),
                    valueColor: AlwaysStoppedAnimation(widget.wa.send),
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Icon(Icons.mic, size: 13, color: color.withOpacity(0.7)),
                    const SizedBox(width: 3),
                    Text(_fmt(mostrar),
                        style: TextStyle(
                            fontSize: 11, color: color.withOpacity(0.8))),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Barra extends StatelessWidget {
  const _Barra({
    required this.controller,
    required this.focus,
    required this.enviando,
    required this.onEnviar,
    required this.emojisAbiertos,
    required this.onToggleEmojis,
    required this.onGaleria,
    required this.onCamara,
    required this.grabando,
    required this.onMic,
    required this.wa,
  });
  final TextEditingController controller;
  final FocusNode focus;
  final bool enviando;
  final VoidCallback onEnviar;
  final bool emojisAbiertos;
  final VoidCallback onToggleEmojis;
  final VoidCallback onGaleria;
  final VoidCallback onCamara;
  final bool grabando;
  final VoidCallback onMic;
  final _WA wa;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        color: wa.barra,
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Pastilla: mientras GRABA muestra "Grabando…"; si no, el campo de
            // texto con emoji/adjuntar/cámara.
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: wa.pill,
                  borderRadius: BorderRadius.circular(24),
                ),
                padding: const EdgeInsets.only(left: 4, right: 8),
                child: grabando
                    ? Padding(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 12),
                        child: Row(
                          children: [
                            const _PuntoGrabando(),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text('Grabando nota de voz…',
                                  style: TextStyle(
                                      color: wa.pillTexto,
                                      fontWeight: FontWeight.w600)),
                            ),
                            Text('toca ▶ para enviar',
                                style:
                                    TextStyle(color: wa.hora, fontSize: 12)),
                          ],
                        ),
                      )
                    : Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          IconButton(
                            onPressed: onToggleEmojis,
                            icon: Icon(
                                emojisAbiertos
                                    ? Icons.keyboard_outlined
                                    : Icons.sentiment_satisfied_outlined,
                                color: wa.hora),
                            splashRadius: 20,
                          ),
                          Expanded(
                            child: TextField(
                              controller: controller,
                              focusNode: focus,
                              minLines: 1,
                              maxLines: 5,
                              textCapitalization:
                                  TextCapitalization.sentences,
                              style: TextStyle(
                                  color: wa.pillTexto, fontSize: 16),
                              decoration: InputDecoration(
                                hintText: 'Mensaje',
                                hintStyle: TextStyle(color: wa.hora),
                                isDense: true,
                                border: InputBorder.none,
                                contentPadding: const EdgeInsets.symmetric(
                                    vertical: 10),
                              ),
                              onSubmitted: (_) => onEnviar(),
                            ),
                          ),
                          IconButton(
                            onPressed: enviando ? null : onGaleria,
                            icon: Icon(Icons.attach_file, color: wa.hora),
                            splashRadius: 20,
                            tooltip: 'Adjuntar foto',
                          ),
                          IconButton(
                            onPressed: enviando ? null : onCamara,
                            icon: Icon(Icons.photo_camera_outlined,
                                color: wa.hora),
                            splashRadius: 20,
                            tooltip: 'Cámara',
                          ),
                        ],
                      ),
              ),
            ),
            const SizedBox(width: 6),
            // Botón circular: grabando → enviar (verde); con texto → enviar;
            // vacío → micrófono (empieza a grabar).
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (context, value, _) {
                final hayTexto = value.text.trim().isNotEmpty;
                final mostrarMic = !grabando && !hayTexto;
                return Material(
                  color: grabando ? Colors.red : wa.send,
                  shape: const CircleBorder(),
                  child: InkWell(
                    customBorder: const CircleBorder(),
                    onTap: enviando
                        ? null
                        : grabando
                            ? onMic
                            : (hayTexto ? onEnviar : onMic),
                    child: Padding(
                      padding: const EdgeInsets.all(11),
                      child: enviando
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : Icon(
                              grabando
                                  ? Icons.send
                                  : (mostrarMic ? Icons.mic : Icons.send),
                              color: Colors.white,
                              size: 22),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// Panel de emojis propio (sin paquete): grilla de los más usados. Al tocar uno
/// se inserta en el texto. Se muestra en vez del teclado, como WhatsApp.
class _EmojiPanel extends StatelessWidget {
  const _EmojiPanel({required this.onSelect, required this.wa});
  final void Function(String) onSelect;
  final _WA wa;

  static const _emojis = [
    '😀','😁','😂','🤣','😊','😍','😘','😎','🤩','🥳',
    '😅','😉','🙂','😇','🤔','😐','😴','😢','😭','😡',
    '👍','👎','👏','🙏','💪','🤝','👌','✌️','🤙','👋',
    '🔥','⭐','✨','🎉','❤️','💚','💙','💯','⚡','🏆',
    '⚽','🏀','🎾','🏐','🏓','🏸','🥅','⛳','🎯','🥇',
    '🏃','🚴','⏰','📍','📅','✅','❌','💰','😱','🤑',
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 240,
      color: wa.barra,
      child: GridView.count(
        crossAxisCount: 8,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        children: [
          for (final e in _emojis)
            InkWell(
              onTap: () => onSelect(e),
              borderRadius: BorderRadius.circular(8),
              child: Center(child: Text(e, style: const TextStyle(fontSize: 26))),
            ),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Text('Aún no hay mensajes. ¡Escribe el primero!',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
      );
}

class _SinBackend extends StatelessWidget {
  const _SinBackend();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Text(
              'El chat necesita conexión con el servidor. Intenta más tarde.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
      );
}

/// Visor de foto a PANTALLA COMPLETA (estilo WhatsApp): fondo negro, zoom/pan
/// con doble toque o pellizco, y botón para descargar/compartir (abre la imagen
/// en el navegador, desde donde se guarda o comparte).
class _VisorFoto extends StatelessWidget {
  const _VisorFoto({required this.url});
  final String url;

  Future<void> _descargar(BuildContext context) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo abrir la imagen.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
        actions: [
          IconButton(
            tooltip: 'Descargar / compartir',
            icon: const Icon(Icons.download),
            onPressed: () => _descargar(context),
          ),
        ],
      ),
      body: Center(
        child: Hero(
          tag: url,
          child: InteractiveViewer(
            minScale: 0.8,
            maxScale: 5,
            child: Image.network(
              url,
              fit: BoxFit.contain,
              loadingBuilder: (c, child, prog) => prog == null
                  ? child
                  : const Center(
                      child: CircularProgressIndicator(color: Colors.white)),
              errorBuilder: (c, e, s) => const Icon(Icons.broken_image_outlined,
                  color: Colors.white54, size: 60),
            ),
          ),
        ),
      ),
    );
  }
}
