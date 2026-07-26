import 'dart:async';

import 'package:flutter/material.dart';

import '../data/grupos_repo.dart';
import '../data/perfiles_repo.dart';
import '../models/grupo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'chat_screen.dart';

/// Crea un grupo de chat: nombre + miembros. Los miembros se buscan por NOMBRE o
/// CORREO (como al buscar un jugador) y se agregan con un toque; no se puede
/// agregar dos veces a la misma persona (estilo WhatsApp). El creador queda como
/// miembro automáticamente.
class CrearGrupoScreen extends StatefulWidget {
  const CrearGrupoScreen({super.key});

  @override
  State<CrearGrupoScreen> createState() => _CrearGrupoScreenState();
}

class _CrearGrupoScreenState extends State<CrearGrupoScreen> {
  final _nombre = TextEditingController();
  final _q = TextEditingController();
  Timer? _debounce;
  bool _buscando = false;
  List<Map<String, dynamic>> _resultados = const [];

  // Miembros elegidos (además del creador): {email, nombre, foto_url}.
  final List<Map<String, dynamic>> _miembros = [];
  bool _creando = false;

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void dispose() {
    _debounce?.cancel();
    _nombre.dispose();
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
    setState(() {
      // Excluye mi propio correo (el creador ya entra al grupo).
      _resultados = r
          .where((p) => (p['email'] ?? '').toString().toLowerCase() != _yo)
          .toList();
      _buscando = false;
    });
  }

  bool _yaAgregado(String email) =>
      _miembros.any((m) => (m['email'] ?? '').toString().toLowerCase() ==
          email.toLowerCase());

  void _alternar(Map<String, dynamic> perfil) {
    final email = (perfil['email'] ?? '').toString().trim();
    if (email.isEmpty) return;
    setState(() {
      if (_yaAgregado(email)) {
        _miembros.removeWhere((m) =>
            (m['email'] ?? '').toString().toLowerCase() == email.toLowerCase());
      } else {
        _miembros.add({
          'email': email,
          'nombre': (perfil['nombre'] ?? '').toString(),
          'foto_url': (perfil['foto_url'] ?? '').toString(),
        });
      }
    });
  }

  bool _emailValido(String s) {
    final e = s.trim();
    return e.contains('@') && e.contains('.') && !e.contains(' ');
  }

