import 'package:flutter/material.dart';
import 'package:geocoding/geocoding.dart';

import '../models/models.dart';
import '../services/avisos_service.dart';
import '../services/circuito_service.dart';
import '../services/location_service.dart';
import '../services/retos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'hazte_pro_screen.dart';
import 'login_google_sheet.dart';

/// JUGADORES DISPONIBLES del circuito: el directorio de quienes se declararon
/// "disponibles para retar". Resuelve el arranque en frío del ranking — puedes
/// retar a alguien aunque nadie haya jugado todavía. Aquí también te unes tú.
class JugadoresDisponiblesScreen extends StatefulWidget {
  const JugadoresDisponiblesScreen({super.key});
  @override
  State<JugadoresDisponiblesScreen> createState() =>
      _JugadoresDisponiblesScreenState();
}

class _JugadoresDisponiblesScreenState
    extends State<JugadoresDisponiblesScreen> {
  Deporte? _filtro; // null = todos
  bool _cargando = true;
  List<Map<String, dynamic>> _jugadores = const [];

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    appState.cargarMiPerfilCircuito();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final l = await CircuitoService.jugadores(deporte: _filtro?.name);
    if (!mounted) return;
    setState(() {
      _jugadores = l;
      _cargando = false;
    });
  }

  String _deporteEtiqueta(String name) {
    for (final d in Deporte.values) {
      if (d.name == name) return d.etiqueta;
    }
    return name;
  }

  Future<void> _unirme() async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'unirte al circuito')) {
      return;
    }
    if (!mounted) return;
    final hecho = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => const _UnirseSheet(),
    );
    if (hecho == true && mounted) {
      _cargar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: bosque,
          content: Text('¡Estás en el circuito! Ya pueden retarte.')));
    }
  }

  Future<void> _salir() async {
    final ok = await appState.salirCircuito();
    if (!mounted) return;
    if (ok) _cargar();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok ? 'Saliste del circuito.' : 'No se pudo. Reintenta.')));
  }

  Future<void> _retar(Map<String, dynamic> j) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'retar a un jugador')) {
      return;
    }
    if (!mounted) return;
    final u = appState.usuario;
    if (u == null) return;
    final retadoEmail = (j['email'] ?? '').toString();
    final retadoNombre =
        (j['nombre'] ?? '').toString().isNotEmpty ? j['nombre'].toString() : 'Jugador';
    final deporte = (j['deporte'] ?? _filtro?.name ?? '').toString();
    final resp = await RetosService.crear(
      retadorEmail: u.email,
      retadorNombre: u.nombre,
      retadoEmail: retadoEmail,
      retadoNombre: retadoNombre,
      deporte: deporte,
      zona: (j['zona'] ?? '').toString(),
    );
    if (!mounted) return;
    if (resp != null && resp['error'] == 'limite_retos_free') {
      _ofrecerPro(resp['limite']);
      return;
    }
    final ok = resp != null && resp['ok'] == true;
    if (ok) {
      AvisosService.retoRecibido(
          retadoEmail: retadoEmail, retadorNombre: u.nombre, deporte: deporte);
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: ok ? bosque : null,
      content: Text(ok
          ? 'Reto enviado a $retadoNombre. Coordinen y repórtenlo en "Mis retos".'
          : 'No se pudo enviar el reto. Reintenta.'),
    ));
  }

  Future<void> _ofrecerPro(dynamic limite) async {
    final n = (limite is num) ? limite.toInt() : 3;
    final ir = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Llegaste a tu límite de retos'),
        content: Text(
            'Sin Pichangol Pro puedes enviar $n retos por semana. Hazte Pro y '
            'reta sin límites, con tu carnet oficial y la insignia PRO.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Ahora no')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () => Navigator.pop(dctx, true),
            child: const Text('Hazte Pro'),
          ),
        ],
      ),
    );
    if (ir == true && mounted) {
      Navigator.of(context)
          .push(MaterialPageRoute(builder: (_) => const HazteProScreen()));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Jugadores disponibles')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final enCircuito = appState.estoyEnCircuito;
          return RefreshIndicator(
            color: lima,
            onRefresh: _cargar,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 30),
              children: [
                // Tarjeta de mi estado en el circuito.
                _MiEstadoCard(
                  enCircuito: enCircuito,
                  perfil: appState.miPerfilCircuito,
                  onUnirme: _unirme,
                  onSalir: _salir,
                  deporteEtiqueta: _deporteEtiqueta,
                ),
                const SizedBox(height: 14),
                // Filtro por deporte.
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ChoiceChip(
                      label: const Text('Todos'),
                      selected: _filtro == null,
                      onSelected: (_) {
                        setState(() => _filtro = null);
                        _cargar();
                      },
                    ),
                    for (final d in deportesCircuito)
                      ChoiceChip(
                        label: Text(d.etiqueta),
                        selected: _filtro == d,
                        onSelected: (_) {
                          setState(() => _filtro = d);
                          _cargar();
                        },
                      ),
                  ],
                ),
                const SizedBox(height: 14),
                if (_cargando)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 40),
                    child: Center(child: CircularProgressIndicator(color: lima)),
                  )
                else if (_jugadores.where((j) => (j['email'] ?? '') != _yo).isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 30),
                    child: Column(
                      children: [
                        const Icon(Icons.groups_2_outlined,
                            size: 54, color: textoTenue),
                        const SizedBox(height: 12),
                        Text(
                            enCircuito
                                ? 'Aún no hay otros jugadores disponibles. '
                                    'Invita a tus amigos a unirse al circuito.'
                                : 'Sé el primero en unirte al circuito y deja '
                                    'que te reten.',
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: textoTenue)),
                      ],
                    ),
                  )
                else
                  for (final j in _jugadores)
                    if ((j['email'] ?? '').toString() != _yo)
                      _JugadorCard(
                        j: j,
                        deporteEtiqueta: _deporteEtiqueta,
                        onRetar: () => _retar(j),
                      ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _MiEstadoCard extends StatelessWidget {
  const _MiEstadoCard({
    required this.enCircuito,
    required this.perfil,
    required this.onUnirme,
    required this.onSalir,
    required this.deporteEtiqueta,
  });
  final bool enCircuito;
  final Map<String, dynamic>? perfil;
  final VoidCallback onUnirme;
  final VoidCallback onSalir;
  final String Function(String) deporteEtiqueta;

  @override
  Widget build(BuildContext context) {
    if (!enCircuito) {
      return Container(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [bosque, teal]),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('¿Quieres que te reten?',
                style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                    fontSize: 17)),
            const SizedBox(height: 4),
            const Text(
                'Únete al circuito con tu deporte y zona. Aparecerás aquí para '
                'que otros te reten y empieces a sumar en el ranking.',
                style: TextStyle(color: Colors.white70, height: 1.3, fontSize: 13)),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: onUnirme,
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Unirme al circuito'),
              ),
            ),
          ],
        ),
      );
    }
    final dep = deporteEtiqueta((perfil?['deporte'] ?? '').toString());
    final zona = (perfil?['zona'] ?? '').toString();
    final cat = (perfil?['categoria'] ?? '').toString();
    final detalle = [
      if (dep.isNotEmpty) dep,
      if (zona.isNotEmpty) zona,
      if (cat.isNotEmpty) cat,
    ].join(' · ');
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: bosque),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Estás en el circuito',
                    style: TextStyle(
                        color: bosque, fontWeight: FontWeight.w800)),
                if (detalle.isNotEmpty)
                  Text(detalle,
                      style: const TextStyle(color: bosque, fontSize: 12.5)),
              ],
            ),
          ),
          TextButton(
              onPressed: onUnirme,
              child: const Text('Editar',
                  style: TextStyle(color: bosque, fontWeight: FontWeight.w700))),
          TextButton(
              onPressed: onSalir,
              child: const Text('Salir',
                  style: TextStyle(color: clayOscuro))),
        ],
      ),
    );
  }
}

