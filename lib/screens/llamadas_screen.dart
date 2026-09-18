import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/llamada_historial.dart';
import '../services/llamada_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/responsive.dart';
import 'chat_screen.dart';

/// Registro de llamadas (estilo WhatsApp): entrante/saliente/perdida, con foto,
/// hora y duración. Historial LOCAL del dispositivo.
class LlamadasScreen extends StatefulWidget {
  const LlamadasScreen({super.key});

  @override
  State<LlamadasScreen> createState() => _LlamadasScreenState();
}

class _LlamadasScreenState extends State<LlamadasScreen> {
  List<LlamadaHistorial> _items = const [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final l = await LlamadaService.leerHistorial();
    if (!mounted) return;
    setState(() {
      _items = l;
      _cargando = false;
    });
  }

  Future<void> _borrarTodo() async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Borrar el registro de llamadas?',
      mensaje: 'Se elimina el historial de este dispositivo. No se puede '
          'deshacer.',
      textoConfirmar: 'Borrar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (!ok) return;
    await LlamadaService.limpiarHistorial();
    await _cargar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Llamadas'),
        actions: [
          if (_items.isNotEmpty)
            IconButton(
              tooltip: 'Borrar todo',
              icon: const Icon(Icons.delete_outline),
              onPressed: _borrarTodo,
            ),
        ],
      ),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : _items.isEmpty
              ? _vacio()
              : AnchoTablet(
                  maxWidth: 760,
                  child: ListView.separated(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => Divider(
                        height: 1,
                        indent: 80,
                        color: Colors.black.withOpacity(0.06)),
                    itemBuilder: (_, i) => _fila(_items[i], i),
                  ),
                ),
    );
  }

  Widget _vacio() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.phone_disabled,
                size: 64, color: Colors.black.withOpacity(0.2)),
            const SizedBox(height: 14),
            const Text('Aún no tienes llamadas',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 6),
            Text('Tus llamadas de voz y video aparecerán aquí.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.black.withOpacity(0.55))),
          ],
        ),
      ),
    );
  }

  Widget _fila(LlamadaHistorial c, int index) {
    final nombre = c.nombre.isNotEmpty ? c.nombre : 'Pichangol';
    // Foto: la guardada, o la del perfil por correo (por si se cargó luego).
    final foto = c.foto.isNotEmpty
        ? c.foto
        : (c.email.isNotEmpty ? (appState.fotoDe(c.email) ?? '') : '');
    // Perdida o rechazada → se pinta en rojo (estado negativo).
    final negativa = c.perdida || c.rechazada;
    final colorTexto = negativa ? clayOscuro : const Color(0xFF222222);
    return ListTile(
      onLongPress: () => _eliminarUna(c, index),
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: CircleAvatar(
        radius: 26,
        backgroundColor: limaSuave,
        backgroundImage: foto.isNotEmpty
            ? CachedNetworkImageProvider(foto) as ImageProvider
            : null,
        child: foto.isEmpty
            ? Text(
                (nombre.isNotEmpty ? nombre[0] : '?').toUpperCase(),
                style: const TextStyle(
                    color: bosque, fontWeight: FontWeight.w800, fontSize: 20),
              )
            : null,
      ),
      title: Text(nombre,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
              fontWeight: FontWeight.w700, fontSize: 15.5, color: colorTexto)),
      subtitle: Row(
        children: [
          Icon(
            c.saliente ? Icons.call_made : Icons.call_received,
            size: 15,
            color: negativa ? clayOscuro : (c.saliente ? teal : bosque),
          ),
          const SizedBox(width: 5),
          Flexible(
            child: Text(_subtitulo(c),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    fontSize: 12.8,
                    color: negativa
                        ? clayOscuro
                        : Colors.black.withOpacity(0.55))),
          ),
        ],
      ),
      trailing: IconButton(
        tooltip: 'Volver a llamar',
        icon: Icon(c.video ? Icons.videocam : Icons.call, color: teal),
        onPressed: c.email.isEmpty ? null : () => _abrirChat(c),
      ),
      onTap: c.email.isEmpty ? null : () => _abrirChat(c),
    );
  }

  String _subtitulo(LlamadaHistorial c) {
    final tipo = c.video ? 'Videollamada' : 'Llamada';
    final cuando = _cuando(c.cuando);
    if (c.rechazada) return 'Rechazada · $cuando';
    if (c.perdida) return 'Perdida · $cuando';
    if (!c.conectada) return '$tipo sin respuesta · $cuando';
    return '$tipo · ${_dur(c.duracionSeg)} · $cuando';
  }

  /// Elimina UNA llamada del registro (mantener pulsado → confirmar).
  Future<void> _eliminarUna(LlamadaHistorial c, int index) async {
    final nombre = c.nombre.isNotEmpty ? c.nombre : 'esta llamada';
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Eliminar del registro?',
      mensaje: 'Se quita la llamada con $nombre de este dispositivo.',
      textoConfirmar: 'Eliminar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (!ok) return;
    await LlamadaService.eliminarHistorialEn(index);
    await _cargar();
  }

  String _dur(int seg) {
    final m = (seg ~/ 60).toString().padLeft(2, '0');
    final s = (seg % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  String _cuando(DateTime t) {
    final ahora = DateTime.now();
    final hoy = DateTime(ahora.year, ahora.month, ahora.day);
    final dia = DateTime(t.year, t.month, t.day);
    final hh = t.hour.toString().padLeft(2, '0');
    final mm = t.minute.toString().padLeft(2, '0');
    final difDias = hoy.difference(dia).inDays;
    if (difDias == 0) return '$hh:$mm';
    if (difDias == 1) return 'Ayer $hh:$mm';
    const meses = [
      'ene', 'feb', 'mar', 'abr', 'may', 'jun',
      'jul', 'ago', 'set', 'oct', 'nov', 'dic'
    ];
    return '${t.day} ${meses[t.month - 1]}';
  }

  void _abrirChat(LlamadaHistorial c) {
    // Abre el chat directo con esa persona (ahí están los botones de llamada).
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: c.email,
        titulo: c.nombre.isNotEmpty ? c.nombre : c.email,
        soyProfe: false,
        tipo: 'directo',
        refId: '',
      ),
    ));
  }
}
