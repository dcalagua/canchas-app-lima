import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../data/bodega_repo.dart';
import '../models/bodega.dart';
import '../services/location_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/geo.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/cargando_pichangol.dart';
import 'login_google_sheet.dart';

/// PEDIR A LA CANCHA (bodega del local): el jugador, DENTRO del local, arma
/// su pedido (2 cervezas 🍺), elige a qué zona se lo llevan y lo envía; al
/// dueño le llega push, confirma y se lo llevan. El PAGO es con el dueño al
/// entregar (efectivo/Yape del local), como siempre — cero comisión.
/// Candados: el dueño debe tener "Acepto pedidos" activo, y se valida por
/// GPS que el cliente esté EN el local (≤250 m).
class PedirBodegaScreen extends StatefulWidget {
  const PedirBodegaScreen({
    super.key,
    required this.duenoEmail,
    required this.nombreLocal,
    this.ubicacionLocal,
  });

  final String duenoEmail;
  final String nombreLocal;
  final LatLng? ubicacionLocal;

  @override
  State<PedirBodegaScreen> createState() => _PedirBodegaScreenState();
}

class _PedirBodegaScreenState extends State<PedirBodegaScreen> {
  bool _cargando = true;
  ConfigBodega? _config;
  List<ProductoBodega> _productos = [];
  List<PedidoBodega> _misPedidos = [];
  final Map<String, int> _ticket = {};
  String _zona = '';
  bool _enviando = false;

  String get _email => (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final res = await Future.wait([
      BodegaRepo.fetchConfig(widget.duenoEmail),
      BodegaRepo.fetchProductos(widget.duenoEmail),
      if (_email.isNotEmpty)
        BodegaRepo.fetchPedidosCliente(_email, widget.duenoEmail),
    ]);
    if (!mounted) return;
    setState(() {
      _config = res[0] as ConfigBodega;
      _productos = (res[1] as List<ProductoBodega>)
          .where((p) => p.stock > 0)
          .toList();
      _misPedidos =
          res.length > 2 ? res[2] as List<PedidoBodega> : const [];
      _cargando = false;
      final zonas = _config?.zonas ?? const [];
      if (_zona.isEmpty && zonas.isNotEmpty) _zona = zonas.first;
    });
  }

  double get _total {
    var t = 0.0;
    _ticket.forEach((id, cant) {
      final p = _productos.cast<ProductoBodega?>().firstWhere(
          (x) => x!.id == id,
          orElse: () => null);
      if (p != null) t += p.precio * cant;
    });
    return t;
  }

  String get _mon =>
      _productos.isNotEmpty ? _productos.first.moneda : 'S/';

