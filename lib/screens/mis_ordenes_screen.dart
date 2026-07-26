import 'package:flutter/material.dart';

import '../config/pais.dart';
import '../services/avisos_service.dart';
import '../services/ventas_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/responsive.dart';
import '../widgets/cargando_pichangol.dart';
import 'chat_screen.dart';

/// Órdenes del Marketplace (escrow). Modo COMPRADOR ("Mis compras": confirmar
/// recepción / reportar problema) o VENDEDOR ("Mis ventas": marcar entregado +
/// resumen de dinero retenido vs liberado).
class MisOrdenesScreen extends StatefulWidget {
  const MisOrdenesScreen({super.key, required this.esVendedor});
  final bool esVendedor;

  @override
  State<MisOrdenesScreen> createState() => _MisOrdenesScreenState();
}

class _MisOrdenesScreenState extends State<MisOrdenesScreen> {
  List<Map<String, dynamic>> _items = const [];
  double _retenido = 0, _liberado = 0;
  bool _cargando = true;

  String get _yo => (appState.usuario?.email ?? '').toLowerCase().trim();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _cargando = true);
    if (widget.esVendedor) {
      final r = await VentasService.misVentas(_yo);
      if (!mounted) return;
      setState(() {
        _items = ((r['ventas'] as List?) ?? const [])
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
        _retenido = ((r['retenido_soles'] ?? 0) as num).toDouble();
        _liberado = ((r['liberado_soles'] ?? 0) as num).toDouble();
        _cargando = false;
      });
    } else {
      final l = await VentasService.misCompras(_yo);
      if (!mounted) return;
      setState(() {
        _items = l;
        _cargando = false;
      });
    }
  }

  Future<void> _confirmarRecepcion(Map<String, dynamic> v) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('¿Recibiste el producto?'),
        content: Text('Al confirmar, se libera el pago a '
            '${v['vendedor_nombre'] ?? 'el vendedor'}. Hazlo solo cuando ya '
            'tengas "${v['producto_nombre'] ?? 'el producto'}" en mano.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Todavía no')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () => Navigator.pop(dctx, true),
              child: const Text('Sí, lo recibí')),
        ],
      ),
    );
    if (ok != true) return;
    final done = await VentasService.recibido((v['id'] as num).toInt(), _yo);
    if (!mounted) return;
    if (done) {
      AvisosService.ventaRecibida(
        vendedorEmail: (v['vendedor_email'] ?? '').toString(),
        compradorNombre: appState.usuario?.nombre ?? 'El comprador',
        producto: (v['producto_nombre'] ?? 'el producto').toString(),
      );
      _cargar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: bosque,
          content: Text('¡Listo! Pago liberado al vendedor.')));
    } else {
      _msg('No se pudo. Reintenta.');
    }
  }

  Future<void> _reportar(Map<String, dynamic> v) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Reportar un problema'),
        content: const Text(
            'Se marca la compra en disputa y el pago NO se libera hasta que se '
            'resuelva. Coordina primero por chat con el vendedor.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dctx, false),
              child: const Text('Cancelar')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
              onPressed: () => Navigator.pop(dctx, true),
              child: const Text('Reportar')),
        ],
      ),
    );
    if (ok != true) return;
    await VentasService.disputa((v['id'] as num).toInt(), _yo);
    AvisosService.ventaDisputa(
      vendedorEmail: (v['vendedor_email'] ?? '').toString(),
      compradorNombre: appState.usuario?.nombre ?? 'El comprador',
      producto: (v['producto_nombre'] ?? 'el producto').toString(),
    );
    if (mounted) _cargar();
  }

  Future<void> _marcarEntregado(Map<String, dynamic> v) async {
    final done = await VentasService.entregado((v['id'] as num).toInt(), _yo);
    if (!mounted) return;
    if (done) {
      AvisosService.ventaEntregada(
        compradorEmail: (v['comprador_email'] ?? '').toString(),
        vendedorNombre: appState.usuario?.nombre ?? 'El vendedor',
        producto: (v['producto_nombre'] ?? 'el producto').toString(),
      );
      _cargar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: bosque,
          content: Text('Marcado como entregado. Falta que el comprador '
              'confirme para liberar el pago.')));
    } else {
      _msg('No se pudo. Reintenta.');
    }
  }

  void _chatear(String email, String nombre) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: email,
        titulo: nombre.isNotEmpty ? nombre : email,
        soyProfe: false,
        tipo: 'directo',
      ),
    ));
  }

  void _msg(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.esVendedor ? 'Mis ventas' : 'Mis compras')),
      body: _cargando
          ? const CargandoPichangol()
          : _items.isEmpty
              ? _vacio()
              : RefreshIndicator(
                  onRefresh: _cargar,
                  child: ListView(
                    // Regla app: contenido centrado en pantallas anchas.
                    padding: EdgeInsets.fromLTRB(
                        ladoTablet(context, 16, 700), 12,
                        ladoTablet(context, 16, 700), 24),
                    children: [
                      if (widget.esVendedor) _resumen(),
                      for (final v in _items) _tarjeta(v),
                    ],
                  ),
                ),
    );
  }

  Widget _resumen() => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [bosque, teal]),
            borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Retenido',
                      style: TextStyle(color: Colors.white70, fontSize: 12)),
                  Text('${paisActual.moneda} ${_retenido.toStringAsFixed(2)}',
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w900,
                          fontSize: 18)),
                  const Text('esperando confirmación',
                      style: TextStyle(color: Colors.white60, fontSize: 10.5)),
                ],
              ),
            ),
            Container(width: 1, height: 40, color: Colors.white24),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Liberado',
                      style: TextStyle(color: Colors.white70, fontSize: 12)),
                  Text('${paisActual.moneda} ${_liberado.toStringAsFixed(2)}',
                      style: const TextStyle(
                          color: lima,
                          fontWeight: FontWeight.w900,
                          fontSize: 18)),
                  const Text('por cobrar (neto)',
                      style: TextStyle(color: Colors.white60, fontSize: 10.5)),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _tarjeta(Map<String, dynamic> v) {
    final estado = (v['estado'] ?? '').toString();
    // Ícono VIVO por estado: el mismo emoji que llega en la notificación, sobre
    // un círculo de color (estilo Airbnb) para que la pantalla tenga vida.
    final (String etiqueta, Color color, String emoji) = switch (estado) {
      'pagado' => ('Pagado · retenido', naranja, '🛍️'),
      'entregado' => ('Entregado · por confirmar', morado, '📦'),
      'recibido' => ('Completado · liberado', lima, '✅'),
      'disputado' => ('En disputa', clayOscuro, '⚠️'),
      'reembolsado' => ('Reembolsado', teal, '↩️'),
      _ => (estado, teal, '🧾'),
    };
    final monto = ((v['monto_soles'] ?? 0) as num).toDouble();
    final otroNombre = (widget.esVendedor
            ? v['comprador_nombre']
            : v['vendedor_nombre'] ?? '')
        .toString();
    final otroEmail = (widget.esVendedor
            ? v['comprador_email']
            : v['vendedor_email'] ?? '')
        .toString();
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                  radius: 18,
                  backgroundColor: color.withOpacity(0.16),
                  child: Text(emoji, style: const TextStyle(fontSize: 18))),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text((v['producto_nombre'] ?? 'Producto').toString(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text(
                        '${widget.esVendedor ? 'Comprador' : 'Vendedor'}: '
                        '${otroNombre.isNotEmpty ? otroNombre : '—'}',
                        style: const TextStyle(
                            color: textoTenue, fontSize: 12)),
                  ],
                ),
              ),
              Text('${paisActual.moneda} ${monto.toStringAsFixed(2)}',
                  style: const TextStyle(fontWeight: FontWeight.w900)),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                    color: color.withOpacity(0.14),
                    borderRadius: BorderRadius.circular(7)),
                child: Text(etiqueta,
                    style: TextStyle(
                        color: color,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700)),
              ),
              const Spacer(),
              if (otroEmail.isNotEmpty)
                TextButton.icon(
                  onPressed: () => _chatear(otroEmail, otroNombre),
                  icon: const Icon(Icons.chat_bubble_outline, size: 16),
                  label: const Text('Chat'),
                ),
            ],
          ),
          ..._acciones(v, estado),
        ],
      ),
    );
  }

  List<Widget> _acciones(Map<String, dynamic> v, String estado) {
    // VENDEDOR: marcar entregado (cuando está pagado).
    if (widget.esVendedor) {
      if (estado == 'pagado') {
        return [
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () => _marcarEntregado(v),
              icon: const Icon(Icons.local_shipping_outlined, size: 18),
              label: const Text('Marcar como entregado'),
            ),
          ),
        ];
      }
      return const [];
    }
    // COMPRADOR: confirmar recepción / reportar (cuando aún no está liberado).
    if (estado == 'pagado' || estado == 'entregado') {
      return [
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: () => _confirmarRecepcion(v),
                icon: const Icon(Icons.check_circle_outline, size: 18),
                label: const Text('Confirmar recepción'),
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.redAccent),
              onPressed: () => _reportar(v),
              child: const Text('Problema'),
            ),
          ],
        ),
      ];
    }
    return const [];
  }

  Widget _vacio() => Center(
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                  widget.esVendedor
                      ? Icons.point_of_sale_outlined
                      : Icons.shopping_bag_outlined,
                  size: 60,
                  color: textoTenue),
              const SizedBox(height: 14),
              Text(
                  widget.esVendedor
                      ? 'Aún no tienes ventas'
                      : 'Aún no tienes compras',
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 18)),
              const SizedBox(height: 6),
              Text(
                  widget.esVendedor
                      ? 'Cuando alguien compre tus productos, verás aquí cada '
                          'orden y podrás marcarla como entregada.'
                      : 'Cuando compres algo en el Marketplace, aquí confirmas '
                          'la recepción para liberar el pago.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: textoTenue)),
            ],
          ),
        ),
      );
}
