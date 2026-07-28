import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/db_local.dart';
import '../data/grupos_repo.dart';
import '../data/lecturas_repo.dart';
import '../data/mensajes_repo.dart';
import '../data/reacciones_repo.dart';
import '../models/grupo.dart';
import '../models/mensaje.dart';
import '../services/giphy_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import 'grupo_info_screen.dart';
import 'selector_chat_screen.dart';

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
/// Estado de un mensaje propio para los checks: 1 gris / 2 gris / 2 azul.
enum _Entrega { enviado, entregado, leido }

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
  Grupo? _grupo; // datos del grupo (solo tipo 'grupo'): nombre, foto, miembros

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

  // Ventana de mensajes que traemos del hilo (paginación): arranca en los 50 más
  // recientes y crece cuando el usuario pide "Cargar mensajes anteriores". Así
  // abrir un chat es instantáneo aunque el hilo tenga miles de mensajes.
  static const _pagina = 50;
  int _limite = _pagina;
  // Stream NO recreado en cada build (si no, parpadearía al enviar): solo se
  // recrea al cambiar [_limite]. Por eso guardamos la referencia.
  late Stream<List<Mensaje>> _stream = _streamConCache(_limite);

  /// Caché device-first: emite PRIMERO los mensajes guardados en el teléfono
  /// (pinta al instante, aunque Android haya matado la app) y LUEGO el stream en
  /// vivo de Supabase. Así no hay spinner de red al volver.
  Stream<List<Mensaje>> _streamConCache(int limite) async* {
    final cache = await DbLocal.leerMensajes(_hilo, limite: limite);
    if (cache.isNotEmpty) yield cache;
    yield* MensajesRepo.streamHilo(_hilo, limite: limite);
  }

  void _cargarAnteriores() {
    setState(() {
      _limite += _pagina;
      _stream = _streamConCache(_limite);
    });
  }

  // Reacciones del hilo en vivo: mensajeId → {correo: emoji}.
  final Map<String, Map<String, String>> _reacciones = {};
  StreamSubscription? _reaccionesSub;

  /// Pone/cambia/quita MI reacción a un mensaje (toggle).
  void _reaccionar(Mensaje m, String emoji) {
    final yo = (appState.usuario?.email ?? '').toLowerCase();
    final actual = _reacciones[m.id]?[yo];
    ReaccionesRepo.alternar(_hilo, m.id, yo, emoji, emojiActual: actual);
  }

  // Mensaje que estoy respondiendo (cita arriba del composer). Null = ninguno.
  Mensaje? _respondiendo;

  // Banner "Agregar contacto" (tipo WhatsApp): sale arriba del chat cuando la
  // contraparte NO está guardada; se oculta al agregarla o al descartarlo.
  bool _bannerContactoDescartado = false;

  bool get _mostrarBannerContacto =>
      appState.logueado &&
      _contraparteEmail.isNotEmpty &&
      !_bannerContactoDescartado &&
      !appState.esContacto(_contraparteEmail) &&
      !appState.bloqueado(_contraparteEmail);

  void _agregarContacto() {
    appState.guardarContacto(_contraparteEmail, perfil: {
      'email': _contraparteEmail,
      'nombre': appState.nombreRealDe(_contraparteEmail) ?? widget.titulo,
      'foto_url': appState.fotoDe(_contraparteEmail) ?? '',
      'celular': appState.celularDe(_contraparteEmail) ?? '',
    });
    setState(() {}); // esContacto pasa a true → el banner se oculta
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Contacto guardado'),
          duration: Duration(milliseconds: 1200)));
    }
  }

  Widget _bannerAgregarContacto(_WA wa) {
    final nombre = _contraparteEmail.isEmpty
        ? widget.titulo
        : (appState.nombreMostrableDe(_contraparteEmail) ?? widget.titulo);
    final foto = appState.fotoDe(_contraparteEmail);
    return Material(
      color: wa.barra,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 6, 8),
        child: Row(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: wa.send.withOpacity(0.15),
              backgroundImage:
                  (foto != null && foto.isNotEmpty) ? CachedNetworkImageProvider(foto) : null,
              child: (foto == null || foto.isEmpty)
                  ? Icon(Icons.person_add_alt_1, color: wa.send, size: 18)
                  : null,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text('¿Agregar a $nombre a tus contactos?',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: wa.textoOtro, fontSize: 13.5)),
            ),
            TextButton(
              onPressed: _agregarContacto,
              style: TextButton.styleFrom(foregroundColor: wa.send),
              child: const Text('Agregar',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ),
            IconButton(
              icon: Icon(Icons.close, color: wa.hora, size: 20),
              onPressed: () =>
                  setState(() => _bannerContactoDescartado = true),
            ),
          ],
        ),
      ),
    );
  }

  String _nombreAutorDe(Mensaje m) {
    final yo = (appState.usuario?.email ?? '').toLowerCase();
    if (m.autorEmail.toLowerCase() == yo) return 'Tú';
    return m.autorNombre.trim().isNotEmpty
        ? m.autorNombre
        : (appState.nombreMostrableDe(m.autorEmail) ?? m.autorEmail);
  }

  /// Snippet legible de un mensaje (para la cita).
  String _snippet(Mensaje m) {
    if (m.esAudio) return '🎤 Nota de voz';
    if (m.esGifSticker) return '🎞️ GIF';
    if (m.tieneFoto) return m.texto.isNotEmpty ? m.texto : '📷 Foto';
    return m.texto;
  }

  void _responder(Mensaje m) {
    setState(() => _respondiendo = m);
    _focus.requestFocus();
  }

  /// Reenviar un mensaje: elige un chat (grupo, academia o contacto) y se lo
  /// manda con la etiqueta "Reenviado". Conserva la foto (misma URL) o el texto.
  Future<void> _reenviar(Mensaje m) async {
    final destino = await Navigator.of(context).push<DestinoChat>(
        MaterialPageRoute(builder: (_) => const SelectorChatScreen()));
    if (destino == null || !mounted) return;
    final u = appState.usuario;
    if (u == null) return;
    final msg = Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
      hilo: destino.hilo,
      tipo: destino.tipo,
      refId: destino.refId,
      academiaId: destino.academiaId,
      cuentaEmail: destino.cuentaEmail,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: destino.soyProfe,
      texto: m.texto,
      mediaUrl: m.mediaUrl,
      reenviado: true,
      creado: DateTime.now(),
    );
    final ok = await MensajesRepo.enviar(msg);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content:
          Text(ok ? 'Reenviado a ${destino.titulo}' : 'No se pudo reenviar'),
      duration: const Duration(milliseconds: 1400),
    ));
  }

  // Checks tipo WhatsApp: hasta cuándo tiene la OTRA persona entregado/leído este
  // hilo (llega en vivo por LecturasRepo.stream). Solo aplica a chats 1:1.
  DateTime? _otroEntregado;
  DateTime? _otroLeido;
  StreamSubscription? _lecturaSub;

  /// Estado de entrega de un mensaje MÍO (para los checks).
  _Entrega _estadoEntrega(Mensaje m) {
    if (widget.tipo == 'grupo') return _Entrega.enviado;
    if (_otroLeido != null && !_otroLeido!.isBefore(m.creado)) {
      return _Entrega.leido;
    }
    if (_otroEntregado != null && !_otroEntregado!.isBefore(m.creado)) {
      return _Entrega.entregado;
    }
    return _Entrega.enviado;
  }

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
    // Grupo: carga nombre/foto/miembros para la cabecera y la ficha del grupo.
    if (widget.tipo == 'grupo') {
      GruposRepo.obtener(_refId).then((g) async {
        if (g != null) await appState.cargarPerfiles(g.miembros);
        if (mounted) setState(() => _grupo = g);
      });
    }
    // Este es el chat visible ahora: mientras esté abierto, los mensajes de este
    // hilo no disparan el aviso de push (llegan solos por Realtime).
    appState.hiloChatAbierto = _hilo;
    // Checks: escucha en vivo hasta cuándo tiene la OTRA persona entregado/leído
    // este hilo (solo 1:1).
    if (widget.tipo != 'grupo' && _contraparteEmail.isNotEmpty) {
      final otro = _contraparteEmail.toLowerCase();
      _lecturaSub = LecturasRepo.stream(_hilo).listen((rows) {
        for (final r in rows) {
          if ((r['email'] ?? '').toString().toLowerCase() != otro) continue;
          final ent =
              DateTime.tryParse((r['entregado_hasta'] ?? '').toString())
                  ?.toLocal();
          final lei = DateTime.tryParse((r['leido_hasta'] ?? '').toString())
              ?.toLocal();
          if (mounted) {
            setState(() {
              _otroEntregado = ent;
              _otroLeido = lei;
            });
          }
        }
      });
    }
    // Reacciones del hilo en vivo (todos los tipos de chat).
    _reaccionesSub = ReaccionesRepo.stream(_hilo).listen((rows) {
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

  /// Guardar el contacto con OTRO nombre (apodo local, tipo WhatsApp): solo lo
  /// veo yo; manda sobre el nombre de su perfil en todo el app.
  Future<void> _editarApodo() async {
    final e = _contraparteEmail;
    if (e.isEmpty) return;
    final ctrl = TextEditingController(text: appState.apodoDe(e) ?? '');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => DialogoPichangol(
        titulo: 'Guardar contacto',
        icono: Icons.drive_file_rename_outline,
        contenido: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Ponle el nombre con el que quieres verlo. Solo lo ves '
                'tú (no cambia su perfil).',
                style: TextStyle(color: textoTenue, fontSize: 13)),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              maxLength: 40,
              textCapitalization: TextCapitalization.words,
              decoration:
                  const InputDecoration(hintText: 'Ej. Profe Gyanina'),
            ),
          ],
        ),
        acciones: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              style: TextButton.styleFrom(foregroundColor: textoTenue),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12)),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Guardar',
                  style: TextStyle(fontWeight: FontWeight.w800))),
        ],
      ),
    );
    if (ok != true) return;
    await appState.guardarApodo(e, ctrl.text);
    if (mounted) setState(() {}); // refresca el nombre del header
  }

  /// Bloquear/desbloquear a la contraparte (tipo WhatsApp). Bloqueado = no le
  /// puedo escribir ni llamar hasta desbloquearlo.
  Future<void> _confirmarBloqueo() async {
    final e = _contraparteEmail;
    if (e.isEmpty) return;
    if (appState.bloqueado(e)) {
      await appState.toggleBloqueado(e);
      if (mounted) setState(() {});
      return;
    }
    final ok = await confirmarPichangol(
      context,
      titulo: 'Bloquear contacto',
      mensaje: 'No podrás enviarle mensajes ni llamarlo desde el app hasta que '
          'lo desbloquees.',
      textoConfirmar: 'Bloquear',
      destructivo: true,
      icono: Icons.block,
    );
    if (ok && mounted) {
      await appState.toggleBloqueado(e);
      if (mounted) setState(() {});
    }
  }

  void _msg(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  /// Info del contacto (tipo WhatsApp): identidad REAL (nombre en Pichangol,
  /// correo, celular, recado) aunque le haya puesto un apodo. Desde aquí puede
  /// renombrar o bloquear. Se abre al tocar el nombre en la cabecera.
  Future<void> _verContacto() async {
    final e = _contraparteEmail;
    if (e.isEmpty) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        final apodo = appState.apodoDe(e);
        final nombreReal = appState.nombreRealDe(e);
        final display = apodo ?? nombreReal ?? e;
        final foto = appState.fotoDe(e);
        final celular = appState.celularDe(e);
        final recado = appState.recadoDe(e);
        final bloq = appState.bloqueado(e);
        final inicial = display.trim().isNotEmpty
            ? display.characters.first.toUpperCase()
            : '?';
        Widget fila(IconData ico, String label, Widget valor) => ListTile(
              leading: Icon(ico, color: lima),
              title: Text(label,
                  style: const TextStyle(color: textoTenue, fontSize: 12)),
              subtitle: valor,
              dense: true,
            );
        return SafeArea(
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 4),
                CircleAvatar(
                  radius: 38,
                  backgroundColor: teal,
                  backgroundImage: (foto != null && foto.isNotEmpty)
                      ? CachedNetworkImageProvider(foto)
                      : null,
                  child: (foto != null && foto.isNotEmpty)
                      ? null
                      : Text(inicial,
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 30,
                              fontWeight: FontWeight.w800)),
                ),
                const SizedBox(height: 10),
                Text(display,
                    style: const TextStyle(
                        fontSize: 19, fontWeight: FontWeight.w800)),
                if (apodo != null && nombreReal != null && nombreReal != apodo)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text('En Pichangol: $nombreReal',
                        style:
                            const TextStyle(color: textoTenue, fontSize: 13)),
                  ),
                const SizedBox(height: 8),
                const Divider(height: 1),
                fila(Icons.alternate_email, 'Correo',
                    SelectableText(e, style: const TextStyle(fontSize: 14))),
                if (celular != null)
                  fila(
                    Icons.phone_outlined,
                    'Celular',
                    Row(children: [
                      Expanded(
                          child: Text(celular,
                              style: const TextStyle(fontSize: 14))),
                      IconButton(
                          tooltip: 'Llamar',
                          icon: const Icon(Icons.call, color: lima, size: 20),
                          onPressed: () => _llamar(celular)),
                      IconButton(
                          tooltip: 'WhatsApp',
                          icon: const FaIcon(FontAwesomeIcons.whatsapp,
                              color: Color(0xFF25D366), size: 20),
                          onPressed: () => WhatsAppLink.abrir(
                              celular, 'Hola, te escribo desde Pichangol.')),
                    ]),
                  ),
                if (recado != null)
                  fila(Icons.info_outline, 'Recado',
                      Text(recado, style: const TextStyle(fontSize: 14))),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.drive_file_rename_outline),
                  title: Text(apodo == null
                      ? 'Guardar con otro nombre'
                      : 'Editar nombre del contacto'),
                  onTap: () {
                    Navigator.pop(ctx);
                    _editarApodo();
                  },
                ),
                ListTile(
                  leading: Icon(bloq ? Icons.lock_open : Icons.block,
                      color: bloq ? null : clayOscuro),
                  title: Text(bloq ? 'Desbloquear contacto' : 'Bloquear contacto',
                      style: TextStyle(color: bloq ? null : clayOscuro)),
                  onTap: () {
                    Navigator.pop(ctx);
                    _confirmarBloqueo();
                  },
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        );
      },
    );
  }

  /// Abre el marcador del teléfono con el número de la contraparte (llamada por
  /// la red del celular; no es llamada dentro del app).
  /// Abre la ficha del grupo (foto, nombre, integrantes). Si el usuario salió,
  /// cierra el chat; si cambió nombre/foto, refresca la cabecera.
  Future<void> _abrirInfoGrupo() async {
    final r = await Navigator.of(context).push<String>(MaterialPageRoute(
        builder: (_) => GrupoInfoScreen(grupoId: _refId)));
    if (!mounted) return;
    if (r == 'salio') {
      Navigator.of(context).maybePop();
      return;
    }
    final g = await GruposRepo.obtener(_refId);
    if (mounted) setState(() => _grupo = g);
  }

  Future<void> _llamar(String celular) async {
    final numero = celular.replaceAll(RegExp(r'[^0-9+]'), '');
    if (numero.isEmpty) return;
    try {
      await launchUrl(Uri(scheme: 'tel', path: numero),
          mode: LaunchMode.externalApplication);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo abrir el marcador.')));
      }
    }
  }

  @override
  void dispose() {
    appState.marcarChatLeido(_hilo);
    // Deja de ser el chat visible (solo si sigo siendo yo el abierto).
    if (appState.hiloChatAbierto == _hilo) appState.hiloChatAbierto = '';
    _lecturaSub?.cancel();
    _reaccionesSub?.cancel();
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
    if (appState.bloqueado(_contraparteEmail)) return; // contacto bloqueado
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
      respTexto: _respondiendo != null ? _snippet(_respondiendo!) : '',
      respAutor: _respondiendo != null ? _nombreAutorDe(_respondiendo!) : '',
      respMedia: (_respondiendo?.tieneFoto ?? false)
          ? _respondiendo!.mediaUrl
          : '',
      creado: DateTime.now(),
    );
    final ok = await MensajesRepo.enviar(msg);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      _respondiendo = null; // limpia la cita tras enviar
    });
    if (ok) {
      _texto.clear();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
  }

  /// Envía un GIF/sticker de Giphy: la URL ya está hospedada por Giphy, no se
  /// sube a nuestro bucket (viaja como mediaUrl y se anima solo en la burbuja).
  Future<void> _enviarGif(String url) async {
    final u = appState.usuario;
    if (url.isEmpty || u == null) return;
    setState(() => _emojis = false); // cierra el panel al enviar
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
      texto: '',
      mediaUrl: url,
      creado: DateTime.now(),
    );
    await MensajesRepo.enviar(msg);
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
    final esGrupo = widget.tipo == 'grupo';
    // Nombre y foto a mostrar: si la contraparte es una persona con perfil, se
    // usa su nombre + foto; si no, el título recibido (nombre de academia/grupo).
    final nombrePerfil = _contraparteEmail.isEmpty
        ? null
        : appState.nombreMostrableDe(_contraparteEmail);
    final fotoPerfil = esGrupo
        ? ((_grupo?.fotoUrl ?? '').isNotEmpty ? _grupo!.fotoUrl : null)
        : (_contraparteEmail.isEmpty
            ? null
            : appState.fotoDe(_contraparteEmail));
    // Recado (estado tipo WhatsApp) de la contraparte, si lo puso.
    final recado = esGrupo
        ? (_grupo != null ? '${_grupo!.miembros.length} integrantes' : null)
        : (_contraparteEmail.isEmpty
            ? null
            : appState.recadoDe(_contraparteEmail));
    final tituloMostrar = esGrupo
        ? (_grupo?.nombre ?? widget.titulo)
        : ((nombrePerfil != null && nombrePerfil.isNotEmpty)
            ? nombrePerfil
            : widget.titulo);
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
            // Tocar la FOTO → agrandarla a pantalla completa (WhatsApp). Si no
            // tiene foto y es una persona, abre su info.
            GestureDetector(
              onTap: () {
                if (esGrupo) {
                  _abrirInfoGrupo();
                } else if (fotoPerfil != null && fotoPerfil.isNotEmpty) {
                  Navigator.of(context).push(MaterialPageRoute(
                      fullscreenDialog: true,
                      builder: (_) => _VisorFoto(url: fotoPerfil)));
                } else if (_contraparteEmail.isNotEmpty) {
                  _verContacto();
                }
              },
              child: CircleAvatar(
                radius: 17,
                backgroundColor: Colors.white24,
                backgroundImage: (fotoPerfil != null && fotoPerfil.isNotEmpty)
                    ? CachedNetworkImageProvider(fotoPerfil)
                    : null,
                child: (fotoPerfil != null && fotoPerfil.isNotEmpty)
                    ? null
                    : (esGrupo
                        ? const Icon(Icons.groups, color: Colors.white, size: 20)
                        : Text(inicial,
                            style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w800))),
              ),
            ),
            const SizedBox(width: 10),
            // Tocar el NOMBRE → info (grupo: ficha del grupo; 1:1: contacto).
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: esGrupo
                    ? _abrirInfoGrupo
                    : (_contraparteEmail.isNotEmpty ? _verContacto : null),
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
            ),
            if (_contraparteVerificada)
              const Padding(
                padding: EdgeInsets.only(left: 6),
                child: Icon(Icons.verified, size: 18, color: Colors.white),
              ),
          ],
        ),
        actions: [
          // ── GRUPO: llamada grupal (si algún integrante tiene número) + menú ──
          if (esGrupo &&
              _grupo != null &&
              _grupo!.miembros.any((e) =>
                  e.toLowerCase() != (appState.usuario?.email ?? '').toLowerCase() &&
                  appState.celularDe(e) != null))
            IconButton(
              tooltip: 'Llamada grupal',
              icon: const Icon(Icons.videocam, color: Colors.white),
              onPressed: () => iniciarLlamadaGrupal(context,
                  grupoId: _refId, grupoNombre: _grupo!.nombre),
            ),
          if (esGrupo)
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: Colors.white),
              onSelected: (v) {
                if (v == 'info') _abrirInfoGrupo();
              },
              itemBuilder: (_) => const [
                PopupMenuItem(
                  value: 'info',
                  child: ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.info_outline),
                    title: Text('Info del grupo'),
                  ),
                ),
              ],
            ),
          // Llamar (marcador del teléfono) si la contraparte compartió su celular.
          if (_contraparteEmail.isNotEmpty &&
              appState.celularDe(_contraparteEmail) != null &&
              !appState.bloqueado(_contraparteEmail))
            IconButton(
              tooltip: 'Llamar',
              icon: const Icon(Icons.call, color: Colors.white),
              onPressed: () =>
                  _llamar(appState.celularDe(_contraparteEmail)!),
            ),
          // Si la contraparte compartió su celular, botón "Contactar por WhatsApp".
          if (_contraparteEmail.isNotEmpty &&
              appState.celularDe(_contraparteEmail) != null &&
              !appState.bloqueado(_contraparteEmail))
            IconButton(
              tooltip: 'Contactar por WhatsApp',
              icon: const FaIcon(FontAwesomeIcons.whatsapp,
                  color: Color(0xFF25D366)),
              onPressed: () => WhatsAppLink.abrir(
                  appState.celularDe(_contraparteEmail)!,
                  'Hola, te escribo desde Pichangol.'),
            ),
          // Menú del contacto (tipo WhatsApp): agenda + apodo + bloquear.
          if (_contraparteEmail.isNotEmpty)
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: Colors.white),
              onSelected: (v) async {
                final e = _contraparteEmail;
                if (v == 'info') {
                  _verContacto();
                } else if (v == 'apodo') {
                  _editarApodo();
                } else if (v == 'contacto') {
                  if (appState.esContacto(e)) {
                    await appState.quitarContacto(e);
                    _msg('Quitado de tus contactos');
                  } else {
                    await appState.guardarContacto(e);
                    _msg('Guardado en tus contactos');
                  }
                } else if (v == 'bloquear') {
                  _confirmarBloqueo();
                }
              },
              itemBuilder: (_) {
                final esCont = appState.esContacto(_contraparteEmail);
                final bloq = appState.bloqueado(_contraparteEmail);
                final tieneApodo = appState.apodoDe(_contraparteEmail) != null;
                return [
                  const PopupMenuItem(
                    value: 'info',
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(Icons.person_outline),
                      title: Text('Ver contacto'),
                    ),
                  ),
                  PopupMenuItem(
                    value: 'contacto',
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(esCont
                          ? Icons.person_remove_outlined
                          : Icons.person_add_alt),
                      title: Text(esCont
                          ? 'Quitar de mis contactos'
                          : 'Guardar en mis contactos'),
                    ),
                  ),
                  PopupMenuItem(
                    value: 'apodo',
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.drive_file_rename_outline),
                      title: Text(tieneApodo
                          ? 'Editar nombre del contacto'
                          : 'Guardar con otro nombre'),
                    ),
                  ),
                  PopupMenuItem(
                    value: 'bloquear',
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading:
                          Icon(Icons.block, color: bloq ? null : clayOscuro),
                      title: Text(
                          bloq ? 'Desbloquear contacto' : 'Bloquear contacto',
                          style: TextStyle(color: bloq ? null : clayOscuro)),
                    ),
                  ),
                ];
              },
            ),
        ],
      ),
      body: Column(
        children: [
          if (_mostrarBannerContacto) _bannerAgregarContacto(wa),
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
                        // Persistir la ventana visible en la caché local (SQLite)
                        // para pintarla al instante la próxima vez que se abra.
                        DbLocal.guardarMensajes(_hilo, msgs);
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (mounted) appState.marcarChatLeido(_hilo);
                        });
                        _alFinal();
                      }
                      if (msgs.isEmpty) return const _Vacio();
                      // Si la ventana está llena, es probable que haya historia
                      // anterior: mostramos un encabezado para traer más (arriba
                      // del todo, índice 0).
                      final hayMas = msgs.length >= _limite;
                      return ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.fromLTRB(10, 12, 10, 12),
                        itemCount: msgs.length + (hayMas ? 1 : 0),
                        itemBuilder: (_, idx) {
                          if (hayMas && idx == 0) {
                            return Center(
                              child: Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: TextButton.icon(
                                  onPressed: _cargarAnteriores,
                                  icon: const Icon(Icons.history, size: 18),
                                  label: const Text('Cargar mensajes anteriores'),
                                  style: TextButton.styleFrom(
                                      foregroundColor: teal),
                                ),
                              ),
                            );
                          }
                          final i = hayMas ? idx - 1 : idx;
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
                              mostrarAutor: esGrupo && !mio,
                              entrega: mio ? _estadoEntrega(m) : _Entrega.enviado,
                              reacciones: _reacciones[m.id] ?? const {},
                              onResponder: () => _responder(m),
                              onReenviar: () => _reenviar(m),
                              onReaccion: (emoji) => _reaccionar(m, emoji));
                        },
                      );
                    },
                  )
                : const _SinBackend(),
          ),
          if (_contraparteEmail.isNotEmpty &&
              appState.bloqueado(_contraparteEmail))
            _BarraBloqueado(onDesbloquear: _confirmarBloqueo)
          else ...[
            if (_respondiendo != null)
              _CitaComposer(
                autor: _nombreAutorDe(_respondiendo!),
                texto: _snippet(_respondiendo!),
                media: (_respondiendo?.tieneFoto ?? false)
                    ? _respondiendo!.mediaUrl
                    : '',
                wa: wa,
                onCerrar: () => setState(() => _respondiendo = null),
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
            if (_emojis)
              _PanelExpresion(
                  onEmoji: _insertarEmoji, onMedia: _enviarGif, wa: wa),
          ],
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
      this.mostrarAutor = false,
      this.entrega = _Entrega.enviado,
      this.reacciones = const {},
      this.onResponder,
      this.onReenviar,
      this.onReaccion});
  final _Entrega entrega;
  final Mensaje mensaje;
  final bool mio;
  final _WA wa;
  final bool mostrarAutor; // en grupos: nombre del autor sobre el mensaje
  final Map<String, String> reacciones; // correo → emoji (de este mensaje)
  final VoidCallback? onResponder;
  final VoidCallback? onReenviar;
  final void Function(String emoji)? onReaccion;

  // Emojis rápidos de reacción (fila superior, tipo WhatsApp).
  static const _emojisRapidos = ['👍', '❤️', '😂', '😮', '😢', '🙏'];

  void _menu(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF202C33)
          : Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            // Fila de reacciones rápidas (como WhatsApp).
            if (onReaccion != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    for (final em in _emojisRapidos)
                      InkWell(
                        borderRadius: BorderRadius.circular(24),
                        onTap: () {
                          Navigator.pop(context);
                          onReaccion!(em);
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(6),
                          child: Text(em, style: const TextStyle(fontSize: 28)),
                        ),
                      ),
                  ],
                ),
              ),
            if (onReaccion != null)
              const Divider(height: 12),
            ListTile(
              leading: const Icon(Icons.reply, color: teal),
              title: const Text('Responder'),
              onTap: () {
                Navigator.pop(context);
                onResponder?.call();
              },
            ),
            ListTile(
              leading: const Icon(Icons.forward, color: teal),
              title: const Text('Reenviar'),
              onTap: () {
                Navigator.pop(context);
                onReenviar?.call();
              },
            ),
            if (mensaje.texto.trim().isNotEmpty)
              ListTile(
                leading: const Icon(Icons.copy_outlined, color: teal),
                title: const Text('Copiar'),
                onTap: () {
                  Clipboard.setData(ClipboardData(text: mensaje.texto));
                  Navigator.pop(context);
                },
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hora = TimeOfDay.fromDateTime(mensaje.creado);
    final hh = hora.hour.toString().padLeft(2, '0');
    final mm = hora.minute.toString().padLeft(2, '0');
    return Align(
      alignment: mio ? Alignment.centerRight : Alignment.centerLeft,
      child: GestureDetector(
        onLongPress: () => _menu(context),
        // Deslizar a la derecha = responder (swipe-to-reply, tipo WhatsApp).
        onHorizontalDragEnd: (d) {
          if ((d.primaryVelocity ?? 0) > 80) onResponder?.call();
        },
        child: Column(
          crossAxisAlignment:
              mio ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
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
            if (mensaje.reenviado)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.forward, size: 13, color: wa.hora),
                  const SizedBox(width: 3),
                  Text('Reenviado',
                      style: TextStyle(
                          fontSize: 11.5,
                          fontStyle: FontStyle.italic,
                          color: wa.hora)),
                ]),
              ),
            if (mensaje.esRespuesta)
              Container(
                margin: const EdgeInsets.only(bottom: 4),
                padding: const EdgeInsets.fromLTRB(8, 5, 8, 5),
                decoration: BoxDecoration(
                  color: wa.dark
                      ? Colors.white.withOpacity(0.08)
                      : Colors.black.withOpacity(0.06),
                  borderRadius: BorderRadius.circular(6),
                  border: Border(left: BorderSide(color: wa.send, width: 3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                              mensaje.respAutor.isNotEmpty
                                  ? mensaje.respAutor
                                  : 'Mensaje',
                              style: TextStyle(
                                  color: wa.send,
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700)),
                          Text(mensaje.respTexto,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 13,
                                  color: mio ? wa.textoMio : wa.textoOtro)),
                        ],
                      ),
                    ),
                    if (mensaje.respMedia.isNotEmpty) ...[
                      const SizedBox(width: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: CachedNetworkImage(
                            imageUrl: mensaje.respMedia,
                            width: 38,
                            height: 38,
                            fit: BoxFit.cover,
                            errorWidget: (_, __, ___) =>
                                const SizedBox(width: 38, height: 38)),
                      ),
                    ],
                  ],
                ),
              ),
            if (mensaje.esAudio)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: _BurbujaAudio(url: mensaje.mediaUrl, mio: mio, wa: wa),
              )
            else if (mensaje.esGifSticker)
              // GIF/sticker (Giphy): sin recorte, fondo transparente, ya animado.
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Image.network(
                  mensaje.mediaUrl,
                  width: 170,
                  fit: BoxFit.contain,
                  loadingBuilder: (c, child, prog) => prog == null
                      ? child
                      : const SizedBox(
                          width: 170,
                          height: 130,
                          child: Center(child: CircularProgressIndicator())),
                  errorBuilder: (c, e, s) => const SizedBox(
                      width: 120,
                      height: 90,
                      child: Icon(Icons.broken_image_outlined, size: 32)),
                ),
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
                      child: CachedNetworkImage(
                        imageUrl: mensaje.mediaUrl,
                        width: 220,
                        fit: BoxFit.cover,
                        placeholder: (c, u) => const SizedBox(
                            width: 220,
                            height: 150,
                            child:
                                Center(child: CircularProgressIndicator())),
                        errorWidget: (c, u, e) => const SizedBox(
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
                    Icon(
                        entrega == _Entrega.enviado
                            ? Icons.done // 1 check
                            : Icons.done_all, // 2 checks
                        size: 14,
                        color: entrega == _Entrega.leido
                            ? (wa.dark
                                ? const Color(0xFF53BDEB)
                                : const Color(0xFF34B7F1)) // azul = leído
                            : wa.hora), // gris = enviado/entregado
                  ],
                ],
              ),
            ),
          ],
            ),
          ],
        ),
            ),
            if (reacciones.isNotEmpty) _chipReacciones(),
          ],
        ),
      ),
    );
  }

  /// Pastilla con las reacciones del mensaje (emojis distintos + total).
  Widget _chipReacciones() {
    final emojis = reacciones.values.toList();
    final distintos = <String>[];
    for (final e in emojis) {
      if (!distintos.contains(e)) distintos.add(e);
    }
    return Transform.translate(
      offset: const Offset(0, -6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        decoration: BoxDecoration(
          color: wa.burbujaOtro,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
                color: Colors.black.withOpacity(0.15),
                blurRadius: 1,
                offset: const Offset(0, 1)),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(distintos.take(3).join(),
                style: const TextStyle(fontSize: 13)),
            if (emojis.length > 1) ...[
              const SizedBox(width: 2),
              Text('${emojis.length}',
                  style: TextStyle(
                      fontSize: 11,
                      color: wa.hora,
                      fontWeight: FontWeight.w600)),
            ],
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

/// Barra que reemplaza la de escribir cuando bloqueaste a la contraparte
/// (tipo WhatsApp): no puedes enviar hasta desbloquear.
/// Cita del mensaje que se está respondiendo, encima del composer.
class _CitaComposer extends StatelessWidget {
  const _CitaComposer(
      {required this.autor,
      required this.texto,
      required this.wa,
      required this.onCerrar,
      this.media = ''});
  final String autor;
  final String texto;
  final String media; // miniatura de la foto citada ('' si no hay)
  final _WA wa;
  final VoidCallback onCerrar;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: wa.barra,
      padding: const EdgeInsets.fromLTRB(8, 6, 6, 0),
      child: Container(
        padding: const EdgeInsets.fromLTRB(10, 6, 4, 6),
        decoration: BoxDecoration(
          color: wa.burbujaOtro,
          borderRadius: BorderRadius.circular(8),
          border: Border(left: BorderSide(color: wa.send, width: 4)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(autor,
                      style: TextStyle(
                          color: wa.send,
                          fontWeight: FontWeight.w700,
                          fontSize: 13)),
                  Text(media.isNotEmpty ? '📷 Foto' : texto,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: wa.textoOtro, fontSize: 13)),
                ],
              ),
            ),
            if (media.isNotEmpty) ...[
              const SizedBox(width: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: CachedNetworkImage(
                    imageUrl: media,
                    width: 40, height: 40, fit: BoxFit.cover,
                    errorWidget: (_, __, ___) => const SizedBox(
                        width: 40, height: 40)),
              ),
            ],
            IconButton(
              icon: Icon(Icons.close, color: wa.hora, size: 20),
              onPressed: onCerrar,
            ),
          ],
        ),
      ),
    );
  }
}

