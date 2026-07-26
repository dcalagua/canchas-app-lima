import 'package:flutter/material.dart';

import '../models/producto.dart';
import '../services/avisos_service.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/pago_tarjeta_sheet.dart';
import 'chat_screen.dart';
import 'login_google_sheet.dart';

/// Ficha de un producto del Marketplace: foto, precio, vendedor y descripción.
/// El comprador paga en la app (Culqi) y coordina la entrega por chat. Pichangol
/// cobra su comisión y le debe el neto al vendedor.
class ProductoDetalleScreen extends StatefulWidget {
  const ProductoDetalleScreen({super.key, required this.producto});
  final Producto producto;

  @override
  State<ProductoDetalleScreen> createState() => _ProductoDetalleScreenState();
}

class _ProductoDetalleScreenState extends State<ProductoDetalleScreen> {
  bool _comprando = false;

  Producto get p => widget.producto;

  @override
  void initState() {
    super.initState();
    // Foto + badge de verificación del vendedor.
    appState.cargarPerfiles([p.vendedorEmail]);
    appState
        .sincronizarVerificados([p.vendedorEmail]).then((_) {
      if (mounted) setState(() {});
    });
  }

  bool get _soyElVendedor =>
      (appState.usuario?.email ?? '').toLowerCase() ==
      p.vendedorEmail.toLowerCase();