class _JugadorCard extends StatelessWidget {
  const _JugadorCard(
      {required this.j, required this.onRetar, required this.deporteEtiqueta});
  final Map<String, dynamic> j;
  final VoidCallback onRetar;
  final String Function(String) deporteEtiqueta;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final nombre = (j['nombre'] ?? '').toString();
    final dep = deporteEtiqueta((j['deporte'] ?? '').toString());
    final zona = (j['zona'] ?? '').toString();
    final cat = (j['categoria'] ?? '').toString();
    final detalle = [
      if (dep.isNotEmpty) dep,
      if (zona.isNotEmpty) zona,
      if (cat.isNotEmpty) cat,
    ].join(' · ');
    final esPro = appState.esProEmail((j['email'] ?? '').toString());
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: limaSuave,
            child: Text(nombre.isNotEmpty ? nombre[0].toUpperCase() : '?',
                style: const TextStyle(
                    color: bosque, fontWeight: FontWeight.w800)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(nombre.isNotEmpty ? nombre : 'Jugador',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                    ),
                    if (esPro) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 5, vertical: 1),
                        decoration: BoxDecoration(
                            color: bosque,
                            borderRadius: BorderRadius.circular(5)),
                        child: const Text('PRO',
                            style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 8.5)),
                      ),
                    ],
                  ],
                ),
                if (detalle.isNotEmpty)
                  Text(detalle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: textoTenue, fontSize: 12.5)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: lima,
                foregroundColor: Colors.white,
                visualDensity: VisualDensity.compact),
            onPressed: onRetar,
            child: const Text('Retar'),
          ),
        ],
      ),
    );
  }
}

