import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/grupos_repo.dart';
import '../data/mensajes_repo.dart';
import '../models/grupo.dart';
import '../models/mensaje.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';

/// Sala de reunión (Jitsi Meet, gratis y sin backend) única por grupo. Todos los
/// integrantes que toquen "Únete" caen en la MISMA sala → llamada grupal real.
String _salaJitsi(String grupoId) {
  final limpio = grupoId.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
  return 'https://meet.jit.si/PichangolGrupo$limpio';
}

/// Inicia la llamada grupal: publica el enlace en el chat del grupo (para que
/// todos puedan unirse) y abre la sala. Compartido por la ficha y la cabecera.
Future<void> iniciarLlamadaGrupal(
  BuildContext context, {
  required String grupoId,
  required String grupoNombre,
}) async {
  final u = appState.usuario;
  if (u == null) return;
  final url = _salaJitsi(grupoId);
  // Avisar en el chat del grupo para que los demás se unan.
  await MensajesRepo.enviar(Mensaje(
    id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
    hilo: Mensaje.hiloGrupo(grupoId),
    tipo: 'grupo',
    refId: grupoId,
    autorEmail: u.email,
    autorNombre: u.nombre,
    esProfe: false,
    texto: '📞 ${u.nombre} inició una llamada grupal. Únete: $url',
    creado: DateTime.now(),
  ));
  try {
    await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo abrir la llamada.')));
    }
  }
}

/// Ficha del grupo estilo WhatsApp: foto (cambiable), nombre (editable), lista de
/// integrantes con su foto real, llamada grupal, añadir integrante y salir.
class GrupoInfoScreen extends StatefulWidget {
  const GrupoInfoScreen({super.key, required this.grupoId});
  final String grupoId;

  @override
  State<GrupoInfoScreen> createState() => _GrupoInfoScreenState();
}

class _GrupoInfoScreenState extends State<GrupoInfoScreen> {
  Grupo? _grupo;
  bool _cargando = true;
  bool _subiendoFoto = false;

  String get _yo => (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final g = await GruposRepo.obtener(widget.grupoId);
    if (g != null) {
      await appState.cargarPerfiles(g.miembros);
    }
    if (!mounted) return;
    setState(() {
      _grupo = g;
      _cargando = false;
    });
  }

  Future<void> _cambiarFoto() async {
    final g = _grupo;
    if (g == null) return;
    final x = await ImagePicker()
        .pickImage(source: ImageSource.gallery, maxWidth: 1024, imageQuality: 85);
    if (x == null) return;
    final Uint8List bytes = await x.readAsBytes();
    setState(() => _subiendoFoto = true);
    final url = await GruposRepo.subirFoto(g.id, bytes);
    if (url != null) {
      await GruposRepo.actualizar(g.id, fotoUrl: url);
    }
    if (!mounted) return;
    setState(() {
      _subiendoFoto = false;
      if (url != null) _grupo = g.copyWith(fotoUrl: url);
    });
    if (url == null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo subir la foto (revisa el bucket "grupos").')));
    }
  }

