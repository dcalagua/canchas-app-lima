import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config/pais.dart';
import '../data/bodega_repo.dart';
import '../models/bodega.dart';
import '../services/supabase_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../services/whatsapp_link.dart';
import '../widgets/candado_pro.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/imagen_producto_bodega.dart';

/// MI BODEGA — POS ligero del dueño (función Pichangol Pro): caja rápida de
/// venta, catálogo con stock y reportes. La plata NO pasa por Pichangol (el
/// dueño cobra con su Yape/efectivo de siempre); aquí registra la venta en
/// 3 segundos y el stock baja solo. Incluye la CARTA digital pública
/// (/b/{cartaId}) con su QR imprimible.
class BodegaScreen extends StatefulWidget {
  const BodegaScreen({super.key});

  @override
  State<BodegaScreen> createState() => _BodegaScreenState();
}

class _BodegaScreenState extends State<BodegaScreen> {
  int _tab = 0; // 0 Caja · 1 Productos · 2 Reporte · 3 Pedidos · 4 Cuentas
  bool _cargando = true;
  List<ProductoBodega> _productos = [];
  List<VentaBodega> _ventas = [];
  List<PedidoBodega> _pedidos = []; // pedidos a la cancha (últimos 2 días)
  List<CuentaBodega> _cuentas = []; // cuentas abiertas/cerradas (30 días)
  ConfigBodega? _config; // acepta pedidos + zonas + cuenta abierta
  final Map<String, int> _ticket = {}; // productoId → cantidad
  // Filtros de la CAJA estilo POS (referencia: Comerza de EBIM).
  String _busquedaCaja = '';
  String _catCaja = 'Todo';

  // Sugerencias rápidas de productos por categoría Y POR PAÍS (regla del
  // director: las marcas cambian — Pilsen/Cristal en Perú, Paceña/Huari en
  // Bolivia, Pilsener/Club en Ecuador). Un tap llena el nombre; el TextField
  // queda para marcas propias, que son nombres.
  static const _categorias = <String>[
    'Bebidas', 'Cervezas', 'Deportivo', 'Snacks', 'Otros',
  ];
  static const _sugerenciasPE = <String, List<String>>{
    'Bebidas': [
      'Agua San Luis', 'Agua San Mateo', 'Coca-Cola', 'Inca Kola', 'Sprite',
      'Fanta', 'Frugos', 'Cifrut',
    ],
    'Cervezas': ['Pilsen', 'Cristal', 'Cusqueña', 'Corona', 'Heineken'],
    'Deportivo': [
      'Gatorade', 'Powerade', 'Sporade', 'Volt', 'Alquiler de paleta',
      'Alquiler de pelotas', 'Tubo de pelotas',
    ],
    'Snacks': [
      'Papitas Lays', 'Doritos', 'Chifles', 'Galletas', 'Chocolate Sublime',
      'Maní', 'Sandwich',
    ],
    'Otros': ['Hielo', 'Cigarros', 'Toalla', 'Gorra'],
  };
  static const _sugerenciasBO = <String, List<String>>{
    'Bebidas': [
      'Agua Vital', 'Coca-Cola', 'Sprite', 'Fanta', 'Salvietti',
      'Jugos Del Valle',
    ],
    'Cervezas': ['Paceña', 'Huari', 'Potosina', 'Corona', 'Heineken'],
    'Deportivo': [
      'Gatorade', 'Powerade', 'Alquiler de paleta', 'Alquiler de pelotas',
      'Tubo de pelotas',
    ],
    'Snacks': ['Papitas', 'Doritos', 'Chizitos', 'Galletas', 'Maní',
      'Sandwich'],
    'Otros': ['Hielo', 'Cigarros', 'Toalla', 'Gorra'],
  };
  static const _sugerenciasEC = <String, List<String>>{
    'Bebidas': [
      'Agua Güitig', 'Agua Tesalia', 'Coca-Cola', 'Sprite', 'Fanta',
      'Fioravanti',
    ],
    'Cervezas': ['Pilsener', 'Club Premium', 'Corona', 'Heineken'],
    'Deportivo': [
      'Gatorade', 'Powerade', 'Profit', 'Alquiler de paleta',
      'Alquiler de pelotas', 'Tubo de pelotas',
    ],
    'Snacks': ['Papitas', 'Doritos', 'Kchitos', 'Galletas', 'Maní',
      'Sandwich'],
    'Otros': ['Hielo', 'Cigarros', 'Toalla', 'Gorra'],
  };

  /// Sugerencias del PAÍS activo (default: Perú).
  Map<String, List<String>> get _sugerencias => switch (paisActual.iso) {
        'BO' => _sugerenciasBO,
        'EC' => _sugerenciasEC,
        _ => _sugerenciasPE,
      };

  /// Símbolo de moneda del país del dueño ('S/', 'Bs', r'$').
  String get _mon => paisActual.moneda;

