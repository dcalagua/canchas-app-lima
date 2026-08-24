import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../data/bodega_repo.dart';
import '../models/bodega.dart';
import '../services/location_service.dart';
import '../services/pagos_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/geo.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/imagen_producto_bodega.dart';
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
  CuentaBodega? _miCuenta; // cuenta abierta con este local ("llevas S/ X")
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
    final cuenta = _email.isEmpty
        ? null
        : await BodegaRepo.fetchCuentaAbiertaCliente(
            _email, widget.duenoEmail);
    if (!mounted) return;
    setState(() {
      _miCuenta = cuenta;
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
    // ¿Puede PREPAGAR con su saldo Pichangol? (fase 3): saldo suficiente y en
    // la MISMA moneda del local. Si no, paga al recibir como siempre.
    final puedeSaldo = appState.saldoClub >= _total &&
        _total > 0 &&
        appState.monedaSaldoSimbolo == _mon;
    var conSaldo = false;
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
                if (puedeSaldo) ...[
                  const SizedBox(height: 14),
                  const Text('¿Cómo pagas? 💳',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      ChoiceChip(
                        label: const Text('Al recibir (efectivo/Yape)'),
                        selected: !conSaldo,
                        onSelected: (_) => setSB(() => conSaldo = false),
                      ),
                      ChoiceChip(
                        label: Text(
                            'Con mi saldo (${appState.monedaSaldoSimbolo} ${appState.saldoClub})'),
                        selected: conSaldo,
                        onSelected: (_) => setSB(() => conSaldo = true),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed:
                        z.isEmpty ? null : () => Navigator.pop(bctx, z),
                    child: Text(
                        conSaldo
                            ? 'Pagar y enviar pedido 💳'
                            : 'Enviar pedido 🛎️',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                ),
                const SizedBox(height: 4),
                Center(
                  child: Text(
                      conSaldo
                          ? 'Se descuenta de tu saldo; si el local no lo '
                              'toma, se te devuelve solo.'
                          : 'Pagas al recibirlo, como siempre.',
                      style:
                          const TextStyle(color: textoTenue, fontSize: 12)),
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
      pagado: conSaldo,
      creado: DateTime.now(),
    );
    final ok = await BodegaRepo.crearPedido(pedido);
    if (!mounted) return;
    if (!ok) {
      setState(() => _enviando = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(conSaldo
              ? 'No se pudo registrar el pedido (no se cobró nada). '
                  'Intenta pagando al recibir.'
              : 'No se pudo enviar el pedido. Revisa tu conexión.')));
      return;
    }
    // PREPAGO con saldo (fase 3): cobra RECIÉN con el pedido ya registrado.
    // Si el cobro falla, el pedido se cancela al instante (no viaja nadie).
    if (conSaldo) {
      final pago = await PagosService.bodegaPago(
        cliente: _email,
        duenoId: pedido.dueno,
        monto: pedido.total,
        pedidoId: pedido.id,
        concepto: 'Bodega · ${pedido.resumen}',
      );
      if (!mounted) return;
      if (pago == null || pago['ok'] != true) {
        await BodegaRepo.cambiarEstadoPedidoSi(pedido.id, 'cancelado',
            desde: 'pendiente');
        setState(() => _enviando = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            backgroundColor: clayOscuro,
            content: Text(pago?['error'] == 'saldo_insuficiente'
                ? 'Tu saldo no alcanza: el pedido se canceló y no se '
                    'cobró nada. Recarga o paga al recibir.'
                : 'No se pudo cobrar tu saldo: el pedido se canceló y no '
                    'se cobró nada.')));
        return;
      }
      unawaited(appState.sincronizarSaldo()); // refleja el débito al toque
    }
    setState(() => _enviando = false);
    // Push al dueño: "📦 2 Pilsen · Cancha 2 · Juan".
    appState.avisarPedidoBodega(
      email: widget.duenoEmail,
      titulo: conSaldo
          ? '💳 Pedido PAGADO a la ${pedido.zona}'
          : '🧃 Pedido a la ${pedido.zona}',
      cuerpo:
          '${pedido.resumen} · $_mon ${pedido.total.toStringAsFixed(2)} · ${pedido.clienteNombre}. '
          '${conSaldo ? 'Ya está pagado con saldo Pichangol: solo entrégalo.' : 'Confírmalo en Mi bodega.'}',
    );
    setState(() {
      _misPedidos = [pedido, ..._misPedidos];
      _ticket.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: bosque,
        content: Text(conSaldo
            ? 'Pedido pagado y enviado 💳 Te avisamos cuando lo confirmen.'
            : 'Pedido enviado 🏃 Te avisamos cuando lo confirmen. '
                'Pagas al recibirlo, como siempre.')));
  }

  Future<void> _cancelar(PedidoBodega p) async {
    // Candado de concurrencia: solo se cancela si SIGUE pendiente. Si el
    // dueño lo confirmó un segundo antes, el pedido ya va en camino y el
    // cliente se entera aquí (en vez de cancelarle a alguien que ya salió).
    final (ok, actual) = await BodegaRepo.cambiarEstadoPedidoSi(
        p.id, 'cancelado',
        desde: 'pendiente');
    if (!mounted) return;
    if (ok) {
      // Pedido PREPAGADO con saldo → reembolso automático (idempotente).
      if (p.pagado) {
        final devuelto = await PagosService.bodegaReembolso(p.id);
        if (devuelto) unawaited(appState.sincronizarSaldo());
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              backgroundColor: bosque,
              content: Text(devuelto
                  ? 'Pedido cancelado: te devolvimos ${p.moneda} '
                      '${p.total.toStringAsFixed(2)} a tu saldo 💸'
                  : 'Pedido cancelado. La devolución a tu saldo se '
                      'procesará en breve.')));
        }
      }
      appState.avisarPedidoBodega(
        email: p.dueno,
        titulo: 'Pedido cancelado',
        cuerpo: '${p.clienteNombre} canceló su pedido (${p.resumen}).',
      );
    } else if (actual == 'confirmado' || actual == 'entregado') {
      await avisarPichangol(
        context,
        titulo: 'Ya va en camino 🏃',
        mensaje: 'El local confirmó tu pedido justo antes de que lo '
            'cancelaras. Recíbelo y paga al recibirlo; cualquier cambio '
            'coordínalo en el mostrador.',
        icono: Icons.delivery_dining,
      );
    }
    _cargar();
  }

  (String, Color) _estadoVisual(PedidoBodega p) {
    final (txt, color) = switch (p.estado) {
      'confirmado' => ('Confirmado · va en camino 🏃', bosque),
      'entregado' => ('Entregado ✅', bosque),
      'rechazado' => ('Rechazado por el local ❌', clayOscuro),
      'cancelado' => ('Cancelado', Colors.grey),
      _ => p.expirado
          ? ('Sin respuesta aún… pregunta en el mostrador', clayOscuro)
          : ('Esperando confirmación ⏳', Colors.orange),
    };
    // Prepagado con saldo: que se vea SIEMPRE (nadie te cobra de nuevo).
    return (p.pagado ? '$txt · pagado 💳' : txt, color);
  }

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
                    // TU CUENTA ABIERTA (si el local te la abrió): total en
                    // vivo, cero sorpresas al salir.
                    if (_miCuenta != null)
                      Container(
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: limaSuave,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: lima),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Expanded(
                                  child: Text('📒 Tu cuenta abierta',
                                      style: TextStyle(
                                          fontWeight: FontWeight.w800,
                                          fontSize: 15)),
                                ),
                                Text(
                                    '${_miCuenta!.moneda} ${_miCuenta!.total.toStringAsFixed(2)}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w900,
                                        color: bosque,
                                        fontSize: 15)),
                              ],
                            ),
                            const SizedBox(height: 2),
                            Text(_miCuenta!.resumen,
                                style: const TextStyle(fontSize: 12.5)),
                            const Text(
                                'La pagas al salir, en el mostrador.',
                                style: TextStyle(
                                    color: textoTenue, fontSize: 12)),
                          ],
                        ),
                      ),
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
                            // Foto real > packshot IA genérico > emoji.
                            leading: ImagenProductoBodega(producto: p),
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
