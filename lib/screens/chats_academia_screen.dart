import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'chat_screen.dart';

/// Bandeja de chats del PROFE: un hilo por cada cuenta de alumno-app de su
/// academia, con el último mensaje y un contador de no leídos. En vivo.
///
/// En pantallas ANCHAS (tablet, dentro del panel con menú lateral) usa
/// **master-detail**: la lista a la izquierda y el chat abierto a la derecha, así
/// el menú lateral SIEMPRE queda visible. En móvil, la lista ocupa todo y el chat
/// se abre a pantalla completa.
class ChatsAcademiaScreen extends StatefulWidget {
  const ChatsAcademiaScreen({super.key, required this.academiaId});
  final String academiaId;

  @override
  State<ChatsAcademiaScreen> createState() => _ChatsAcademiaScreenState();
}

/// Fila resuelta de la bandeja.
typedef _Fila = ({String email, String nombre, String hilo, Mensaje? ult});

class _ChatsAcademiaScreenState extends State<ChatsAcademiaScreen> {
  // Panel derecho (tablet): conversación abierta.
  String? _hiloSel;
  String _emailSel = '';
  String _tituloSel = '';
  // Correos cuyos perfiles ya pedimos (evita repetir la consulta a Supabase).
  final Set<String> _perfilesPedidos = {};

  /// Pide a Supabase los perfiles (nombre/foto) que aún no tenemos.
  void _pedirPerfiles(Iterable<String> emails) {
    final nuevos = emails
        .map((e) => e.trim().toLowerCase())
        .where((e) => e.isNotEmpty && !_perfilesPedidos.contains(e))
        .toList();
    if (nuevos.isEmpty) return;
    _perfilesPedidos.addAll(nuevos);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      appState.cargarPerfiles(nuevos);
    });
  }

  // Tablet: la lista de conversaciones se puede colapsar para dar más ancho al
  // chat. Cabecera verde igual a la del chat → alineadas (estilo WhatsApp Web).
  bool _listaColapsada = false;

  Color _headerBg(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF1F2C34)
          : const Color(0xFF008069);

  /// Cabecera del panel MASTER (lista): en tablet trae el botón de COLAPSAR; en
  /// móvil, el de volver. Misma altura/color que la cabecera del chat.
  Widget _headerMaster(BuildContext context, {required bool colapsable}) {
    return Material(
      color: _headerBg(context),
      child: SizedBox(
        height: kToolbarHeight,
        child: Row(children: [
          IconButton(
            tooltip: colapsable ? 'Ocultar lista' : 'Volver',
            icon: Icon(colapsable ? Icons.chevron_left : Icons.arrow_back,
                color: Colors.white),
            onPressed: colapsable
                ? () => setState(() => _listaColapsada = true)
                : () => Navigator.of(context).maybePop(),
          ),
          const Text('Mensajes',
              style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 20)),
        ]),
      ),
    );
  }

  Widget _avisoConHeader(String texto) => Column(children: [
        _headerMaster(context, colapsable: false),
        Expanded(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
            ),
          ),
        ),
      ]);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: MensajesRepo.disponible
            ? StreamBuilder<List<Mensaje>>(
                stream: MensajesRepo.streamAcademia(widget.academiaId),
                builder: (context, snap) {
                  final msgs = snap.data ?? const <Mensaje>[];
                  return ListenableBuilder(
                    listenable: appState,
                    builder: (context, _) => _cuerpo(context, msgs),
                  );
                },
              )
            : _avisoConHeader(
                'El chat necesita conexión con el servidor. Intenta más tarde.'),
      ),
    );
  }

  /// Nombre a mostrar de una cuenta: el de su perfil (elegido) manda; si no, el
  /// del alumno/mensaje; si no, el correo.
  String _nombreDe(String email, String fallback) {
    final perfil = appState.nombreMostrableDe(email);
    if (perfil != null) return perfil;
    return fallback.isNotEmpty ? fallback : email;
  }

  Widget _cuerpo(BuildContext context, List<Mensaje> msgs) {
    // Cuentas de alumno-app de esta academia (email → nombre a mostrar).
    final cuentas = <String, String>{};
    for (final a in appState.alumnosDe(widget.academiaId)) {
      if (a.email.isEmpty) continue;
      final key = a.email.toLowerCase();
      final nombre = a.esMenor ? a.apoderadoNombre : a.nombre;
      cuentas.putIfAbsent(key, () => nombre.isNotEmpty ? nombre : a.email);
      if (!a.esMenor && a.nombre.isNotEmpty) cuentas[key] = a.nombre;
    }
    // Cuentas que sólo aparecen en mensajes (escribieron sin figurar aún).
    for (final m in msgs) {
      final key = m.cuentaEmail.toLowerCase();
      if (!cuentas.containsKey(key)) {
        cuentas[key] =
            m.esProfe ? key : (m.autorNombre.isEmpty ? key : m.autorNombre);
      }
    }

    // Trae los perfiles (nombre/foto) de todas las cuentas para no mostrar el
    // correo pelado.
    _pedirPerfiles(cuentas.keys);

    if (cuentas.isEmpty) {
      return _avisoConHeader(
          'Aún no tienes alumnos que usen la app. Invítalos por correo o con tu '
          'código y podrás chatear con ellos aquí.');
    }

    // Último mensaje por hilo.
    final ultimo = <String, Mensaje>{};
    for (final m in msgs) {
      ultimo[m.hilo] = m; // msgs viene ascendente → queda el más nuevo
    }

    final filas = cuentas.entries.map((e) {
      final hilo = Mensaje.hiloDe(widget.academiaId, e.key);
      return (email: e.key, nombre: e.value, hilo: hilo, ult: ultimo[hilo]);
    }).toList()
      ..sort((a, b) {
        final ta = a.ult?.creado;
        final tb = b.ult?.creado;
        if (ta != null && tb != null) return tb.compareTo(ta);
        if (ta != null) return -1;
        if (tb != null) return 1;
        return a.nombre.toLowerCase().compareTo(b.nombre.toLowerCase());
      });

    // ¿Hay espacio para master-detail? En el panel con menú lateral (tablet) sí;
    // en móvil (lista pushada a pantalla completa) no.
    return LayoutBuilder(builder: (context, cons) {
      final ancho = cons.maxWidth >= 640;
      final lista = _ListaHilos(
        filas: filas,
        msgs: msgs,
        nombreDe: _nombreDe,
        seleccion: ancho ? _hiloSel : null,
        onTap: (f) => _abrir(context, f, ancho),
      );
      // Móvil: solo la lista, con su cabecera.
      if (!ancho) {
        return Column(children: [
          _headerMaster(context, colapsable: false),
          Expanded(child: lista),
        ]);
      }
      // Tablet: master-detail con lista COLAPSABLE y cabeceras alineadas.
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!_listaColapsada) ...[
            SizedBox(
              width: 340,
              child: Column(children: [
                _headerMaster(context, colapsable: true),
                Expanded(child: lista),
              ]),
            ),
            const VerticalDivider(width: 1),
          ] else
            Column(children: [
              Material(
                color: _headerBg(context),
                child: SizedBox(
                  height: kToolbarHeight,
                  width: 48,
                  child: IconButton(
                    tooltip: 'Mostrar conversaciones',
                    icon:
                        const Icon(Icons.chevron_right, color: Colors.white),
                    onPressed: () => setState(() => _listaColapsada = false),
                  ),
                ),
              ),
              const Expanded(child: SizedBox(width: 48)),
            ]),
          Expanded(child: _panelDetalle()),
        ],
      );
    });
  }

  void _abrir(BuildContext context, _Fila f, bool ancho) {
    final titulo = _nombreDe(f.email, f.nombre);
    if (ancho) {
      setState(() {
        _hiloSel = f.hilo;
        _emailSel = f.email;
        _tituloSel = titulo;
      });
    } else {
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ChatScreen(
          academiaId: widget.academiaId,
          cuentaEmail: f.email,
          titulo: titulo,
          soyProfe: true,
        ),
      ));
    }
  }

  /// Panel derecho: el chat abierto, o un aviso para elegir uno.
  Widget _panelDetalle() {
    if (_hiloSel == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: const [
              Icon(Icons.forum_outlined, size: 54, color: textoTenue),
              SizedBox(height: 12),
              Text('Elige una conversación para chatear.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: textoTenue)),
            ],
          ),
        ),
      );
    }
    return ChatScreen(
      key: ValueKey(_hiloSel),
      academiaId: widget.academiaId,
      cuentaEmail: _emailSel,
      titulo: _tituloSel,
      soyProfe: true,
      embebido: true,
    );
  }
}

