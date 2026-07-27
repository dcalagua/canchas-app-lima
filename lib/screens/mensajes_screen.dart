import 'package:flutter/material.dart';

import '../data/grupos_repo.dart';
import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import 'buscar_usuario_screen.dart';
import 'chat_screen.dart';
import 'crear_grupo_screen.dart';
import 'login_google_sheet.dart';

/// Inbox unificado "Mensajes": junta en UN solo lugar todas las conversaciones
/// del usuario logueado (como profe de sus academias y como alumno de las que
/// pertenece). Es la pestaña fija de chat, siempre a la mano. Preparado para
/// sumar chats de canchas y grupos más adelante.
class MensajesScreen extends StatefulWidget {
  const MensajesScreen({super.key, this.abrirHilo});

  /// Si se abre desde una notificación, el hilo a abrir automáticamente al cargar.
  final String? abrirHilo;

  @override
  State<MensajesScreen> createState() => _MensajesScreenState();
}

/// Filtros de la bandeja (chips estilo WhatsApp, look Airbnb).
enum _FiltroChat { todos, noLeidos, grupos, fijados }

/// Descriptor de una conversación para pintar la fila del inbox.
class _Conv {
  _Conv({
    required this.hilo,
    required this.academiaId,
    required this.cuentaEmail,
    required this.titulo,
    required this.preview,
    required this.soyProfe,
    required this.cuando,
    required this.noLeidos,
    this.tipo = 'academia',
    this.refId = '',
  });
  final String hilo;
  final String academiaId;
  final String cuentaEmail;
  final String titulo;
  final String preview;
  final bool soyProfe;
  final DateTime cuando;
  final int noLeidos;
  final String tipo; // 'academia' | 'cancha'
  final String refId; // canchaId/dueño para cancha
}

class _MensajesScreenState extends State<MensajesScreen> {
  bool _cargando = true;
  List<_Conv> _convs = const [];
  // Panel derecho (tablet, master-detail): conversación abierta.
  _Conv? _sel;
  // Hilos ya abiertos en el panel → se muestran sin badge de no leídos.
  final Set<String> _abiertos = {};

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    if (mounted) setState(() => _cargando = true);
    final email = (appState.usuario?.email ?? '').toLowerCase();
    if (email.isEmpty) {
      if (mounted) setState(() {
        _cargando = false;
        _convs = const [];
      });
      return;
    }
    // Academias donde el usuario es dueño (profe) o alumno.
    final owned = <String>{};
    for (final a in appState.academias) {
      if (a.dueno.toLowerCase() == email) owned.add(a.id);
    }
    final student = <String>{};
    for (final al in appState.alumnos) {
      if (al.email.toLowerCase() == email) student.add(al.academiaId);
    }
    final ids = {...owned, ...student}.toList();
    final msgs = await MensajesRepo.mensajesDeAcademias(ids);
    // Carga los perfiles (nombre/foto elegidos) de las contrapartes para
    // mostrar su NOMBRE y foto en vez del correo.
    await appState.cargarPerfiles([
      for (final m in msgs) m.cuentaEmail,
      for (final m in msgs) m.autorEmail,
    ]);

    // Agrupa por hilo (vienen en orden ascendente → el último es el más nuevo).
    final porHilo = <String, List<Mensaje>>{};
    for (final m in msgs) {
      porHilo.putIfAbsent(m.hilo, () => []).add(m);
    }
    final convs = <_Conv>[];
    porHilo.forEach((hilo, list) {
      final primero = list.first;
      final acId = primero.academiaId;
      final esProfe = owned.contains(acId);
      // Si soy alumno (no dueño), solo mi propio hilo — nunca los de otros.
      if (!esProfe && primero.cuentaEmail.toLowerCase() != email) return;
      final ultimo = list.last;
      final String titulo;
      final String cuenta;
      if (esProfe) {
        cuenta = primero.cuentaEmail;
        titulo = _nombreAlumno(acId, cuenta);
      } else {
        cuenta = email;
        titulo = _nombreAcademia(acId);
      }
      final leida = appState.chatUltimaLectura(hilo);
      var noLeidos = 0;
      for (final x in list) {
        if (x.autorEmail.toLowerCase() == email) continue; // los míos no cuentan
        if (leida == null || x.creado.isAfter(leida)) noLeidos++;
      }
      convs.add(_Conv(
        hilo: hilo,
        academiaId: acId,
        cuentaEmail: cuenta,
        titulo: titulo,
        preview: ultimo.texto,
        soyProfe: esProfe,
        cuando: ultimo.creado,
        noLeidos: noLeidos,
        tipo: 'academia',
        refId: acId,
      ));
    });

