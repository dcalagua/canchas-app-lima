import 'package:flutter/material.dart';

import '../data/grupos_repo.dart';
import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';

/// Un destino al que se puede REENVIAR (o compartir) un mensaje: lleva todo lo
/// necesario para construir el mensaje en ese hilo.
class DestinoChat {
  const DestinoChat({
    required this.hilo,
    required this.tipo,
    required this.titulo,
    this.refId = '',
    this.academiaId = '',
    this.cuentaEmail = '',
    this.soyProfe = false,
    this.subtitulo = '',
    this.fotoEmail = '',
  });
  final String hilo;
  final String tipo; // 'directo' | 'grupo' | 'academia' | 'cancha'
  final String titulo;
  final String refId;
  final String academiaId;
  final String cuentaEmail;
  final bool soyProfe;
  final String subtitulo;
  final String fotoEmail; // correo para buscar la foto de perfil ('' = sin foto)
}

/// Selector de un CHAT existente (grupos, academias y contactos) para reenviar.
class SelectorChatScreen extends StatefulWidget {
  const SelectorChatScreen({super.key});

  @override
  State<SelectorChatScreen> createState() => _SelectorChatScreenState();
}

class _SelectorChatScreenState extends State<SelectorChatScreen> {
  bool _cargando = true;
  List<DestinoChat> _destinos = const [];
  final _q = TextEditingController();
  String _filtro = '';

  @override
  void initState() {
    super.initState();
    _q.addListener(() => setState(() => _filtro = _q.text.trim().toLowerCase()));
    _cargar();
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    final email = (appState.usuario?.email ?? '').toLowerCase();
    final destinos = <DestinoChat>[];
    // Dedupe SEMÁNTICO: una sola entrada por persona/grupo/academia, aunque
    // exista como chat de academia Y como contacto (mismo correo). Clave:
    //   'g:<grupoId>' | 'p:<correo persona>' | 'a:<academiaId>'.
    final claves = <String>{};

    if (email.isNotEmpty) {
      final nombreAcademia = <String, String>{
        for (final a in appState.academias) a.id: a.nombre,
      };

      // 1) GRUPOS
      try {
        final grupos = await GruposRepo.gruposDe(email);
        for (final g in grupos) {
          if (!claves.add('g:${g.id}')) continue;
          destinos.add(DestinoChat(
              hilo: Mensaje.hiloGrupo(g.id),
              tipo: 'grupo',
              refId: g.id,
              titulo: g.nombre,
              subtitulo: 'Grupo'));
        }
      } catch (_) {}

      // 2) CHATS DE ACADEMIA existentes (profe ↔ alumno). Tienen historial real,
      //    por eso van ANTES que los contactos sueltos.
      try {
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
        final porHilo = <String, Mensaje>{};
        for (final m in msgs) {
          porHilo.putIfAbsent(m.hilo, () => m);
        }
        porHilo.forEach((hilo, m) {
          final soyProfe = owned.contains(m.academiaId);
          if (!soyProfe && m.cuentaEmail.toLowerCase() != email) return;
          // Clave por persona (profe↔alumno) o por academia (yo alumno).
          final clave = soyProfe
              ? 'p:${m.cuentaEmail.toLowerCase()}'
              : 'a:${m.academiaId}';
          if (!claves.add(clave)) return;
          final acad = nombreAcademia[m.academiaId] ?? 'Academia';
          destinos.add(DestinoChat(
              hilo: hilo,
              tipo: 'academia',
              academiaId: m.academiaId,
              cuentaEmail: soyProfe ? m.cuentaEmail : email,
              soyProfe: soyProfe,
              fotoEmail: soyProfe ? m.cuentaEmail : '',
              titulo: soyProfe
                  ? (appState.nombreMostrableDe(m.cuentaEmail) ?? m.cuentaEmail)
                  : acad,
              subtitulo: soyProfe ? acad : 'Academia'));
        });
      } catch (_) {}

      // 3) CONTACTOS (chats directos). Se saltan si esa persona ya salió arriba.
      for (final c in appState.contactos) {
        if (!claves.add('p:${c.toLowerCase()}')) continue;
        destinos.add(DestinoChat(
            hilo: Mensaje.hiloDirecto(email, c),
            tipo: 'directo',
            cuentaEmail: c,
            fotoEmail: c,
            titulo: appState.nombreMostrableDe(c) ?? c,
            subtitulo: 'Contacto'));
      }
    }

    // Precarga los perfiles (foto/nombre) de las contrapartes → avatar real.
    final correos = destinos
        .map((d) => d.fotoEmail)
        .where((e) => e.isNotEmpty)
        .toList();
    if (correos.isNotEmpty) await appState.cargarPerfiles(correos);

    if (!mounted) return;
    setState(() {
      _destinos = destinos;
      _cargando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final vis = _filtro.isEmpty
        ? _destinos
        : _destinos
            .where((d) => d.titulo.toLowerCase().contains(_filtro))
            .toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Reenviar a',
            style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
            child: TextField(
              controller: _q,
              decoration: InputDecoration(
                hintText: 'Buscar chat…',
                prefixIcon: const Icon(Icons.search),
                filled: true,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none),
              ),
            ),
          ),
          Expanded(
            child: _cargando
                ? const CargandoPichangol()
                : vis.isEmpty
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.all(28),
                          child: Text(
                            'No tienes chats para reenviar todavía. Guarda un '
                            'contacto o crea un grupo.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: textoTenue),
                          ),
                        ),
                      )
                    : ListView.separated(
                        itemCount: vis.length,
                        separatorBuilder: (_, __) =>
                            Divider(height: 1, color: trazo.withOpacity(0.5)),
                        itemBuilder: (_, i) {
                          final d = vis[i];
                          final ini = (d.titulo.trim().isNotEmpty
                                  ? d.titulo.trim()[0]
                                  : '?')
                              .toUpperCase();
                          final foto = appState.fotoDe(d.fotoEmail);
                          return ListTile(
                            leading: CircleAvatar(
                              backgroundColor: limaSuave,
                              backgroundImage: (foto != null && foto.isNotEmpty)
                                  ? NetworkImage(foto)
                                  : null,
                              child: d.tipo == 'grupo'
                                  ? const Icon(Icons.groups, color: teal)
                                  : (foto == null || foto.isEmpty)
                                      ? Text(ini,
                                          style: const TextStyle(
                                              color: teal,
                                              fontWeight: FontWeight.bold))
                                      : null,
                            ),
                            title: Text(d.titulo,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600)),
                            subtitle: d.subtitulo.isEmpty
                                ? null
                                : Text(d.subtitulo),
                            onTap: () => Navigator.of(context).pop(d),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
