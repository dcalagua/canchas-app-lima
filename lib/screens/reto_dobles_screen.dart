import 'dart:async';

import 'package:flutter/material.dart';

import '../data/perfiles_repo.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/reto_flow.dart';

/// Reto de DOBLES (2 vs 2): eliges a tu **compañero** y a los **dos rivales**
/// (4 jugadores registrados). Al enviar, a los rivales les llega la notificación
/// del reto; el resultado se reporta en "Mis retos" y suma al ranking de dobles.
class RetoDoblesScreen extends StatefulWidget {
  const RetoDoblesScreen({super.key, required this.deporte});

  final Deporte deporte;

  @override
  State<RetoDoblesScreen> createState() => _RetoDoblesScreenState();
}

class _RetoDoblesScreenState extends State<RetoDoblesScreen> {
  // Cada slot: (email, nombre, foto). Null = sin elegir.
  (String, String, String)? _companero;
  (String, String, String)? _rival1;
  (String, String, String)? _rival2;
  bool _enviando = false;

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  List<String> get _yaElegidos => [
        _yo,
        if (_companero != null) _companero!.$1.toLowerCase(),
        if (_rival1 != null) _rival1!.$1.toLowerCase(),
        if (_rival2 != null) _rival2!.$1.toLowerCase(),
      ];

  Future<void> _elegir(void Function((String, String, String)) set) async {
    final r = await showModalBottomSheet<(String, String, String)>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _PickerJugador(excluir: _yaElegidos),
    );
    if (r != null) setState(() => set(r));
  }

  bool get _listo => _companero != null && _rival1 != null && _rival2 != null;

  Future<void> _enviar() async {
    if (!_listo || _enviando) return;
    setState(() => _enviando = true);
    await enviarRetoDoblesConGuardia(
      context,
      deporte: widget.deporte.name,
      companeroEmail: _companero!.$1,
      companeroNombre: _companero!.$2,
      rival1Email: _rival1!.$1,
      rival1Nombre: _rival1!.$2,
      rival2Email: _rival2!.$1,
      rival2Nombre: _rival2!.$2,
    );
    if (!mounted) return;
    setState(() => _enviando = false);
    // Si se envió bien, cierra la pantalla (el snackbar lo muestra reto_flow).
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    final yoNombre = appState.usuario?.nombre ?? 'Tú';
    return Scaffold(
      appBar: AppBar(title: const Text('Reto de dobles')),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Text('${emojiDeporte(widget.deporte)}  Dobles de ${widget.deporte.etiqueta}',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          Text(
            'Arma el partido: tu pareja vs la pareja rival. Los cuatro deben '
            'estar registrados en el app.',
            style: TextStyle(color: textoTenue, height: 1.35),
          ),
          const SizedBox(height: 18),
          const _Etiqueta('Tu pareja'),
          _SlotJugador(
            titulo: 'Tú',
            sub: yoNombre,
            fijo: true,
            color: lima,
            foto: appState.usuario?.fotoUrl ?? appState.fotoDe(_yo),
          ),
          const SizedBox(height: 8),
          _SlotJugador(
            titulo: 'Compañero',
            sub: _companero?.$2 ?? 'Elegir compañero',
            elegido: _companero != null,
            color: lima,
            foto: _companero?.$3,
            onTap: () => _elegir((v) => _companero = v),
          ),
          const SizedBox(height: 18),
          const _Etiqueta('Pareja rival'),
          _SlotJugador(
            titulo: 'Rival 1',
            sub: _rival1?.$2 ?? 'Elegir rival',
            elegido: _rival1 != null,
            color: naranja,
            foto: _rival1?.$3,
            onTap: () => _elegir((v) => _rival1 = v),
          ),
          const SizedBox(height: 8),
          _SlotJugador(
            titulo: 'Rival 2',
            sub: _rival2?.$2 ?? 'Elegir rival',
            elegido: _rival2 != null,
            color: naranja,
            foto: _rival2?.$3,
            onTap: () => _elegir((v) => _rival2 = v),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: (_listo && !_enviando) ? _enviar : null,
              icon: const Icon(Icons.sports_kabaddi),
              label: const Text('Enviar reto de dobles',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ),
        ],
      ),
    );
  }
}

class _Etiqueta extends StatelessWidget {
  const _Etiqueta(this.texto);
  final String texto;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(texto,
            style: const TextStyle(
                fontWeight: FontWeight.w800, color: textoTenue, fontSize: 13)),
      );
}

class _SlotJugador extends StatelessWidget {
  const _SlotJugador({
    required this.titulo,
    required this.sub,
    required this.color,
    this.elegido = false,
    this.fijo = false,
    this.foto,
    this.onTap,
  });
  final String titulo;
  final String sub;
  final Color color;
  final bool elegido;
  final bool fijo;