/// Lista de hilos (columna izquierda o pantalla completa).
class _ListaHilos extends StatelessWidget {
  const _ListaHilos({
    required this.filas,
    required this.msgs,
    required this.nombreDe,
    required this.seleccion,
    required this.onTap,
  });
  final List<_Fila> filas;
  final List<Mensaje> msgs;
  final String Function(String email, String fallback) nombreDe;
  final String? seleccion;
  final void Function(_Fila) onTap;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: filas.length,
      separatorBuilder: (_, __) =>
          Divider(height: 1, color: trazo.withOpacity(0.6)),
      itemBuilder: (_, i) {
        final f = filas[i];
        final leida = appState.chatUltimaLectura(f.hilo);
        var noLeidos = 0;
        for (final m in msgs) {
          if (m.hilo != f.hilo) continue;
          if (m.esProfe) continue; // sólo cuentan los del alumno
          if (leida == null || m.creado.isAfter(leida)) noLeidos++;
        }
        return _FilaHilo(
          nombre: nombreDe(f.email, f.nombre),
          foto: appState.fotoDe(f.email),
          preview: f.ult?.texto ?? 'Toca para escribir',
          noLeidos: noLeidos,
          seleccionado: seleccion != null && seleccion == f.hilo,
          onTap: () => onTap(f),
        );
      },
    );
  }
}

class _FilaHilo extends StatelessWidget {
  const _FilaHilo({
    required this.nombre,
    required this.foto,
    required this.preview,
    required this.noLeidos,
    required this.seleccionado,
    required this.onTap,
  });
  final String nombre;
  final String? foto;
  final String preview;
  final int noLeidos;
  final bool seleccionado;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tieneFoto = foto != null && foto!.isNotEmpty;
    return ListTile(
      onTap: onTap,
      selected: seleccionado,
      selectedTileColor: cs.primary.withOpacity(0.08),
      leading: CircleAvatar(
        backgroundColor: cs.primary.withOpacity(0.15),
        backgroundImage: tieneFoto ? NetworkImage(foto!) : null,
        child: tieneFoto
            ? null
            : Text(
                nombre.isNotEmpty ? nombre.characters.first.toUpperCase() : '?',
                style:
                    TextStyle(color: cs.primary, fontWeight: FontWeight.w800)),
      ),
      title: Text(nombre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(preview,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: textoTenue)),
      trailing: noLeidos == 0
          ? const Icon(Icons.chevron_right, color: textoTenue)
          : Container(
              padding: const EdgeInsets.all(7),
              decoration:
                  BoxDecoration(color: cs.primary, shape: BoxShape.circle),
              child: Text('$noLeidos',
                  style: TextStyle(
                      color: cs.onPrimary,
                      fontSize: 11,
                      fontWeight: FontWeight.w800)),
            ),
    );
  }
}