    // Conversaciones de CANCHA (dueño ↔ jugador). refId = email del dueño.
    final msgsCancha = await MensajesRepo.mensajesCanchaDe(email);
    await appState.cargarPerfiles([
      for (final m in msgsCancha) m.cuentaEmail,
      for (final m in msgsCancha) m.autorEmail,
    ]);
    final porHiloC = <String, List<Mensaje>>{};
    for (final m in msgsCancha) {
      porHiloC.putIfAbsent(m.hilo, () => []).add(m);
    }
    porHiloC.forEach((hilo, list) {
      final owner = list.first.refEfectivo.toLowerCase();
      final soyDueno = owner == email;
      final ultimo = list.last;
      final String titulo;
      final String cuenta;
      if (soyDueno) {
        cuenta = list.first.cuentaEmail;
        titulo = _nombreJugador(list, cuenta);
      } else {
        cuenta = email;
        titulo = _nombreLocalDe(owner);
      }
      final leida = appState.chatUltimaLectura(hilo);
      var noLeidos = 0;
      for (final x in list) {
        if (x.autorEmail.toLowerCase() == email) continue;
        if (leida == null || x.creado.isAfter(leida)) noLeidos++;
      }
      convs.add(_Conv(
        hilo: hilo,
        academiaId: '',
        cuentaEmail: cuenta,
        titulo: titulo,
        preview: ultimo.texto,
        soyProfe: soyDueno,
        cuando: ultimo.creado,
        noLeidos: noLeidos,
        tipo: 'cancha',
        refId: owner,
      ));
    });

    // Conversaciones de GRUPO (usuarios registrados).
    final grupos = await GruposRepo.gruposDe(email);
    final grupoIds = grupos.map((g) => g.id).toList();
    final msgsGrupo = await MensajesRepo.mensajesDeGrupos(grupoIds);
    final porGrupo = <String, List<Mensaje>>{};
    for (final m in msgsGrupo) {
      porGrupo.putIfAbsent(m.refEfectivo, () => []).add(m);
    }
    for (final g in grupos) {
      final list = porGrupo[g.id] ?? const <Mensaje>[];
      final ultimo = list.isNotEmpty ? list.last : null;
      final hilo = Mensaje.hiloGrupo(g.id);
      final leida = appState.chatUltimaLectura(hilo);
      var noLeidos = 0;
      for (final x in list) {
        if (x.autorEmail.toLowerCase() == email) continue;
        if (leida == null || x.creado.isAfter(leida)) noLeidos++;
      }
      final preview = ultimo != null
          ? (ultimo.autorNombre.isNotEmpty
              ? '${ultimo.autorNombre}: ${ultimo.texto}'
              : ultimo.texto)
          : '${g.miembros.length} miembros · toca para escribir';
      convs.add(_Conv(
        hilo: hilo,
        academiaId: '',
        cuentaEmail: '',
        titulo: g.nombre,
        preview: preview,
        soyProfe: false,
        cuando: ultimo?.creado ?? DateTime.now(),
        noLeidos: noLeidos,
        tipo: 'grupo',
        refId: g.id,
      ));
    }

