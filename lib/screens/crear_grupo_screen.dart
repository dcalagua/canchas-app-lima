import 'package:flutter/material.dart';

import '../data/grupos_repo.dart';
import '../models/grupo.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import 'chat_screen.dart';

/// Crea un grupo de chat: nombre + miembros por email (cuentas registradas).
/// El creador queda como miembro automáticamente.
class CrearGrupoScreen extends StatefulWidget {
  const CrearGrupoScreen({super.key});

  @override
  State<CrearGrupoScreen> createState() => _CrearGrupoScreenState();
}

class _CrearGrupoScreenState extends State<CrearGrupoScreen> {
  final _nombre = TextEditingController();
  final _email = TextEditingController();
  final List<String> _miembros = []; // emails agregados (además del creador)
  bool _creando = false;

  @override
  void dispose() {
    _nombre.dispose();
    _email.dispose();
    super.dispose();
  }

  void _agregar() {
    final e = _email.text.trim().toLowerCase();
    final yo = (appState.usuario?.email ?? '').toLowerCase();
    if (e.isEmpty || !e.contains('@') || !e.contains('.')) {
      _aviso('Escribe un correo válido.');
      return;
    }
    if (e == yo) {
      _aviso('Ya eres miembro del grupo.');
      return;
    }
    if (_miembros.contains(e)) {
      _aviso('Ese correo ya está en la lista.');
      return;
    }
    setState(() {
      _miembros.add(e);
      _email.clear();
    });
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
      _aviso('Agrega al menos un miembro por su correo.');
      return;
    }
    if (_creando) return;
    setState(() => _creando = true);
    final id = 'grp_${DateTime.now().microsecondsSinceEpoch}';
    final grupo = Grupo(id: id, nombre: nombre, creadorEmail: me.email);
    final miembros = <Map<String, String>>[
      {'email': me.email, 'nombre': me.nombre},
      for (final e in _miembros) {'email': e, 'nombre': ''},
    ];
    bool ok;
    try {
      ok = await conPreload(
          context, () => GruposRepo.crear(grupo, miembros),
          texto: 'Creando grupo…');
    } finally {
      if (mounted) setState(() => _creando = false);
    }
    if (!mounted) return;
    if (!ok) {
      _aviso('No se pudo crear el grupo. Revisa tu conexión.');
      return;
    }
    // Abre el chat del grupo recién creado.
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
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo grupo')),
      body: ListView(
        // Regla app: contenido centrado (ancho máx) en pantallas anchas.
        padding: EdgeInsets.symmetric(
            horizontal: ladoTablet(context, 18, 600), vertical: 18),
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
          const SizedBox(height: 20),
          const Text('Miembros',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                    labelText: 'Correo del miembro',
                    hintText: 'correo@ejemplo.com',
                    prefixIcon: Icon(Icons.alternate_email),
                  ),
                  onSubmitted: (_) => _agregar(),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: _agregar,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text('Deben ser cuentas registradas en la app.',
              style: TextStyle(color: textoTenue, fontSize: 12)),
          const SizedBox(height: 12),
          for (final e in _miembros)
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: cs.primary.withOpacity(0.15),
                  child: Text(e.characters.first.toUpperCase(),
                      style: TextStyle(
                          color: cs.primary, fontWeight: FontWeight.w800)),
                ),
                title: Text(e, maxLines: 1, overflow: TextOverflow.ellipsis),
                trailing: IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => setState(() => _miembros.remove(e)),
                ),
              ),
            ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _creando ? null : _crear,
              icon: const Icon(Icons.check),
              label: const Text('Crear grupo',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ),
        ],
      ),
    );
  }
}