  void _sumar(ProductoBodega p, int delta) {
    final nuevo = (_ticket[p.id] ?? 0) + delta;
    if (delta > 0 && nuevo > p.stock) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Solo quedan ${p.stock} de ${p.nombre}.')));
      return;
    }
    setState(() {
      if (nuevo <= 0) {
        _ticket.remove(p.id);
      } else {
        _ticket[p.id] = nuevo;
      }
    });
  }

  Future<void> _enviar() async {
    if (_ticket.isEmpty || _enviando) return;
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'pedir a la bodega')) {
      return;
    }
    if (!mounted) return;
    // CONFIRMACIÓN (el único "paso 2", modal): resumen del pedido + a dónde
    // te lo llevamos. La carta queda limpia y el pedido sale en 2 taps.
    final zonas = _config?.zonas ?? const <String>[];
    var z = zonas.contains(_zona) ? _zona : (zonas.isNotEmpty ? zonas.first : '');
    final resumen = [
      for (final e in _ticket.entries)
        (
          _productos.firstWhere((x) => x.id == e.key),
          e.value,
        ),
    ];
    final zonaSel = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => StatefulBuilder(
        builder: (bctx, setSB) => SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
                20, 16, 20, 16 + MediaQuery.of(bctx).viewInsets.bottom),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Confirma tu pedido 🧾',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                const SizedBox(height: 10),
                for (final (p, cant) in resumen)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      children: [
                        Expanded(child: Text('$cant × ${p.nombre}')),
                        Text('${p.moneda} ${(p.precio * cant).toStringAsFixed(2)}',
                            style: const TextStyle(
                                fontWeight: FontWeight.w700)),
                      ],
                    ),
                  ),
                const Divider(height: 18),
                Row(
                  children: [
                    const Expanded(
                        child: Text('Total',
                            style: TextStyle(fontWeight: FontWeight.w800))),
                    Text('$_mon ${_total.toStringAsFixed(2)}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w900, fontSize: 16)),
                  ],
                ),
                const SizedBox(height: 14),
                const Text('¿Dónde te lo llevamos? 🏃',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final zz in zonas)
                      ChoiceChip(
                        label: Text(zz),
                        selected: z == zz,
                        onSelected: (_) => setSB(() => z = zz),
                      ),
                  ],
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed:
                        z.isEmpty ? null : () => Navigator.pop(bctx, z),
                    child: const Text('Enviar pedido 🛎️',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                ),
                const SizedBox(height: 4),
                const Center(
                  child: Text('Pagas al recibirlo, como siempre.',
                      style: TextStyle(color: textoTenue, fontSize: 12)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (zonaSel == null || !mounted) return;
    _zona = zonaSel;
    setState(() => _enviando = true);
    // Anti-troll: debes estar EN el local (≤250 m) para pedir.
    if (widget.ubicacionLocal != null) {
      final pos = await LocationService.ubicacionActual();
      if (!mounted) return;
      if (pos == null) {
        setState(() => _enviando = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Activa tu ubicación: el pedido solo se puede '
                'hacer estando en el local.')));
        return;
      }
      final km = distanciaKm(pos, widget.ubicacionLocal!);
      if (km > 0.25) {
        setState(() => _enviando = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Estás lejos del local: los pedidos a la cancha '
                'son para cuando estás ahí jugando.')));
        return;
      }
    }
    final items = <ItemVentaBodega>[];
    for (final e in _ticket.entries) {
      final p = _productos.firstWhere((x) => x.id == e.key);
      items.add(ItemVentaBodega(
          productoId: p.id,
          nombre: p.nombre,
          cantidad: e.value,
          precio: p.precio));
    }
    final pedido = PedidoBodega(
      id: 'bpd_${DateTime.now().microsecondsSinceEpoch}',
      dueno: widget.duenoEmail.toLowerCase(),
      cliente: _email,
      clienteNombre: appState.usuario?.nombre ?? _email,
      zona: _zona,
      items: items,
      total: _total,
      moneda: _mon,
      creado: DateTime.now(),
    );
    final ok = await BodegaRepo.crearPedido(pedido);
    if (!mounted) return;
    setState(() => _enviando = false);
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo enviar el pedido. Revisa tu conexión.')));
      return;
    }
    // Push al dueño: "📦 2 Pilsen · Cancha 2 · Juan".
    appState.avisarPedidoBodega(
      email: widget.duenoEmail,
      titulo: '🧃 Pedido a la ${pedido.zona}',
      cuerpo:
          '${pedido.resumen} · $_mon ${pedido.total.toStringAsFixed(2)} · ${pedido.clienteNombre}. Confírmalo en Mi bodega.',
    );
    setState(() {
      _misPedidos = [pedido, ..._misPedidos];
      _ticket.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: bosque,
        content: Text('Pedido enviado 🏃 Te avisamos cuando lo confirmen. '
            'Pagas al recibirlo, como siempre.')));
  }

  Future<void> _cancelar(PedidoBodega p) async {
    await BodegaRepo.actualizarEstadoPedido(p.id, 'cancelado');
    appState.avisarPedidoBodega(
      email: p.dueno,
      titulo: 'Pedido cancelado',
      cuerpo: '${p.clienteNombre} canceló su pedido (${p.resumen}).',
    );
    _cargar();
  }

  (String, Color) _estadoVisual(PedidoBodega p) => switch (p.estado) {
        'confirmado' => ('Confirmado · va en camino 🏃', bosque),
        'entregado' => ('Entregado ✅', bosque),
        'rechazado' => ('Rechazado por el local ❌', clayOscuro),
        'cancelado' => ('Cancelado', Colors.grey),
        _ => p.expirado
            ? ('Sin respuesta aún… pregunta en el mostrador', clayOscuro)
            : ('Esperando confirmación ⏳', Colors.orange),
      };

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cfg = _config;
    return Scaffold(
      appBar: AppBar(title: Text('Bodega · ${widget.nombreLocal}')),
      body: AnchoLectura(
        child: _cargando
            ? const Center(child: CargandoPichangol())
            : RefreshIndicator(
                onRefresh: _cargar,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
                  children: [
                    // Mis pedidos activos (estado en vivo con pull-to-refresh).
                    for (final p in _misPedidos.where(
                        (p) => p.estado != 'cancelado'))
                      Container(
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: cs.surface,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: trazo),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('${p.resumen} → ${p.zona}',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700)),
                                  const SizedBox(height: 2),
                                  Text(_estadoVisual(p).$1,
                                      style: TextStyle(
                                          fontSize: 12.5,
                                          fontWeight: FontWeight.w600,
                                          color: _estadoVisual(p).$2)),
                                ],
                              ),
                            ),
                            if (p.pendiente)
                              TextButton(
                                onPressed: () => _cancelar(p),
                                child: const Text('Cancelar',
                                    style:
                                        TextStyle(color: Colors.redAccent)),
                              ),
                          ],
                        ),
                      ),
                    // La CARTA se ve SIEMPRE (aunque el local no reciba
                    // pedidos todavía): el cliente conoce los precios y compra
                    // en el mostrador. Solo el PEDIR depende del toggle.
                    if (cfg != null && !cfg.aceptaPedidos) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(bottom: 12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFF6E5),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Text(
                            '🛒 Este local aún no recibe pedidos a la '
                            'cancha: mira la carta y compra en el mostrador.',
                            style: TextStyle(fontSize: 12.5)),
                      ),
                    ],
                    if (_productos.isEmpty) ...[
                      const SizedBox(height: 30),
                      const Center(
                        child: Text('La bodega aún no tiene productos.',
                            style: TextStyle(color: textoTenue)),
                      ),
                    ] else ...[
                      if (cfg?.aceptaPedidos ?? false) ...[
                        // El antojo primero (regla UX): la ZONA se elige al
                        // confirmar el pedido, no antes de ver la carta.
                        const Text('Toca para agregar a tu pedido',
                            style:
                                TextStyle(color: textoTenue, fontSize: 12.5)),
                        const SizedBox(height: 8),
                      ],
                      for (final p in _productos)
                        Container(
                          margin: const EdgeInsets.only(bottom: 8),
                          decoration: BoxDecoration(
                            color: (_ticket[p.id] ?? 0) > 0
                                ? limaSuave
                                : cs.surface,
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                                color: (_ticket[p.id] ?? 0) > 0
                                    ? lima
                                    : trazo),
                          ),
                          child: ListTile(
                            onTap: (cfg?.aceptaPedidos ?? false)
                                ? () => _sumar(p, 1)
                                : null,
                            leading: p.fotoUrl != null &&
                                    p.fotoUrl!.isNotEmpty
                                ? ClipRRect(
                                    borderRadius: BorderRadius.circular(10),
                                    child: Image.network(p.fotoUrl!,
                                        width: 44,
                                        height: 44,
                                        fit: BoxFit.cover))
                                : Container(
                                    width: 44,
                                    height: 44,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: limaSuave,
                                      borderRadius:
                                          BorderRadius.circular(10),
                                    ),
                                    child: Text(p.emoji,
                                        style:
                                            const TextStyle(fontSize: 22)),
                                  ),
                            title: Text(p.nombre,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            subtitle: Text(
                                '${p.moneda} ${p.precio.toStringAsFixed(2)}',
                                style: const TextStyle(
                                    color: bosque,
                                    fontWeight: FontWeight.w700)),
                            trailing: !(cfg?.aceptaPedidos ?? false)
                                ? null
                                : (_ticket[p.id] ?? 0) == 0
                                    ? const Icon(Icons.add_circle_outline,
                                        color: bosque)
                                    : Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      IconButton(
                                        onPressed: () => _sumar(p, -1),
                                        icon: const Icon(
                                            Icons.remove_circle,
                                            color: clayOscuro),
                                      ),
                                      Text('${_ticket[p.id]}',
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w900,
                                              fontSize: 16)),
                                      IconButton(
                                        onPressed: () => _sumar(p, 1),
                                        icon: const Icon(Icons.add_circle,
                                            color: bosque),
                                      ),
                                    ],
                                  ),
                          ),
                        ),
                      const SizedBox(height: 6),
                      const Text(
                          'Pagas al recibir tu pedido (efectivo o el QR del '
                          'local), como siempre.',
                          style:
                              TextStyle(color: textoTenue, fontSize: 12)),
                    ],
                  ],
                ),
              ),
      ),
      bottomNavigationBar: _ticket.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      padding: const EdgeInsets.symmetric(vertical: 15)),
                  onPressed: _enviando ? null : _enviar,
                  child: Text(
                      _enviando
                          ? 'Enviando…'
                          : 'Pedir · $_mon ${_total.toStringAsFixed(2)} · ${_ticket.values.fold(0, (a, b) => a + b)} ítem(s)',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 16)),
                ),
              ),
            ),
    );
  }
}