  void _chatear() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: p.vendedorEmail,
        titulo: p.vendedorNombre.isNotEmpty
            ? p.vendedorNombre
            : p.vendedorEmail,
        soyProfe: false,
        tipo: 'directo',
      ),
    ));
  }

  Future<void> _comprar() async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'comprar')) return;
    if (!mounted) return;
    final u = appState.usuario;
    if (u == null) return;
    if (_soyElVendedor) {
      _msg('Este producto es tuyo.');
      return;
    }
    setState(() => _comprando = true);
    // 1) Cobro al comprador (Culqi: Yape/tarjeta). El monto va en céntimos.
    final centimos = (p.precio * 100).round();
    var operacion = '';
    final pagado = await PagoTarjeta.cobrar(
      context,
      monto: centimos,
      concepto: 'Compra: ${p.nombre}',
      email: u.email,
      moneda: p.moneda,
      onOperacion: (op) => operacion = op,
    );
    if (!mounted) return;
    if (!pagado) {
      setState(() => _comprando = false);
      return;
    }
    // 2) Registra la venta: Pichangol se queda la comisión y le debe el neto al
    //    vendedor (id de venta = operación Culqi o compuesto, para idempotencia).
    //    Es un paso de red tras el pago → preload de marca mientras confirma.
    final ventaId = operacion.isNotEmpty
        ? operacion
        : '${p.id}_${u.email}_${DateTime.now().millisecondsSinceEpoch}';
    await conPreload(context, () async {
      await PagosService.venta(
        vendedorId: p.vendedorEmail.toLowerCase(),
        montoSoles: p.precio,
        ventaId: ventaId,
        concepto: 'Venta: ${p.nombre}',
        productoId: p.id,
        productoNombre: p.nombre,
        compradorEmail: u.email.toLowerCase(),
        compradorNombre: u.nombre,
        vendedorNombre: p.vendedorNombre,
      );
      // Avisa al vendedor que le compraron (push best-effort).
      AvisosService.ventaNueva(
        vendedorEmail: p.vendedorEmail,
        compradorNombre: u.nombre,
        producto: p.nombre,
        montoTexto: p.precioTexto,
      );
    }, texto: 'Confirmando tu compra…');
    if (!mounted) return;
    setState(() => _comprando = false);
    await _dialogoOk();
  }

  Future<void> _dialogoOk() async {
    await showDialog<void>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('¡Compra realizada! ✓'),
        content: Text(
            'Pagaste ${p.precioTexto}. Ahora coordina la entrega con '
            '${p.vendedorNombre} por chat.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx),
              child: const Text('Después')),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () {
              Navigator.pop(dctx);
              _chatear();
            },
            icon: const Icon(Icons.chat_bubble_outline, size: 18),
            label: const Text('Coordinar entrega'),
          ),
        ],
      ),
    );
  }

  void _msg(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final fotoVendedor = appState.fotoDe(p.vendedorEmail);
    return Scaffold(
      appBar: AppBar(title: const Text('Producto')),
      body: ListView(
        children: [
          AspectRatio(
            aspectRatio: 1,
            child: p.fotoUrl.isNotEmpty
                ? Image.network(p.fotoUrl, fit: BoxFit.cover)
                : Container(
                    color: const Color(0xFFF0F0F0),
                    child: const Center(
                        child: Icon(Icons.image, size: 48, color: textoTenue))),
          ),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(p.nombre,
                    style: const TextStyle(
                        fontWeight: FontWeight.w900, fontSize: 21)),
                const SizedBox(height: 6),
                Text(p.precioTexto,
                    style: const TextStyle(
                        fontWeight: FontWeight.w900,
                        fontSize: 22,
                        color: lima)),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                          color: limaSuave,
                          borderRadius: BorderRadius.circular(7)),
                      child: Text(p.categoriaEtiqueta,
                          style: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w700)),
                    ),
                    if (p.agotado) ...[
                      const SizedBox(width: 8),
                      const Text('Agotado',
                          style: TextStyle(
                              color: Colors.redAccent,
                              fontWeight: FontWeight.w700)),
                    ],
                  ],
                ),
                if (p.descripcion.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(p.descripcion,
                      style: const TextStyle(height: 1.4, fontSize: 14.5)),
                ],
                const SizedBox(height: 18),
                const Divider(),
                const SizedBox(height: 6),
                Row(
                  children: [
                    CircleAvatar(
                      radius: 22,
                      backgroundColor: teal,
                      backgroundImage:
                          (fotoVendedor != null && fotoVendedor.isNotEmpty)
                              ? NetworkImage(fotoVendedor)
                              : null,
                      child: (fotoVendedor == null || fotoVendedor.isEmpty)
                          ? Text(
                              p.vendedorNombre.isNotEmpty
                                  ? p.vendedorNombre[0].toUpperCase()
                                  : '?',
                              style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w800))
                          : null,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Vendedor',
                              style: TextStyle(
                                  color: textoTenue, fontSize: 12)),
                          Row(
                            children: [
                              Flexible(
                                child: Text(
                                    p.vendedorNombre.isNotEmpty
                                        ? p.vendedorNombre
                                        : 'Vendedor',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 15)),
                              ),
                              if (appState.estaVerificado(p.vendedorEmail)) ...[
                                const SizedBox(width: 5),
                                const Icon(Icons.verified,
                                    size: 16, color: lima),
                              ],
                            ],
                          ),
                        ],
                      ),
                    ),
                    OutlinedButton.icon(
                      onPressed: _chatear,
                      icon: const Icon(Icons.chat_bubble_outline, size: 18),
                      label: const Text('Chat'),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                      color: const Color(0xFFF7F7F7),
                      borderRadius: BorderRadius.circular(12)),
                  child: const Row(
                    children: [
                      Icon(Icons.verified_user_outlined,
                          size: 18, color: bosque),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                            'Pago protegido por Pichangol. Pagas en la app y '
                            'coordinas la entrega con el vendedor por chat.',
                            style: TextStyle(fontSize: 12, color: bosque)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: _soyElVendedor
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: SizedBox(
                  height: 52,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima, foregroundColor: Colors.white),
                    onPressed: (_comprando || p.agotado) ? null : _comprar,
                    icon: const Icon(Icons.shopping_bag_outlined),
                    label: Text(
                        p.agotado
                            ? 'Agotado'
                            : 'Comprar · ${p.precioTexto}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15.5)),
                  ),
                ),
              ),
            ),
    );
  }
}
