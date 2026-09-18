import 'package:flutter/material.dart';

import '../data/productos_repo.dart';
import '../models/producto.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/responsive.dart';
import '../widgets/vacio_airbnb.dart';
import 'editar_producto_screen.dart';
import 'login_google_sheet.dart';
import 'mis_ordenes_screen.dart';
import 'verificar_identidad_screen.dart';

/// "Mi tienda": el vendedor (dueño/academia) gestiona sus productos del
/// Marketplace Pichangol — publicar, editar, pausar y borrar.
class MisProductosScreen extends StatefulWidget {
  const MisProductosScreen({super.key});

  @override
  State<MisProductosScreen> createState() => _MisProductosScreenState();
}

class _MisProductosScreenState extends State<MisProductosScreen> {
  List<Producto> _items = const [];
  bool _cargando = true;

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    final l = await ProductosRepo.fetchDeVendedor(_yo);
    if (!mounted) return;
    setState(() {
      _items = l;
      _cargando = false;
    });
  }

  Future<void> _nuevo() async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'vender en el marketplace')) {
      return;
    }
    if (!mounted) return;
    // Candado anti-fraude: para publicar hay que estar verificado (o ser dueño).
    if (!appState.puedeVender) {
      await _pedirVerificacion();
      return;
    }
    final ok = await Navigator.of(context).push<bool>(
        MaterialPageRoute(builder: (_) => const EditarProductoScreen()));
    if (ok == true) _cargar();
  }

  Future<void> _pedirVerificacion() async {
    final ir = await confirmarPichangol(
      context,
      titulo: 'Verifícate para vender',
      mensaje: 'Para publicar en el Marketplace Pichangol necesitas verificar tu '
          'identidad. Así los compradores confían en quién les vende. Es rápido.',
      textoConfirmar: 'Verificar identidad',
      textoCancelar: 'Ahora no',
      icono: Icons.verified_user_outlined,
    );
    if (ir && mounted) {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => const VerificarIdentidadScreen()));
      if (mounted) setState(() {}); // refresca por si ya se verificó
    }
  }

  Future<void> _editar(Producto p) async {
    final ok = await Navigator.of(context).push<bool>(MaterialPageRoute(
        builder: (_) => EditarProductoScreen(producto: p)));
    if (ok == true) _cargar();
  }

  Future<void> _borrar(Producto p) async {
    final ok = await confirmarPichangol(
      context,
      titulo: '¿Borrar producto?',
      mensaje: 'Se quitará "${p.nombre}" del marketplace.',
      textoConfirmar: 'Borrar',
      destructivo: true,
      icono: Icons.delete_outline,
    );
    if (!ok) return;
    await ProductosRepo.eliminar(p.id);
    _cargar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mi tienda'),
        actions: [
          IconButton(
            tooltip: 'Mis ventas',
            icon: const Icon(Icons.point_of_sale_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => const MisOrdenesScreen(esVendedor: true))),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        onPressed: _nuevo,
        icon: const Icon(Icons.add),
        label: const Text('Publicar'),
      ),
      body: _cargando
          ? const CargandoPichangol()
          : _items.isEmpty
              ? _vacio()
              : RefreshIndicator(
                  onRefresh: _cargar,
                  child: ListView.separated(
                    // Regla app: contenido centrado en pantallas anchas.
                    padding: EdgeInsets.fromLTRB(
                        ladoTablet(context, 16, 700), 12,
                        ladoTablet(context, 16, 700), 90),
                    itemCount: _items.length + 1,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) {
                      if (i == 0) return _intro();
                      return _Item(
                        p: _items[i - 1],
                        onEditar: () => _editar(_items[i - 1]),
                        onBorrar: () => _borrar(_items[i - 1]),
                      );
                    },
                  ),
                ),
    );
  }

  Widget _intro() => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
            color: limaSuave, borderRadius: BorderRadius.circular(14)),
        child: const Row(
          children: [
            CircleAvatar(
                radius: 18,
                backgroundColor: lima,
                child: Icon(Icons.storefront, color: Colors.white, size: 20)),
            SizedBox(width: 12),
            Expanded(
              child: Text(
                  'Publica lo que vendes (raquetas, pelotas, ropa…). El '
                  'comprador paga en la app y coordinan la entrega por chat.',
                  style: TextStyle(fontSize: 12.5, color: bosque, height: 1.3)),
            ),
          ],
        ),
      );

  Widget _vacio() => VacioAirbnb(
        icono: Icons.storefront,
        titulo: 'Tu tienda\nestá vacía',
        mensaje: 'Publica tu primer producto y aparecerá en el Marketplace '
            'Pichangol para todos los jugadores.',
        textoBoton: 'Publicar producto',
        onBoton: _nuevo,
      );
}

class _Item extends StatelessWidget {
  const _Item(
      {required this.p, required this.onEditar, required this.onBorrar});
  final Producto p;
  final VoidCallback onEditar;
  final VoidCallback onBorrar;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: p.fotoUrl.isNotEmpty
                ? Image.network(p.fotoUrl,
                    width: 62, height: 62, fit: BoxFit.cover)
                : Container(
                    width: 62,
                    height: 62,
                    color: const Color(0xFFF0F0F0),
                    child: const Icon(Icons.image, color: textoTenue)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(p.nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text('${p.precioTexto} · ${p.categoriaEtiqueta}',
                    style:
                        const TextStyle(color: textoTenue, fontSize: 12.5)),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: p.activo ? limaSuave : const Color(0xFFF0F0F0),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(p.activo ? 'Publicado' : 'Pausado',
                          style: TextStyle(
                              fontSize: 10.5,
                              fontWeight: FontWeight.w700,
                              color: p.activo ? bosque : textoTenue)),
                    ),
                    if (p.agotado) ...[
                      const SizedBox(width: 6),
                      const Text('Agotado',
                          style: TextStyle(
                              fontSize: 10.5,
                              fontWeight: FontWeight.w700,
                              color: Colors.redAccent)),
                    ],
                  ],
                ),
              ],
            ),
          ),
          IconButton(
              icon: const Icon(Icons.edit_outlined, color: bosque),
              onPressed: onEditar),
          IconButton(
              icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
              onPressed: onBorrar),
        ],
      ),
    );
  }
}
