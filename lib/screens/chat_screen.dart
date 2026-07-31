import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/llamada_service.dart';
import '../services/llamada_webrtc.dart';
import 'llamada_screen.dart';

import '../data/db_local.dart';
import '../data/grupos_repo.dart';
import '../data/lecturas_repo.dart';
import '../data/mensajes_repo.dart';
import '../data/presencia_repo.dart';
import '../data/reacciones_repo.dart';
import '../data/ubicacion_vivo_repo.dart';
import '../models/grupo.dart';
import '../models/mensaje.dart';
import '../services/giphy_service.dart';
import '../services/places_service.dart';
import '../services/ubicacion_vivo_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import 'grupo_info_screen.dart';
import 'selector_chat_screen.dart';
import 'ubicacion_screen.dart';

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
    if (m.esUbicacionVivo) return '📍 Ubicación en tiempo real';
    if (m.esUbicacion) return '📍 Ubicación';
    if (m.esDocumento) return '📄 ${m.nombreArchivo}';
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

  // Presencia "en línea / última vez". Dos señales combinadas:
  //  - broadcast (_ultPingOtro): el otro tiene ESTE chat abierto (instantáneo).
  //  - tabla pichangol_presencia (_ultimoVistoOtro): su último latido global
  //    (sirve para "en línea" aunque no esté en este chat, y para "última vez").
  Presencia? _presencia;
  DateTime? _ultPingOtro;
  DateTime? _ultimoVistoOtro;
  Timer? _presenciaTimer;
  int _tickPresencia = 0;
  bool get _otroEnLinea {
    final ahora = DateTime.now();
    if (_ultPingOtro != null && ahora.difference(_ultPingOtro!).inSeconds < 12) {
      return true;
    }
    return _ultimoVistoOtro != null &&
        ahora.difference(_ultimoVistoOtro!).inSeconds < 40;
  }

  Future<void> _refrescarUltimoVisto() async {
    if (widget.tipo == 'grupo' || _contraparteEmail.isEmpty) return;
    final v = await PresenciaRepo.ultimoVisto(_contraparteEmail);
    if (v != null && mounted) setState(() => _ultimoVistoOtro = v);
  }

  /// Texto "última vez …" (solo si NO está en línea).
  String? _ultimaVezTexto() {
    final v = _ultimoVistoOtro;
    if (v == null) return null;
    final ahora = DateTime.now();
    final hoy = DateTime(ahora.year, ahora.month, ahora.day);
    final dia = DateTime(v.year, v.month, v.day);
    final hh = v.hour.toString().padLeft(2, '0');
    final mm = v.minute.toString().padLeft(2, '0');
    final dif = hoy.difference(dia).inDays;
    if (dif == 0) return 'última vez hoy a las $hh:$mm';
    if (dif == 1) return 'última vez ayer a las $hh:$mm';
    final d = v.day.toString().padLeft(2, '0');
    final mo = v.month.toString().padLeft(2, '0');
    return 'última vez el $d/$mo a las $hh:$mm';
  }

  /// Estado de entrega de un mensaje MÍO (para los checks). Reciprocidad: si YO
  /// apagué la confirmación de lectura, no veo los 2 azules del otro (se queda
  /// en "entregado" como máximo).
  _Entrega _estadoEntrega(Mensaje m) {
    if (widget.tipo == 'grupo') return _Entrega.enviado;
    if (appState.confirmacionLectura &&
        _otroLeido != null &&
        !_otroLeido!.isBefore(m.creado)) {
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
    // Presencia "en línea": solo 1:1 con una persona (correo). Late cada 4 s
    // mientras el chat esté abierto; se refresca el estado del otro (staleness).
    // Reciprocidad: si YO apagué "última vez", no abro presencia → no reporto la
    // mía y tampoco veo la del otro (queda solo el recado en el subtítulo).
    if (widget.tipo != 'grupo' &&
        _contraparteEmail.isNotEmpty &&
        appState.mostrarUltimaVez) {
      final miEmail = (appState.usuario?.email ?? '').toLowerCase();
      final otro = _contraparteEmail.toLowerCase();
      _presencia = PresenciaRepo.abrir(
        hilo: _hilo,
        miEmail: miEmail,
        onPing: (e) {
          if (e == otro && mounted) setState(() => _ultPingOtro = DateTime.now());
        },
      );
      _refrescarUltimoVisto(); // "última vez" al abrir
      _presenciaTimer = Timer.periodic(const Duration(seconds: 4), (_) {
        _presencia?.ping(miEmail);
        // Cada ~20 s relee la "última vez" de la tabla (para el subtítulo).
        if (_tickPresencia++ % 5 == 0) _refrescarUltimoVisto();
        if (mounted) setState(() {}); // re-evalúa "en línea" (staleness)
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

  /// Llamada 1-a-1 con WebRTC propio (pantalla tipo WhatsApp). Publica un aviso
  /// en el chat ("📹 Videollamada"/"📞 Llamada de voz") que dispara el push
  /// (CallKit) al otro, y abre la pantalla de llamada como quien LLAMA. La sala
  /// es estable por hilo (ambos caen en la misma señalización).
  Future<void> _iniciarLlamada({required bool video}) async {
    final u = appState.usuario;
    if (u == null) return;
    // La OTRA persona: en directo es la contraparte; en cancha, el dueño va en
    // refId (correo). Así podemos consolidar la llamada en el chat DIRECTO.
    var otro = _contraparteEmail;
    if (otro.isEmpty && _refId.contains('@')) otro = _refId;
    if (appState.bloqueado(otro)) return;
    // Ya hay una llamada en curso: NO arranques otra; en su lugar REABRE su
    // pantalla completa (como WhatsApp cuando tocas el chat de la llamada), en
    // vez de dejar solo la barra de arriba.
    if (LlamadaWebRTC.instance.activa) {
      // Si ya estás viendo la pantalla, no apiles otra.
      if (!LlamadaWebRTC.pantallaVisible) {
        final svc = LlamadaWebRTC.instance;
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => LlamadaScreen(
            callId: '',
            video: svc.video,
            iniciar: false,
            reattach: true,
            nombreOtro: svc.nombreOtro,
            fotoUrl: svc.fotoOtro,
            emailOtro: svc.emailOtro,
          ),
        ));
      }
      return;
    }
    // Abre la pantalla completa AL INSTANTE (antes del envío del aviso).

    // Las llamadas 1:1 SIEMPRE van al hilo DIRECTO con la persona: así no se
    // fragmentan entre el chat de academia/cancha y el chat personal (todo se
    // consolida en un solo chat con ese usuario, como WhatsApp). Si no se puede
    // saber el correo del otro (raro), cae al hilo actual.
    final bool porDirecto = otro.isNotEmpty;
    final String hiloLlamada =
        porDirecto ? Mensaje.hiloDirecto(u.email, otro) : _hilo;
    final sala = LlamadaService.salaChat(hiloLlamada);
    final nombre = appState.nombreMostrableDe(otro) ??
        (otro.isNotEmpty ? otro : widget.titulo);
    // WhatsApp-style: abre la PANTALLA COMPLETA de la llamada AL INSTANTE (antes
    // de mandar el aviso/push, que puede tardar por la red). Ahí adentro arranca
    // el WebRTC y se ve "Llamando…".
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => LlamadaScreen(
        callId: sala,
        video: video,
        iniciar: true,
        nombreOtro: nombre,
        fotoUrl: appState.fotoDe(otro) ?? '',
        emailOtro: otro,
      ),
    ));
    // Aviso en el chat → el backend manda el push de llamada al otro.
    await MensajesRepo.enviar(Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
      hilo: hiloLlamada,
      tipo: porDirecto ? 'directo' : widget.tipo,
      refId: porDirecto ? '' : _refId,
      academiaId: porDirecto ? '' : widget.academiaId,
      cuentaEmail: porDirecto ? otro : widget.cuentaEmail,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: porDirecto ? false : widget.soyProfe,
      texto: video ? '📹 Videollamada' : '📞 Llamada de voz',
      creado: DateTime.now(),
    ));
  }

  @override
  void dispose() {
    appState.marcarChatLeido(_hilo);
    // Deja de ser el chat visible (solo si sigo siendo yo el abierto).
    if (appState.hiloChatAbierto == _hilo) appState.hiloChatAbierto = '';
    _lecturaSub?.cancel();
    _reaccionesSub?.cancel();
    _presenciaTimer?.cancel();
    _presencia?.cerrar();
    _timerGrab?.cancel();
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

  /// Menú del clip estilo WhatsApp: un popup con una grilla de íconos redondos
  /// de colores (Galería, Cámara, Ubicación). Contacto se evaluará más adelante.
  void _menuAdjuntar() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF202C33)
          : Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 18),
                decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.35),
                    borderRadius: BorderRadius.circular(999)),
              ),
              Wrap(
                spacing: 26,
                runSpacing: 18,
                alignment: WrapAlignment.center,
                children: [
                  _AccionAdjunto(
                    icon: Icons.photo_library_rounded,
                    color: const Color(0xFF9B59B6), // morado
                    label: 'Galería',
                    onTap: () {
                      Navigator.pop(context);
                      _enviarFoto(ImageSource.gallery);
                    },
                  ),
                  _AccionAdjunto(
                    icon: Icons.photo_camera_rounded,
                    color: const Color(0xFFE8556D), // rojo/rosado
                    label: 'Cámara',
                    onTap: () {
                      Navigator.pop(context);
                      _enviarFoto(ImageSource.camera);
                    },
                  ),
                  _AccionAdjunto(
                    icon: Icons.insert_drive_file_rounded,
                    color: const Color(0xFF5B7FE8), // azul
                    label: 'Documento',
                    onTap: () {
                      Navigator.pop(context);
                      _enviarDocumento();
                    },
                  ),
                  _AccionAdjunto(
                    icon: Icons.location_on_rounded,
                    color: const Color(0xFF2ECC71), // verde
                    label: 'Ubicación',
                    onTap: () {
                      Navigator.pop(context);
                      _abrirUbicacion();
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Abre la pantalla de ubicación (mapa + elegir) estilo WhatsApp y, según lo
  /// que elija, envía la ubicación actual o arranca la de tiempo real.
  Future<void> _abrirUbicacion() async {
    final res = await Navigator.of(context).push<ResultadoUbicacion>(
      MaterialPageRoute(builder: (_) => const UbicacionScreen()),
    );
    if (res == null || !mounted) return;
    if (res.envivo == null) {
      await _enviarUbicacionEstatica(res.pos);
    } else {
      await _compartirUbicacionVivo(res.envivo!, res.pos);
    }
  }

  /// Arranca la ubicación EN VIVO: envía el mensaje-marcador y prende el servicio
  /// que sube mi posición cada pocos segundos hasta que venza [dur] o la detenga.
  Future<void> _compartirUbicacionVivo(Duration dur, LatLng pos) async {
    final u = appState.usuario;
    if (u == null || _enviando) return;
    setState(() => _enviando = true);
    try {
      final expira = DateTime.now().add(dur);
      // Sube el primer fix y prende el servicio (sigue aunque salga del chat).
      await UbicacionVivoRepo.actualizar(
        hilo: _hilo,
        email: u.email,
        lat: pos.latitude,
        lng: pos.longitude,
        expira: expira,
      );
      await UbicacionVivoService.instance
          .iniciar(hilo: _hilo, email: u.email, expira: expira);
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
        texto: '📍 Ubicación en tiempo real',
        mediaUrl: 'geolive:${expira.millisecondsSinceEpoch}',
        creado: DateTime.now(),
      );
      await MensajesRepo.enviar(msg);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo compartir tu ubicación.')));
      }
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  /// Elige un ARCHIVO/documento, lo sube y lo envía como mensaje (tarjeta de
  /// documento). Estilo WhatsApp: pdf, docx, xlsx, zip, etc.
  Future<void> _enviarDocumento() async {
    final u = appState.usuario;
    if (u == null || _enviando) return;
    try {
      final res = await FilePicker.platform.pickFiles(withData: true);
      if (res == null || res.files.isEmpty || !mounted) return;
      final f = res.files.first;
      final bytes = f.bytes;
      if (bytes == null) return;
      setState(() => _enviando = true);
      final url = await MensajesRepo.subirArchivo(_hilo, bytes, f.name);
      if (url == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('No se pudo subir el archivo. Revisa tu conexión.')));
        }
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
        texto: '📄 ${f.name}',
        mediaUrl: url,
        creado: DateTime.now(),
      );
      await MensajesRepo.enviar(msg);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo enviar el archivo.')));
      }
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  /// Envía el punto [pos] como un mensaje de ubicación estática (se codifica en
  /// mediaUrl como geo:lat,lng; el receptor la ve como una tarjeta que abre
  /// Google Maps).
  Future<void> _enviarUbicacionEstatica(LatLng pos) async {
    final u = appState.usuario;
    if (u == null || _enviando) return;
    setState(() => _enviando = true);
    try {
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
        texto: '📍 Ubicación',
        mediaUrl: 'geo:${pos.latitude},${pos.longitude}',
        creado: DateTime.now(),
      );
      await MensajesRepo.enviar(msg);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No se pudo obtener tu ubicación.')));
      }
    } finally {
      if (mounted) setState(() => _enviando = false);
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

  // ── Notas de voz (estilo WhatsApp: mantener para grabar) ────────────────────
  final AudioRecorder _rec = AudioRecorder();
  bool _grabando = false;
  bool _cancelandoGrab = false; // deslizó a la izquierda → soltar cancela
  bool _grabBloqueada = false; // deslizó arriba → manos libres
  int _segGrab = 0; // cronómetro
  Timer? _timerGrab;

  /// Empieza a grabar (al MANTENER presionado el micrófono).
  Future<void> _iniciarGrabacion() async {
    if (_grabando) return;
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
      _segGrab = 0;
      _timerGrab?.cancel();
      _timerGrab = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() => _segGrab++);
      });
      if (mounted) {
        setState(() {
          _grabando = true;
          _cancelandoGrab = false;
          _grabBloqueada = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _grabando = false);
    }
  }

  /// Mientras se mantiene, sigue el arrastre: izquierda = cancelar, arriba = bloquear.
  void _arrastreGrab(Offset delta) {
    if (!_grabando || _grabBloqueada) return;
    if (delta.dy < -70) {
      setState(() {
        _grabBloqueada = true;
        _cancelandoGrab = false;
      });
      return;
    }
    final cancelar = delta.dx < -90;
    if (cancelar != _cancelandoGrab) setState(() => _cancelandoGrab = cancelar);
  }

  /// Se soltó el micrófono. Si está bloqueada, sigue grabando (manos libres);
  /// si no, envía (o cancela si estaba deslizando a la izquierda).
  Future<void> _soltarGrab() async {
    if (!_grabando || _grabBloqueada) return;
    await _finGrabacion(cancelar: _cancelandoGrab);
  }

  /// Termina la grabación: sube y envía, o descarta si se canceló / muy corta.
  Future<void> _finGrabacion({required bool cancelar}) async {
    _timerGrab?.cancel();
    final segs = _segGrab;
    String? ruta;
    try {
      ruta = await _rec.stop();
    } catch (_) {}
    if (mounted) {
      setState(() {
        _grabando = false;
        _cancelandoGrab = false;
        _grabBloqueada = false;
        _segGrab = 0;
      });
    }
    // Cancelada, sin archivo o demasiado corta (< 1 s) → se descarta.
    if (cancelar || ruta == null || segs < 1) {
      if (ruta != null) {
        try {
          await File(ruta).delete();
        } catch (_) {}
      }
      return;
    }
    await _enviarAudio(ruta);
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
    // NO cortar si aún no hay clients (primera apertura): igual programamos el
    // salto para el próximo frame, cuando la lista ya esté montada. Así al abrir
    // el chat siempre se ven los ÚLTIMOS mensajes (abajo).
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
                    // "En línea" / "última vez …" (presencia) tiene prioridad.
                    if (!esGrupo && _otroEnLinea)
                      const Text('en línea',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 11.5,
                              fontWeight: FontWeight.w600))
                    else if (!esGrupo && _ultimaVezTexto() != null)
                      Text(_ultimaVezTexto()!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 11.5))
                    else if (recado != null && recado.isNotEmpty)
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
          // ── 1-a-1: videollamada + llamada de voz (Jitsi, gratis) ──
          if (_contraparteEmail.isNotEmpty &&
              !appState.bloqueado(_contraparteEmail)) ...[
            IconButton(
              tooltip: 'Videollamada',
              icon: const Icon(Icons.videocam, color: Colors.white),
              onPressed: () => _iniciarLlamada(video: true),
            ),
            IconButton(
              tooltip: 'Llamada de voz',
              icon: const Icon(Icons.call, color: Colors.white),
              onPressed: () => _iniciarLlamada(video: false),
            ),
          ],
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
                } else if (v == 'llamar_tel') {
                  final cel = appState.celularDe(e);
                  if (cel != null) _llamar(cel);
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
                  if (appState.celularDe(_contraparteEmail) != null)
                    const PopupMenuItem(
                      value: 'llamar_tel',
                      child: ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(Icons.phone_outlined),
                        title: Text('Llamar al número'),
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
                          // En grupo y en chat DIRECTO (1:1 entre dos usuarios),
                          // "mío" se decide por el CORREO del autor (como
                          // WhatsApp): así los mensajes que me envían salen a la
                          // izquierda. La lógica por rol (esProfe) solo aplica a
                          // los chats de academia/cancha (profe/dueño ↔ alumno).
                          final mio = (esGrupo || widget.tipo == 'directo')
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
                              onReaccion: (emoji) => _reaccionar(m, emoji),
                              onLlamar: (video) =>
                                  _iniciarLlamada(video: video));
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
              onGaleria: _menuAdjuntar, // clip → menú (Foto / Ubicación)
              onCamara: () => _enviarFoto(ImageSource.camera),
              grabando: _grabando,
              cancelandoGrab: _cancelandoGrab,
              grabBloqueada: _grabBloqueada,
              segGrab: _segGrab,
              onGrabInicio: _iniciarGrabacion,
              onGrabArrastre: _arrastreGrab,
              onGrabSoltar: _soltarGrab,
              onGrabEnviarBloqueada: () => _finGrabacion(cancelar: false),
              onGrabCancelarBloqueada: () => _finGrabacion(cancelar: true),
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
      this.onReaccion,
      this.onLlamar});
  final _Entrega entrega;
  final Mensaje mensaje;
  final bool mio;
  final _WA wa;
  final bool mostrarAutor; // en grupos: nombre del autor sobre el mensaje
  final Map<String, String> reacciones; // correo → emoji (de este mensaje)
  final VoidCallback? onResponder;
  final VoidCallback? onReenviar;
  final void Function(String emoji)? onReaccion;
  final void Function(bool video)? onLlamar; // rellamar desde el aviso de llamada

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
            if (mensaje.esLlamada)
              GestureDetector(
                onTap: () => onLlamar?.call(mensaje.esVideollamada),
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundColor: teal,
                        child: Icon(
                            mensaje.esVideollamada
                                ? Icons.videocam
                                : Icons.call,
                            color: Colors.white,
                            size: 19),
                      ),
                      const SizedBox(width: 10),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                              mensaje.esVideollamada
                                  ? 'Videollamada'
                                  : 'Llamada de voz',
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 14,
                                  color: mio ? wa.textoMio : wa.textoOtro)),
                          Text('Toca para llamar',
                              style: TextStyle(
                                  fontSize: 12, color: teal)),
                        ],
                      ),
                    ],
                  ),
                ),
              )
            else if (mensaje.esAudio)
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
              )
            else if (mensaje.esDocumento)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: _TarjetaDocumento(mensaje: mensaje, mio: mio, wa: wa),
              )
            else if (mensaje.esUbicacionVivo)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: _UbicacionVivoCard(
                  hilo: mensaje.hilo,
                  emailAutor: mensaje.autorEmail,
                  expiraMsg: mensaje.expiraVivo,
                  mio: mio,
                ),
              )
            else if (mensaje.esUbicacion)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: GestureDetector(
                  onTap: () {
                    final loc = mensaje.ubicacion;
                    if (loc == null) return;
                    launchUrl(
                      Uri.parse(
                          'https://www.google.com/maps/search/?api=1&query=${loc.lat},${loc.lng}'),
                      mode: LaunchMode.externalApplication,
                    );
                  },
                  child: Container(
                    width: 220,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                      color: mio
                          ? Colors.white.withOpacity(0.15)
                          : Colors.black.withOpacity(0.04),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _MapaMini(
                            lat: mensaje.ubicacion?.lat ?? 0,
                            lng: mensaje.ubicacion?.lng ?? 0),
                        Padding(
                          padding: const EdgeInsets.all(10),
                          child: Row(
                            children: [
                              const Icon(Icons.map_outlined,
                                  size: 18, color: teal),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text('Ver ubicación en el mapa',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                        color: mio
                                            ? wa.textoMio
                                            : wa.textoOtro)),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            Wrap(
          alignment: WrapAlignment.end,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: [
            if (mensaje.texto.isNotEmpty &&
                !mensaje.esLlamada &&
                !mensaje.esDocumento &&
                !(mensaje.tieneFoto && mensaje.texto == '📷 Foto') &&
                !(mensaje.esUbicacion && mensaje.texto == '📍 Ubicación') &&
                !mensaje.esUbicacionVivo &&
                !(mensaje.esAudio && mensaje.texto == '🎤 Nota de voz'))
              _TextoMensaje(
                  texto: mensaje.texto,
                  color: mio ? wa.textoMio : wa.textoOtro,
                  linkColor: mio ? Colors.white : teal),
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
    required this.cancelandoGrab,
    required this.grabBloqueada,
    required this.segGrab,
    required this.onGrabInicio,
    required this.onGrabArrastre,
    required this.onGrabSoltar,
    required this.onGrabEnviarBloqueada,
    required this.onGrabCancelarBloqueada,
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
  final bool cancelandoGrab;
  final bool grabBloqueada;
  final int segGrab;
  final VoidCallback onGrabInicio;
  final void Function(Offset delta) onGrabArrastre;
  final VoidCallback onGrabSoltar;
  final VoidCallback onGrabEnviarBloqueada;
  final VoidCallback onGrabCancelarBloqueada;
  final _WA wa;

  String _fmt(int s) => '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';

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
            // Pastilla: mientras GRABA muestra el cronómetro + hint; si no, el
            // campo de texto con emoji/adjuntar/cámara.
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
                            horizontal: 8, vertical: 10),
                        child: Row(
                          children: [
                            // Bloqueada → botón papelera para cancelar; si no,
                            // punto rojo parpadeando.
                            if (grabBloqueada)
                              GestureDetector(
                                onTap: onGrabCancelarBloqueada,
                                child: const Icon(Icons.delete_outline,
                                    color: Colors.red, size: 22),
                              )
                            else
                              const _PuntoGrabando(),
                            const SizedBox(width: 10),
                            Text(_fmt(segGrab),
                                style: TextStyle(
                                    color: wa.pillTexto,
                                    fontWeight: FontWeight.w700)),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                grabBloqueada
                                    ? 'Manos libres · toca ➤ para enviar'
                                    : (cancelandoGrab
                                        ? 'Suelta para cancelar'
                                        : '‹ Desliza para cancelar  ·  ↑ bloquear'),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    color: cancelandoGrab
                                        ? Colors.red
                                        : wa.hora,
                                    fontSize: 12.5,
                                    fontWeight: cancelandoGrab
                                        ? FontWeight.w700
                                        : FontWeight.w500),
                              ),
                            ),
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
                            tooltip: 'Adjuntar',
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
            // Botón circular derecho: con texto → enviar; grabando bloqueada →
            // enviar; vacío → MICRÓFONO (mantener presionado para grabar).
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (context, value, _) {
                final hayTexto = value.text.trim().isNotEmpty;
                if (enviando) {
                  return const _BotonCircular(
                      color: Color(0xFF00A884),
                      child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white)));
                }
                // Con texto → enviar (no micrófono).
                if (hayTexto && !grabando) {
                  return _BotonCircular(
                    color: wa.send,
                    onTap: onEnviar,
                    child: const Icon(Icons.send, color: Colors.white, size: 22),
                  );
                }
                // Grabando y bloqueada → botón de enviar.
                if (grabando && grabBloqueada) {
                  return _BotonCircular(
                    color: wa.send,
                    onTap: onGrabEnviarBloqueada,
                    child: const Icon(Icons.send, color: Colors.white, size: 22),
                  );
                }
                // Micrófono: MANTENER para grabar; arrastrar para cancelar/bloquear.
                final rec = grabando && !grabBloqueada;
                return GestureDetector(
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                        duration: Duration(milliseconds: 1400),
                        content: Text(
                            'Mantén presionado para grabar, suelta para enviar')));
                  },
                  onLongPressStart: (_) => onGrabInicio(),
                  onLongPressMoveUpdate: (d) =>
                      onGrabArrastre(d.offsetFromOrigin),
                  onLongPressEnd: (_) => onGrabSoltar(),
                  child: AnimatedScale(
                    scale: rec ? 1.25 : 1,
                    duration: const Duration(milliseconds: 150),
                    child: _BotonCircular(
                      color: rec ? Colors.red : wa.send,
                      child: const Icon(Icons.mic, color: Colors.white, size: 22),
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

/// Botón circular relleno (reutilizado por la barra de escritura).
class _BotonCircular extends StatelessWidget {
  const _BotonCircular({required this.color, required this.child, this.onTap});
  final Color color;
  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(padding: const EdgeInsets.all(11), child: child),
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
    // Como WhatsApp: baja la imagen y abre la hoja de compartir (guardar en
    // galería / enviar), en vez de mostrar el link crudo de Supabase.
    final nombre = url.split('?').first.split('/').last;
    await _descargarYCompartir(
        url, nombre.isEmpty ? 'imagen.jpg' : nombre);
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

/// Mini-mapa (imagen estática de Google Maps) para la previsualización de
/// ubicación en el chat, como WhatsApp. Si no hay key o falla la descarga, cae a
/// un placeholder con el pin — pero nunca a una imagen rota.
class _MapaMini extends StatelessWidget {
  const _MapaMini({required this.lat, required this.lng, this.height = 108});
  final double lat;
  final double lng;
  final double height;

  @override
  Widget build(BuildContext context) {
    final placeholder = Container(
      height: height,
      color: const Color(0xFFDCE7DA),
      child: const Center(
          child: Icon(Icons.location_on, color: clayOscuro, size: 42)),
    );
    final url = PlacesService.mapaEstaticoUrl(lat, lng);
    if (url.isEmpty) return placeholder;
    return CachedNetworkImage(
      imageUrl: url,
      height: height,
      width: double.infinity,
      fit: BoxFit.cover,
      placeholder: (_, __) => placeholder,
      errorWidget: (_, __, ___) => placeholder,
    );
  }
}

/// Descarga [url] y abre la HOJA DE COMPARTIR del sistema (guardar en galería,
/// enviar por WhatsApp, abrir con otra app…) — como WhatsApp, en vez de mostrar
/// el link crudo de Supabase. Si falla la descarga, cae a abrir el enlace.
Future<void> _descargarYCompartir(String url, String nombre) async {
  try {
    final resp = await http.get(Uri.parse(url));
    if (resp.statusCode != 200) throw Exception('descarga fallida');
    final dir = await getTemporaryDirectory();
    final seguro = nombre.trim().isEmpty
        ? 'archivo'
        : nombre.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
    final ruta = '${dir.path}/$seguro';
    await File(ruta).writeAsBytes(resp.bodyBytes);
    await Share.shareXFiles([XFile(ruta)]);
  } catch (_) {
    final uri = Uri.tryParse(url);
    if (uri != null) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }
}

/// Tarjeta de DOCUMENTO en el chat (pdf/docx/xlsx/zip…), estilo WhatsApp: ícono
/// según el tipo, nombre del archivo y descarga/compartir al tocar.
class _TarjetaDocumento extends StatelessWidget {
  const _TarjetaDocumento(
      {required this.mensaje, required this.mio, required this.wa});
  final Mensaje mensaje;
  final bool mio;
  final _WA wa;

  /// Ícono (FontAwesome, con "esquina doblada"), color de marca y tipo según la
  /// extensión — como WhatsApp (PDF rojo, Word azul, Excel verde…).
  ({IconData icono, Color color}) get _info {
    final n = mensaje.nombreArchivo.toLowerCase();
    if (n.endsWith('.pdf')) {
      return (icono: FontAwesomeIcons.filePdf, color: const Color(0xFFE5342A));
    }
    if (n.endsWith('.doc') || n.endsWith('.docx')) {
      return (icono: FontAwesomeIcons.fileWord, color: const Color(0xFF2B579A));
    }
    if (n.endsWith('.xls') || n.endsWith('.xlsx') || n.endsWith('.csv')) {
      return (
        icono: FontAwesomeIcons.fileExcel,
        color: const Color(0xFF217346)
      );
    }
    if (n.endsWith('.ppt') || n.endsWith('.pptx')) {
      return (
        icono: FontAwesomeIcons.filePowerpoint,
        color: const Color(0xFFD24726)
      );
    }
    if (n.endsWith('.zip') || n.endsWith('.rar') || n.endsWith('.7z')) {
      return (
        icono: FontAwesomeIcons.fileZipper,
        color: const Color(0xFF8E7B4C)
      );
    }
    if (n.endsWith('.txt')) {
      return (icono: FontAwesomeIcons.fileLines, color: Colors.blueGrey);
    }
    return (icono: FontAwesomeIcons.file, color: Colors.blueGrey);
  }

  /// Extensión en mayúsculas para el subtítulo (ej. "PDF", "DOCX").
  String get _tipo {
    final n = mensaje.nombreArchivo;
    final dot = n.lastIndexOf('.');
    if (dot < 0 || dot == n.length - 1) return 'ARCHIVO';
    return n.substring(dot + 1).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final txt = mio ? wa.textoMio : wa.textoOtro;
    final info = _info;
    return GestureDetector(
      onTap: () =>
          _descargarYCompartir(mensaje.mediaUrl, mensaje.nombreArchivo),
      child: Container(
        width: 236,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: mio
              ? Colors.white.withOpacity(0.12)
              : Colors.black.withOpacity(0.04),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 44,
              decoration: BoxDecoration(
                color: info.color.withOpacity(0.14),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: FaIcon(info.icono, color: info.color, size: 22),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(mensaje.nombreArchivo,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: txt)),
                  const SizedBox(height: 3),
                  Text('$_tipo · toca para abrir',
                      style: TextStyle(
                          fontSize: 11.5, color: txt.withOpacity(0.55))),
                ],
              ),
            ),
            const SizedBox(width: 6),
            Icon(Icons.download_rounded, size: 20, color: txt.withOpacity(0.5)),
          ],
        ),
      ),
    );
  }
}

