import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../config/pais.dart';
import '../data/perfiles_repo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/nivel_chip.dart';
import '../widgets/responsive.dart';
import 'nivel_onboarding_screen.dart';

/// EDITAR MI PERFIL — rediseño al UI/UX de Airbnb ("Edita el perfil"):
///  - Título centrado + X para cerrar.
///  - Avatar GRANDE con pastilla "📷 Editar" superpuesta.
///  - "Mi perfil" + texto de confianza.
///  - Lista de PROMPTS con ícono de línea y divisores, versión deportiva:
///    "Mi cancha favorita", "Mi mayor logro deportivo", etc. (se guardan como
///    BIO jsonb en `pichangol_perfiles` — docs/piloto/supabase_perfil_bio.sql).
///  - Sección "Mis deportes" (niveles) con botón para editarlos.
///  - Botón charcoal "Listo" fijo abajo.
class EditarPerfilScreen extends StatefulWidget {
  const EditarPerfilScreen({super.key});
  @override
  State<EditarPerfilScreen> createState() => _EditarPerfilScreenState();
}

/// Prompts de la bio (clave estable → ícono + etiqueta). Versión PCG de los
/// "A donde siempre quise ir / Me dedico a" de Airbnb.
const List<(String, IconData, String)> _kPromptsBio = [
  ('cancha_favorita', Icons.stadium_outlined, 'Mi cancha favorita'),
  ('dedico', Icons.work_outline, 'Me dedico a'),
  ('juego_desde', Icons.history_outlined, 'Juego desde'),
  ('logro', Icons.emoji_events_outlined, 'Mi mayor logro deportivo'),
  ('tiempo', Icons.schedule_outlined, 'Dedico demasiado tiempo a'),
  ('dato', Icons.lightbulb_outline, 'Dato curioso sobre mí'),
  ('cancion', Icons.music_note_outlined, 'Mi canción para entrar en calor'),
  ('amo', Icons.favorite_border, 'Amo'),
  ('idiomas', Icons.translate_outlined, 'Idiomas que hablo'),
];

class _EditarPerfilScreenState extends State<EditarPerfilScreen> {
  late final TextEditingController _nombre =
      TextEditingController(text: appState.usuario?.nombre ?? '');
  // Celular guardado SIN el código de país (se muestra con el prefijo aparte).
  late final TextEditingController _celular =
      TextEditingController(text: _celularLocal(appState.miCelular));
  bool _guardando = false;
  bool _subiendoFoto = false;

  /// BIO estilo Airbnb (clave → texto). Device-first: se pinta lo que llegue.
  final Map<String, String> _bio = {};

  @override
  void initState() {
    super.initState();
    final email = appState.usuario?.email;
    if (email != null) {
      PerfilesRepo.leerBio(email).then((b) {
        if (mounted && b.isNotEmpty) setState(() => _bio.addAll(b));
      });
    }
  }

  /// Quita el código de país del celular guardado, para editarlo local.
  String _celularLocal(String full) {
    var d = full.replaceAll(RegExp(r'[^0-9]'), '');
    final cc = paisActual.codigoTel;
    if (d.startsWith(cc) && d.length > paisActual.telLongitud) {
      d = d.substring(cc.length);
    }
    return d;
  }

  @override
  void dispose() {
    _nombre.dispose();
    _celular.dispose();
    super.dispose();
  }

