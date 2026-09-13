import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../data/canales_repo.dart';
import '../models/canal.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'canal_detalle_screen.dart';
import 'crear_canal_screen.dart';
import 'login_google_sheet.dart';

/// CANALES (tipo WhatsApp Channels): lista los canales que sigo + descubrir
/// otros + crear el mío. Difusión uno-a-muchos.
class CanalesScreen extends StatefulWidget {
  const CanalesScreen({super.key});

  @override
  State<CanalesScreen> createState() => _CanalesScreenState();
}

class _CanalesScreenState extends State<CanalesScreen> {
  List<Canal> _todos = const [];
  Set<String> _seguidos = {};
  Map<String, CanalPost> _ultimas = {};
  bool _cargando = true;
  String _filtro = '';

  String get _yo => (appState.usuario?.email ?? '').toLowerCase();

  bool _coincide(Canal c) {
    if (_filtro.isEmpty) return true;
    return c.nombre.toLowerCase().contains(_filtro) ||
        c.descripcion.toLowerCase().contains(_filtro);
  }

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final todos = await CanalesRepo.todos();
    final seguidos = await CanalesRepo.seguidosDe(_yo);
    final ultimas = await CanalesRepo.ultimasDe(todos.map((c) => c.id).toList());
    if (!mounted) return;
    setState(() {
      _todos = todos;
      _seguidos = seguidos;
      _ultimas = ultimas;
      _cargando = false;
    });
  }

  Future<void> _crear() async {
    if (!appState.logueado) {
      if (!await LoginGoogleSheet.mostrar(context, motivo: 'crear un canal')) {
        return;
      }
    }
    final nuevo = await Navigator.of(context).push<Canal>(
        MaterialPageRoute(builder: (_) => const CrearCanalScreen()));
    if (nuevo != null && mounted) {
      await _cargar();
      if (mounted) _abrir(nuevo);
    }
  }

  Future<void> _abrir(Canal c) async {
    await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => CanalDetalleScreen(canal: c)));
    if (mounted) _cargar();
  }

  @override
  Widget build(BuildContext context) {
    final misCanales =
        _todos.where((c) => c.ownerEmail == _yo && _coincide(c)).toList();
    final sigo = _todos
        .where((c) =>
            _seguidos.contains(c.id) && c.ownerEmail != _yo && _coincide(c))
        .toList();
    final descubrir = _todos
        .where((c) =>
            !_seguidos.contains(c.id) && c.ownerEmail != _yo && _coincide(c))
        .toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Canales',
            style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        onPressed: _crear,
        icon: const Icon(Icons.add, color: Colors.white),
        label: const Text('Crear canal',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
      ),
      body: _cargando
          ? const CargandoPichangol()
          : AnchoTablet(
              maxWidth: 760,
              child: RefreshIndicator(
                onRefresh: _cargar,
                child: ListView(
                  padding: const EdgeInsets.only(bottom: 90),
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
                      child: TextField(
                        onChanged: (v) =>
                            setState(() => _filtro = v.trim().toLowerCase()),
                        decoration: InputDecoration(
                          hintText: 'Buscar',
                          prefixIcon: const Icon(Icons.search),
                          isDense: true,
                          filled: true,
                          fillColor: Theme.of(context).brightness ==
                                  Brightness.dark
                              ? const Color(0xFF1F2C34)
                              : const Color(0xFFF0F0F0),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(24),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),
                    ),
                    if (_todos.isEmpty)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(28, 60, 28, 20),
                        child: Column(
                          children: [
                            const Icon(Icons.campaign_outlined,
                                size: 56, color: lima),
                            const SizedBox(height: 12),
                            Text(
                                'Aún no hay canales. Crea el primero para '
                                'difundir novedades a tus seguidores.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: textoTenueDe(context))),
                          ],
                        ),
                      ),
                    if (misCanales.isNotEmpty) ...[
                      _seccion('Mis canales'),
                      for (final c in misCanales) _fila(c, esMio: true),
                    ],
                    if (sigo.isNotEmpty) ...[
                      _seccion('Siguiendo'),
                      for (final c in sigo) _fila(c),
                    ],
                    if (descubrir.isNotEmpty) ...[
                      _seccion('Descubrir canales'),
                      for (final c in descubrir) _fila(c),
                    ],
                  ],
                ),
              ),
            ),
    );
  }

  Widget _seccion(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 6),
        child: Text(t,
            style: TextStyle(
                color: textoTenueDe(context),
                fontWeight: FontWeight.w800,
                fontSize: 13)),
      );

  Widget _fila(Canal c, {bool esMio = false}) {
    final ultima = _ultimas[c.id];
    final foto = c.fotoUrl;
    final sub = ultima != null
        ? (ultima.esFoto
            ? '📷 Foto'
            : ultima.esVideo
                ? '🎥 Video'
                : ultima.texto)
        : '${c.seguidores} seguidores';
    return ListTile(
      onTap: () => _abrir(c),
      leading: CircleAvatar(
        radius: 26,
        backgroundColor: limaSuave,
        backgroundImage: foto.isNotEmpty ? CachedNetworkImageProvider(foto) : null,
        child: foto.isEmpty
            ? const Icon(Icons.campaign, color: lima)
            : null,
      ),
      title: Row(
        children: [
          Flexible(
            child: Text(c.nombre,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          if (esMio)
            const Padding(
              padding: EdgeInsets.only(left: 6),
              child: Icon(Icons.verified, size: 15, color: lima),
            ),
        ],
      ),
      subtitle: Text(sub,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(color: textoTenueDe(context))),
      trailing: esMio
          ? null
          : _seguidos.contains(c.id)
              ? Text('Siguiendo',
                  style: TextStyle(
                      color: textoTenueDe(context),
                      fontSize: 12,
                      fontWeight: FontWeight.w600))
              : TextButton(
                  onPressed: () async {
                    await CanalesRepo.seguir(c.id, _yo);
                    if (mounted) {
                      setState(() => _seguidos = {..._seguidos, c.id});
                    }
                  },
                  child: const Text('Seguir',
                      style: TextStyle(
                          color: lima, fontWeight: FontWeight.w800)),
                ),
    );
  }
}