/// Tarjeta de UBICACIÓN EN TIEMPO REAL (estilo WhatsApp). Relee la posición del
/// autor en `pichangol_ubicacion_vivo` cada pocos segundos: mientras esté activa
/// muestra "En vivo" + hace cuánto fue el último punto y abre el mapa con la
/// posición MÁS RECIENTE. Si es MÍA, ofrece "Detener". Al vencer/parar → "Compartir
/// finalizado".
class _UbicacionVivoCard extends StatefulWidget {
  const _UbicacionVivoCard({
    required this.hilo,
    required this.emailAutor,
    required this.expiraMsg,
    required this.mio,
  });

  final String hilo;
  final String emailAutor;
  final DateTime? expiraMsg; // tope según el mensaje (la parada real la da la BD)
  final bool mio;

  @override
  State<_UbicacionVivoCard> createState() => _UbicacionVivoCardState();
}

class _UbicacionVivoCardState extends State<_UbicacionVivoCard> {
  Timer? _poll;
  UbicacionVivo? _pos;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _refrescar();
    // Refresco frecuente mientras la burbuja esté visible (mueve el pin).
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _refrescar());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refrescar() async {
    final p = await UbicacionVivoRepo.ultima(
        hilo: widget.hilo, email: widget.emailAutor);
    if (!mounted) return;
    setState(() {
      _pos = p;
      _cargando = false;
    });
  }

  bool get _activa {
    final p = _pos;
    if (p != null) return p.activa; // la BD manda (incluye parada anticipada)
    // Sin fila aún: cae al tope del mensaje.
    final exp = widget.expiraMsg;
    return exp != null && DateTime.now().isBefore(exp);
  }

  String _haceCuanto(DateTime t) {
    final s = DateTime.now().difference(t).inSeconds;
    if (s < 15) return 'ahora mismo';
    if (s < 60) return 'hace ${s}s';
    final m = s ~/ 60;
    if (m < 60) return 'hace $m min';
    return 'hace ${m ~/ 60} h';
  }

  /// "Finaliza en X min" / "Finaliza a las HH:MM" (como WhatsApp). '' si no aplica.
  String _finalizaTexto() {
    final exp = _pos?.expira ?? widget.expiraMsg;
    if (exp == null) return '';
    final mins = exp.difference(DateTime.now()).inMinutes;
    if (mins <= 0) return '';
    if (mins < 60) return 'Finaliza en $mins min';
    final hh = exp.hour.toString().padLeft(2, '0');
    final mm = exp.minute.toString().padLeft(2, '0');
    return 'Finaliza a las $hh:$mm';
  }

  Future<void> _detener() async {
    await UbicacionVivoService.instance.detener();
    await _refrescar();
  }

  void _abrirMapa() {
    final p = _pos;
    if (p == null) return;
    launchUrl(
      Uri.parse(
          'https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}'),
      mode: LaunchMode.externalApplication,
    );
  }

  @override
  Widget build(BuildContext context) {
    final activa = _activa;
    final dark = Theme.of(context).brightness == Brightness.dark;
    // Texto oscuro sobre burbuja verde clara (o claro en modo oscuro): antes iba
    // blanco y no se leía en mis burbujas.
    final txt = dark ? const Color(0xFFE9EDEF) : const Color(0xFF111B21);
    final p = _pos;
    final foto = appState.fotoDe(widget.emailAutor);
    return Container(
      width: 230,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: dark
            ? Colors.white.withOpacity(0.10)
            : Colors.black.withOpacity(0.04),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GestureDetector(
            onTap: p != null ? _abrirMapa : null,
            child: (p != null)
                ? Stack(
                    alignment: Alignment.center,
                    children: [
                      _MapaMini(lat: p.lat, lng: p.lng),
                      // Terminada: el mapa se mantiene pero ATENUADO (como
                      // WhatsApp), no un cuadro gris plano.
                      if (!activa)
                        Positioned.fill(
                          child: Container(
                              color: Colors.black.withOpacity(0.38)),
                        ),
                      // Marcador con la foto del que comparte (gris si terminó).
                      Opacity(
                        opacity: activa ? 1 : 0.75,
                        child: Container(
                          padding: const EdgeInsets.all(2),
                          decoration: const BoxDecoration(
                              color: Colors.white, shape: BoxShape.circle),
                          child: CircleAvatar(
                            radius: 16,
                            backgroundColor: activa ? teal : Colors.grey,
                            backgroundImage: (foto != null && foto.isNotEmpty)
                                ? NetworkImage(foto)
                                : null,
                            child: (foto == null || foto.isEmpty)
                                ? const Icon(Icons.person,
                                    color: Colors.white, size: 18)
                                : null,
                          ),
                        ),
                      ),
                    ],
                  )
                : Container(
                    height: 108,
                    color: activa
                        ? const Color(0xFFDCE7DA)
                        : const Color(0xFFE6E6E6),
                    child: Center(
                      child: Icon(
                          activa ? Icons.my_location : Icons.location_off,
                          color: activa ? teal : Colors.grey,
                          size: 42),
                    ),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    if (activa) ...[
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                            color: Color(0xFF2ECC71), shape: BoxShape.circle),
                      ),
                      const SizedBox(width: 6),
                    ],
                    const Text('Ubicación en tiempo real',
                        style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 13,
                            color: Color(0xFF128C7E))),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  _cargando
                      ? 'Cargando…'
                      : (!activa
                          ? 'Compartir finalizado'
                          : (_finalizaTexto().isNotEmpty
                              ? _finalizaTexto()
                              : (_pos == null
                                  ? 'Esperando ubicación…'
                                  : 'Actualizado ${_haceCuanto(_pos!.actualizado)}'))),
                  style: TextStyle(
                      fontSize: 11.5, color: txt.withOpacity(0.6)),
                ),
                if (activa) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      InkWell(
                        onTap: _pos == null ? null : _abrirMapa,
                        child: const Row(children: [
                          Icon(Icons.map_outlined, size: 16, color: teal),
                          SizedBox(width: 4),
                          Text('Ver mapa',
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 12,
                                  color: teal)),
                        ]),
                      ),
                      if (widget.mio) ...[
                        const Spacer(),
                        InkWell(
                          onTap: _detener,
                          child: const Text('Detener',
                              style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 12,
                                  color: clayOscuro)),
                        ),
                      ],
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Un ícono redondo de color con su etiqueta, para la grilla del clip (estilo
/// WhatsApp: Galería / Cámara / Ubicación).
class _AccionAdjunto extends StatelessWidget {
  const _AccionAdjunto({
    required this.icon,
    required this.color,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final Color color;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: SizedBox(
        width: 68,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 58,
              height: 58,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: Icon(icon, color: Colors.white, size: 26),
            ),
            const SizedBox(height: 7),
            Text(label,
                style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                    color: textoTenueDe(context))),
          ],
        ),
      ),
    );
  }
}