    // Conversaciones DIRECTAS 1:1 (buscador / contactos, tipo WhatsApp).
    final msgsDir = await MensajesRepo.mensajesDirectosDe(email);
    await appState.cargarPerfiles([
      for (final m in msgsDir) m.autorEmail,
      for (final m in msgsDir) m.cuentaEmail,
    ]);
    final porHiloD = <String, List<Mensaje>>{};
    for (final m in msgsDir) {
      porHiloD.putIfAbsent(m.hilo, () => []).add(m);
    }
    porHiloD.forEach((hilo, list) {
      // El "otro" = el participante que no soy yo.
      var otro = '';
      for (final m in list) {
        if (m.autorEmail.toLowerCase() != email) {
          otro = m.autorEmail;
          break;
        }
        if (m.cuentaEmail.toLowerCase() != email) {
          otro = m.cuentaEmail;
          break;
        }
      }
      if (otro.isEmpty) return;
      final ultimo = list.last;
      final leida = appState.chatUltimaLectura(hilo);
      var noLeidos = 0;
      for (final x in list) {
        if (x.autorEmail.toLowerCase() == email) continue;
        if (leida == null || x.creado.isAfter(leida)) noLeidos++;
      }
      convs.add(_Conv(
        hilo: hilo,
        academiaId: '',
        cuentaEmail: otro,
        titulo: appState.nombreMostrableDe(otro) ?? otro,
        preview: ultimo.texto,
        soyProfe: false,
        cuando: ultimo.creado,
        noLeidos: noLeidos,
        tipo: 'directo',
        refId: '',
      ));
    });

