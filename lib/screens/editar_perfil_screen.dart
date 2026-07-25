import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../config/pais.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// EDITAR MI PERFIL: el nombre (y foto) con que la persona se muestra en el chat,
/// el ranking, los retos, etc. Muchos usuarios tienen cualquier cosa en su Gmail;
/// aquí ponen el nombre real que quieren que vean los demás.
/// Fase 1: editar el NOMBRE. La foto se muestra (la de Google); cambiarla por una
/// propia queda para una fase siguiente.
class EditarPerfilScreen extends StatefulWidget {
  const EditarPerfilScreen({super.key});
  @override
  State<EditarPerfilScreen> createState() => _EditarPerfilScreenState();
}

class _EditarPerfilScreenState extends State<EditarPerfilScreen> {
  late final TextEditingController _nombre =
      TextEditingController(text: appState.usuario?.nombre ?? '');
  // Celular guardado SIN el código de país (se muestra con el prefijo aparte).
  late final TextEditingController _celular =
      TextEditingController(text: _celularLocal(appState.miCelular));
  bool _guardando = false;
  bool _subiendoFoto = false;

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

  Future<void> _guardar() async {
    final n = _nombre.text.trim();
    if (n.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Escribe tu nombre.')));
      return;
    }
    setState(() => _guardando = true);
    // Celular en formato internacional (con código de país), o '' si lo borró.
    final celDigits = _celular.text.replaceAll(RegExp(r'[^0-9]'), '');
    final cel = celDigits.isEmpty ? '' : '${paisActual.codigoTel}$celDigits';
    final ok = await appState.actualizarMiNombre(n, celular: cel);
    if (!mounted) return;
    setState(() => _guardando = false);
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

  @override
  Widget build(BuildContext context) {
    final u = appState.usuario;
    final foto = u?.fotoUrl;
    return Scaffold(
      appBar: AppBar(title: const Text('Mi perfil')),
      body: u == null
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Inicia sesión para editar tu perfil.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 30),
              children: [
                Center(
                  child: Stack(
                    children: [
                      CircleAvatar(
                        radius: 44,
                        backgroundColor: limaSuave,
                        backgroundImage: (foto != null && foto.isNotEmpty)
                            ? NetworkImage(foto)
                            : null,
                        child: _subiendoFoto
                            ? const CircularProgressIndicator(color: bosque)
                            : (foto == null || foto.isEmpty)
                                ? const Icon(Icons.person,
                                    size: 40, color: bosque)
                                : null,
                      ),
                      Positioned(
                        right: 0,
                        bottom: 0,
                        child: Material(
                          color: bosque,
                          shape: const CircleBorder(),
                          child: InkWell(
                            customBorder: const CircleBorder(),
                            onTap: _subiendoFoto ? null : _menuFoto,
                            child: const Padding(
                              padding: EdgeInsets.all(7),
                              child: Icon(Icons.photo_camera,
                                  color: Colors.white, size: 18),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Center(
                  child: Text(u.email,
                      style: const TextStyle(color: textoTenue, fontSize: 13)),
                ),
                const SizedBox(height: 24),
                const Text('Tu nombre',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                TextField(
                  controller: _nombre,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(
                      hintText: 'Ej.: Dennis Calagua',
                      prefixIcon: Icon(Icons.badge_outlined)),
                ),
                const SizedBox(height: 8),
                const Text(
                    'Este es el nombre que verán los demás en el chat, el ranking '
                    'y los retos (aunque tu Gmail muestre otra cosa).',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
                const SizedBox(height: 20),
                const Text('Celular / WhatsApp (opcional)',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                TextField(
                  controller: _celular,
                  keyboardType: TextInputType.phone,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(paisActual.telLongitud),
                  ],
                  decoration: InputDecoration(
                    prefixText: '${banderaActual} $codigoTelActual  ',
                    hintText: 'Tu número',
                    prefixIcon: const Icon(Icons.chat, color: Color(0xFF25D366)),
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                    'Si lo pones, los demás verán un botón "WhatsApp" para '
                    'escribirte por ahí. Es opcional; puedes dejarlo vacío.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _guardando ? null : _guardar,
                    child: _guardando
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2.4, color: Colors.white))
                        : const Text('Guardar'),
                  ),
                ),
                const SizedBox(height: 14),
                const Row(
                  children: [
                    Icon(Icons.info_outline, size: 18, color: textoTenue),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                          'Toca la cámara para cambiar tu foto (galería o cámara). '
                          'El nombre se guarda con el botón de arriba.',
                          style: TextStyle(
                              color: textoTenue, fontSize: 12, height: 1.3)),
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}