/// Texto de un mensaje con los enlaces tocables (tipo WhatsApp). Sirve para el
/// enlace de "Únete" de una llamada y para cualquier link que se comparta.
class _TextoMensaje extends StatefulWidget {
  const _TextoMensaje(
      {required this.texto, required this.color, required this.linkColor});
  final String texto;
  final Color color;
  final Color linkColor;

  @override
  State<_TextoMensaje> createState() => _TextoMensajeState();
}

class _TextoMensajeState extends State<_TextoMensaje> {
  static final _re = RegExp(r'((https?:\/\/|www\.)[^\s]+)', caseSensitive: false);
  final List<TapGestureRecognizer> _recs = [];

  @override
  void dispose() {
    for (final r in _recs) {
      r.dispose();
    }
    super.dispose();
  }

  Future<void> _abrir(String url) async {
    // Si es una sala Pichangol, únete DENTRO de la app (Jitsi embebido).
    final sala = LlamadaService.salaDeEnlace(url);
    if (sala != null) {
      final yo = appState.usuario;
      final ok = await LlamadaService.unir(
        sala: sala,
        audioSolo: url.contains('startAudioOnly'),
        nombre: yo?.nombre ?? '',
        email: yo?.email ?? '',
      );
      if (ok) return;
    }
    var u = url;
    if (!u.startsWith('http')) u = 'https://$u';
    try {
      await launchUrl(Uri.parse(u), mode: LaunchMode.externalApplication);
    } catch (_) {}
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
      final rec = TapGestureRecognizer()..onTap = () => _abrir(url);
      _recs.add(rec);
      spans.add(TextSpan(
        text: url,
        style: TextStyle(
            color: widget.linkColor,
            decoration: TextDecoration.underline,
            fontWeight: FontWeight.w600),
        recognizer: rec,
      ));
      last = m.end;
    }
    if (last < t.length) spans.add(TextSpan(text: t.substring(last)));
    return Text.rich(TextSpan(
        style: TextStyle(color: widget.color, fontSize: 15.5), children: spans));
  }
}