  /// Elige una foto (galería o cámara), la sube y actualiza el perfil.
  Future<void> _cambiarFoto(ImageSource source) async {
    try {
      final XFile? file = await ImagePicker()
          .pickImage(source: source, maxWidth: 800, imageQuality: 82);
      if (file == null || !mounted) return;
      setState(() => _subiendoFoto = true);
      final bytes = await file.readAsBytes();
      final ok = await appState.actualizarMiFoto(bytes);
      if (!mounted) return;
      setState(() => _subiendoFoto = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: ok ? bosque : null,
          content: Text(ok
              ? 'Foto actualizada.'
              : 'No se pudo subir la foto. Reintenta.')));
    } catch (_) {
      if (mounted) setState(() => _subiendoFoto = false);
    }
  }

  void _menuFoto() {
    showModalBottomSheet<void>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Elegir de la galería'),
              onTap: () {
                Navigator.pop(context);
                _cambiarFoto(ImageSource.gallery);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Tomar una foto'),
              onTap: () {
                Navigator.pop(context);
                _cambiarFoto(ImageSource.camera);
              },
            ),
          ],
        ),
      ),
    );
  }

  /// Edita un prompt de la bio en un bottom sheet (estilo Airbnb).
  Future<void> _editarPrompt(String clave, String etiqueta) async {
    final ctrl = TextEditingController(text: _bio[clave] ?? '');
    final res = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(
            20, 18, 20, 18 + MediaQuery.of(ctx).viewInsets.bottom),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(etiqueta,
                style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 18)),
            const SizedBox(height: 12),
            TextField(
              controller: ctrl,
              autofocus: true,
              maxLength: 80,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(
                hintText: 'Escribe aquí…',
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
              onSubmitted: (v) => Navigator.of(ctx).pop(v),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                if ((_bio[clave] ?? '').isNotEmpty)
                  TextButton(
                    onPressed: () => Navigator.of(ctx).pop(''),
                    child: const Text('Quitar',
                        style: TextStyle(color: textoTenue)),
                  ),
                const Spacer(),
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: tinta,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999))),
                  onPressed: () => Navigator.of(ctx).pop(ctrl.text),
                  child: const Text('Guardar'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (res == null || !mounted) return;
    setState(() {
      final v = res.trim();
      if (v.isEmpty) {
        _bio.remove(clave);
      } else {
        _bio[clave] = v;
      }
    });
  }

  Future<void> _guardar() async {
    final n = _nombre.text.trim();
    if (n.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Escribe tu nombre.')));
      return;
    }
    if (_guardando) return;
    setState(() => _guardando = true);
    // Celular en formato internacional (con código de país), o '' si lo borró.
    final celDigits = _celular.text.replaceAll(RegExp(r'[^0-9]'), '');
    final cel = celDigits.isEmpty ? '' : '${paisActual.codigoTel}$celDigits';
    bool ok;
    try {
      ok = await conPreload(
          context, () => appState.actualizarMiNombre(n, celular: cel),
          texto: 'Guardando…');
      // La BIO viaja aparte (upsert sobre el mismo perfil). Best-effort: si la
      // columna aún no existe en Supabase, el perfil base igual queda guardado.
      final email = appState.usuario?.email;
      if (ok && email != null) {
        await PerfilesRepo.guardar(email: email, nombre: n, bio: _bio);
      }
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: bosque,
          content: Text('Listo. Así te verán en el chat y el ranking.')));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo guardar. Reintenta.')));
    }
  }

  /// Campo de texto minimalista (nombre / celular) con etiqueta arriba.
  Widget _campo(String etiqueta, TextEditingController ctrl,
      {String? prefijo, TextInputType? tipo, List<TextInputFormatter>? fmt}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(etiqueta,
            style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: textoTenueDe(context))),
        const SizedBox(height: 6),
        TextField(
          controller: ctrl,
          keyboardType: tipo,
          inputFormatters: fmt,
          decoration: InputDecoration(
            prefixText: prefijo,
            isDense: true,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final u = appState.usuario;
    final foto = u?.fotoUrl;
    return Scaffold(
      // Barra estilo modal de Airbnb: título centrado + X.
      appBar: AppBar(
        automaticallyImplyLeading: false,
        centerTitle: true,
        title: const Text('Edita el perfil',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
        actions: [
          IconButton(
            icon: const Icon(Icons.close),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
      body: u == null
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Inicia sesión para editar tu perfil.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            )
          : AnchoTablet(
              maxWidth: 560,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 110),
                children: [
                  // ── Avatar GRANDE con pastilla "Editar" superpuesta ──
                  Center(
                    child: Stack(
                      clipBehavior: Clip.none,
                      alignment: Alignment.center,
                      children: [
                        CircleAvatar(
                          radius: 76,
                          backgroundColor: limaSuave,
                          backgroundImage: (foto != null && foto.isNotEmpty)
                              ? NetworkImage(foto)
                              : null,
                          child: _subiendoFoto
                              ? const CircularProgressIndicator(color: bosque)
                              : (foto == null || foto.isEmpty)
                                  ? const Icon(Icons.person,
                                      size: 64, color: bosque)
                                  : null,
                        ),
                        Positioned(
                          bottom: -14,
                          child: Material(
                            elevation: 3,
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(999),
                            child: InkWell(
                              borderRadius: BorderRadius.circular(999),
                              onTap: _subiendoFoto ? null : _menuFoto,
                              child: const Padding(
                                padding: EdgeInsets.symmetric(
                                    horizontal: 16, vertical: 9),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(Icons.photo_camera,
                                        size: 17, color: tinta),
                                    SizedBox(width: 7),
                                    Text('Editar',
                                        style: TextStyle(
                                            fontWeight: FontWeight.w800,
                                            fontSize: 14.5,
                                            color: tinta)),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 34),
                  // ── "Mi perfil" + texto de confianza (como Airbnb) ──
                  const Text('Mi perfil',
                      style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.4)),
                  const SizedBox(height: 6),
                  Text(
                    'Los jugadores y dueños pueden ver tu perfil en el chat, '
                    'los retos y el ranking. Completarlo genera confianza en '
                    'la comunidad.',
                    style: TextStyle(
                        fontSize: 14.5,
                        height: 1.45,
                        color: textoTenueDe(context)),
                  ),
                  const SizedBox(height: 18),
                  _campo('Tu nombre', _nombre),
                  const SizedBox(height: 14),
                  _campo('Celular (opcional)', _celular,
                      prefijo: '+${paisActual.codigoTel} ',
                      tipo: TextInputType.phone,
                      fmt: [FilteringTextInputFormatter.digitsOnly]),
                  const SizedBox(height: 10),
                  // ── Prompts estilo Airbnb (versión deportiva) ──
                  for (final (clave, icono, etiqueta) in _kPromptsBio) ...[
                    InkWell(
                      onTap: () => _editarPrompt(clave, etiqueta),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Row(
                          children: [
                            Icon(icono, size: 25, color: tinta),
                            const SizedBox(width: 15),
                            Expanded(
                              child: (_bio[clave] ?? '').isEmpty
                                  ? Text(etiqueta,
                                      style: TextStyle(
                                          fontSize: 15.5,
                                          fontWeight: FontWeight.w600,
                                          color: textoTenueDe(context)))
                                  : Text('$etiqueta: ${_bio[clave]}',
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontSize: 15.5,
                                          fontWeight: FontWeight.w600,
                                          color: tinta)),
                            ),
                            const Icon(Icons.chevron_right,
                                color: Color(0xFF9A9A9A)),
                          ],
                        ),
                      ),
                    ),
                    const Divider(height: 1, color: Color(0xFFEBEBEB)),
                  ],
                  const SizedBox(height: 26),
                  // ── "Mis deportes" (equivalente a "Mis intereses") ──
                  const Text('Mis deportes',
                      style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.3)),
                  const SizedBox(height: 12),
                  if (appState.misNiveles.isEmpty)
                    Text(
                      'Aún no marcas tu nivel en ningún deporte.',
                      style: TextStyle(
                          fontSize: 14, color: textoTenueDe(context)),
                    )
                  else
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final n in appState.misNiveles)
                          NivelChip(nivel: n),
                      ],
                    ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: Material(
                      color: const Color(0xFFF0F1EF),
                      borderRadius: BorderRadius.circular(12),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(12),
                        onTap: () => Navigator.of(context)
                            .push(MaterialPageRoute(
                                builder: (_) =>
                                    const NivelOnboardingScreen()))
                            .then((_) => setState(() {})),
                        child: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 14),
                          child: Center(
                            child: Text('Edita tus deportes',
                                style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 15,
                                    color: tinta)),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
      // ── Botón charcoal "Listo" fijo abajo (como Airbnb) ──
      bottomNavigationBar: u == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 14),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: tinta,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                    onPressed: _guardando ? null : _guardar,
                    child: const Text('Listo',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 16.5)),
                  ),
                ),
              ),
            ),
    );
  }
}
