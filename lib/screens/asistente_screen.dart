import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../models/models.dart';
import '../services/concierge_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/geo.dart';
import 'cancha_detalle_screen.dart';

/// Asistente Pichangol (primer agente de IA): el jugador escribe en lenguaje
/// natural ("fútbol mañana 8pm por Surco") y el concierge le sugiere canchas.
/// La IA corre en el backend; aquí sólo se manda el mensaje + las canchas
/// visibles y se pintan las sugerencias.
class AsistenteScreen extends StatefulWidget {
  const AsistenteScreen({super.key, this.centro});

  /// Centro de búsqueda (zona del usuario) para calcular distancias.
  final LatLng? centro;

  @override
  State<AsistenteScreen> createState() => _AsistenteScreenState();
}

class _Turno {
  final bool mio;
  final String texto;
  final List<SugerenciaConcierge> sugerencias;
  _Turno.usuario(this.texto)
      : mio = true,
        sugerencias = const [];
  _Turno.bot(this.texto, [this.sugerencias = const []]) : mio = false;
}

class _AsistenteScreenState extends State<AsistenteScreen> {
  final _texto = TextEditingController();
  final _scroll = ScrollController();
  final _turnos = <_Turno>[];
  bool _pensando = false;

  static const _ejemplos = [
    'Fútbol hoy a las 8pm cerca',
    'Cancha de tenis por Surco',
    'Algo barato para la tarde',
  ];

  @override
  void initState() {
    super.initState();
    _turnos.add(_Turno.bot(
        '¡Hola! Soy tu asistente de reservas. Dime qué quieres jugar, cuándo y '
        'por dónde, y te busco cancha. 🎾⚽'));
  }

  @override
  void dispose() {
    _texto.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _enviar([String? sugerido]) async {
    final msg = (sugerido ?? _texto.text).trim();
    if (msg.isEmpty || _pensando) return;
    _texto.clear();
    setState(() {
      _turnos.add(_Turno.usuario(msg));
      _pensando = true;
    });
    _alFinal();

    if (!ConciergeService.disponible) {
      setState(() {
        _pensando = false;
        _turnos.add(_Turno.bot(
            'El asistente necesita conexión con el servidor. Intenta más tarde.'));
      });
      _alFinal();
      return;
    }

    final canchas = appState.todasLasCanchas();
    final res =
        await ConciergeService.recomendar(msg, canchas, centro: widget.centro);
    if (!mounted) return;
    setState(() {
      _pensando = false;
      if (res == null) {
        _turnos.add(_Turno.bot(
            'No pude conectarme ahora. Revisa tu internet y vuelve a intentar.'));
      } else {
        _turnos.add(_Turno.bot(
            res.respuesta.isEmpty
                ? 'Esto es lo que encontré:'
                : res.respuesta,
            res.sugerencias));
      }
    });
    _alFinal();
  }

  void _alFinal() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 240), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Asistente Pichangol'),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
              itemCount: _turnos.length + (_pensando ? 1 : 0),
              itemBuilder: (context, i) {
                if (i >= _turnos.length) return const _Escribiendo();
                return _BurbujaTurno(turno: _turnos[i], centro: widget.centro);
              },
            ),
          ),
          if (_turnos.length <= 1)
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  for (final e in _ejemplos)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ActionChip(
                        label: Text(e),
                        onPressed: () => _enviar(e),
                      ),
                    ),
                ],
              ),
            ),
          SafeArea(
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
                      controller: _texto,
                      minLines: 1,
                      maxLines: 4,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: InputDecoration(
                        hintText: 'Escribe qué quieres jugar…',
                        filled: true,
                        fillColor: Theme.of(context).scaffoldBackgroundColor,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(22),
                            borderSide: BorderSide.none),
                      ),
                      onSubmitted: (_) => _enviar(),
                    ),
                  ),
                  const SizedBox(width: 6),
                  IconButton.filled(
                    onPressed: _pensando ? null : () => _enviar(),
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BurbujaTurno extends StatelessWidget {
  const _BurbujaTurno({required this.turno, required this.centro});
  final _Turno turno;
  final LatLng? centro;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final mio = turno.mio;
    return Column(
      crossAxisAlignment:
          mio ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: [
        Align(
          alignment: mio ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.8),
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.fromLTRB(12, 9, 12, 9),
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
            child: Text(turno.texto,
                style: TextStyle(
                    color: mio ? cs.onPrimary : cs.onSurface, fontSize: 15)),
          ),
        ),
        for (final s in turno.sugerencias)
          _TarjetaSugerencia(sugerencia: s, centro: centro),
        if (turno.sugerencias.isNotEmpty) const SizedBox(height: 6),
      ],
    );
  }
}

class _TarjetaSugerencia extends StatelessWidget {
  const _TarjetaSugerencia({required this.sugerencia, required this.centro});
  final SugerenciaConcierge sugerencia;
  final LatLng? centro;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final c = sugerencia.cancha;
    final dist = centro == null
        ? null
        : distanciaKm(centro!, c.ubicacion);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => CanchaDetalleScreen(cancha: c))),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: colorDeporte(c.deporte),
                child: Icon(iconoDeporte(c.deporte), color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(c.nombre,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 2),
                    Text(
                        '${c.deporte.etiqueta} · ${c.distrito.etiqueta}'
                        '${dist != null ? ' · ${dist.toStringAsFixed(1)} km' : ''}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: textoTenue, fontSize: 12)),
                    if (sugerencia.motivo.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(sugerencia.motivo,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: cs.primary,
                              fontSize: 12,
                              fontWeight: FontWeight.w600)),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('S/ ${c.precioHora.toStringAsFixed(2)}',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, color: cs.onSurface)),
                  const Text('/ hora',
                      style: TextStyle(color: textoTenue, fontSize: 11)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Escribiendo extends StatelessWidget {
  const _Escribiendo();
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo),
        ),
        child: const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      ),
    );
  }
}
