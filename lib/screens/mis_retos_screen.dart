import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/avisos_service.dart';
import '../services/retos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// MIS RETOS P2P: retos recibidos (aceptar/rechazar) y enviados; reportar el
/// resultado de los aceptados (suma al ranking global).
class MisRetosScreen extends StatefulWidget {
  const MisRetosScreen({super.key});
  @override
  State<MisRetosScreen> createState() => _MisRetosScreenState();
}

class _MisRetosScreenState extends State<MisRetosScreen> {
  bool _cargando = true;
  List<Map<String, dynamic>> _recibidos = const [];
  List<Map<String, dynamic>> _enviados = const [];

  String get _email => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    if (_email.isEmpty) {
      setState(() => _cargando = false);
      return;
    }
    setState(() => _cargando = true);
    final r = await RetosService.mios(_email);
    if (!mounted) return;
    setState(() {
      _recibidos = ((r?['recibidos'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      _enviados = ((r?['enviados'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      _cargando = false;
    });
  }

  String _deporte(String name) {
    for (final d in Deporte.values) {
      if (d.name == name) return d.etiqueta;
    }
    return name;
  }

  Future<void> _responder(Map<String, dynamic> r, bool aceptar) async {
    final ok = await RetosService.responder((r['id'] as num).toInt(), aceptar);
    if (!mounted) return;
    if (ok) {
      // Avisa al retador que respondí su reto (push, best-effort).
      AvisosService.retoRespondido(
          retadorEmail: (r['retador_email'] ?? '').toString(),
          retadoNombre: (r['retado_nombre'] ?? 'Tu rival').toString(),
          aceptado: aceptar);
      await _cargar();
      await appState.cargarRetosPendientes(); // refresca el badge del perfil
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo. Reintenta.')));
    }
  }

  Future<void> _reportar(Map<String, dynamic> r) async {
    final retadorEmail = (r['retador_email'] ?? '').toString();
    final retadoEmail = (r['retado_email'] ?? '').toString();
    final retadorNombre = (r['retador_nombre'] ?? 'Retador').toString();
    final retadoNombre = (r['retado_nombre'] ?? 'Retado').toString();
    final marcador = TextEditingController();
    String? ganador;
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => StatefulBuilder(
        builder: (dctx, setSB) => AlertDialog(
          title: Row(
            children: const [
              CircleAvatar(
                radius: 16,
                backgroundColor: amarillo,
                child: Icon(Icons.emoji_events, color: Colors.white, size: 18),
              ),
              SizedBox(width: 10),
              Text('Reportar resultado'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('¿Quién ganó?',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              for (final o in [
                (retadorEmail, retadorNombre),
                (retadoEmail, retadoNombre),
              ])
                _OpcionGanador(
                  nombre: o.$2,
                  seleccionado: ganador == o.$1,
                  onTap: () => setSB(() => ganador = o.$1),
                ),
              const SizedBox(height: 8),
              TextField(
                controller: marcador,
                decoration: const InputDecoration(
                    labelText: 'Marcador (opcional)', hintText: 'ej. 6-3 6-4'),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dctx, false),
                child: const Text('Cancelar')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: ganador == null
                  ? null
                  : () => Navigator.pop(dctx, true),
              child: const Text('Guardar'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || ganador == null) return;
    final done = await RetosService.resultado(
        (r['id'] as num).toInt(), ganador!,
        marcador: marcador.text.trim());
    if (!mounted) return;
    if (done) {
      // Avisa al OTRO jugador que reporté el resultado (push, best-effort).
      final yo = _email;
      final otroEmail = retadorEmail.toLowerCase() == yo
          ? retadoEmail
          : retadorEmail;
      final miNombre =
          retadorEmail.toLowerCase() == yo ? retadorNombre : retadoNombre;
      AvisosService.resultadoReportado(
          email: otroEmail, porNombre: miNombre, marcador: marcador.text.trim());
      await appState.cargarRetosResultados(); // refresca el ranking
      await appState.cargarRetosPendientes(); // refresca el badge del perfil
      await _cargar();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            backgroundColor: bosque,
            content: Text('Resultado guardado. Sumó al ranking.')));
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No se pudo guardar.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis retos')),
      body: _email.isEmpty
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(28),
                child: Text('Inicia sesión para ver tus retos.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: textoTenue)),
              ),
            )
          : _cargando
              ? const Center(child: CircularProgressIndicator(color: lima))
              : RefreshIndicator(
                  color: lima,
                  onRefresh: _cargar,
                  child: (_recibidos.isEmpty && _enviados.isEmpty)
                      ? ListView(children: const [
                          SizedBox(height: 80),
                          Icon(Icons.sports_kabaddi,
                              size: 60, color: textoTenue),
                          SizedBox(height: 12),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 30),
                            child: Text(
                                'Aún no tienes retos. Abre el Ranking Global, '
                                'toca un jugador y rétalo.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: textoTenue)),
                          ),
                        ])
                      : ListView(
                          padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
                          children: [
                            if (_recibidos.isNotEmpty) ...[
                              const Text('Recibidos',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 16)),
                              const SizedBox(height: 8),
                              for (final r in _recibidos)
                                _RetoCard(
                                    r: r,
                                    soyRetado: true,
                                    deporte: _deporte(
                                        (r['deporte'] ?? '').toString()),
                                    onAceptar: () => _responder(r, true),
                                    onRechazar: () => _responder(r, false),
                                    onReportar: () => _reportar(r)),
                              const SizedBox(height: 12),
                            ],
                            if (_enviados.isNotEmpty) ...[
                              const Text('Enviados',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 16)),
                              const SizedBox(height: 8),
                              for (final r in _enviados)
                                _RetoCard(
                                    r: r,
                                    soyRetado: false,
                                    deporte: _deporte(
                                        (r['deporte'] ?? '').toString()),
                                    onReportar: () => _reportar(r)),
                            ],
                          ],
                        ),
                ),
    );
  }
}

/// Opción de ganador en "Reportar resultado": tarjeta con avatar de color +
/// nombre, resaltada al elegirla. Más viva y clara que un radio pelado.
class _OpcionGanador extends StatelessWidget {
  const _OpcionGanador(
      {required this.nombre, required this.seleccionado, required this.onTap});
  final String nombre;
  final bool seleccionado;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final inicial =
        nombre.trim().isNotEmpty ? nombre.trim()[0].toUpperCase() : '?';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: seleccionado
                ? limaSuave
                : Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
                color: seleccionado ? lima : trazo,
                width: seleccionado ? 1.5 : 1),
          ),
          child: Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: teal,
                child: Text(inicial,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              Icon(
                  seleccionado
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  color: seleccionado ? lima : textoTenue),
            ],
          ),
        ),
      ),
    );
  }
}