    // Quita los chats que el usuario eliminó de su bandeja. Reaparecen solos si
    // llega un mensaje más nuevo que el momento en que se ocultaron (WhatsApp).
    convs.removeWhere((c) => appState.chatOculto(c.hilo, c.cuando));
    convs.sort((a, b) => b.cuando.compareTo(a.cuando));
    if (!mounted) return;
    setState(() {
      _convs = convs;
      _cargando = false;
    });
    _abrirHiloPendiente(); // si vino de una notificación, entra al chat
  }

  bool _autoAbierto = false;

  /// Abre automáticamente el chat indicado por [widget.abrirHilo] (deep-link de
  /// notificación), una sola vez, a pantalla completa.
  void _abrirHiloPendiente() {
    final hilo = widget.abrirHilo;
    if (hilo == null || hilo.isEmpty || _autoAbierto) return;
    _Conv? match;
    for (final c in _convs) {
      if (c.hilo == hilo) {
        match = c;
        break;
      }
    }
    if (match == null) return;
    _autoAbierto = true;
    final c = match;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Navigator.of(context)
          .push(MaterialPageRoute(
            builder: (_) => ChatScreen(
              academiaId: c.academiaId,
              cuentaEmail: c.cuentaEmail,
              titulo: c.titulo,
              soyProfe: c.soyProfe,
              tipo: c.tipo,
              refId: c.refId,
            ),
          ))
          .then((_) => _cargar());
    });
  }

  String _nombreAlumno(String acId, String cuenta) {
    // El nombre que la persona eligió (perfil) manda sobre el correo.
    final perfil = appState.nombreMostrableDe(cuenta);
    if (perfil != null) return perfil;
    for (final al in appState.alumnos) {
      if (al.academiaId == acId &&
          al.email.toLowerCase() == cuenta.toLowerCase()) {
        if (al.esMenor && al.apoderadoNombre.isNotEmpty) {
          return al.apoderadoNombre;
        }
        return al.nombre.isNotEmpty ? al.nombre : cuenta;
      }
    }
    return cuenta;
  }

  String _nombreAcademia(String acId) {
    for (final a in appState.academias) {
      if (a.id == acId) return a.nombre;
    }
    return 'Academia';
  }

  /// Nombre del jugador en una conversación de cancha (perfil > mensajes > correo).
  String _nombreJugador(List<Mensaje> list, String cuenta) {
    final perfil = appState.nombreMostrableDe(cuenta);
    if (perfil != null) return perfil;
    for (final m in list) {
      if (m.autorEmail.toLowerCase() == cuenta.toLowerCase() &&
          m.autorNombre.isNotEmpty) {
        return m.autorNombre;
      }
    }
    return cuenta;
  }

  /// Nombre del local para el jugador (por el email del dueño).
  String _nombreLocalDe(String ownerEmail) {
    for (final c in appState.todasLasCanchas()) {
      if (c.dueno.toLowerCase() == ownerEmail) {
        return c.club.isNotEmpty ? c.club : c.nombre;
      }
    }
    return 'Dueño de cancha';
  }

  /// Abre una conversación. En pantallas anchas (tablet) la muestra en el panel
  /// derecho (el menú lateral sigue visible); en móvil, a pantalla completa.
  void _abrir(_Conv c, bool ancho) {
    if (ancho) {
      setState(() {
        _sel = c;
        _abiertos.add(c.hilo);
      });
    } else {
      Navigator.of(context)
          .push(MaterialPageRoute(
            builder: (_) => ChatScreen(
              academiaId: c.academiaId,
              cuentaEmail: c.cuentaEmail,
              titulo: c.titulo,
              soyProfe: c.soyProfe,
              tipo: c.tipo,
              refId: c.refId,
            ),
          ))
          .then((_) => _cargar()); // al volver, refresca no-leídos/preview
    }
  }

  /// Alterna el marcado de un chat en modo selección (WhatsApp). Al quedar en 0,
  /// sale del modo selección solo.
  void _toggleSeleccion(String hilo) {
    setState(() {
      if (!_seleccion.remove(hilo)) _seleccion.add(hilo);
    });
  }

  /// Buscador + chips de filtro de la bandeja (Todos · No leídos · Grupos ·
  /// Fijados), estilo WhatsApp con pastillas Airbnb.
  Widget _buscadorYFiltros(BuildContext context, int noLeidos, int grupos) {
    final cs = Theme.of(context).colorScheme;
    final oscuro = Theme.of(context).brightness == Brightness.dark;
    final fill = oscuro ? Colors.white10 : const Color(0xFFEFEFEF);
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
          child: TextField(
            controller: _busqueda,
            onChanged: (v) => setState(() => _q = v.trim().toLowerCase()),
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Buscar',
              prefixIcon: const Icon(Icons.search, size: 20, color: textoTenue),
              suffixIcon: _q.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      onPressed: () {
                        _busqueda.clear();
                        setState(() => _q = '');
                      },
                    ),
              isDense: true,
              filled: true,
              fillColor: fill,
              contentPadding:
                  const EdgeInsets.symmetric(vertical: 0, horizontal: 12),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(999),
                  borderSide: BorderSide.none),
            ),
          ),
        ),
        SizedBox(
          height: 42,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            children: [
              _chipFiltro(_FiltroChat.todos, 'Todos', null, cs),
              _chipFiltro(_FiltroChat.noLeidos, 'No leídos', noLeidos, cs),
              _chipFiltro(_FiltroChat.grupos, 'Grupos', grupos, cs),
              _chipFiltro(_FiltroChat.fijados, 'Fijados', null, cs),
            ],
          ),
        ),
        const SizedBox(height: 2),
      ],
    );
  }

  Widget _chipFiltro(
      _FiltroChat f, String label, int? count, ColorScheme cs) {
    final sel = _filtro == f;
    final txt = (count != null && count > 0) ? '$label $count' : label;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(
        label: Text(txt),
        selected: sel,
        showCheckmark: false,
        onSelected: (_) => setState(() => _filtro = f),
        backgroundColor: cs.surface,
        selectedColor: limaSuave,
        side: BorderSide(color: sel ? lima : const Color(0xFFE4E4E4)),
        labelStyle: TextStyle(
            color: sel ? lima : cs.onSurface,
            fontWeight: FontWeight.w700,
            fontSize: 13),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
      ),
    );
  }

  /// Panel derecho: el chat abierto (embebido, sin flecha de volver) o un aviso.
  Widget _panelDetalle() {
    final c = _sel;
    if (c == null) {
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
      key: ValueKey(c.hilo),
      academiaId: c.academiaId,
      cuentaEmail: c.cuentaEmail,
      titulo: c.titulo,
      soyProfe: c.soyProfe,
      tipo: c.tipo,
      refId: c.refId,
      embebido: true,
    );
  }

  /// Verde de la cabecera (igual al del chat), para que master y detalle queden
  /// alineados y con la misma barra superior (estilo WhatsApp Web).
  Color _headerBg(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark
          ? const Color(0xFF1F2C34)
          : const Color(0xFF008069);

  /// Cabecera del panel MASTER (lista). En tablet trae el botón de COLAPSAR; en
  /// móvil, el de volver. Misma altura/color que la cabecera del chat → alineadas.
  Widget _headerMaster(BuildContext context, {required bool colapsable}) {
    final bg = _headerBg(context);
    // Modo selección: barra de acciones estilo WhatsApp (fijar/silenciar/
    // archivar/eliminar) sobre los chats marcados.
    if (_enSeleccion) {
      final todosFijados = _seleccion.every(appState.chatFijado);
      final todosArchivados = _seleccion.every(appState.chatArchivado);
      return Material(
        color: bg,
        child: SizedBox(
          height: kToolbarHeight,
          child: Row(
            children: [
              IconButton(
                tooltip: 'Cancelar',
                icon: const Icon(Icons.arrow_back, color: Colors.white),
                onPressed: () => setState(_seleccion.clear),
              ),
              Text('${_seleccion.length}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      fontSize: 20)),
              const Spacer(),
              IconButton(
                tooltip: todosFijados ? 'Desfijar' : 'Fijar',
                icon: const Icon(Icons.push_pin_outlined, color: Colors.white),
                onPressed: _fijarSeleccion,
              ),
              IconButton(
                tooltip: 'Silenciar',
                icon: const Icon(Icons.notifications_off_outlined,
                    color: Colors.white),
                onPressed: _silenciarSeleccion,
              ),
              IconButton(
                tooltip: todosArchivados ? 'Desarchivar' : 'Archivar',
                icon: const Icon(Icons.archive_outlined, color: Colors.white),
                onPressed: _archivarSeleccion,
              ),
              IconButton(
                tooltip: 'Eliminar',
                icon: const Icon(Icons.delete_outline, color: Colors.white),
                onPressed: _eliminarSeleccion,
              ),
            ],
          ),
        ),
      );
    }
    return Material(
      color: bg,
      child: SizedBox(
        height: kToolbarHeight,
        child: Row(
          children: [
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
            const Spacer(),
            IconButton(
              tooltip: 'Buscar jugador',
              icon: const Icon(Icons.person_search, color: Colors.white),
              onPressed: () => Navigator.of(context)
                  .push(MaterialPageRoute(
                      builder: (_) => const BuscarUsuarioScreen()))
                  .then((_) => _cargar()),
            ),
          ],
        ),
      ),
    );
  }

  // ── Acciones de la barra de selección (operan sobre TODOS los marcados) ──────
  void _fijarSeleccion() {
    final target = !_seleccion.every(appState.chatFijado);
    for (final h in _seleccion) {
      if (appState.chatFijado(h) != target) appState.toggleChatFijado(h);
    }
    setState(_seleccion.clear);
  }

  void _silenciarSeleccion() {
    final target = !_seleccion.every(appState.chatSilenciado);
    for (final h in _seleccion) {
      if (appState.chatSilenciado(h) != target) appState.toggleChatSilenciado(h);
    }
    setState(_seleccion.clear);
  }

  void _archivarSeleccion() {
    final target = !_seleccion.every(appState.chatArchivado);
    for (final h in _seleccion) {
      if (appState.chatArchivado(h) != target) appState.toggleChatArchivado(h);
    }
    if (_sel != null && _seleccion.contains(_sel!.hilo)) _sel = null;
    setState(_seleccion.clear);
  }

  Future<void> _eliminarSeleccion() async {
    final n = _seleccion.length;
    final ok = await confirmarPichangol(
      context,
      titulo:
          n == 1 ? 'Eliminar conversación' : 'Eliminar $n conversaciones',
      mensaje: 'Se quitan de tu bandeja. Si te vuelven a escribir, reaparecen.',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (!ok) return;
    for (final h in _seleccion) {
      appState.ocultarChat(h);
      _abiertos.remove(h);
      if (_sel?.hilo == h) _sel = null;
    }
    setState(_seleccion.clear);
    await _cargar();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(n == 1 ? 'Conversación eliminada' : '$n eliminadas')),
    );
  }

  // Panel derecho colapsado: franja delgada para volver a mostrar la lista.
  bool _listaColapsada = false;
  // Viendo la bandeja de "Archivados" (en vez de la bandeja normal).
  bool _verArchivados = false;
  // Modo selección (estilo WhatsApp): hilos marcados con long-press. Cuando hay
  // al menos uno, la cabecera se vuelve una barra de acciones (fijar/silenciar/
  // archivar/eliminar) que opera sobre TODOS los marcados.
  final Set<String> _seleccion = {};
  bool get _enSeleccion => _seleccion.isNotEmpty;
  // Buscador + filtro de la bandeja (estilo WhatsApp, look Airbnb).
  final TextEditingController _busqueda = TextEditingController();
  String _q = '';
  _FiltroChat _filtro = _FiltroChat.todos;

  @override
  void dispose() {
    _busqueda.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: appState.logueado
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.of(context)
                  .push(MaterialPageRoute(
                      builder: (_) => const CrearGrupoScreen()))
                  .then((_) => _cargar()),
              icon: const Icon(Icons.group_add),
              label: const Text('Nuevo grupo'),
            )
          : null,
      body: SafeArea(
        bottom: false,
        child: ListenableBuilder(
          listenable: appState,
          builder: (context, _) {
            if (!appState.logueado) {
              return Column(children: [
                _headerMaster(context, colapsable: false),
                Expanded(
                  child: _Aviso(
                    _kSinSesion,
                    accion: FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: lima),
                      onPressed: () async {
                        if (await LoginGoogleSheet.mostrar(context,
                            motivo: 'ver tus mensajes')) {
                          _cargar();
                        }
                      },
                      icon: const Icon(Icons.login, size: 18),
                      label: const Text('Iniciar sesión'),
                    ),
                  ),
                ),
              ]);
            }
            if (!MensajesRepo.disponible) {
              return Column(children: [
                _headerMaster(context, colapsable: false),
                const Expanded(child: _Aviso(_kSinBackend)),
              ]);
            }
            return LayoutBuilder(builder: (context, cons) {
              final ancho = cons.maxWidth >= 640;
              // Separa activos / archivados y ordena los activos con los FIJADOS
              // primero (el resto por fecha desc). Se hace en cada build para que
              // fijar/archivar se reflejen al instante (sin recargar del backend).
              final activos = <_Conv>[];
              final archivados = <_Conv>[];
              for (final c in _convs) {
                if (appState.chatArchivado(c.hilo)) {
                  archivados.add(c);
                } else {
                  activos.add(c);
                }
              }
              activos.sort((a, b) {
                final pa = appState.chatFijado(a.hilo);
                final pb = appState.chatFijado(b.hilo);
                if (pa != pb) return pa ? -1 : 1;
                return b.cuando.compareTo(a.cuando);
              });
              // Contadores para los chips (sobre TODOS los activos, sin filtrar).
              final nNoLeidos = activos.where((c) => c.noLeidos > 0).length;
              final nGrupos = activos.where((c) => c.tipo == 'grupo').length;
              // Búsqueda + filtro de chip → lista visible.
              Iterable<_Conv> vis = activos;
              if (_q.isNotEmpty) {
                vis = vis.where((c) =>
                    c.titulo.toLowerCase().contains(_q) ||
                    c.preview.toLowerCase().contains(_q));
              }
              switch (_filtro) {
                case _FiltroChat.noLeidos:
                  vis = vis.where((c) => c.noLeidos > 0);
                  break;
                case _FiltroChat.grupos:
                  vis = vis.where((c) => c.tipo == 'grupo');
                  break;
                case _FiltroChat.fijados:
                  vis = vis.where((c) => appState.chatFijado(c.hilo));
                  break;
                case _FiltroChat.todos:
                  break;
              }
              final visibles = vis.toList();
              final hayFiltro = _q.isNotEmpty || _filtro != _FiltroChat.todos;
              final mostrando = _verArchivados ? archivados : visibles;

              Widget filaDe(_Conv c, bool conSep) => Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _FilaConv(
                        conv: c,
                        noLeidos: _abiertos.contains(c.hilo) ? 0 : c.noLeidos,
                        seleccionado: ancho && _sel?.hilo == c.hilo,
                        fijado: appState.chatFijado(c.hilo),
                        silenciado: appState.chatSilenciado(c.hilo),
                        marcado: _seleccion.contains(c.hilo),
                        // En modo selección, tocar marca/desmarca; si no, abre.
                        onTap: () => _enSeleccion
                            ? _toggleSeleccion(c.hilo)
                            : _abrir(c, ancho),
                        onLongPress: () => _toggleSeleccion(c.hilo),
                      ),
                      if (conSep)
                        Divider(height: 1, color: trazo.withOpacity(0.6)),
                    ],
                  );

              final filas = <Widget>[];
              // Cabecera de "Archivados": banner para entrar (bandeja normal) o
              // para volver (viendo archivados), estilo WhatsApp.
              if (_verArchivados) {
                filas.add(ListTile(
                  leading: const Icon(Icons.arrow_back, color: teal),
                  title: const Text('Archivados',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  onTap: () => setState(() => _verArchivados = false),
                ));
                filas.add(Divider(height: 1, color: trazo.withOpacity(0.6)));
              } else if (archivados.isNotEmpty) {
                filas.add(ListTile(
                  leading: const Icon(Icons.archive_outlined, color: textoTenue),
                  title: const Text('Archivados',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  trailing: Text('${archivados.length}',
                      style: const TextStyle(
                          color: textoTenue, fontWeight: FontWeight.w800)),
                  onTap: () => setState(() => _verArchivados = true),
                ));
                filas.add(Divider(height: 1, color: trazo.withOpacity(0.6)));
              }
              for (var i = 0; i < mostrando.length; i++) {
                filas.add(filaDe(mostrando[i], i < mostrando.length - 1));
              }
              if (mostrando.isEmpty) {
                filas.add(const SizedBox(height: 60));
                filas.add(_Aviso(_verArchivados
                    ? 'No tienes chats archivados.'
                    : hayFiltro
                        ? 'Sin resultados.'
                        : _kVacio));
              }

              final lista = RefreshIndicator(
                onRefresh: _cargar,
                child: _cargando
                    ? const CargandoPichangol()
                    : ListView(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        children: filas,
                      ),
              );
              // Columna maestra: cabecera + (buscador/chips, si no estás en
              // selección ni en Archivados) + lista.
              Widget masterCol(bool colapsable) => Column(children: [
                    _headerMaster(context, colapsable: colapsable),
                    if (!_enSeleccion && !_verArchivados)
                      _buscadorYFiltros(context, nNoLeidos, nGrupos),
                    Expanded(child: lista),
                  ]);
              // Móvil: solo la columna maestra.
              if (!ancho) return masterCol(false);
              // Tablet (master-detail). La lista es COLAPSABLE para dar más
              // espacio al chat. Ambas cabeceras van al mismo nivel (alineadas).
              return Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!_listaColapsada) ...[
                    SizedBox(width: 340, child: masterCol(true)),
                    const VerticalDivider(width: 1),
                  ] else
                    // Franja delgada con botón para reabrir la lista.
                    Column(children: [
                      Material(
                        color: _headerBg(context),
                        child: SizedBox(
                          height: kToolbarHeight,
                          width: 48,
                          child: IconButton(
                            tooltip: 'Mostrar conversaciones',
                            icon: const Icon(Icons.chevron_right,
                                color: Colors.white),
                            onPressed: () =>
                                setState(() => _listaColapsada = false),
                          ),
                        ),
                      ),
                      const Expanded(child: SizedBox(width: 48)),
                    ]),
                  Expanded(child: _panelDetalle()),
                ],
              );
            });
          },
        ),
      ),
    );
  }
}

