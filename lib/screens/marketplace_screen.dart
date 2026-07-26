import 'package:flutter/material.dart';

import '../data/productos_repo.dart';
import '../models/producto.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import 'mis_ordenes_screen.dart';
import 'mis_productos_screen.dart';
import 'producto_detalle_screen.dart';

/// Marketplace Pichangol (comprador): feed único de productos que publican los
/// dueños de cancha y academias. Buscador por nombre + filtro por categoría,
/// estilo Airbnb. Tocar un producto abre su ficha para comprar/coordinar.
class MarketplaceScreen extends StatefulWidget {
  const MarketplaceScreen({super.key});

  @override
  State<MarketplaceScreen> createState() => _MarketplaceScreenState();
}

class _MarketplaceScreenState extends State<MarketplaceScreen> {
  final _q = TextEditingController();
  List<Producto> _todos = const [];
  bool _cargando = true;
  String _categoria = ''; // '' = todas

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final l = await ProductosRepo.fetchActivos();
    if (!mounted) return;
    setState(() {
      _todos = l;
      _cargando = false;
    });
    // Fotos + estado de verificación de los vendedores (avatar y badge).
    final emails = l
        .map((p) => p.vendedorEmail)
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();
    if (emails.isNotEmpty) {
      appState.cargarPerfiles(emails);
      await appState.sincronizarVerificados(emails);
      if (mounted) setState(() {}); // refresca los badges
    }
  }

  List<Producto> get _filtrados {
    final q = _q.text.trim().toLowerCase();
    return _todos.where((p) {
      if (_categoria.isNotEmpty && p.categoria != _categoria) return false;
      if (q.isEmpty) return true;
      return p.nombre.toLowerCase().contains(q) ||
          p.vendedorNombre.toLowerCase().contains(q) ||
          p.categoriaEtiqueta.toLowerCase().contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    // Categorías presentes en el catálogo (para no mostrar filtros vacíos).
    final catsPresentes = <String>{for (final p in _todos) p.categoria};
    final items = _filtrados;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Marketplace Pichangol'),
        actions: [
          IconButton(
            tooltip: 'Mis compras',
            icon: const Icon(Icons.shopping_bag_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => const MisOrdenesScreen(esVendedor: false))),
          ),
        ],
      ),
      // "Vender" vive DENTRO del marketplace (no en el Perfil): abre Mi tienda,
      // que gatea la publicación si el usuario no está verificado.
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const MisProductosScreen())),
        icon: const Icon(Icons.sell_outlined),
        label: const Text('Vender'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
            child: TextField(
              controller: _q,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: 'Buscar producto o vendedor…',
                prefixIcon: const Icon(Icons.search),
                filled: true,
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: BorderSide.none),
              ),
            ),
          ),
          if (catsPresentes.isNotEmpty)
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: [
                  _chip('Todo', _categoria.isEmpty,
                      () => setState(() => _categoria = '')),
                  for (final e in Producto.categorias.entries)
                    if (catsPresentes.contains(e.key))
                      _chip(e.value, _categoria == e.key,
                          () => setState(() => _categoria = e.key)),
                ],
              ),
            ),
          Expanded(
            child: _cargando
                ? const CargandoPichangol()
                : items.isEmpty
                    ? _vacio()
                    : RefreshIndicator(
                        onRefresh: _cargar,
                        child: GridView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 90),
                          gridDelegate:
                              const SliverGridDelegateWithFixedCrossAxisCount(
                            crossAxisCount: 2,
                            mainAxisSpacing: 12,
                            crossAxisSpacing: 12,
                            childAspectRatio: 0.68,
                          ),
                          itemCount: items.length,
                          itemBuilder: (_, i) => _Card(p: items[i]),
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String label, bool sel, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.only(right: 8),
        child: ChoiceChip(
          label: Text(label),
          selected: sel,
          selectedColor: lima,
          labelStyle: TextStyle(
              color: sel ? Colors.white : null, fontWeight: FontWeight.w700),
          onSelected: (_) => onTap(),
        ),
      );

  Widget _vacio() => ListView(
        children: [
          const SizedBox(height: 90),
          const Icon(Icons.storefront_outlined,
              size: 64, color: textoTenue),
          const SizedBox(height: 14),
          const Text('Aún no hay productos',
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          const SizedBox(height: 6),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 40),
            child: Text(
                'Cuando los locales publiquen raquetas, pelotas y más, '
                'aparecerán aquí.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
          ),
        ],
      );
}

class _Card extends StatelessWidget {
  const _Card({required this.p});
  final Producto p;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => ProductoDetalleScreen(producto: p))),
      child: Container(
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: trazo),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(16)),
                child: p.fotoUrl.isNotEmpty
                    ? Image.network(p.fotoUrl,
                        width: double.infinity, fit: BoxFit.cover)
                    : Container(
                        color: const Color(0xFFF0F0F0),
                        child: const Center(
                            child: Icon(Icons.image, color: textoTenue))),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(p.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 13.5)),
                  const SizedBox(height: 2),
                  Text(p.precioTexto,
                      style: const TextStyle(
                          fontWeight: FontWeight.w900,
                          fontSize: 14.5,
                          color: bosque)),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Flexible(
                        child: Text(p.vendedorNombre,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                color: textoTenue, fontSize: 11.5)),
                      ),
                      if (appState.estaVerificado(p.vendedorEmail)) ...[
                        const SizedBox(width: 3),
                        const Icon(Icons.verified,
                            size: 13, color: lima),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
