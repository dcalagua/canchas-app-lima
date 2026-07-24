import 'package:flutter/material.dart';

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
  bool _guardando = false;

  @override
  void dispose() {
    _nombre.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    final n = _nombre.text.trim();
    if (n.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Escribe tu nombre.')));
      return;
    }
    setState(() => _guardando = true);
    final ok = await appState.actualizarMiNombre(n);
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
                  child: CircleAvatar(
                    radius: 44,
                    backgroundColor: limaSuave,
                    backgroundImage:
                        (foto != null && foto.isNotEmpty) ? NetworkImage(foto) : null,
                    child: (foto == null || foto.isEmpty)
                        ? const Icon(Icons.person, size: 40, color: bosque)
                        : null,
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
                Row(
                  children: [
                    const Icon(Icons.photo_camera_outlined,
                        size: 18, color: textoTenue),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                          'Cambiar tu foto por una propia estará disponible pronto. '
                          'Por ahora se usa la de tu cuenta de Google.',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12, height: 1.3)),
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}
