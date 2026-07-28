import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../data/perfiles_repo.dart';
import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/reto_flow.dart';
import 'chat_screen.dart';
import 'login_google_sheet.dart';

/// BUSCAR USUARIO (tipo WhatsApp): encuentra a un jugador por nombre o correo,
/// chatéale directo y guárdalo como contacto. Con la búsqueda vacía muestra tus
/// contactos guardados para escribir rápido.
///
/// Si se pasa [deporteReto], además de chatear se puede **RETAR** al jugador
/// (para el circuito): cada fila ofrece Retar + Chatear para coordinar.
class BuscarUsuarioScreen extends StatefulWidget {
  const BuscarUsuarioScreen({super.key, this.deporteReto, this.onAbrirChat});

  /// Deporte del reto (p. ej. tenis del circuito). Null = solo chatear.
  final Deporte? deporteReto;

  /// Si se pasa, al elegir "chatear" se llama a este callback (para que quien
  /// abrió el buscador reuse una conversación EXISTENTE con esa persona) en vez
  /// de abrir una conversación directa nueva. Null = comportamiento por defecto.
  final void Function(String email, String nombre)? onAbrirChat;

  @override
  State<BuscarUsuarioScreen> createState() => _BuscarUsuarioScreenState();
}

class _BuscarUsuarioScreenState extends State<BuscarUsuarioScreen> {
  final _q = TextEditingController();
  Timer? _debounce;
  bool _buscando = false;
  List<Map<String, dynamic>> _resultados = const [];

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    // Carga los perfiles de mis contactos para mostrar nombre/foto.
    appState.cargarPerfiles(appState.contactos);
    // Trae la agenda (apodos/contactos/bloqueados) desde la nube para reflejar
    // cambios hechos en OTRO dispositivo sin tener que reiniciar la app.
    appState.sincronizarAgenda();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _q.dispose();
    super.dispose();
  }

  void _onCambio(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _buscar(v));
  }

  Future<void> _buscar(String v) async {
    final q = v.trim();
    if (q.length < 2) {
      setState(() {
        _resultados = const [];
        _buscando = false;
      });
      return;
    }
    setState(() => _buscando = true);
    final r = await PerfilesRepo.buscar(q);
    if (!mounted) return;
    setState(() {
      _resultados =
          r.where((p) => (p['email'] ?? '').toString().toLowerCase() != _yo)
              .toList();
      _buscando = false;
    });
  }

  Future<void> _chatear(String email, String nombre) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'enviar un mensaje')) {
      return;
    }
    if (!mounted) return;
    // Si quien abrió el buscador sabe reusar una conversación existente, que él
    // decida (evita abrir un chat directo NUEVO cuando ya hay historial).
    if (widget.onAbrirChat != null) {
      widget.onAbrirChat!(email, nombre);
      return;
    }
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: email,
        titulo: nombre.isNotEmpty ? nombre : email,
        soyProfe: false,
        tipo: 'directo',
      ),
    ));
  }

  /// Reta a un jugador (solo si esta pantalla se abrió con [deporteReto]).
  /// Un solo reto por click: guardia anti doble-clic + preload centralizados.
  Future<void> _retar(String email, String nombre) async {
    final dep = widget.deporteReto;
    if (dep == null) return;
    await enviarRetoConGuardia(
      context,
      deporte: dep.name,
      retadoEmail: email,
      retadoNombre: nombre,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(
              widget.deporteReto != null ? 'Buscar jugador' : 'Contactos')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: TextField(
              controller: _q,
              autofocus: true,
              onChanged: _onCambio,
              decoration: InputDecoration(
                hintText: 'Nombre o correo…',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _q.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () {
                          _q.clear();
                          _buscar('');
                          setState(() {});
                        },
                      ),
                filled: true,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide.none),
              ),
            ),
          ),
          Expanded(
            child: ListenableBuilder(
              listenable: appState,
              builder: (context, _) {
                final hayQuery = _q.text.trim().length >= 2;
                if (_buscando) {
                  return const Center(
                      child: CircularProgressIndicator(color: lima));
                }
                if (!hayQuery) {
                  return _Contactos(
                      onChatear: _chatear,
                      onRetar: widget.deporteReto != null ? _retar : null);
                }
                if (_resultados.isEmpty) {
                  return const _Vacio(
                      icono: Icons.search_off,
                      texto: 'No se encontró a nadie con ese nombre o correo. '
                          'Recuerda: la persona debe haber entrado al app.');
                }
                return ListView.separated(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  itemCount: _resultados.length,
                  separatorBuilder: (_, __) =>
                      Divider(height: 1, color: trazo.withOpacity(0.5)),
                  itemBuilder: (_, i) => _FilaUsuario(
                    perfil: _resultados[i],
                    onChatear: _chatear,
                    onRetar: widget.deporteReto != null ? _retar : null,
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// Lista de mis contactos guardados (búsqueda vacía).
class _Contactos extends StatelessWidget {
  const _Contactos({required this.onChatear, this.onRetar});
  final void Function(String email, String nombre) onChatear;
  final void Function(String email, String nombre)? onRetar;
  @override
  Widget build(BuildContext context) {
    final emails = appState.contactos;
    if (emails.isEmpty) {
      return const _Vacio(
          icono: Icons.contacts_outlined,
          texto: 'Aún no tienes contactos.\nBusca a un jugador por su nombre o '
              'correo para escribirle y guardarlo en tu agenda.');
    }
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 6),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 8, 18, 4),
          child: Text('Mis contactos (${emails.length})',
              style: const TextStyle(
                  fontWeight: FontWeight.w800, color: textoTenue)),
        ),
        for (final e in emails)
          _FilaUsuario(
            perfil: {
              'email': e,
              'nombre': appState.nombreMostrableDe(e) ?? e,
              'foto_url': appState.fotoDe(e),
              'celular': appState.celularDe(e),
            },
            onChatear: onChatear,
            onRetar: onRetar,
          ),
      ],
    );
  }
}