  void _aviso(String m) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(m)));

  Future<void> _crear() async {
    final nombre = _nombre.text.trim();
    final me = appState.usuario;
    if (me == null) return;
    if (nombre.isEmpty) {
      _aviso('Ponle un nombre al grupo.');
      return;
    }
    if (_miembros.isEmpty) {
      _aviso('Agrega al menos un miembro.');
      return;
    }
    if (_creando) return;
    setState(() => _creando = true);
    final id = 'grp_${DateTime.now().microsecondsSinceEpoch}';
    final grupo = Grupo(id: id, nombre: nombre, creadorEmail: me.email);
    final miembros = <Map<String, String>>[
      {'email': me.email, 'nombre': me.nombre},
      for (final m in _miembros)
        {
          'email': (m['email'] ?? '').toString(),
          'nombre': (m['nombre'] ?? '').toString(),
        },
    ];
    bool ok;
    try {
      ok = await conPreload(context, () => GruposRepo.crear(grupo, miembros),
          texto: 'Creando grupo…');
    } finally {
      if (mounted) setState(() => _creando = false);
    }
    if (!mounted) return;
    if (!ok) {
      _aviso('No se pudo crear el grupo. Revisa tu conexión.');
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: '',
        titulo: nombre,
        soyProfe: false,
        tipo: 'grupo',
        refId: id,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final hayQuery = _q.text.trim().length >= 2;
    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo grupo')),
      body: AnchoTablet(
        maxWidth: 600,
        child: Column(
          children: [
            // Encabezado fijo: nombre + miembros elegidos + buscador.
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    controller: _nombre,
                    textCapitalization: TextCapitalization.sentences,
                    decoration: const InputDecoration(
                      labelText: 'Nombre del grupo',
                      hintText: 'Ej. Fútbol de los martes',
                      prefixIcon: Icon(Icons.groups_outlined),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      const Text('Miembros',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 15)),
                      if (_miembros.isNotEmpty)
                        Text('  ·  ${_miembros.length}',
                            style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 15,
                                color: lima)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  // Chips de los miembros ya agregados (quitar con la X).
                  if (_miembros.isNotEmpty)
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final m in _miembros)
                          _ChipMiembro(
                            perfil: m,
                            onQuitar: () => _alternar(m),
                          ),
                      ],
                    ),
                  if (_miembros.isNotEmpty) const SizedBox(height: 12),
                  TextField(
                    controller: _q,
                    onChanged: (v) {
                      _onCambio(v);
                      setState(() {}); // refresca el ícono de limpiar
                    },
                    decoration: InputDecoration(
                      hintText: 'Buscar por nombre o correo…',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: _q.text.isEmpty
                          ? null
                          : IconButton(
                              icon: const Icon(Icons.close),
                              onPressed: () {
                                _q.clear();
                                _buscar('');
                                setState(() {});
                              },
                            ),
                      filled: true,
                      border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide.none),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text('Deben ser cuentas registradas en la app.',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ],
              ),
            ),
            // Resultados de la búsqueda (o ayuda).
            Expanded(
              child: ListenableBuilder(
                listenable: appState,
                builder: (context, _) {
                  if (_buscando) {
                    return const Padding(
                      padding: EdgeInsets.only(top: 30),
                      child: Align(
                        alignment: Alignment.topCenter,
                        child:
                            CircularProgressIndicator(color: lima, strokeWidth: 3),
                      ),
                    );
                  }
                  if (!hayQuery) {
                    return _Ayuda(
                        texto: _miembros.isEmpty
                            ? 'Busca por nombre o correo para agregar miembros.'
                            : 'Sigue buscando para agregar más, o toca "Crear grupo".');
                  }
                  final q = _q.text.trim();
                  final sinResultados = _resultados.isEmpty;
                  return ListView(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    children: [
                      for (final p in _resultados)
                        _FilaResultado(
                          perfil: p,
                          agregado:
                              _yaAgregado((p['email'] ?? '').toString()),
                          onTap: () => _alternar(p),
                        ),
                      // Fallback: agregar por correo exacto aunque no aparezca en
                      // la búsqueda (perfil aún no indexado).
                      if (sinResultados && _emailValido(q) && !_yaAgregado(q))
                        _FilaResultado(
                          perfil: {'email': q, 'nombre': ''},
                          agregado: false,
                          onTap: () => _alternar({'email': q, 'nombre': ''}),
                        ),
                      if (sinResultados && !_emailValido(q))
                        const _Ayuda(
                            texto:
                                'No se encontró a nadie con ese nombre o correo. '
                                'La persona debe haber entrado al app.'),
                    ],
                  );
                },
              ),
            ),
            // Botón crear (fijo abajo).
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(18, 8, 18, 12),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 15)),
                    onPressed: _creando ? null : _crear,
                    icon: const Icon(Icons.check),
                    label: Text(
                        _miembros.isEmpty
                            ? 'Crear grupo'
                            : 'Crear grupo (${_miembros.length})',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Chip de un miembro ya agregado (foto real + nombre + quitar).
class _ChipMiembro extends StatelessWidget {
  const _ChipMiembro({required this.perfil, required this.onQuitar});
  final Map<String, dynamic> perfil;
  final VoidCallback onQuitar;

  @override
  Widget build(BuildContext context) {
    final email = (perfil['email'] ?? '').toString();
    final nombre = (perfil['nombre'] ?? '').toString();
    final foto = (perfil['foto_url'] ?? '').toString();
    final mostrar = nombre.isNotEmpty ? nombre : email;
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 4, 8, 4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFE4E4E4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircleAvatar(
            radius: 13,
            backgroundColor: teal,
            backgroundImage: foto.isNotEmpty ? NetworkImage(foto) : null,
            child: foto.isEmpty
                ? Text(mostrar.isNotEmpty ? mostrar[0].toUpperCase() : '?',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w800))
                : null,
          ),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 140),
            child: Text(mostrar,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 4),
          InkWell(
            onTap: onQuitar,
            borderRadius: BorderRadius.circular(999),
            child: const Icon(Icons.close, size: 16, color: textoTenue),
          ),
        ],
      ),
    );
  }
}

/// Fila de un resultado de búsqueda: foto real + nombre/correo + agregar/quitar.
class _FilaResultado extends StatelessWidget {
  const _FilaResultado(
      {required this.perfil, required this.agregado, required this.onTap});
  final Map<String, dynamic> perfil;
  final bool agregado;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final email = (perfil['email'] ?? '').toString();
    final nombre = (perfil['nombre'] ?? '').toString();
    final foto = (perfil['foto_url'] ?? '').toString();
    final mostrar = nombre.isNotEmpty ? nombre : email;
    return ListTile(
      onTap: onTap,
      leading: CircleAvatar(
        radius: 22,
        backgroundColor: teal,
        backgroundImage: foto.isNotEmpty ? NetworkImage(foto) : null,
        child: foto.isEmpty
            ? Text(mostrar.isNotEmpty ? mostrar[0].toUpperCase() : '?',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w800))
            : null,
      ),
      title: Text(mostrar,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: nombre.isNotEmpty
          ? Text(email,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: textoTenue, fontSize: 12))
          : null,
      // Ya agregado = check lima (no se puede agregar dos veces); si no, un "+".
      trailing: agregado
          ? const Icon(Icons.check_circle, color: lima)
          : const Icon(Icons.add_circle_outline, color: bosque),
    );
  }
}

class _Ayuda extends StatelessWidget {
  const _Ayuda({required this.texto});
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.person_search_outlined, size: 48, color: textoTenue),
            const SizedBox(height: 12),
            Text(texto,
                textAlign: TextAlign.center,
                style: const TextStyle(color: textoTenue)),
          ],
        ),
      ),
    );
  }
}
