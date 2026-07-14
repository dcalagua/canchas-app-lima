import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';

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
  });

  final String academiaId;
  final String cuentaEmail; // otra parte en 1:1 (alumno/jugador)
  final String titulo; // nombre de la contraparte (o de la academia)
  final bool soyProfe; // true = soy el anfitrión (profe/dueño)
  final String tipo; // 'academia' | 'cancha' | 'grupo'
  final String refId; // canchaId/grupoId cuando no es academia

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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      appState.marcarChatLeido(_hilo);
    });
  }

  @override
  void dispose() {
    appState.marcarChatLeido(_hilo);
    _texto.dispose();
    _scroll.dispose();
    _focus.dispose();
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
    final u = appState.usuario;
    if (u == null || _enviando) return;
    try {
      final XFile? file = await ImagePicker()
          .pickImage(source: source, maxWidth: 1600, imageQuality: 80);
      if (file == null || !mounted) return;
      setState(() => _enviando = true);
      final bytes = await file.readAsBytes();
      final url = await MensajesRepo.subirFoto(_hilo, bytes);
      if (url == null) {
        if (!mounted) return;
        setState(() => _enviando = false);
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
    final inicial = widget.titulo.trim().isNotEmpty
        ? widget.titulo.characters.first.toUpperCase()
        : '?';
    return Scaffold(
      backgroundColor: wa.fondo,
      appBar: AppBar(
        backgroundColor: wa.appBar,
        foregroundColor: Colors.white,
        titleSpacing: 0,
        title: Row(
          children: [
            CircleAvatar(
              radius: 17,
              backgroundColor: Colors.white24,
              child: Text(inicial,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(widget.titulo,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: MensajesRepo.disponible
                ? StreamBuilder<List<Mensaje>>(
                    stream: _stream,
                    builder: (context, snap) {
                      if (snap.connectionState == ConnectionState.waiting) {
                        return const Center(child: CircularProgressIndicator());
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
            if (mensaje.tieneFoto)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
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
                            child: Center(child: CircularProgressIndicator())),
                    errorBuilder: (c, e, s) => const SizedBox(
                        width: 220,
                        height: 90,
                        child: Icon(Icons.broken_image_outlined, size: 32)),
                  ),
                ),
              ),
            Wrap(
          alignment: WrapAlignment.end,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: [
            if (mensaje.texto.isNotEmpty &&
                !(mensaje.tieneFoto && mensaje.texto == '📷 Foto'))
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
            // Pastilla con emoji + campo de texto (los emojis salen del teclado
            // del sistema; el botón carita solo abre/enfoca el teclado).
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: wa.pill,
                  borderRadius: BorderRadius.circular(24),
                ),
                padding: const EdgeInsets.only(left: 4, right: 8),
                child: Row(
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
                        textCapitalization: TextCapitalization.sentences,
                        style: TextStyle(color: wa.pillTexto, fontSize: 16),
                        decoration: InputDecoration(
                          hintText: 'Mensaje',
                          hintStyle: TextStyle(color: wa.hora),
                          isDense: true,
                          border: InputBorder.none,
                          contentPadding:
                              const EdgeInsets.symmetric(vertical: 10),
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
                      icon: Icon(Icons.photo_camera_outlined, color: wa.hora),
                      splashRadius: 20,
                      tooltip: 'Cámara',
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 6),
            // Botón de envío circular verde WhatsApp.
            Material(
              color: wa.send,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: enviando ? null : onEnviar,
                child: Padding(
                  padding: const EdgeInsets.all(11),
                  child: enviando
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.send, color: Colors.white, size: 22),
                ),
              ),
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
