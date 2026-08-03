import 'package:flutter/material.dart';

import '../data/db_local.dart';
import '../screens/chat_screen.dart';
import '../screens/login_google_sheet.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// COMPARTIR EN PICHANGOL: envía algo (link/texto de una ficha, producto,
/// referido…) a un chat INTERNO de Pichangol, en vez del share sheet externo.
///
/// Base reutilizable para ir empoderando el chat de a pocos: muestra un selector
/// de conversaciones (cache device-first del inbox) y, al elegir, abre ese chat
/// con el texto **pre-cargado** para que el usuario lo revise y envíe.
class CompartirPichangol {
  CompartirPichangol._();

  /// Comparte [texto] en un chat de Pichangol. Exige sesión (usa el portón único
  /// si no hay). Si no hay conversaciones, avisa y no rompe.
  static Future<void> compartir(BuildContext context,
      {required String texto, String titulo = 'Compartir en Pichangol'}) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'compartir')) return;
    if (!context.mounted) return;
    final email = appState.usuario?.email ?? '';
    final convs = await DbLocal.leerConvs(email);
    if (!context.mounted) return;
    if (convs.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text(
              'Aún no tienes chats en Pichangol. Escríbele a alguien primero.')));
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => _SelectorChats(convs: convs, texto: texto, titulo: titulo),
    );
  }
}

class _SelectorChats extends StatefulWidget {
  const _SelectorChats(
      {required this.convs, required this.texto, required this.titulo});
  final List<Map<String, dynamic>> convs;
  final String texto;
  final String titulo;

  @override
  State<_SelectorChats> createState() => _SelectorChatsState();
}

class _SelectorChatsState extends State<_SelectorChats> {
  String _q = '';

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final q = _q.trim().toLowerCase();
    final lista = q.isEmpty
        ? widget.convs
        : widget.convs
            .where((c) =>
                (c['titulo'] ?? '').toString().toLowerCase().contains(q))
            .toList();
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scroll) => Column(
          children: [
            const SizedBox(height: 10),
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                  color: trazo, borderRadius: BorderRadius.circular(999)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
              child: Row(
                children: [
                  const IconoChatPichanFallback(),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(widget.titulo,
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                onChanged: (v) => setState(() => _q = v),
                decoration: InputDecoration(
                  hintText: 'Buscar chat…',
                  prefixIcon: const Icon(Icons.search),
                  filled: true,
                  fillColor: Theme.of(context).colorScheme.surface,
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
                  enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: Color(0xFFE4E4E4))),
                ),
              ),
            ),
            const SizedBox(height: 6),
            Expanded(
              child: ListView.builder(
                controller: scroll,
                itemCount: lista.length,
                itemBuilder: (context, i) {
                  final c = lista[i];
                  final titulo = (c['titulo'] ?? 'Chat').toString();
                  final foto = appState.fotoDe((c['cuentaEmail'] ?? '').toString());
                  return ListTile(
                    leading: CircleAvatar(
                      backgroundColor: limaSuave,
                      backgroundImage:
                          (foto != null && foto.isNotEmpty)
                              ? NetworkImage(foto)
                              : null,
                      child: (foto == null || foto.isEmpty)
                          ? Text(
                              titulo.isEmpty ? '?' : titulo[0].toUpperCase(),
                              style: const TextStyle(
                                  color: bosque, fontWeight: FontWeight.w800))
                          : null,
                    ),
                    title: Text(titulo,
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    trailing: const Icon(Icons.send, size: 18, color: lima),
                    onTap: () {
                      Navigator.of(context).pop();
                      Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => ChatScreen(
                          academiaId: (c['academiaId'] ?? '').toString(),
                          cuentaEmail: (c['cuentaEmail'] ?? '').toString(),
                          titulo: titulo,
                          soyProfe: (c['soyProfe'] ?? false) == true,
                          tipo: (c['tipo'] ?? 'academia').toString(),
                          refId: (c['refId'] ?? '').toString(),
                          borradorInicial: widget.texto,
                        ),
                      ));
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Ícono de marca del chat (burbuja "P"), tolerante si el widget dedicado no
/// está disponible en este contexto.
class IconoChatPichanFallback extends StatelessWidget {
  const IconoChatPichanFallback({super.key});
  @override
  Widget build(BuildContext context) => Container(
        width: 30,
        height: 30,
        decoration: const BoxDecoration(
            color: Color(0xFF25D366), shape: BoxShape.circle),
        child: const Center(
            child: Text('P',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w900))),
      );
}