  /// Foto del jugador de este slot (tú / compañero / rival). Si está, se muestra
  /// en el avatar; si no, el ícono.
  final String? foto;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tieneFoto = (foto ?? '').trim().isNotEmpty;
    return Material(
      color: cs.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: fijo ? null : onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: (elegido || fijo) ? color : trazo,
                width: (elegido || fijo) ? 1.5 : 1),
          ),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: (elegido || fijo)
                    ? color
                    : color.withOpacity(0.14),
                backgroundImage:
                    tieneFoto ? NetworkImage(foto!.trim()) : null,
                child: tieneFoto
                    ? null
                    : Icon(fijo ? Icons.person : Icons.person_add_alt_1,
                        color: (elegido || fijo) ? Colors.white : color),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titulo,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text(sub,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            color: elegido ? bosque : textoTenue,
                            fontSize: 12.5,
                            fontWeight:
                                elegido ? FontWeight.w600 : FontWeight.w400)),
                  ],
                ),
              ),
              if (!fijo)
                Icon(elegido ? Icons.check_circle : Icons.chevron_right,
                    color: elegido ? color : textoTenue),
            ],
          ),
        ),
      ),
    );
  }
}

/// Buscador para elegir un jugador (por nombre o correo). Devuelve (email,
/// nombre) al tocar. Excluye a los ya elegidos.
class _PickerJugador extends StatefulWidget {
  const _PickerJugador({required this.excluir});
  final List<String> excluir;
  @override
  State<_PickerJugador> createState() => _PickerJugadorState();
}

class _PickerJugadorState extends State<_PickerJugador> {
  final _q = TextEditingController();
  Timer? _debounce;
  bool _buscando = false;
  List<Map<String, dynamic>> _resultados = const [];

  @override
  void dispose() {
    _debounce?.cancel();
    _q.dispose();
    super.dispose();
  }

  void _onCambio(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _buscar(v));
  }

  Future<void> _buscar(String v) async {
    final q = v.trim();
    if (q.length < 2) {
      setState(() {
        _resultados = const [];
        _buscando = false;
      });
      return;
    }
    setState(() => _buscando = true);
    final r = await PerfilesRepo.buscar(q);
    if (!mounted) return;
    final excl = widget.excluir.map((e) => e.toLowerCase()).toSet();
    setState(() {
      _resultados = r
          .where((p) =>
              !excl.contains((p['email'] ?? '').toString().toLowerCase()))
          .toList();
      _buscando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final insets = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: insets),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        maxChildSize: 0.92,
        builder: (context, scroll) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: TextField(
                controller: _q,
                autofocus: true,
                onChanged: _onCambio,
                decoration: InputDecoration(
                  hintText: 'Nombre o correo del jugador…',
                  prefixIcon: const Icon(Icons.search),
                  filled: true,
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: BorderSide.none),
                ),
              ),
            ),
            Expanded(
              child: _buscando
                  ? const CargandoPichangol()
                  : _q.text.trim().length < 2
                      ? _pista('Escribe al menos 2 letras para buscar.')
                      : _resultados.isEmpty
                          ? _pista('Nadie con ese nombre o correo. La persona '
                              'debe haber entrado al app.')
                          : ListView.separated(
                              controller: scroll,
                              itemCount: _resultados.length,
                              separatorBuilder: (_, __) => Divider(
                                  height: 1, color: trazo.withOpacity(0.5)),
                              itemBuilder: (_, i) {
                                final p = _resultados[i];
                                final email = (p['email'] ?? '').toString();
                                final nombre = (p['nombre'] ?? '').toString();
                                final foto = (p['foto_url'] ?? '').toString();
                                final mostrar =
                                    nombre.isNotEmpty ? nombre : email;
                                return ListTile(
                                  onTap: () => Navigator.pop(
                                      context,
                                      (email,
                                          nombre.isNotEmpty ? nombre : email,
                                          foto)),
                                  leading: CircleAvatar(
                                    backgroundColor: teal,
                                    backgroundImage: foto.isNotEmpty
                                        ? NetworkImage(foto)
                                        : null,
                                    child: foto.isEmpty
                                        ? Text(
                                            mostrar.isNotEmpty
                                                ? mostrar[0].toUpperCase()
                                                : '?',
                                            style: const TextStyle(
                                                color: Colors.white,
                                                fontWeight: FontWeight.w800))
                                        : null,
                                  ),
                                  title: Text(mostrar,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700)),
                                  subtitle: nombre.isNotEmpty
                                      ? Text(email,
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                              color: textoTenue, fontSize: 12))
                                      : null,
                                );
                              },
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _pista(String t) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Text(t,
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue)),
        ),
      );
}