  Future<void> _editarNombre() async {
    final g = _grupo;
    if (g == null) return;
    final ctrl = TextEditingController(text: g.nombre);
    final nuevo = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Theme.of(ctx).colorScheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Nombre del grupo'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(hintText: 'Nombre del grupo'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancelar')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
              child: const Text('Guardar')),
        ],
      ),
    );
    if (nuevo == null || nuevo.isEmpty || nuevo == g.nombre) return;
    final ok = await GruposRepo.actualizar(g.id, nombre: nuevo);
    if (!mounted) return;
    if (ok) {
      setState(() => _grupo = g.copyWith(nombre: nuevo));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo guardar el nombre.')));
    }
  }

  Future<void> _anadirIntegrante() async {
    final g = _grupo;
    if (g == null) return;
    // Mis contactos que aún no están en el grupo.
    final yaEstan = g.miembros.map((e) => e.toLowerCase()).toSet();
    final candidatos = appState.contactos
        .where((e) => !yaEstan.contains(e.toLowerCase()))
        .toList();
    if (candidatos.isEmpty) {
      await avisarPichangol(context,
          titulo: 'Sin contactos por añadir',
          mensaje:
              'Todos tus contactos ya están en el grupo, o aún no tienes contactos guardados.');
      return;
    }
    await appState.cargarPerfiles(candidatos);
    if (!mounted) return;
    final email = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 12),
            Text('Añadir integrante',
                style: Theme.of(ctx)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final e in candidatos)
                    ListTile(
                      leading: _avatar(e, 20),
                      title: Text(appState.nombreMostrableDe(e) ?? e),
                      onTap: () => Navigator.pop(ctx, e),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
    if (email == null) return;
    final nombre = appState.nombreMostrableDe(email) ?? email;
    final ok = await GruposRepo.agregarMiembro(g.id, email, nombre);
    if (ok) {
      await appState.cargarPerfiles([email]);
      if (!mounted) return;
      setState(() => _grupo = g.copyWith(miembros: [...g.miembros, email]));
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo añadir al integrante.')));
    }
  }

  Future<void> _salir() async {
    final g = _grupo;
    if (g == null) return;
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Salir del grupo?',
      mensaje: 'Dejarás de recibir los mensajes de "${g.nombre}".',
      textoConfirmar: 'Salir',
      destructivo: true,
      icono: Icons.logout,
    );
    if (!ok) return;
    final hecho = await GruposRepo.salir(g.id, _yo);
    if (!mounted) return;
    if (hecho) {
      Navigator.of(context).pop('salio'); // el chat cierra al recibirlo
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo salir del grupo.')));
    }
  }

  Widget _avatar(String email, double radio) {
    final foto = appState.fotoDe(email);
    final nombre = appState.nombreMostrableDe(email) ?? email;
    final inicial =
        nombre.trim().isNotEmpty ? nombre.characters.first.toUpperCase() : '?';
    return CircleAvatar(
      radius: radio,
      backgroundColor: limaSuave,
      backgroundImage: (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
      child: (foto != null && foto.isNotEmpty)
          ? null
          : Text(inicial,
              style: TextStyle(
                  color: lima, fontWeight: FontWeight.w800, fontSize: radio * 0.8)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (_cargando) {
      return Scaffold(
        appBar: AppBar(title: const Text('Info del grupo')),
        body: const CargandoPichangol(),
      );
    }
    final g = _grupo;
    if (g == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Info del grupo')),
        body: const Center(child: Text('No se pudo cargar el grupo.')),
      );
    }
    final soyCreador = g.creadorEmail.toLowerCase() == _yo;
    // ¿Algún integrante (además de mí) tiene celular? → habilita la llamada.
    final conNumero = g.miembros
        .where((e) => e.toLowerCase() != _yo)
        .where((e) => appState.celularDe(e) != null)
        .length;
    return Scaffold(
      appBar: AppBar(title: const Text('Info del grupo')),
      body: AnchoTablet(
        maxWidth: 640,
        child: ListView(
          children: [
            const SizedBox(height: 20),
            // Foto del grupo (tocar para cambiar).
            Center(
              child: Stack(
                children: [
                  GestureDetector(
                    onTap: _subiendoFoto ? null : _cambiarFoto,
                    child: CircleAvatar(
                      radius: 54,
                      backgroundColor: limaSuave,
                      backgroundImage: g.fotoUrl.isNotEmpty
                          ? NetworkImage(g.fotoUrl)
                          : null,
                      child: g.fotoUrl.isNotEmpty
                          ? null
                          : const Icon(Icons.groups, size: 52, color: lima),
                    ),
                  ),
                  Positioned(
                    right: 0,
                    bottom: 0,
                    child: CircleAvatar(
                      radius: 16,
                      backgroundColor: lima,
                      child: _subiendoFoto
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : const Icon(Icons.camera_alt,
                              size: 16, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            // Nombre + lápiz para editar.
            Center(
              child: GestureDetector(
                onTap: _editarNombre,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(g.nombre,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 21,
                              fontWeight: FontWeight.w800,
                              color: cs.onSurface)),
                    ),
                    const SizedBox(width: 6),
                    Icon(Icons.edit, size: 18, color: textoTenueDe(context)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 4),
            Center(
              child: Text('Grupo · ${g.miembros.length} integrantes',
                  style: TextStyle(color: textoTenueDe(context), fontSize: 13.5)),
            ),
            const SizedBox(height: 18),
            // Llamada grupal (si hay al menos un integrante con número).
            if (conNumero > 0)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      minimumSize: const Size.fromHeight(48)),
                  onPressed: () => iniciarLlamadaGrupal(context,
                      grupoId: g.id, grupoNombre: g.nombre),
                  icon: const Icon(Icons.videocam),
                  label: const Text('Llamada grupal'),
                ),
              ),
            const SizedBox(height: 18),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text('${g.miembros.length} integrantes',
                  style: TextStyle(
                      color: textoTenueDe(context),
                      fontWeight: FontWeight.w700,
                      fontSize: 13)),
            ),
            // Añadir integrante.
            ListTile(
              leading: const CircleAvatar(
                  backgroundColor: limaSuave,
                  child: Icon(Icons.person_add_alt, color: lima)),
              title: const Text('Añadir integrante',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              onTap: _anadirIntegrante,
            ),
            // Lista de integrantes con su foto real.
            for (final e in g.miembros) _filaMiembro(e, g, soyCreador),
            const Divider(height: 24),
            ListTile(
              leading: const Icon(Icons.logout, color: clayOscuro),
              title: const Text('Salir del grupo',
                  style: TextStyle(
                      color: clayOscuro, fontWeight: FontWeight.w700)),
              onTap: _salir,
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _filaMiembro(String email, Grupo g, bool soyCreador) {
    final esYo = email.toLowerCase() == _yo;
    final esCreador = email.toLowerCase() == g.creadorEmail.toLowerCase();
    final nombre =
        esYo ? 'Tú' : (appState.nombreMostrableDe(email) ?? email);
    final cel = appState.celularDe(email);
    return ListTile(
      leading: _avatar(email, 22),
      title: Text(nombre, style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: esCreador
          ? Text('Creador del grupo',
              style: TextStyle(color: textoTenueDe(context), fontSize: 12.5))
          : null,
      trailing: (!esYo && cel != null)
          ? Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: 'Llamar',
                  icon: const Icon(Icons.call, color: lima),
                  onPressed: () async {
                    final numero = cel.replaceAll(RegExp(r'[^0-9+]'), '');
                    if (numero.isEmpty) return;
                    try {
                      await launchUrl(Uri(scheme: 'tel', path: numero),
                          mode: LaunchMode.externalApplication);
                    } catch (_) {}
                  },
                ),
                IconButton(
                  tooltip: 'WhatsApp',
                  icon: const FaIcon(FontAwesomeIcons.whatsapp,
                      color: Color(0xFF25D366), size: 20),
                  onPressed: () => WhatsAppLink.abrir(
                      cel, 'Hola, te escribo desde Pichangol.'),
                ),
              ],
            )
          : null,
    );
  }
}