class _RetoCard extends StatelessWidget {
  const _RetoCard({
    required this.r,
    required this.soyRetado,
    required this.deporte,
    this.onAceptar,
    this.onRechazar,
    this.onReportar,
  });
  final Map<String, dynamic> r;
  final bool soyRetado;
  final String deporte;
  final VoidCallback? onAceptar;
  final VoidCallback? onRechazar;
  final VoidCallback? onReportar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final estado = (r['estado'] ?? '').toString();
    // El "otro" jugador según mi rol.
    final otro = soyRetado
        ? (r['retador_nombre'] ?? 'Retador').toString()
        : (r['retado_nombre'] ?? 'Retado').toString();
    // Colores VIVOS y distintos por estado (como los deportes de la home), no
    // tonos oscuros/apagados.
    final (String etiqueta, Color color, IconData icono) = switch (estado) {
      'pendiente' => ('Pendiente', amarillo, Icons.hourglass_top),
      'aceptado' => ('Aceptado', lima, Icons.handshake),
      'jugado' => ('Jugado', morado, Icons.emoji_events),
      'rechazado' => ('Rechazado', clayOscuro, Icons.close),
      _ => (estado, teal, Icons.sports_kabaddi),
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Ícono estilo Airbnb: círculo de color según el estado del reto.
              CircleAvatar(
                radius: 22,
                backgroundColor: color,
                child: Icon(icono, color: Colors.white, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                              soyRetado ? 'Te retó $otro' : 'Retaste a $otro',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                              color: color.withOpacity(0.14),
                              borderRadius: BorderRadius.circular(8)),
                          child: Text(etiqueta,
                              style: TextStyle(
                                  color: color,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 11.5)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                        '$deporte'
                        '${(r['zona'] ?? '').toString().isNotEmpty ? ' · ${r['zona']}' : ''}',
                        style:
                            const TextStyle(color: textoTenue, fontSize: 12.5)),
                    if (estado == 'jugado' &&
                        (r['marcador'] ?? '').toString().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text('Resultado: ${r['marcador']}',
                          style: const TextStyle(
                              color: textoTenue, fontSize: 12.5)),
                    ],
                  ],
                ),
              ),
            ],
          ),
          if (estado == 'pendiente' && soyRetado) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onRechazar,
                    style: OutlinedButton.styleFrom(
                        foregroundColor: clayOscuro,
                        side: const BorderSide(color: clayOscuro)),
                    child: const Text('Rechazar'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: lima),
                    onPressed: onAceptar,
                    child: const Text('Aceptar'),
                  ),
                ),
              ],
            ),
          ],
          if (estado == 'aceptado') ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: onReportar,
                icon: const Icon(Icons.emoji_events, size: 18),
                label: const Text('Reportar resultado'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