const _kSinSesion = 'Inicia sesión para ver tus mensajes.';
const _kSinBackend =
    'El chat necesita conexión con el servidor. Intenta más tarde.';
const _kVacio =
    'Aún no tienes conversaciones. Cuando escribas (o te escriban) desde una '
    'academia, aparecerán aquí.';

class _Aviso extends StatelessWidget {
  const _Aviso(this.texto, {this.accion});
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

class _FilaConv extends StatelessWidget {
  const _FilaConv({
    required this.conv,
    required this.noLeidos,
    required this.seleccionado,
    required this.fijado,
    required this.silenciado,
    required this.marcado,
    required this.onTap,
    required this.onLongPress,
  });
  final _Conv conv;
  final int noLeidos; // efectivo (0 si ya se abrió en el panel)
  final bool seleccionado;
  final bool fijado;
  final bool silenciado;
  final bool marcado; // marcado en modo selección (WhatsApp)
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  String _cuando(DateTime d) {
    final now = DateTime.now();
    final hoy = d.year == now.year && d.month == now.month && d.day == now.day;
    if (hoy) {
      return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    }
    return '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final inicial =
        conv.titulo.trim().isNotEmpty ? conv.titulo.characters.first.toUpperCase() : '?';
    // Foto de la contraparte (chat 1:1 con una persona), si tiene perfil.
    final esPersona =
        conv.tipo == 'directo' || (conv.soyProfe && conv.tipo != 'grupo');
    final foto = (esPersona && conv.cuentaEmail.isNotEmpty)
        ? appState.fotoDe(conv.cuentaEmail)
        : null;
    // Ícono estilo Airbnb: círculo de color sólido + contenido blanco. Color e
    // ícono según el TIPO de conversación (grupo, cancha, persona/academia).
    final (Color colAvatar, IconData? icoTipo) = switch (conv.tipo) {
      'grupo' => (morado, Icons.groups),
      'cancha' => (naranja, Icons.sports_tennis),
      _ => (teal, null), // directo / academia → inicial del nombre
    };
    return ListTile(
      onTap: onTap,
      onLongPress: onLongPress,
      selected: seleccionado || marcado,
      selectedTileColor:
          cs.primary.withOpacity(marcado ? 0.16 : 0.08),
      leading: Stack(
        clipBehavior: Clip.none,
        children: [
          CircleAvatar(
            backgroundColor: colAvatar,
            backgroundImage:
                (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
            child: (foto != null && foto.isNotEmpty)
                ? null
                : (icoTipo != null
                    ? Icon(icoTipo, color: Colors.white, size: 20)
                    : Text(inicial,
                        style: const TextStyle(
                            color: Colors.white, fontWeight: FontWeight.w800))),
          ),
          // Check de selección (esquina inferior derecha), estilo WhatsApp.
          if (marcado)
            Positioned(
              right: -2,
              bottom: -2,
              child: Container(
                decoration: BoxDecoration(
                    color: cs.surface, shape: BoxShape.circle),
                child: Icon(Icons.check_circle, color: cs.primary, size: 18),
              ),
            ),
        ],
      ),
      title: Text(conv.titulo,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(conv.preview,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: textoTenue)),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(_cuando(conv.cuando),
              style: TextStyle(
                  fontSize: 11,
                  color: noLeidos > 0 ? cs.primary : textoTenue,
                  fontWeight:
                      noLeidos > 0 ? FontWeight.w800 : FontWeight.w400)),
          const SizedBox(height: 6),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Campana silenciada (como WhatsApp: junto al contador).
              if (silenciado) ...[
                const Icon(Icons.notifications_off, size: 15, color: textoTenue),
                const SizedBox(width: 4),
              ],
              if (fijado) ...[
                Transform.rotate(
                  angle: 0.785, // 45° → look de "chincheta" de WhatsApp
                  child: const Icon(Icons.push_pin, size: 15, color: textoTenue),
                ),
                if (noLeidos > 0) const SizedBox(width: 4),
              ],
              if (noLeidos > 0)
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration:
                      BoxDecoration(color: cs.primary, shape: BoxShape.circle),
                  child: Text('$noLeidos',
                      style: TextStyle(
                          color: cs.onPrimary,
                          fontSize: 10,
                          fontWeight: FontWeight.w800)),
                )
              else if (!fijado && !silenciado)
                const SizedBox(height: 12),
            ],
          ),
        ],
      ),
    );
  }
}
