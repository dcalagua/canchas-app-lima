import 'package:flutter/material.dart';

import '../data/mensajes_repo.dart';
import '../models/mensaje.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Conversación 1:1 profe ↔ alumno de una academia (Etapa A: Realtime, sin
/// push). Se usa igual desde el lado del profe ([soyProfe] = true) que del
/// alumno ([soyProfe] = false); [cuentaEmail] identifica el lado alumno.
class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.academiaId,
    required this.cuentaEmail,
    required this.titulo,
    required this.soyProfe,
  });

  final String academiaId;
  final String cuentaEmail;
  final String titulo; // nombre de la contraparte (o de la academia)
  final bool soyProfe;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _texto = TextEditingController();
  final _scroll = ScrollController();
  bool _enviando = false;

  String get _hilo => Mensaje.hiloDe(widget.academiaId, widget.cuentaEmail);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      appState.marcarChatLeido(_hilo);
    });
  }

  @override
  void dispose() {
    appState.marcarChatLeido(_hilo);
    _texto.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _enviar() async {
    final txt = _texto.text.trim();
    final u = appState.usuario;
    if (txt.isEmpty || u == null || _enviando) return;
    setState(() => _enviando = true);
    final msg = Mensaje(
      id: 'msg_${DateTime.now().microsecondsSinceEpoch}',
      hilo: _hilo,
      academiaId: widget.academiaId,
      cuentaEmail: widget.cuentaEmail,
      autorEmail: u.email,
      autorNombre: u.nombre,
      esProfe: widget.soyProfe,
      texto: txt,
      creado: DateTime.now(),
    );
    final ok = await MensajesRepo.enviar(msg);
    if (!mounted) return;
    setState(() => _enviando = false);
    if (ok) {
      _texto.clear();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar. Revisa tu conexión.')));
    }
  }

  void _alFinal() {
    if (!_scroll.hasClients) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.titulo)),
      body: Column(
        children: [
          Expanded(
            child: MensajesRepo.disponible
                ? StreamBuilder<List<Mensaje>>(
                    stream: MensajesRepo.streamHilo(_hilo),
                    builder: (context, snap) {
                      if (snap.connectionState == ConnectionState.waiting) {
                        return const Center(child: CircularProgressIndicator());
                      }
                      final msgs = snap.data ?? const <Mensaje>[];
                      if (msgs.isNotEmpty) {
                        // Fuera de la fase de build (evita notifyListeners en build).
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (mounted) appState.marcarChatLeido(_hilo);
                        });
                        _alFinal();
                      }
                      if (msgs.isEmpty) return const _Vacio();
                      return ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                        itemCount: msgs.length,
                        itemBuilder: (_, i) {
                          final m = msgs[i];
                          final mio = m.esProfe == widget.soyProfe;
                          return _Burbuja(mensaje: m, mio: mio);
                        },
                      );
                    },
                  )
                : const _SinBackend(),
          ),
          _Barra(
              controller: _texto, enviando: _enviando, onEnviar: _enviar),
        ],
      ),
    );
  }
}

class _Burbuja extends StatelessWidget {
  const _Burbuja({required this.mensaje, required this.mio});
  final Mensaje mensaje;
  final bool mio;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hora = TimeOfDay.fromDateTime(mensaje.creado);
    final hh = hora.hour.toString().padLeft(2, '0');
    final mm = hora.minute.toString().padLeft(2, '0');
    return Align(
      alignment: mio ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.76),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.fromLTRB(12, 9, 12, 7),
        decoration: BoxDecoration(
          color: mio ? cs.primary : cs.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(mio ? 16 : 4),
            bottomRight: Radius.circular(mio ? 4 : 16),
          ),
          border: mio ? null : Border.all(color: trazo),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(mensaje.texto,
                style: TextStyle(
                    color: mio ? cs.onPrimary : cs.onSurface, fontSize: 15)),
            const SizedBox(height: 2),
            Text('$hh:$mm',
                style: TextStyle(
                    fontSize: 10,
                    color: mio
                        ? cs.onPrimary.withOpacity(0.8)
                        : textoTenue)),
          ],
        ),
      ),
    );
  }
}

class _Barra extends StatelessWidget {
  const _Barra(
      {required this.controller,
      required this.enviando,
      required this.onEnviar});
  final TextEditingController controller;
  final bool enviando;
  final VoidCallback onEnviar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
        decoration: BoxDecoration(
          color: cs.surface,
          border: Border(top: BorderSide(color: trazo)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                decoration: InputDecoration(
                  hintText: 'Escribe un mensaje…',
                  filled: true,
                  fillColor: Theme.of(context).scaffoldBackgroundColor,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(22),
                      borderSide: BorderSide.none),
                ),
                onSubmitted: (_) => onEnviar(),
              ),
            ),
            const SizedBox(width: 6),
            IconButton.filled(
              onPressed: enviando ? null : onEnviar,
              icon: enviando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Text('Aún no hay mensajes. ¡Escribe el primero!',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
      );
}

class _SinBackend extends StatelessWidget {
  const _SinBackend();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Text(
              'El chat necesita conexión con el servidor. Intenta más tarde.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
      );
}
