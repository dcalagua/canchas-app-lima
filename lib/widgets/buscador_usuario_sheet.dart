import 'dart:async';

import 'package:flutter/material.dart';

import '../data/perfiles_repo.dart';
import '../theme.dart';

/// Hoja para BUSCAR un usuario REGISTRADO del app (por nombre o correo).
/// Devuelve el perfil elegido `{email, nombre, foto_url, celular}` vía
/// `Navigator.pop`, o null si se cierra sin elegir. Reutilizable: la usan la
/// reserva manual (elegir cliente) y el campeonato (agregar participante).
class BuscadorUsuarioSheet extends StatefulWidget {
  const BuscadorUsuarioSheet(
      {super.key,
      this.hint = 'Nombre o correo…',
      this.mensajeVacio =
          'Escribe el nombre o correo. Debe haber entrado al app al menos '
              'una vez.'});

  final String hint;
  final String mensajeVacio;

  /// Abre la hoja y devuelve el perfil elegido (o null).
  static Future<Map<String, dynamic>?> mostrar(BuildContext context,
      {String hint = 'Nombre o correo…',
      String mensajeVacio =
          'Escribe el nombre o correo. Debe haber entrado al app al menos '
              'una vez.'}) {
    return showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) =>
          BuscadorUsuarioSheet(hint: hint, mensajeVacio: mensajeVacio),
    );
  }

  @override
  State<BuscadorUsuarioSheet> createState() => _BuscadorUsuarioSheetState();
}

class _BuscadorUsuarioSheetState extends State<BuscadorUsuarioSheet> {
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
    setState(() {
      _resultados = r;
      _buscando = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    final hayQuery = _q.text.trim().length >= 2;
    return Padding(
      padding: EdgeInsets.only(bottom: inset),
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.92,
        builder: (context, scroll) => Container(
          decoration: BoxDecoration(
            color: Theme.of(context).scaffoldBackgroundColor,
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: trazo,
                    borderRadius: BorderRadius.circular(999)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: TextField(
                  controller: _q,
                  autofocus: true,
                  onChanged: _onCambio,
                  decoration: InputDecoration(
                    hintText: widget.hint,
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
                    ? const Center(
                        child: CircularProgressIndicator(color: lima))
                    : !hayQuery
                        ? _mensaje(context, widget.mensajeVacio)
                        : _resultados.isEmpty
                            ? _mensaje(context,
                                'No se encontró a nadie. Debe estar '
                                'registrado en el app.')
                            : ListView.separated(
                                controller: scroll,
                                itemCount: _resultados.length,
                                separatorBuilder: (_, __) => Divider(
                                    height: 1, color: trazo.withOpacity(0.5)),
                                itemBuilder: (_, i) {
                                  final p = _resultados[i];
                                  final email =
                                      (p['email'] ?? '').toString();
                                  final nombre =
                                      (p['nombre'] ?? '').toString();
                                  final foto =
                                      (p['foto_url'] ?? '').toString();
                                  final mostrar =
                                      nombre.isNotEmpty ? nombre : email;
                                  return ListTile(
                                    onTap: () => Navigator.pop(context, p),
                                    leading: CircleAvatar(
                                      radius: 22,
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
                                                  fontWeight:
                                                      FontWeight.w800))
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
                                                color: textoTenue,
                                                fontSize: 12))
                                        : null,
                                  );
                                },
                              ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _mensaje(BuildContext context, String texto) => Center(
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.person_search, size: 54, color: textoTenue),
              const SizedBox(height: 12),
              Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
            ],
          ),
        ),
      );
}