  String get _email => (appState.usuario?.email ?? '').toLowerCase();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    if (_email.isEmpty) {
      setState(() => _cargando = false);
      return;
    }
    final desde = DateTime.now().subtract(const Duration(days: 30));
    final res = await Future.wait([
      BodegaRepo.fetchProductos(_email),
      BodegaRepo.fetchVentas(_email, desde: desde),
      BodegaRepo.fetchPedidosDueno(_email),
      BodegaRepo.fetchConfig(_email),
      BodegaRepo.fetchCuentas(_email),
    ]);
    if (!mounted) return;
    setState(() {
      _productos = res[0] as List<ProductoBodega>;
      _ventas = res[1] as List<VentaBodega>;
      _pedidos = res[2] as List<PedidoBodega>;
      _config = res[3] as ConfigBodega;
      _cuentas = res[4] as List<CuentaBodega>;
      _cargando = false;
      // Limpia del ticket productos que ya no existen.
      _ticket.removeWhere((id, _) => !_productos.any((p) => p.id == id));
    });
  }

  // ── CAJA RÁPIDA ────────────────────────────────────────────────────────────

  double get _totalTicket {
    var t = 0.0;
    _ticket.forEach((id, cant) {
      final p = _productos.cast<ProductoBodega?>().firstWhere(
          (x) => x!.id == id,
          orElse: () => null);
      if (p != null) t += p.precio * cant;
    });
    return t;
  }

  void _sumar(ProductoBodega p, int delta) {
    final actual = _ticket[p.id] ?? 0;
    final nuevo = actual + delta;
    if (delta > 0 && nuevo > p.stock) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Solo te quedan ${p.stock} de ${p.nombre}.')));
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

  Future<void> _cobrar() async {
    if (_ticket.isEmpty) return;
    // Medio de pago por SELECCIÓN (el cobro real es con el Yape/efectivo del
    // dueño, como siempre; esto es el registro para caja y reportes).
    final medio = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                    'Cobrar $_mon ${_totalTicket.toStringAsFixed(2)} — ¿cómo pagó?',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17)),
              ),
            ),
            ListTile(
              leading: const Text('💵', style: TextStyle(fontSize: 22)),
              title: const Text('Efectivo'),
              onTap: () => Navigator.pop(bctx, 'efectivo'),
            ),
            ListTile(
              leading: const Text('📱', style: TextStyle(fontSize: 22)),
              title: Text(paisActual.iso == 'PE'
                  ? 'Yape / Plin del local'
                  : 'QR / transferencia del local'),
              onTap: () => Navigator.pop(bctx, 'yape'),
            ),
            ListTile(
              leading: const Text('🎁', style: TextStyle(fontSize: 22)),
              title: const Text('Cortesía (no se cobra)'),
              onTap: () => Navigator.pop(bctx, 'cortesia'),
            ),
            // CUENTA ABIERTA: anota el consumo del mostrador a la cuenta de
            // un cliente REGISTRADO (una ya abierta, o se abre eligiendo al
            // cliente de la base del local); paga TODO al retirarse.
            if (_config?.permiteCuenta ?? false)
              ListTile(
                leading: const Text('📒', style: TextStyle(fontSize: 22)),
                title: const Text('A la cuenta (paga al salir)'),
                subtitle: Text(
                    _abiertas > 0
                        ? '$_abiertas cuenta(s) abierta(s)'
                        : 'Abrir cuenta a un cliente registrado',
                    style: const TextStyle(fontSize: 12)),
                onTap: () => Navigator.pop(bctx, 'cuenta'),
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (medio == null || !mounted) return;

    final items = <ItemVentaBodega>[];
    final nuevoStock = <String, int>{};
    for (final e in _ticket.entries) {
      final p =
          _productos.firstWhere((x) => x.id == e.key);
      items.add(ItemVentaBodega(
          productoId: p.id,
          nombre: p.nombre,
          cantidad: e.value,
          precio: p.precio));
      nuevoStock[p.id] = (p.stock - e.value) < 0 ? 0 : p.stock - e.value;
    }
    if (medio == 'cuenta') {
      await _anotarTicketACuenta(items, nuevoStock);
      return;
    }
    final venta = VentaBodega(
      id: 'bv_${DateTime.now().microsecondsSinceEpoch}',
      dueno: _email,
      items: items,
      total: medio == 'cortesia' ? 0 : _totalTicket,
      medioPago: medio,
      creado: DateTime.now(),
    );
    final ok = await conPreload(
        context, () => BodegaRepo.registrarVenta(venta, nuevoStock),
        texto: 'Registrando venta…');
    if (!mounted) return;
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content:
              Text('No se pudo registrar. Revisa tu conexión e intenta.')));
      return;
    }
    setState(() {
      _ventas = [venta, ..._ventas];
      _productos = [
        for (final p in _productos)
          nuevoStock.containsKey(p.id)
              ? p.copyWith(stock: nuevoStock[p.id])
              : p,
      ];
      _ticket.clear();
    });
    // Alerta de reposición al instante (lo que el dueño quiere: logística).
    final bajos = _productos
        .where((p) => nuevoStock.containsKey(p.id) && p.stockBajo)
        .map((p) => '${p.nombre} (${p.stock})')
        .toList();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: bosque,
      content: Text(bajos.isEmpty
          ? 'Venta registrada ✅ · stock actualizado'
          : 'Venta registrada ✅ · ¡Repón: ${bajos.join(', ')}!'),
    ));
  }

  /// Elige un cliente REGISTRADO de la base del local (reservas de sus
  /// canchas) para abrirle cuenta: primero los que tienen reserva HOY (están
  /// en el local), luego los recientes. Por SELECCIÓN (regla del app).
  Future<(String, String)?> _elegirClienteRegistrado(
      Set<String> conCuenta) async {
    final hoy = appState.isoDe(DateTime.now());
    final vistos = <String>{};
    final deHoy = <(String, String)>[];
    final otros = <(String, String)>[];
    final rs = [...appState.reservas]
      ..sort((a, b) => b.fecha.compareTo(a.fecha));
    for (final r in rs) {
      if (appState.miCanchaDeReserva(r.canchaId) == null) continue;
      final e = r.usuario.trim().toLowerCase();
      if (e.isEmpty || conCuenta.contains(e) || !vistos.add(e)) continue;
      final item = (e, r.jugador.trim().isEmpty ? e : r.jugador.trim());
      (r.fecha == hoy ? deHoy : otros).add(item);
    }
    final lista = [...deHoy, ...otros.take(300)];
    if (lista.isEmpty) {
      if (mounted) {
        await avisarPichangol(
          context,
          titulo: 'Sin clientes registrados',
          mensaje: 'La cuenta abierta es solo para clientes registrados '
              '(así sabes quién te debe). Aparecerán aquí cuando reserven '
              'en tus canchas con la app.',
          icono: Icons.badge_outlined,
        );
      }
      return null;
    }
    appState.cargarPerfiles([for (final (e, _) in lista) e]);
    if (!mounted) return null;
    // Con muchos registrados hace falta BUSCAR (pedido del director): campo
    // de búsqueda arriba + lista filtrada en vivo (texto libre permitido:
    // es un buscador).
    var filtro = '';
    return showModalBottomSheet<(String, String)>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => StatefulBuilder(builder: (bctx, setSB) {
        final q = filtro.trim().toLowerCase();
        final visibles = [
          for (final it in lista)
            if (q.isEmpty ||
                it.$2.toLowerCase().contains(q) ||
                it.$1.contains(q))
              it,
        ];
        final bottom = MediaQuery.of(bctx).viewInsets.bottom;
        return SafeArea(
          child: Padding(
            padding: EdgeInsets.only(bottom: bottom),
            child: SizedBox(
              height: MediaQuery.of(bctx).size.height * 0.72,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.fromLTRB(20, 16, 20, 8),
                    child: Text('Abrir cuenta · ¿para quién?',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 17)),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 6),
                    child: TextField(
                      autofocus: false,
                      onChanged: (v) => setSB(() => filtro = v),
                      decoration: InputDecoration(
                        isDense: true,
                        hintText: 'Buscar por nombre…',
                        prefixIcon: const Icon(Icons.search, size: 20),
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 10),
                        border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(999),
                            borderSide: const BorderSide(color: trazo)),
                        enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(999),
                            borderSide: const BorderSide(color: trazo)),
                      ),
                    ),
                  ),
                  Expanded(
                    child: visibles.isEmpty
                        ? const Center(
                            child: Text('Nadie coincide con esa búsqueda.',
                                style: TextStyle(color: textoTenue)))
                        : ListView(
                            children: [
                              for (final (e, nombre) in visibles)
                                Builder(builder: (_) {
                                  final foto = appState.fotoDe(e);
                                  return ListTile(
                                    // Avatar con FOTO real (regla del app).
                                    leading: CircleAvatar(
                                      radius: 18,
                                      backgroundColor: limaSuave,
                                      backgroundImage:
                                          foto != null && foto.isNotEmpty
                                              ? CachedNetworkImageProvider(
                                                  foto)
                                              : null,
                                      child: foto == null || foto.isEmpty
                                          ? Text(
                                              nombre.isNotEmpty
                                                  ? nombre[0].toUpperCase()
                                                  : '?',
                                              style: const TextStyle(
                                                  fontWeight:
                                                      FontWeight.w800,
                                                  color: bosque))
                                          : null,
                                    ),
                                    title: Text(nombre,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w700)),
                                    subtitle: deHoy.any((x) => x.$1 == e)
                                        ? const Text(
                                            'Con reserva hoy · está en el local',
                                            style: TextStyle(
                                                fontSize: 11.5,
                                                color: bosque))
                                        : null,
                                    onTap: () =>
                                        Navigator.pop(bctx, (e, nombre)),
                                  );
                                }),
                              const SizedBox(height: 8),
                            ],
                          ),
                  ),
                ],
              ),
            ),
          ),
        );
      }),
    );
  }

  /// Anota el ticket de la CAJA a una cuenta abierta — o ABRE una nueva
  /// eligiendo al cliente registrado (pedido de palabra en el mostrador). El
  /// stock baja al instante; la venta se registra al CERRAR la cuenta.
  Future<void> _anotarTicketACuenta(
      List<ItemVentaBodega> items, Map<String, int> nuevoStock) async {
    final abiertas = [for (final c in _cuentas) if (c.abierta) c];
    String cliente;
    String clienteNombre;
    double totalPrevio;
    if (abiertas.isEmpty) {
      // Sin cuentas abiertas → directo al selector de cliente registrado.
      final sel = await _elegirClienteRegistrado(const {});
      if (sel == null || !mounted) return;
      (cliente, clienteNombre) = sel;
      totalPrevio = 0;
    } else {
      final cuenta = await showModalBottomSheet<Object>(
        context: context,
        backgroundColor: Theme.of(context).colorScheme.surface,
        shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
        builder: (bctx) => SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 16, 20, 4),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('¿A la cuenta de quién?',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 17)),
                ),
              ),
              for (final c in abiertas)
                ListTile(
                  leading: const Text('📒', style: TextStyle(fontSize: 22)),
                  title: Text(c.clienteNombre,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text(
                      'Lleva ${c.moneda} ${c.total.toStringAsFixed(2)}',
                      style: const TextStyle(fontSize: 12)),
                  onTap: () => Navigator.pop(bctx, c),
                ),
              ListTile(
                leading: const Icon(Icons.person_add_alt_1_outlined,
                    color: bosque),
                title: const Text('Abrir cuenta nueva',
                    style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text('A un cliente registrado del local',
                    style: TextStyle(fontSize: 12)),
                onTap: () => Navigator.pop(bctx, 'nueva'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      );
      if (cuenta == null || !mounted) return;
      if (cuenta == 'nueva') {
        final sel = await _elegirClienteRegistrado(
            {for (final c in abiertas) c.cliente});
        if (sel == null || !mounted) return;
        (cliente, clienteNombre) = sel;
        totalPrevio = 0;
      } else {
        final c = cuenta as CuentaBodega;
        cliente = c.cliente;
        clienteNombre = c.clienteNombre;
        totalPrevio = c.total;
      }
    }
    final agregado = items.fold<double>(0, (a, i) => a + i.subtotal);
    final tope = _config?.topeCuenta ?? 0;
    if (tope > 0 && totalPrevio + agregado > tope) {
      await avisarPichangol(
        context,
        titulo: 'Tope de cuenta alcanzado',
        mensaje: 'La cuenta de $clienteNombre llegaría a '
            '$_mon ${(totalPrevio + agregado).toStringAsFixed(2)} '
            'y tu tope es $_mon ${tope.toStringAsFixed(0)}. '
            'Cobra este consumo al entregar (o cierra la cuenta primero).',
        icono: Icons.speed,
      );
      return;
    }
    final res = await conPreload(
        context,
        () => BodegaRepo.anotarACuenta(
              dueno: _email,
              cliente: cliente,
              clienteNombre: clienteNombre,
              items: items,
              moneda: _mon,
            ),
        texto: 'Anotando…');
    if (!mounted) return;
    if (res == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: clayOscuro,
          content: Text('No se pudo anotar (¿la cuenta se cerró?). '
              'Refresca e intenta de nuevo.')));
      _cargar();
      return;
    }
    await BodegaRepo.actualizarStock(nuevoStock);
    setState(() {
      // Upsert: si la cuenta es nueva (recién abierta) entra a la lista.
      _cuentas = _cuentas.any((x) => x.id == res.id)
          ? [for (final x in _cuentas) x.id == res.id ? res : x]
          : [res, ..._cuentas];
      _productos = [
        for (final p in _productos)
          nuevoStock.containsKey(p.id)
              ? p.copyWith(stock: nuevoStock[p.id])
              : p,
      ];
      _ticket.clear();
    });
    if (res.cliente.isNotEmpty) {
      appState.avisarPedidoBodega(
        email: res.cliente,
        titulo: 'Anotado en tu cuenta 📒',
        cuerpo: 'Se agregó ${items.map((i) => '${i.cantidad} ${i.nombre}').join(' + ')}. '
            'Llevas ${res.moneda} ${res.total.toStringAsFixed(2)}; pagas al salir.',
      );
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: bosque,
        content: Text('Anotado a la cuenta de ${res.clienteNombre} 📒 · '
            'lleva ${res.moneda} ${res.total.toStringAsFixed(2)}')));
  }

  // ── PRODUCTOS (alta/edición) ───────────────────────────────────────────────

  Future<void> _editarProducto(ProductoBodega? base) async {
    final nombre = TextEditingController(text: base?.nombre ?? '');
    final precio = TextEditingController(
        text: base != null && base.precio > 0
            ? base.precio.toStringAsFixed(2)
            : '');
    var categoria = base?.categoria ?? 'Bebidas';
    // Stock TIPEABLE además de los botones +/- (pedido del director).
    final stockCtrl = TextEditingController(text: '${base?.stock ?? 0}');
    final stockMinCtrl =
        TextEditingController(text: '${base?.stockMin ?? 2}');
    String? error;

    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => StatefulBuilder(
        builder: (bctx, setSB) {
          final bottom = MediaQuery.of(bctx).viewInsets.bottom;
          // Número EDITABLE (teclado) + botones +/- (ambos caminos valen).
          Widget stepper(String label, TextEditingController ctrl,
              {int min = 0}) {
            int val() => int.tryParse(ctrl.text.trim()) ?? min;
            void poner(int v) =>
                setSB(() => ctrl.text = '${v < min ? min : v}');
            return Row(
              children: [
                Expanded(
                    child: Text(label,
                        style: const TextStyle(fontWeight: FontWeight.w600))),
                IconButton(
                    onPressed: val() > min ? () => poner(val() - 1) : null,
                    icon: const Icon(Icons.remove_circle_outline)),
                SizedBox(
                  width: 64,
                  child: TextField(
                    controller: ctrl,
                    textAlign: TextAlign.center,
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(5),
                    ],
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 15),
                    decoration: const InputDecoration(
                      isDense: true,
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                    onPressed: () => poner(val() + 1),
                    icon: const Icon(Icons.add_circle_outline, color: bosque)),
              ],
            );
          }

          return Padding(
            padding: EdgeInsets.fromLTRB(20, 16, 20, 16 + bottom),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(base == null ? 'Nuevo producto' : 'Editar producto',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 18)),
                  const SizedBox(height: 12),
                  const Text('Categoría',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final c in _categorias)
                        ChoiceChip(
                          label: Text(c),
                          selected: categoria == c,
                          onSelected: (_) => setSB(() => categoria = c),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: nombre,
                    textCapitalization: TextCapitalization.words,
                    decoration: const InputDecoration(
                        labelText: 'Producto',
                        hintText: 'Toca una sugerencia o escribe la marca'),
                  ),
                  const SizedBox(height: 8),
                  // Sugerencias de un tap (data limpia y cero tipeo).
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final s
                          in _sugerencias[categoria] ?? const <String>[])
                        ActionChip(
                          label: Text(s,
                              style: const TextStyle(fontSize: 12)),
                          onPressed: () => setSB(() => nombre.text = s),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: precio,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    decoration: InputDecoration(
                        labelText: 'Precio de venta',
                        prefixText: '${paisActual.moneda} '),
                  ),
                  const SizedBox(height: 8),
                  stepper('Stock actual', stockCtrl),
                  stepper('Avisarme cuando queden', stockMinCtrl),
                  if (error != null) ...[
                    const SizedBox(height: 6),
                    Text(error!,
                        style: const TextStyle(
                            color: Colors.redAccent, fontSize: 12.5)),
                  ],
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      if (base != null)
                        TextButton(
                          onPressed: () async {
                            final si = await confirmarPichangol(
                              bctx,
                              titulo: 'Eliminar producto',
                              mensaje:
                                  '¿Quitar "${base.nombre}" de tu bodega?',
                              textoConfirmar: 'Eliminar',
                              destructivo: true,
                              icono: Icons.delete_outline,
                            );
                            if (si && bctx.mounted) {
                              await BodegaRepo.eliminarProducto(base.id);
                              if (bctx.mounted) Navigator.pop(bctx, true);
                            }
                          },
                          child: const Text('Eliminar',
                              style: TextStyle(color: Colors.redAccent)),
                        ),
                      const Spacer(),
                      TextButton(
                          onPressed: () => Navigator.pop(bctx, false),
                          child: const Text('Cancelar')),
                      const SizedBox(width: 8),
                      FilledButton(
                        onPressed: () async {
                          final n = nombre.text.trim();
                          final pr = double.tryParse(
                              precio.text.trim().replaceAll(',', '.'));
                          if (n.isEmpty) {
                            setSB(() => error = 'Ponle nombre al producto.');
                            return;
                          }
                          if (pr == null || pr <= 0) {
                            setSB(() =>
                                error = 'Ponle el precio de venta.');
                            return;
                          }
                          final p = ProductoBodega(
                            id: base?.id ??
                                'bp_${DateTime.now().microsecondsSinceEpoch}',
                            dueno: _email,
                            cartaId: BodegaRepo.cartaIdDe(_email),
                            nombre: n,
                            categoria: categoria,
                            precio: pr,
                            stock:
                                int.tryParse(stockCtrl.text.trim()) ?? 0,
                            stockMin:
                                int.tryParse(stockMinCtrl.text.trim()) ?? 0,
                            fotoUrl: base?.fotoUrl,
                            moneda: paisActual.moneda,
                          );
                          final okG = await BodegaRepo.guardarProducto(p);
                          if (!bctx.mounted) return;
                          if (!okG) {
                            setSB(() => error =
                                'No se pudo guardar. ¿Corriste el SQL de la '
                                'bodega en Supabase?');
                            return;
                          }
                          Navigator.pop(bctx, true);
                        },
                        child: const Text('Guardar'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
    if (ok == true) _cargar();
  }

  Future<void> _cambiarFoto(ProductoBodega p) async {
    final XFile? f = await ImagePicker().pickImage(
        source: ImageSource.gallery, maxWidth: 900, imageQuality: 85);
    if (f == null || !mounted) return;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    final url = await conPreload(
        context, () => BodegaRepo.subirFoto(p.id, bytes),
        texto: 'Subiendo foto…');
    if (!mounted || url == null) return;
    await BodegaRepo.guardarProducto(p.copyWith(fotoUrl: url));
    _cargar();
  }

  // ── CARTA DIGITAL (QR) ─────────────────────────────────────────────────────

  Future<void> _verCarta() async {
    final enlace = SupabaseService.paginaBodega(BodegaRepo.cartaIdDe(_email));
    if (enlace == null) return;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Carta digital de tu bodega 🧾',
                  style:
                      TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 4),
              const Text(
                  'Imprime el QR y pégalo junto a tu Yape: tus clientes ven '
                  'la carta con precios siempre al día. Pagan contigo, como '
                  'siempre.',
                  style: TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: bosque),
                    onPressed: () => launchUrl(Uri.parse('$enlace/qr.png'),
                        mode: LaunchMode.externalApplication),
                    icon: const Icon(Icons.qr_code_2, size: 18),
                    label: const Text('Ver QR (imprimir)'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => launchUrl(Uri.parse(enlace),
                        mode: LaunchMode.externalApplication),
                    icon: const Icon(Icons.visibility_outlined, size: 18),
                    label: const Text('Ver mi carta'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () =>
                        WhatsAppLink.compartir('Mira la carta de mi bodega '
                            '🧃🍺: $enlace'),
                    icon: const Icon(Icons.share, size: 18),
                    label: const Text('Compartir'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: enlace));
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                          content: Text('Enlace copiado.')));
                    },
                    icon: const Icon(Icons.link, size: 18),
                    label: const Text('Copiar enlace'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── BUILD ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mi bodega'),
        actions: [
          IconButton(
            tooltip: 'Carta digital y QR',
            onPressed: _verCarta,
            icon: const Icon(Icons.qr_code_2),
          ),
        ],
      ),
      body: AnchoLectura(
        child: ListenableBuilder(
          listenable: appState,
          builder: (context, _) {
            if (!appState.proActivo) return _vistaPro(context);
            if (_cargando) {
              return const Center(child: CargandoPichangol());
            }
            return RefreshIndicator(
              onRefresh: _cargar,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
                children: [
                  // Pestañas internas estilo chips (Caja / Productos / Reporte).
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final (i, t) in [
                        (0, '🛒 Caja'),
                        (1, '📦 Productos'),
                        (2, '📊 Reporte'),
                        (
                          3,
                          _pendientes == 0
                              ? '🛎️ Pedidos'
                              : '🛎️ Pedidos ($_pendientes)'
                        ),
                        (
                          4,
                          _abiertas == 0
                              ? '📒 Cuentas'
                              : '📒 Cuentas ($_abiertas)'
                        ),
                      ])
                        ChoiceChip(
                          label: Text(t),
                          selected: _tab == i,
                          onSelected: (_) => setState(() => _tab = i),
                        ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  if (_tab == 3)
                    ..._vistaPedidos(context)
                  else if (_tab == 4)
                    ..._vistaCuentas(context)
                  else if (_productos.isEmpty)
                    _vacio(context)
                  else if (_tab == 0)
                    ..._vistaCaja(context)
                  else if (_tab == 1)
                    ..._vistaProductos(context)
                  else
                    ..._vistaReporte(context),
                ],
              ),
            );
          },
        ),
      ),
      bottomNavigationBar: _ticket.isEmpty || _tab != 0
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      padding: const EdgeInsets.symmetric(vertical: 15)),
                  onPressed: _cobrar,
                  child: Text(
                      'Cobrar $_mon ${_totalTicket.toStringAsFixed(2)} · ${_ticket.values.fold(0, (a, b) => a + b)} ítem(s)',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 16)),
                ),
              ),
            ),
      floatingActionButton: !appState.proActivo || _tab != 1
          ? null
          : FloatingActionButton.extended(
              heroTag: 'fab-bodega',
              backgroundColor: lima,
              foregroundColor: Colors.white,
              onPressed: () => _editarProducto(null),
              icon: const Icon(Icons.add),
              label: const Text('Producto'),
            ),
    );
  }

  /// Candado Pro: la bodega es parte de la suscripción del dueño.
  Widget _vistaPro(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('🧃🍺', style: TextStyle(fontSize: 44)),
            const SizedBox(height: 12),
            const Text('Administra tu bodega',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 19)),
            const SizedBox(height: 8),
            const Text(
                'Caja rápida, stock con alertas de reposición, reportes de '
                'venta y la carta digital con QR para tus clientes. Tú '
                'cobras con tu Yape o efectivo, como siempre.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: lima),
              onPressed: () async {
                await exigirPro(context, funcion: 'La bodega');
                if (mounted) setState(() {});
              },
              icon: const Icon(Icons.workspace_premium),
              label: const Text('Activar con Pichangol Pro'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _vacio(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        children: [
          const Text('📦', style: TextStyle(fontSize: 40)),
          const SizedBox(height: 10),
          const Text('Arma tu bodega en 2 minutos',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 6),
          const Text(
              'Agrega tus productos con precio y stock; luego vendes con '
              'un tap desde la Caja.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
          const SizedBox(height: 16),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: lima),
            onPressed: () => _editarProducto(null),
            icon: const Icon(Icons.add),
            label: const Text('Agregar mi primer producto'),
          ),
        ],
      ),
    );
  }

  int get _pendientes =>
      _pedidos.where((p) => p.pendiente && !p.expirado).length;

  int get _abiertas => _cuentas.where((c) => c.abierta).length;

  Future<void> _toggleAceptaPedidos(bool v) async {
    final cfg = (_config ?? ConfigBodega(dueno: _email))
        .copyWith(aceptaPedidos: v);
    setState(() => _config = cfg);
    final ok = await BodegaRepo.guardarConfig(cfg);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('No se pudo guardar. ¿Corriste el SQL de pedidos '
              'de la bodega en Supabase?')));
    }
  }

  Future<void> _editarZonas() async {
    final cfg = _config ?? ConfigBodega(dueno: _email);
    final zonas = List<String>.of(cfg.zonas);
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => StatefulBuilder(
        builder: (bctx, setSB) {
          final bottom = MediaQuery.of(bctx).viewInsets.bottom;
          final nueva = TextEditingController();
          return Padding(
            padding: EdgeInsets.fromLTRB(20, 16, 20, 16 + bottom),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Zonas de entrega 📍',
                    style:
                        TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                const SizedBox(height: 4),
                const Text(
                    'El cliente elige a dónde le llevas su pedido.',
                    style: TextStyle(color: textoTenue, fontSize: 12.5)),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final z in zonas)
                      InputChip(
                        label: Text(z),
                        onDeleted: zonas.length > 1
                            ? () => setSB(() => zonas.remove(z))
                            : null,
                      ),
                  ],
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: nueva,
                  maxLength: 20,
                  textCapitalization: TextCapitalization.words,
                  decoration: InputDecoration(
                    labelText: 'Agregar zona',
                    hintText: 'Ej.: Cancha 3',
                    counterText: '',
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.add_circle, color: bosque),
                      onPressed: () {
                        final z = nueva.text.trim();
                        if (z.isNotEmpty && !zonas.contains(z)) {
                          setSB(() {
                            zonas.add(z);
                            nueva.clear();
                          });
                        }
                      },
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton(
                    onPressed: () => Navigator.pop(bctx, true),
                    child: const Text('Guardar'),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
    if (ok == true) {
      final cfg2 = cfg.copyWith(zonas: zonas);
      setState(() => _config = cfg2);
      await BodegaRepo.guardarConfig(cfg2);
    }
  }

  Future<void> _responderPedido(PedidoBodega p, bool confirmar) async {
    final estado = confirmar ? 'confirmado' : 'rechazado';
    // Candado de concurrencia: responde solo si SIGUE pendiente. Si el
    // cliente lo canceló (o el otro equipo del dueño ya respondió) un
    // segundo antes, el primero gana y aquí solo se refleja.
    final (ok, actual) = await BodegaRepo.cambiarEstadoPedidoSi(p.id, estado,
        desde: 'pendiente');
    if (!mounted) return;
    if (!ok) {
      if (actual == null) return; // error de red: no tocar nada
      setState(() {
        _pedidos = [
          for (final x in _pedidos) x.id == p.id ? x.conEstado(actual) : x,
        ];
      });
      if (actual == 'cancelado') {
        await avisarPichangol(
          context,
          titulo: 'El cliente lo canceló',
          mensaje: 'Este pedido fue cancelado por el cliente antes de que '
              'lo confirmaras. No hay nada que llevar.',
          icono: Icons.remove_shopping_cart_outlined,
        );
      }
      return; // sin push: el que ganó ya avisó lo suyo
    }
    setState(() {
      _pedidos = [
        for (final x in _pedidos) x.id == p.id ? x.conEstado(estado) : x,
      ];
    });
    appState.avisarPedidoBodega(
      email: p.cliente,
      titulo: confirmar
          ? 'Pedido confirmado 🏃'
          : 'Pedido rechazado 😔',
      cuerpo: confirmar
          ? 'Tu pedido (${p.resumen}) va en camino a la ${p.zona}. Pagas al '
              'recibirlo.'
          : 'El local no pudo tomar tu pedido (${p.resumen}). Acércate al '
              'mostrador.',
    );
  }

  /// ENTREGAR Y COBRAR: registra la venta (descuenta stock) con el medio
  /// elegido y marca el pedido entregado. El pedido pre-carga el ticket.
  /// Con cuenta abierta activada, "A la cuenta" anota el consumo y el
  /// cliente paga TODO al retirarse.
  Future<void> _entregarPedido(PedidoBodega p) async {
    // ¿Puede ir a la cuenta? Cliente identificado + toggle activo + tope.
    final cuentaCliente = _cuentas.cast<CuentaBodega?>().firstWhere(
        (c) => c!.abierta && c.cliente == p.cliente,
        orElse: () => null);
    final tope = _config?.topeCuenta ?? 0;
    final cabeEnCuenta = (_config?.permiteCuenta ?? false) &&
        p.cliente.isNotEmpty &&
        (tope <= 0 || (cuentaCliente?.total ?? 0) + p.total <= tope);
    final medio = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                    'Entregado a la ${p.zona} · cobrar ${p.moneda} ${p.total.toStringAsFixed(2)} — ¿cómo pagó?',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
            ListTile(
                leading: const Text('💵', style: TextStyle(fontSize: 22)),
                title: const Text('Efectivo'),
                onTap: () => Navigator.pop(bctx, 'efectivo')),
            ListTile(
                leading: const Text('📱', style: TextStyle(fontSize: 22)),
                title: Text(paisActual.iso == 'PE'
                    ? 'Yape / Plin del local'
                    : 'QR / transferencia del local'),
                onTap: () => Navigator.pop(bctx, 'yape')),
            ListTile(
                leading: const Text('🎁', style: TextStyle(fontSize: 22)),
                title: const Text('Cortesía (no se cobra)'),
                onTap: () => Navigator.pop(bctx, 'cortesia')),
            if (cabeEnCuenta)
              ListTile(
                  leading: const Text('📒', style: TextStyle(fontSize: 22)),
                  title: const Text('A la cuenta (paga al salir)'),
                  subtitle: Text(
                      cuentaCliente == null
                          ? 'Le abre su cuenta en la bodega'
                          : 'Lleva ${cuentaCliente.moneda} ${cuentaCliente.total.toStringAsFixed(2)}',
                      style: const TextStyle(fontSize: 12)),
                  onTap: () => Navigator.pop(bctx, 'cuenta')),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (medio == null || !mounted) return;
    // Candado de concurrencia: RECLAMA el pedido (confirmado → entregado)
    // ANTES de registrar la venta. Si el dueño tiene la bodega abierta en
    // dos equipos, solo UNO cobra — sin esto habría venta y descuento de
    // stock DOBLES por el mismo pedido.
    final (claim, actual) = await BodegaRepo.cambiarEstadoPedidoSi(
        p.id, 'entregado',
        desde: 'confirmado');
    if (!mounted) return;
    if (!claim) {
      if (actual == null) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            backgroundColor: clayOscuro,
            content: Text('Sin conexión: no se pudo registrar. '
                'Vuelve a intentarlo.')));
        return;
      }
      setState(() {
        _pedidos = [
          for (final x in _pedidos) x.id == p.id ? x.conEstado(actual) : x,
        ];
      });
      if (actual == 'entregado') {
        await avisarPichangol(
          context,
          titulo: 'Ya estaba cobrado',
          mensaje: 'Este pedido ya fue entregado y cobrado desde otro '
              'equipo. No se registró una segunda venta.',
          icono: Icons.done_all,
        );
      }
      return;
    }
    final nuevoStock = <String, int>{};
    for (final i in p.items) {
      final prod = _productos
          .cast<ProductoBodega?>()
          .firstWhere((x) => x!.id == i.productoId, orElse: () => null);
      if (prod != null) {
        nuevoStock[prod.id] =
            (prod.stock - i.cantidad) < 0 ? 0 : prod.stock - i.cantidad;
      }
    }
    if (medio == 'cuenta') {
      // A LA CUENTA: stock baja ya, la VENTA se registra al cerrar la
      // cuenta (así el reporte no duplica).
      final res = await conPreload(
          context,
          () => BodegaRepo.anotarACuenta(
                dueno: _email,
                cliente: p.cliente,
                clienteNombre: p.clienteNombre,
                items: p.items,
                moneda: p.moneda,
              ),
          texto: 'Anotando…');
      if (!mounted) return;
      if (res == null) {
        await BodegaRepo.actualizarEstadoPedido(p.id, 'confirmado');
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            backgroundColor: clayOscuro,
            content: Text('No se pudo anotar a la cuenta. '
                'Vuelve a intentarlo.')));
        return;
      }
      await BodegaRepo.actualizarStock(nuevoStock);
      setState(() {
        _pedidos = [
          for (final x in _pedidos)
            x.id == p.id ? x.conEstado('entregado') : x,
        ];
        _productos = [
          for (final x in _productos)
            nuevoStock.containsKey(x.id)
                ? x.copyWith(stock: nuevoStock[x.id])
                : x,
        ];
        _cuentas = _cuentas.any((c) => c.id == res.id)
            ? [for (final c in _cuentas) c.id == res.id ? res : c]
            : [res, ..._cuentas];
      });
      appState.avisarPedidoBodega(
        email: p.cliente,
        titulo: 'Anotado en tu cuenta 📒',
        cuerpo: 'Tu pedido (${p.resumen}) quedó en tu cuenta. Llevas '
            '${res.moneda} ${res.total.toStringAsFixed(2)}; pagas al salir.',
      );
      return;
    }
    final venta = VentaBodega(
      id: 'bv_${DateTime.now().microsecondsSinceEpoch}',
      dueno: _email,
      items: p.items,
      total: medio == 'cortesia' ? 0 : p.total,
      medioPago: medio,
      creado: DateTime.now(),
    );
    final ok = await conPreload(
        context, () => BodegaRepo.registrarVenta(venta, nuevoStock),
        texto: 'Registrando…');
    if (!mounted) return;
    if (!ok) {
      // La venta no entró: devuelve el pedido a "confirmado" (best-effort)
      // para que se pueda volver a cobrar, y avisa.
      await BodegaRepo.actualizarEstadoPedido(p.id, 'confirmado');
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: clayOscuro,
          content: Text('No se pudo registrar la venta. '
              'Vuelve a intentarlo.')));
      return;
    }
    setState(() {
      _ventas = [venta, ..._ventas];
      _productos = [
        for (final x in _productos)
          nuevoStock.containsKey(x.id)
              ? x.copyWith(stock: nuevoStock[x.id])
              : x,
      ];
      _pedidos = [
        for (final x in _pedidos)
          x.id == p.id ? x.conEstado('entregado') : x,
      ];
    });
    appState.avisarPedidoBodega(
      email: p.cliente,
      titulo: 'Pedido entregado ✅',
      cuerpo: '¡Que lo disfrutes! Gracias por pedir en ${'la bodega'}.',
    );
  }

  List<Widget> _vistaPedidos(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cfg = _config ?? ConfigBodega(dueno: _email);
    final orden = [..._pedidos]..sort((a, b) {
        int peso(PedidoBodega p) =>
            p.pendiente ? 0 : p.confirmado ? 1 : 2;
        final d = peso(a) - peso(b);
        return d != 0 ? d : b.creado.compareTo(a.creado);
      });
    String hace(DateTime d) {
      final m = DateTime.now().difference(d).inMinutes;
      return m < 1 ? 'ahora' : m < 60 ? 'hace $m min' : 'hace ${m ~/ 60} h';
    }

    return [
      // Toggle + zonas (config del dueño).
      Container(
        padding: const EdgeInsets.fromLTRB(14, 4, 6, 4),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: trazo),
        ),
        child: Row(
          children: [
            Expanded(
              child: SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Acepto pedidos a la cancha',
                    style: TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 14.5)),
                subtitle: const Text(
                    'Tus clientes piden desde su cancha y tú confirmas.',
                    style: TextStyle(fontSize: 12)),
                value: cfg.aceptaPedidos,
                onChanged: _toggleAceptaPedidos,
              ),
            ),
            IconButton(
              tooltip: 'Zonas de entrega',
              onPressed: _editarZonas,
              icon: const Icon(Icons.edit_location_alt_outlined,
                  color: bosque),
            ),
          ],
        ),
      ),
      const SizedBox(height: 12),
      if (orden.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 30),
          child: Center(
            child: Text('Sin pedidos aún. Activa el switch y tus clientes '
                'podrán pedir desde su cancha 🍺',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
          ),
        ),
      for (final p in orden)
        Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: p.pendiente && !p.expirado ? limaSuave : cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
                color: p.pendiente && !p.expirado ? lima : trazo),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('${p.resumen} → ${p.zona}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                  Text('${p.moneda} ${p.total.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900, color: bosque)),
                ],
              ),
              const SizedBox(height: 2),
              Text('${p.clienteNombre} · ${hace(p.creado)}',
                  style:
                      const TextStyle(color: textoTenue, fontSize: 12.5)),
              const SizedBox(height: 10),
              if (p.pendiente)
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        style:
                            FilledButton.styleFrom(backgroundColor: lima),
                        onPressed: () => _responderPedido(p, true),
                        child: const Text('Confirmar ✅'),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: () => _responderPedido(p, false),
                      child: const Text('Rechazar',
                          style: TextStyle(color: Colors.redAccent)),
                    ),
                  ],
                )
              else if (p.confirmado)
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: bosque),
                    onPressed: () => _entregarPedido(p),
                    icon: const Icon(Icons.check_circle_outline, size: 18),
                    label: const Text('Entregado · cobrar y descontar stock'),
                  ),
                )
              else
                Text(
                    switch (p.estado) {
                      'entregado' => 'Entregado ✅ (venta registrada)',
                      'rechazado' => 'Rechazado',
                      'cancelado' => 'Cancelado por el cliente',
                      _ => 'Sin respuesta (expiró)',
                    },
                    style: const TextStyle(
                        color: textoTenue,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600)),
            ],
          ),
        ),
    ];
  }

  // ── CUENTA ABIERTA ("apúntamelo, pago al salir") ───────────────────────────

  Future<void> _togglePermiteCuenta(bool v) async {
    final cfg =
        (_config ?? ConfigBodega(dueno: _email)).copyWith(permiteCuenta: v);
    setState(() => _config = cfg);
    await BodegaRepo.guardarConfig(cfg);
    // Verifica que persistió (si falta correr el SQL de cuentas, el guardado
    // cae al modo sin columnas nuevas y el toggle se perdería en silencio).
    final relee = await BodegaRepo.fetchConfig(_email);
    if (!mounted) return;
    if (relee.permiteCuenta != v) {
      setState(() => _config = relee);
      await avisarPichangol(
        context,
        titulo: 'Falta actualizar la base',
        mensaje: 'Para activar la cuenta abierta hay que correr el script '
            'supabase_bodega_cuentas.sql en Supabase (avísale a tu admin).',
        icono: Icons.storage_outlined,
      );
    }
  }

  Future<void> _ponerTope(double v) async {
    final cfg =
        (_config ?? ConfigBodega(dueno: _email)).copyWith(topeCuenta: v);
    setState(() => _config = cfg);
    await BodegaRepo.guardarConfig(cfg);
  }

  /// CIERRA la cuenta: cobra TODO junto y recién ahí registra UNA venta en
  /// el reporte (el stock ya bajó al entregar cada consumo). Candado: con
  /// dos equipos, solo uno cierra.
  Future<void> _cerrarCuenta(CuentaBodega c) async {
    final medio = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (bctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                    'Cerrar la cuenta de ${c.clienteNombre} · cobrar '
                    '${c.moneda} ${c.total.toStringAsFixed(2)} — ¿cómo pagó?',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 16)),
              ),
            ),
            ListTile(
                leading: const Text('💵', style: TextStyle(fontSize: 22)),
                title: const Text('Efectivo'),
                onTap: () => Navigator.pop(bctx, 'efectivo')),
            ListTile(
                leading: const Text('📱', style: TextStyle(fontSize: 22)),
                title: Text(paisActual.iso == 'PE'
                    ? 'Yape / Plin del local'
                    : 'QR / transferencia del local'),
                onTap: () => Navigator.pop(bctx, 'yape')),
            ListTile(
                leading: const Text('🎁', style: TextStyle(fontSize: 22)),
                title: const Text('Cortesía (no se cobra)'),
                onTap: () => Navigator.pop(bctx, 'cortesia')),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (medio == null || !mounted) return;
    final gano = await BodegaRepo.cerrarCuentaSi(c.id, medio);
    if (!mounted) return;
    if (!gano) {
      await avisarPichangol(
        context,
        titulo: 'Ya estaba cerrada',
        mensaje: 'Esta cuenta ya fue cerrada desde otro equipo. '
            'No se cobró dos veces.',
        icono: Icons.done_all,
      );
      _cargar();
      return;
    }
    final venta = VentaBodega(
      id: 'bv_${DateTime.now().microsecondsSinceEpoch}',
      dueno: _email,
      items: c.items,
      total: medio == 'cortesia' ? 0 : c.total,
      medioPago: medio,
      creado: DateTime.now(),
    );
    // Stock YA descontado al anotar cada consumo → mapa vacío.
    final ok = await conPreload(
        context, () => BodegaRepo.registrarVenta(venta, const {}),
        texto: 'Registrando…');
    if (!mounted) return;
    final cerrada = CuentaBodega(
      id: c.id,
      dueno: c.dueno,
      cliente: c.cliente,
      clienteNombre: c.clienteNombre,
      items: c.items,
      total: c.total,
      moneda: c.moneda,
      estado: 'cerrada',
      medioPago: medio,
      creado: c.creado,
    );
    setState(() {
      if (ok) _ventas = [venta, ..._ventas];
      _cuentas = [for (final x in _cuentas) x.id == c.id ? cerrada : x];
    });
    if (c.cliente.isNotEmpty) {
      appState.avisarPedidoBodega(
        email: c.cliente,
        titulo: 'Cuenta cerrada ✅',
        cuerpo: medio == 'cortesia'
            ? 'Tu cuenta quedó como cortesía del local. ¡Gracias!'
            : 'Pagaste ${c.moneda} ${c.total.toStringAsFixed(2)}. '
                '¡Gracias, vuelve pronto!',
      );
    }
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: ok ? bosque : clayOscuro,
        content: Text(ok
            ? 'Cuenta cerrada y venta registrada ✅'
            : 'Cuenta cerrada, pero la venta no entró al reporte '
                '(sin conexión). Revisa el reporte más tarde.')));
  }

  List<Widget> _vistaCuentas(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cfg = _config ?? ConfigBodega(dueno: _email);
    String hace(DateTime d) {
      final m = DateTime.now().difference(d).inMinutes;
      if (m < 60) return 'hace $m min';
      final h = m ~/ 60;
      if (h < 24) return 'hace $h h';
      return 'hace ${h ~/ 24} día(s)';
    }

    final abiertas = [for (final c in _cuentas) if (c.abierta) c];
    final cerradas = [for (final c in _cuentas) if (!c.abierta) c];
    return [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: trazo),
        ),
        child: Column(
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Permito cuenta abierta 📒',
                  style:
                      TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5)),
              subtitle: const Text(
                  'El cliente identificado consume y paga todo al retirarse. '
                  'La abres con "A la cuenta" al entregar o cobrar.',
                  style: TextStyle(fontSize: 12)),
              value: cfg.permiteCuenta,
              onChanged: _togglePermiteCuenta,
            ),
            if (cfg.permiteCuenta) ...[
              const Align(
                alignment: Alignment.centerLeft,
                child: Text('Tope por cuenta (pasado el tope, se cobra al '
                    'entregar)',
                    style: TextStyle(fontSize: 12.5, color: textoTenue)),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final v in const [50.0, 100.0, 200.0, 300.0, 0.0])
                      ChoiceChip(
                        label: Text(v == 0
                            ? 'Sin tope'
                            : '$_mon ${v.toStringAsFixed(0)}'),
                        selected: cfg.topeCuenta == v,
                        onSelected: (_) => _ponerTope(v),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
            ],
          ],
        ),
      ),
      const SizedBox(height: 12),
      if (abiertas.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 26),
          child: Center(
            child: Text(
                'Sin cuentas abiertas. Al entregar un pedido (o cobrar en '
                'caja) elige "A la cuenta 📒" y el cliente paga al salir.',
                textAlign: TextAlign.center,
                style: TextStyle(color: textoTenue)),
          ),
        ),
      for (final c in abiertas)
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
                  Expanded(
                    child: Text('📒 ${c.clienteNombre}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                  Text('${c.moneda} ${c.total.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900, color: bosque)),
                ],
              ),
              const SizedBox(height: 2),
              Text(c.resumen,
                  style: const TextStyle(fontSize: 12.5)),
              Text('Abierta ${hace(c.creado)}',
                  style:
                      const TextStyle(color: textoTenue, fontSize: 12)),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: bosque),
                  onPressed: () => _cerrarCuenta(c),
                  icon: const Icon(Icons.point_of_sale, size: 18),
                  label: const Text('Cobrar y cerrar cuenta'),
                ),
              ),
            ],
          ),
        ),
      if (cerradas.isNotEmpty) ...[
        const SizedBox(height: 6),
        const Text('Cerradas (últimos 30 días)',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
        const SizedBox(height: 8),
        for (final c in cerradas)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: cs.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: trazo),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                      '${c.clienteNombre} · ${c.resumen}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12.5)),
                ),
                Text(
                    c.medioPago == 'cortesia'
                        ? 'Cortesía'
                        : '${c.moneda} ${c.total.toStringAsFixed(2)}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 12.5,
                        color: textoTenue)),
              ],
            ),
          ),
      ],
    ];
  }

  // CAJA: un card por producto; tap = +1, botón "-" resta.
  List<Widget> _vistaCaja(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Filtro tipo POS (referencia Comerza, el POS de EBIM): búsqueda +
    // categorías arriba, y el TICKET siempre visible con sus líneas.
    final q = _busquedaCaja.trim().toLowerCase();
    final cats = [
      'Todo',
      for (final c in _categorias)
        if (_productos.any((p) => p.categoria == c)) c,
    ];
    final filtrados = [
      for (final p in _productos)
        if ((_catCaja == 'Todo' || p.categoria == _catCaja) &&
            (q.isEmpty || p.nombre.toLowerCase().contains(q)))
          p,
    ];
    return [
      // Búsqueda (texto libre permitido: es un buscador).
      TextField(
        onChanged: (v) => setState(() => _busquedaCaja = v),
        decoration: InputDecoration(
          isDense: true,
          hintText: 'Buscar producto…',
          prefixIcon: const Icon(Icons.search, size: 20),
          suffixIcon: _busquedaCaja.isEmpty
              ? null
              : IconButton(
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: () => setState(() => _busquedaCaja = ''),
                ),
          filled: true,
          fillColor: cs.surface,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(999),
              borderSide: const BorderSide(color: trazo)),
          enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(999),
              borderSide: const BorderSide(color: trazo)),
        ),
      ),
      const SizedBox(height: 10),
      if (cats.length > 2)
        SizedBox(
          height: 38,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: cats.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (_, i) => ChoiceChip(
              label: Text(cats[i]),
              selected: _catCaja == cats[i],
              onSelected: (_) => setState(() => _catCaja = cats[i]),
            ),
          ),
        ),
      if (cats.length > 2) const SizedBox(height: 10),
      // TICKET visible con sus líneas (editar cantidad / quitar / vaciar),
      // total grande y Cobrar — el corazón de un POS.
      if (_ticket.isNotEmpty) ...[
        Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: lima, width: 1.4),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                        'Ticket · ${_ticket.length} línea(s)',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 14.5)),
                  ),
                  TextButton(
                    onPressed: () => setState(_ticket.clear),
                    style: TextButton.styleFrom(
                        padding:
                            const EdgeInsets.symmetric(horizontal: 8),
                        foregroundColor: textoTenue),
                    child: const Text('Vaciar'),
                  ),
                ],
              ),
              for (final e in _ticket.entries.toList())
                if (_productos.any((p) => p.id == e.key))
                  Builder(builder: (_) {
                    final p =
                        _productos.firstWhere((x) => x.id == e.key);
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment:
                                  CrossAxisAlignment.start,
                              children: [
                                Text(p.nombre,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13.5)),
                                Text(
                                    '$_mon ${p.precio.toStringAsFixed(2)} c/u',
                                    style: const TextStyle(
                                        color: textoTenue,
                                        fontSize: 11.5)),
                              ],
                            ),
                          ),
                          GestureDetector(
                            onTap: () => _sumar(p, -1),
                            child: const Icon(Icons.remove_circle_outline,
                                size: 22, color: clayOscuro),
                          ),
                          SizedBox(
                            width: 30,
                            child: Text('${e.value}',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w900)),
                          ),
                          GestureDetector(
                            onTap: () => _sumar(p, 1),
                            child: const Icon(Icons.add_circle_outline,
                                size: 22, color: bosque),
                          ),
                          SizedBox(
                            width: 74,
                            child: Text(
                                '$_mon ${(p.precio * e.value).toStringAsFixed(2)}',
                                textAlign: TextAlign.right,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 13.5)),
                          ),
                          const SizedBox(width: 4),
                          GestureDetector(
                            onTap: () =>
                                setState(() => _ticket.remove(p.id)),
                            child: const Icon(Icons.close,
                                size: 16, color: textoTenue),
                          ),
                        ],
                      ),
                    );
                  }),
              const Divider(height: 18),
              Row(
                children: [
                  const Expanded(
                    child: Text('TOTAL',
                        style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 13,
                            color: textoTenue)),
                  ),
                  Text('$_mon ${_totalTicket.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900, fontSize: 21)),
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      padding:
                          const EdgeInsets.symmetric(vertical: 13)),
                  onPressed: _cobrar,
                  child: const Text('Cobrar',
                      style: TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 15)),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
      ] else ...[
        const Text('Toca un producto para sumarlo al ticket.',
            style: TextStyle(color: textoTenue, fontSize: 12.5)),
        const SizedBox(height: 10),
      ],
      if (filtrados.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 26),
          child: Center(
            child: Text('Sin resultados con ese filtro.',
                style: TextStyle(color: textoTenue)),
          ),
        ),
      GridView.count(
        crossAxisCount: MediaQuery.of(context).size.width >= 480 ? 3 : 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 10,
        crossAxisSpacing: 10,
        childAspectRatio: 1.35,
        children: [
          for (final p in filtrados)
            InkWell(
              onTap: p.stock <= 0 ? null : () => _sumar(p, 1),
              borderRadius: BorderRadius.circular(16),
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: (_ticket[p.id] ?? 0) > 0 ? limaSuave : cs.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                      color: (_ticket[p.id] ?? 0) > 0 ? lima : trazo,
                      width: (_ticket[p.id] ?? 0) > 0 ? 1.6 : 1),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(p.emoji,
                              style: const TextStyle(fontSize: 20)),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(p.nombre,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: p.stock <= 0
                                        ? Colors.grey
                                        : cs.onSurface)),
                          ),
                        ],
                      ),
                    ),
                    Text('$_mon ${p.precio.toStringAsFixed(2)}',
                        style: const TextStyle(
                            color: bosque, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                              p.stock <= 0
                                  ? 'Agotado'
                                  : p.stockBajo
                                      ? '¡Quedan ${p.stock}!'
                                      : 'Stock: ${p.stock}',
                              style: TextStyle(
                                  fontSize: 11.5,
                                  fontWeight: FontWeight.w600,
                                  color: p.stock <= 0 || p.stockBajo
                                      ? clayOscuro
                                      : textoTenue)),
                        ),
                        if ((_ticket[p.id] ?? 0) > 0) ...[
                          GestureDetector(
                            onTap: () => _sumar(p, -1),
                            child: const Icon(Icons.remove_circle,
                                size: 22, color: clayOscuro),
                          ),
                          Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 6),
                            child: Text('${_ticket[p.id]}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w900)),
                          ),
                          const Icon(Icons.add_circle,
                              size: 22, color: bosque),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    ];
  }

  List<Widget> _vistaProductos(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return [
      for (final p in _productos)
        Container(
          margin: const EdgeInsets.only(bottom: 8),
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: trazo),
          ),
          child: ListTile(
            onTap: () => _editarProducto(p),
            leading: GestureDetector(
              onTap: () => _cambiarFoto(p),
              // Cascada: foto real del dueño > packshot IA genérico > emoji.
              // La mini cámara indica que puede subir SU foto cuando quiera.
              child: p.fotoUrl != null && p.fotoUrl!.isNotEmpty
                  ? ImagenProductoBodega(producto: p)
                  : Stack(
                      clipBehavior: Clip.none,
                      children: [
                        ImagenProductoBodega(producto: p),
                        const Positioned(
                          right: -4,
                          bottom: -4,
                          child: CircleAvatar(
                            radius: 8,
                            backgroundColor: bosque,
                            child: Icon(Icons.add_a_photo_outlined,
                                size: 9, color: Colors.white),
                          ),
                        ),
                      ],
                    ),
            ),
            title: Text(p.nombre,
                style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(
                '${p.categoria} · $_mon ${p.precio.toStringAsFixed(2)}',
                style: const TextStyle(fontSize: 12.5)),
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('${p.stock}',
                    style: TextStyle(
                        fontWeight: FontWeight.w900,
                        fontSize: 16,
                        color: p.stockBajo ? clayOscuro : bosque)),
                Text(p.stockBajo ? '¡reponer!' : 'en stock',
                    style: TextStyle(
                        fontSize: 10.5,
                        color: p.stockBajo ? clayOscuro : textoTenue)),
              ],
            ),
          ),
        ),
    ];
  }

  List<Widget> _vistaReporte(BuildContext context) {
    final hoy = DateTime.now();
    bool esHoy(DateTime d) =>
        d.year == hoy.year && d.month == hoy.month && d.day == hoy.day;
    final semana = hoy.subtract(const Duration(days: 7));
    final ventasHoy = _ventas.where((v) => esHoy(v.creado)).toList();
    final ventas7 = _ventas.where((v) => v.creado.isAfter(semana)).toList();
    final totalHoy = ventasHoy.fold(0.0, (a, v) => a + v.total);
    final total7 = ventas7.fold(0.0, (a, v) => a + v.total);
    // Top productos por unidades (7 días).
    final unidades = <String, int>{};
    for (final v in ventas7) {
      for (final i in v.items) {
        unidades[i.nombre] = (unidades[i.nombre] ?? 0) + i.cantidad;
      }
    }
    final top = unidades.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final bajos = _productos.where((p) => p.stockBajo).toList();
    final valorizado =
        _productos.fold(0.0, (a, p) => a + p.stock * p.precio);
    final cs = Theme.of(context).colorScheme;

    Widget kpi(String eti, String val) => Expanded(
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: cs.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: trazo),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(eti,
                    style:
                        const TextStyle(color: textoTenue, fontSize: 12)),
                const SizedBox(height: 4),
                Text(val,
                    style: const TextStyle(
                        fontWeight: FontWeight.w900, fontSize: 17)),
              ],
            ),
          ),
        );

    return [
      Row(children: [
        kpi('Hoy', '$_mon ${totalHoy.toStringAsFixed(2)}'),
        const SizedBox(width: 10),
        kpi('Últimos 7 días', '$_mon ${total7.toStringAsFixed(2)}'),
      ]),
      const SizedBox(height: 10),
      Row(children: [
        kpi('Ventas hoy', '${ventasHoy.length}'),
        const SizedBox(width: 10),
        kpi('Stock valorizado', '$_mon ${valorizado.toStringAsFixed(2)}'),
      ]),
      if (bajos.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('⚠️ Para reponer',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
        const SizedBox(height: 6),
        for (final p in bajos)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('• ${p.nombre}: quedan ${p.stock}',
                style: const TextStyle(color: clayOscuro)),
          ),
      ],
      if (top.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('🏆 Lo más vendido (7 días)',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
        const SizedBox(height: 6),
        for (final e in top.take(5))
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('• ${e.key} — ${e.value} und.'),
          ),
      ],
      if (_ventas.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 30),
          child: Text('Aún no registras ventas. Ve a la Caja y prueba una.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenue)),
        ),
    ];
  }
}