/// Hoja para unirse/actualizar el perfil de circuito (deporte + zona + nivel).
class _UnirseSheet extends StatefulWidget {
  const _UnirseSheet();
  @override
  State<_UnirseSheet> createState() => _UnirseSheetState();
}

class _UnirseSheetState extends State<_UnirseSheet> {
  // Escalera de categorías de tenis (Perú): de principiante a avanzado.
  static const _categorias = ['5P', '5A', '5B', '4ta', '3ra', '2da', '1ra'];

  Deporte _deporte = deportesCircuito.first;
  final _zona = TextEditingController();
  String _categoria = ''; // '' = sin categoría
  bool _guardando = false;
  bool _detectando = false;

  @override
  void initState() {
    super.initState();
    // Precarga con lo que ya tenía (si edita).
    final p = appState.miPerfilCircuito;
    if (p != null) {
      final dName = (p['deporte'] ?? '').toString();
      for (final d in Deporte.values) {
        if (d.name == dName) _deporte = d;
      }
      _zona.text = (p['zona'] ?? '').toString();
      _categoria = (p['categoria'] ?? '').toString();
    }
    // Si aún no tiene zona, autodetecta su distrito por GPS (país incluido).
    if (_zona.text.trim().isEmpty) _detectarDistrito();
  }

  @override
  void dispose() {
    _zona.dispose();
    super.dispose();
  }

  /// Detecta el distrito por la ubicación actual (reverse-geocode). Respeta el
  /// país donde está el usuario (la geocodificación devuelve el distrito local).
  Future<void> _detectarDistrito() async {
    setState(() => _detectando = true);
    try {
      final pos = await LocationService.ubicacionActual();
      if (pos == null) return;
      final marks = await placemarkFromCoordinates(pos.latitude, pos.longitude);
      if (marks.isEmpty) return;
      final m = marks.first;
      String pick(String? s) => (s ?? '').trim();
      final distrito = pick(m.subLocality).isNotEmpty
          ? pick(m.subLocality)
          : pick(m.locality).isNotEmpty
              ? pick(m.locality)
              : pick(m.subAdministrativeArea);
      if (distrito.isNotEmpty && mounted) {
        setState(() => _zona.text = distrito);
      }
    } catch (_) {
    } finally {
      if (mounted) setState(() => _detectando = false);
    }
  }

  Future<void> _guardar() async {
    setState(() => _guardando = true);
    final ok = await appState.unirseCircuito(
      deporte: _deporte,
      zona: _zona.text.trim(),
      categoria: _categoria.trim(),
    );
    if (!mounted) return;
    setState(() => _guardando = false);
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo. Revisa tu conexión.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Unirme al circuito',
              style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text('Elige tu deporte y zona para que te encuentren y te reten.',
              style: TextStyle(color: textoTenueDe(context), fontSize: 13)),
          const SizedBox(height: 16),
          Text('Deporte', style: t.labelLarge),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final d in deportesCircuito)
                ChoiceChip(
                  label: Text(d.etiqueta),
                  selected: _deporte == d,
                  selectedColor: lima,
                  labelStyle: TextStyle(
                      color: _deporte == d ? Colors.white : cs.onSurface,
                      fontWeight: FontWeight.w600),
                  onSelected: (_) => setState(() => _deporte = d),
                ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _zona,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(
              labelText: 'Zona / distrito',
              hintText: 'Ej.: San Borja',
              prefixIcon: const Icon(Icons.place_outlined),
              // Botón para (re)detectar el distrito por GPS.
              suffixIcon: _detectando
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2.2, color: lima)),
                    )
                  : IconButton(
                      tooltip: 'Usar mi ubicación',
                      icon: const Icon(Icons.my_location, color: bosque),
                      onPressed: _detectarDistrito,
                    ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Nivel / categoría (opcional)', style: t.labelLarge),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ChoiceChip(
                label: const Text('Sin categoría'),
                selected: _categoria.isEmpty,
                onSelected: (_) => setState(() => _categoria = ''),
              ),
              for (final c in _categorias)
                ChoiceChip(
                  label: Text(c),
                  selected: _categoria == c,
                  onSelected: (_) => setState(() => _categoria = c),
                ),
            ],
          ),
          const SizedBox(height: 20),
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
                  : const Text('Guardar y aparecer'),
            ),
          ),
        ],
      ),
    );
  }
}