class _FilaUsuario extends StatelessWidget {
  const _FilaUsuario(
      {required this.perfil, required this.onChatear, this.onRetar});
  final Map<String, dynamic> perfil;
  final void Function(String email, String nombre) onChatear;
  final void Function(String email, String nombre)? onRetar;

  /// Hoja con las dos acciones cuando se puede retar: Retar / Chatear.
  void _opciones(BuildContext context, String email, String nombre) {
    final mostrar = nombre.isNotEmpty ? nombre : email;
    showModalBottomSheet(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 6),
              child: Text(mostrar,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 16)),
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: naranja,
                  child: Icon(Icons.sports_kabaddi, color: Colors.white)),
              title: const Text('Retar a un partido'),
              subtitle: const Text('Le llega una notificación del reto'),
              onTap: () {
                Navigator.pop(context);
                onRetar!(email, nombre);
              },
            ),
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: teal,
                  child: Icon(Icons.chat_bubble, color: Colors.white)),
              title: const Text('Chatear para coordinar'),
              subtitle: const Text('Ponte de acuerdo en cancha y hora'),
              onTap: () {
                Navigator.pop(context);
                onChatear(email, nombre);
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
    final email = (perfil['email'] ?? '').toString();
    final nombre = (perfil['nombre'] ?? '').toString();
    final foto = (perfil['foto_url'] ?? '').toString();
    final mostrar = nombre.isNotEmpty ? nombre : email;
    final guardado = appState.esContacto(email);
    final celular = (perfil['celular'] ?? '').toString();
    return ListTile(
      onTap: () => onRetar != null
          ? _opciones(context, email, nombre)
          : onChatear(email, nombre),
      leading: CircleAvatar(
        radius: 22,
        backgroundColor: teal,
        backgroundImage: foto.isNotEmpty ? NetworkImage(foto) : null,
        child: foto.isEmpty
            ? Text(mostrar.isNotEmpty ? mostrar[0].toUpperCase() : '?',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w800))
            : null,
      ),
      title: Text(mostrar,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: nombre.isNotEmpty
          ? Text(email,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: textoTenue, fontSize: 12))
          : null,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: guardado ? 'Quitar de contactos' : 'Guardar contacto',
            icon: Icon(guardado ? Icons.star : Icons.star_border,
                color: guardado ? lima : textoTenue),
            onPressed: () {
              if (guardado) {
                appState.quitarContacto(email);
              } else {
                appState.guardarContacto(email, perfil: perfil);
              }
            },
          ),
          if (celular.isNotEmpty)
            IconButton(
              tooltip: 'WhatsApp',
              icon: const FaIcon(FontAwesomeIcons.whatsapp,
                  color: Color(0xFF25D366), size: 20),
              onPressed: () => WhatsAppLink.abrir(
                  celular, 'Hola, te escribo desde Pichangol.'),
            ),
          if (onRetar != null)
            IconButton(
              tooltip: 'Retar',
              icon: const Icon(Icons.sports_kabaddi, color: naranja),
              onPressed: () => onRetar!(email, nombre),
            ),
          IconButton(
            tooltip: 'Enviar mensaje',
            icon: const Icon(Icons.chat_bubble_outline, color: bosque),
            onPressed: () => onChatear(email, nombre),
          ),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio({required this.icono, required this.texto});
  final IconData icono;
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 54, color: textoTenue),
            const SizedBox(height: 12),
            Text(texto,
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue)),
          ],
        ),
      ),
    );
  }
}