class _BarraBloqueado extends StatelessWidget {
  const _BarraBloqueado({required this.onDesbloquear});
  final VoidCallback onDesbloquear;
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        width: double.infinity,
        color: Theme.of(context).brightness == Brightness.dark
            ? const Color(0xFF1F2C34)
            : const Color(0xFFF0F2F5),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.block, size: 18, color: clayOscuro),
            const SizedBox(width: 8),
            const Flexible(
              child: Text('Bloqueaste a este contacto.',
                  style: TextStyle(color: textoTenue, fontSize: 13)),
            ),
            const SizedBox(width: 8),
            TextButton(
              onPressed: onDesbloquear,
              style: TextButton.styleFrom(foregroundColor: lima),
              child: const Text('Desbloquear',
                  style: TextStyle(fontWeight: FontWeight.w800)),
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
/// Panel de expresión estilo WhatsApp: pestañas Emoji · GIF · Stickers.
/// Los GIF/stickers vienen de Giphy.
class _PanelExpresion extends StatelessWidget {
  const _PanelExpresion(
      {required this.onEmoji, required this.onMedia, required this.wa});
  final void Function(String) onEmoji;
  final void Function(String url) onMedia;
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
    return DefaultTabController(
      length: 3,
      child: Container(
        height: 300,
        color: wa.barra,
        child: Column(
          children: [
            TabBar(
              labelColor: wa.send,
              unselectedLabelColor: wa.hora,
              indicatorColor: wa.send,
              tabs: const [
                Tab(icon: Icon(Icons.emoji_emotions_outlined)),
                Tab(icon: Icon(Icons.gif_box_outlined)),
                Tab(icon: Icon(Icons.sticky_note_2_outlined)),
              ],
            ),
            Expanded(
              child: TabBarView(
                children: [
                  // Emoji
                  GridView.count(
                    crossAxisCount: 8,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    children: [
                      for (final e in _emojis)
                        InkWell(
                          onTap: () => onEmoji(e),
                          borderRadius: BorderRadius.circular(8),
                          child: Center(
                              child: Text(e,
                                  style: const TextStyle(fontSize: 26))),
                        ),
                    ],
                  ),
                  // GIF
                  _GifGrid(sticker: false, onSelect: onMedia, wa: wa),
                  // Stickers
                  _GifGrid(sticker: true, onSelect: onMedia, wa: wa),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Grilla de GIFs/stickers de Giphy con buscador (tendencia si el texto vacío).
class _GifGrid extends StatefulWidget {
  const _GifGrid(
      {required this.sticker, required this.onSelect, required this.wa});
  final bool sticker;
  final void Function(String url) onSelect;
  final _WA wa;

  @override
  State<_GifGrid> createState() => _GifGridState();
}

class _GifGridState extends State<_GifGrid> {
  final _q = TextEditingController();
  List<GifItem> _items = const [];
  bool _cargando = false;

  @override
  void initState() {
    super.initState();
    if (GiphyService.configurado) _buscar('');
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _buscar(String q) async {
    setState(() => _cargando = true);
    final r = await GiphyService.buscar(q, sticker: widget.sticker);
    if (!mounted) return;
    setState(() {
      _items = r;
      _cargando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!GiphyService.configurado) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
              '${widget.sticker ? "Stickers" : "GIF"} aún no activados.\n'
              'Falta configurar la clave de Giphy.',
              textAlign: TextAlign.center,
              style: TextStyle(color: widget.wa.hora)),
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 6),
          child: TextField(
            controller: _q,
            style: TextStyle(color: widget.wa.pillTexto),
            textInputAction: TextInputAction.search,
            onSubmitted: _buscar,
            decoration: InputDecoration(
              isDense: true,
              hintText: widget.sticker ? 'Buscar stickers' : 'Buscar GIF',
              hintStyle: TextStyle(color: widget.wa.hora),
              prefixIcon: Icon(Icons.search, color: widget.wa.hora, size: 20),
              filled: true,
              fillColor: widget.wa.pill,
              contentPadding: const EdgeInsets.symmetric(vertical: 8),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(20),
                borderSide: BorderSide.none,
              ),
            ),
          ),
        ),
        Expanded(
          child: _cargando
              ? const Center(child: CircularProgressIndicator())
              : _items.isEmpty
                  ? Center(
                      child: Text('Sin resultados',
                          style: TextStyle(color: widget.wa.hora)))
                  : GridView.count(
                      crossAxisCount: widget.sticker ? 4 : 3,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      mainAxisSpacing: 6,
                      crossAxisSpacing: 6,
                      children: [
                        for (final it in _items)
                          InkWell(
                            onTap: () => widget.onSelect(it.full),
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(8),
                              child: Image.network(
                                it.preview,
                                fit: BoxFit.cover,
                                errorBuilder: (c, e, s) => Container(
                                    color: widget.wa.pill,
                                    child: Icon(Icons.broken_image_outlined,
                                        color: widget.wa.hora)),
                              ),
                            ),
                          ),
                      ],
                    ),
        ),
      ],
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
            child: CachedNetworkImage(
              imageUrl: url,
              fit: BoxFit.contain,
              placeholder: (c, u) => const Center(
                  child: CircularProgressIndicator(color: Colors.white)),
              errorWidget: (c, u, e) => const Icon(
                  Icons.broken_image_outlined,
                  color: Colors.white54, size: 60),
            ),
          ),
        ),
      ),
    );
  }
}
