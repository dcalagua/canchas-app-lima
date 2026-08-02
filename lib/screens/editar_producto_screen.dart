import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../config/pais.dart';
import '../data/productos_repo.dart';
import '../models/producto.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';

/// Publicar o editar un producto del Marketplace Pichangol. El vendedor pone
/// foto, nombre, precio, categoría y (opcional) stock. Al guardar, sube la foto
/// al bucket `productos` y hace upsert en Supabase.
class EditarProductoScreen extends StatefulWidget {
  const EditarProductoScreen({super.key, this.producto});

  /// Producto a editar; null = crear uno nuevo.
  final Producto? producto;

  @override
  State<EditarProductoScreen> createState() => _EditarProductoScreenState();
}

class _EditarProductoScreenState extends State<EditarProductoScreen> {
  late final TextEditingController _nombre;
  late final TextEditingController _desc;
  late final TextEditingController _precio;
  late final TextEditingController _stock;
  String _categoria = 'raquetas';
  bool _activo = true;
  Uint8List? _fotoNueva;
  String _fotoUrl = '';
  bool _guardando = false;

  bool get _esNuevo => widget.producto == null;

  @override
  void initState() {
    super.initState();
    final p = widget.producto;
    _nombre = TextEditingController(text: p?.nombre ?? '');
    _desc = TextEditingController(text: p?.descripcion ?? '');
    _precio = TextEditingController(
        text: p != null ? p.precio.toStringAsFixed(2) : '');
    _stock = TextEditingController(text: p?.stock?.toString() ?? '');
    _categoria = p?.categoria ?? 'raquetas';
    _activo = p?.activo ?? true;
    _fotoUrl = p?.fotoUrl ?? '';
  }

  @override
  void dispose() {
    _nombre.dispose();
    _desc.dispose();
    _precio.dispose();
    _stock.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final XFile? f = await ImagePicker().pickImage(
        source: ImageSource.gallery, maxWidth: 1400, imageQuality: 82);
    if (f == null) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() => _fotoNueva = bytes);
  }

  Future<void> _guardar() async {
    final nombre = _nombre.text.trim();
    final precio = double.tryParse(_precio.text.trim().replaceAll(',', '.'));
    if (nombre.isEmpty) {
      _err('Ponle un nombre al producto.');
      return;
    }
    if (precio == null || precio <= 0) {
      _err('Pon un precio válido.');
      return;
    }
    if (_fotoNueva == null && _fotoUrl.isEmpty) {
      _err('Agrega una foto del producto.');
      return;
    }
    final u = appState.usuario;
    if (u == null) {
      _err('Inicia sesión para publicar.');
      return;
    }
    if (_guardando) return;
    setState(() => _guardando = true);

    final id = widget.producto?.id ??
        'prod_${DateTime.now().microsecondsSinceEpoch}';
    final stock = _stock.text.trim().isEmpty
        ? null
        : int.tryParse(_stock.text.trim());
    String? errFoto;
    bool ok;
    try {
      // Regla: acción que demora (subir foto + guardar) → preload de marca.
      ok = await conPreload(context, () async {
        var fotoUrl = _fotoUrl;
        if (_fotoNueva != null) {
          final url = await ProductosRepo.subirFoto(id, _fotoNueva!);
          if (url == null) {
            errFoto = ProductosRepo.ultimoErrorFoto ?? 'No se pudo subir la foto.';
            return false;
          }
          fotoUrl = url;
        }
        final prod = Producto(
          id: id,
          vendedorEmail: u.email.toLowerCase(),
          vendedorNombre: u.nombre,
          nombre: nombre,
          descripcion: _desc.text.trim(),
          precio: precio,
          moneda: widget.producto?.moneda ?? paisActual.moneda,
          categoria: _categoria,
          fotoUrl: fotoUrl,
          stock: stock,
          activo: _activo,
          creadoEn: widget.producto?.creadoEn ?? DateTime.now(),
        );
        return ProductosRepo.guardar(prod);
      }, texto: 'Guardando…');
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
    if (!mounted) return;
    if (errFoto != null) {
      _err(errFoto!);
      return;
    }
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      _err('No se pudo guardar. Revisa tu conexión.');
    }
  }

  void _err(String m) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(_esNuevo ? 'Publicar producto' : 'Editar producto')),
      body: ListView(
        // Regla app: contenido centrado (ancho máx) en pantallas anchas.
        padding: EdgeInsets.symmetric(
            horizontal: ladoTablet(context, 18, 600), vertical: 18),
        children: [
          // Foto.
          GestureDetector(
            onTap: _elegirFoto,
            child: Container(
              height: 190,
              decoration: BoxDecoration(
                color: const Color(0xFFF3F3F3),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: trazo),
                image: _fotoNueva != null
                    ? DecorationImage(
                        image: MemoryImage(_fotoNueva!), fit: BoxFit.cover)
                    : (_fotoUrl.isNotEmpty
                        ? DecorationImage(
                            image: NetworkImage(_fotoUrl), fit: BoxFit.cover)
                        : null),
              ),
              child: (_fotoNueva == null && _fotoUrl.isEmpty)
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.add_a_photo_outlined,
                              size: 34, color: textoTenue),
                          SizedBox(height: 8),
                          Text('Agregar foto',
                              style: TextStyle(color: textoTenue)),
                        ],
                      ),
                    )
                  : Align(
                      alignment: Alignment.bottomRight,
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: CircleAvatar(
                          backgroundColor: Colors.black54,
                          child: IconButton(
                            icon: const Icon(Icons.edit, color: Colors.white),
                            onPressed: _elegirFoto,
                          ),
                        ),
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _nombre,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
                labelText: 'Nombre', hintText: 'Ej. Raqueta Wilson Pro'),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _precio,
                  keyboardType: const TextInputType.numberWithOptions(
                      decimal: true),
                  inputFormatters: [
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                  ],
                  decoration: InputDecoration(
                      labelText: 'Precio', prefixText: '${paisActual.moneda} '),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _stock,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(
                      labelText: 'Stock (opcional)', hintText: 'ilimitado'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _categoria,
            decoration: const InputDecoration(labelText: 'Categoría'),
            items: [
              for (final e in Producto.categorias.entries)
                DropdownMenuItem(value: e.key, child: Text(e.value)),
            ],
            onChanged: (v) => setState(() => _categoria = v ?? 'otros'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _desc,
            maxLines: 3,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
                labelText: 'Descripción (opcional)',
                hintText: 'Estado, marca, detalles…'),
          ),
          const SizedBox(height: 8),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _activo,
            title: const Text('Publicado'),
            subtitle: Text(_activo
                ? 'Visible en el marketplace'
                : 'Pausado (no aparece en el feed)'),
            onChanged: (v) => setState(() => _activo = v),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: lima,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 15)),
              onPressed: _guardando ? null : _guardar,
              icon: const Icon(Icons.check),
              label: Text(_esNuevo ? 'Publicar' : 'Guardar cambios',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ),
        ],
      ),
    );
  }
}
