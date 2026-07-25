import 'package:flutter/material.dart';

import '../data/grupos_repo.dart';
import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'buscar_usuario_screen.dart';
import 'chat_screen.dart';
import 'crear_grupo_screen.dart';
import 'login_google_sheet.dart';

/// Inbox unificado "Mensajes": junta en UN solo lugar todas las conversaciones
/// del usuario logueado (como profe de sus academias y como alumno de las que
/// pertenece). Es la pestaña fija de chat, siempre a la mano. Preparado para
/// sumar chats de canchas y grupos más adelante.
class MensajesScreen extends StatefulWidget {
  const MensajesScreen({super.key});

  @override
  State<MensajesScreen> createState() => _MensajesScreenState();
}

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

    convs.sort((a, b) => b.cuando.compareTo(a.cuando));
    if (!mounted) return;
    setState(() {
      _convs = convs;
      _cargando = false;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mensajes'),
        actions: [
          IconButton(
            tooltip: 'Buscar jugador',
            icon: const Icon(Icons.person_search),
            onPressed: () => Navigator.of(context)
                .push(MaterialPageRoute(
                    builder: (_) => const BuscarUsuarioScreen()))
                .then((_) => _cargar()),
          ),
        ],
      ),
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
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (!appState.logueado) {
            return _Aviso(
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
            );
          }
          if (!MensajesRepo.disponible) return const _Aviso(_kSinBackend);
          return LayoutBuilder(builder: (context, cons) {
            final ancho = cons.maxWidth >= 640;
            final lista = RefreshIndicator(
              onRefresh: _cargar,
              child: _cargando
                  ? const Center(child: CircularProgressIndicator())
                  : _convs.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          _Aviso(_kVacio),
                        ])
                      : ListView.separated(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          itemCount: _convs.length,
                          separatorBuilder: (_, __) => Divider(
                              height: 1, color: trazo.withOpacity(0.6)),
                          itemBuilder: (_, i) {
                            final c = _convs[i];
                            return _FilaConv(
                              conv: c,
                              noLeidos:
                                  _abiertos.contains(c.hilo) ? 0 : c.noLeidos,
                              seleccionado: ancho && _sel?.hilo == c.hilo,
                              onTap: () => _abrir(c, ancho),
                            );
                          },
                        ),
            );
            if (!ancho) return lista;
            return Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(width: 340, child: lista),
                const VerticalDivider(width: 1),
                Expanded(child: _panelDetalle()),
              ],
            );
          });
        },
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
    required this.onTap,
  });
  final _Conv conv;
  final int noLeidos; // efectivo (0 si ya se abrió en el panel)
  final bool seleccionado;
  final VoidCallback onTap;

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
      selected: seleccionado,
      selectedTileColor: cs.primary.withOpacity(0.08),
      leading: CircleAvatar(
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
          if (noLeidos > 0)
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: cs.primary, shape: BoxShape.circle),
              child: Text('$noLeidos',
                  style: TextStyle(
                      color: cs.onPrimary,
                      fontSize: 10,
                      fontWeight: FontWeight.w800)),
            )
          else
            const SizedBox(height: 12),
        ],
      ),
    );
  }
}
