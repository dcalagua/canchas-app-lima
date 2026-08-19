import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/candado_pro.dart';
import '../widgets/vacio_airbnb.dart';
import 'chat_screen.dart';
import 'reserva_manual_screen.dart';

/// BASE DE CLIENTES del dueño (CRM ligero) — refuerzo del panel de gestión al
/// nivel SaaS de la competencia. No inventa datos ni pide SQL nuevo: agrega las
/// reservas reales de las canchas del dueño en una ficha por cliente (quién
/// reserva, cuántas veces, cuánto gastó / debe, última visita, no-shows) con
/// acceso directo al chat. Es el "cuaderno de clientes" del club, digitalizado.
class ClientesScreen extends StatefulWidget {
  const ClientesScreen({super.key});

  @override
  State<ClientesScreen> createState() => _ClientesScreenState();
}

enum _Orden { frecuentes, gasto, recientes }

/// Segmentos de cliente (estilo CRM Playtomic/MindBody): clave técnica + rótulo.
/// 'todos' es el neutro. Un cliente puede pertenecer a varios; el filtro pide
/// pertenencia y el badge de la tarjeta muestra el más accionable.
const _segmentos = <(String, String)>[
  ('todos', 'Todos'),
  ('vip', 'VIP'),
  ('recurrente', 'Recurrentes'),
  ('nuevo', 'Nuevos'),
  ('riesgo', 'En riesgo'),
  ('moroso', 'Deudores'),
];

/// Días sin volver a partir de los cuales un cliente recurrente pasa a "en
/// riesgo" (churn). Umbral conservador para un negocio de canchas.
const int _diasRiesgo = 30;

class _ClientesScreenState extends State<ClientesScreen> {
  _Orden _orden = _Orden.frecuentes;
  String _seg = 'todos';
  String _busqueda = '';

  @override
  void initState() {
    super.initState();
    // Insignia de verificado + PERFIL (foto real del cliente). Resuelve cada
    // reserva a la cancha del dueño (tolerante a ids duplicados del local).
    final emails = appState.reservas
        .where((r) => appState.miCanchaDeReserva(r.canchaId) != null)
        .map((r) => r.usuario)
        .where((e) => e.trim().isNotEmpty)
        .toList();
    appState.sincronizarVerificados(emails);
    appState.cargarPerfiles(emails);
  }

  /// Agrega las reservas de las canchas del dueño en una ficha por cliente.
  /// [aplicarBusqueda] false = universo completo (para los KPIs de arriba).
  List<_Cliente> _clientes({bool aplicarBusqueda = true}) {
    final map = <String, _Cliente>{};
    for (final r in appState.reservas) {
      if (appState.miCanchaDeReserva(r.canchaId) == null) continue;
      final email = r.usuario.trim().toLowerCase();
      final nombre = r.jugador.trim();
      // Clave estable: por correo si lo hay; si no, por nombre (walk-in).
      final key = email.isNotEmpty ? email : 'n:${nombre.toLowerCase()}';
      if (email.isEmpty && nombre.isEmpty) continue;
      final cl = map.putIfAbsent(key, () => _Cliente(email: email)..clave = key);
      if (cl.nombre.isEmpty && nombre.isNotEmpty) cl.nombre = nombre;
      if (cl.telefono.isEmpty && r.telefono.isNotEmpty) {
        cl.telefono = r.telefono;
      }
      if (r.nivel.isNotEmpty) cl.nivel = r.nivel;
      if (r.moneda.isNotEmpty) cl.moneda = r.monedaSimbolo;
      cl.reservas++;
      if (r.estado == EstadoReserva.noShow) {
        cl.noShows++;
      } else if (r.pagado) {
        cl.gastado += r.totalConExtras;
      } else {
        cl.porCobrar += r.totalConExtras;
      }
      if (r.fecha.isNotEmpty) {
        if (cl.ultima.isEmpty || r.fecha.compareTo(cl.ultima) > 0) {
          cl.ultima = r.fecha;
        }
        if (cl.primera.isEmpty || r.fecha.compareTo(cl.primera) < 0) {
          cl.primera = r.fecha;
        }
      }
    }
    var lista = map.values.toList();
    // Búsqueda por nombre o correo.
    final q = aplicarBusqueda ? _busqueda.trim().toLowerCase() : '';
    if (q.isNotEmpty) {
      lista = lista
          .where((c) =>
              c.nombreVisible.toLowerCase().contains(q) ||
              c.email.contains(q))
          .toList();
    }
    lista.sort((a, b) {
      switch (_orden) {
        case _Orden.gasto:
          return b.gastado.compareTo(a.gastado);
        case _Orden.recientes:
          return b.ultima.compareTo(a.ultima);
        case _Orden.frecuentes:
          final byRes = b.reservas.compareTo(a.reservas);
          return byRes != 0 ? byRes : b.gastado.compareTo(a.gastado);
      }
    });
    return lista;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Base de clientes')),
      body: AnchoLectura(child: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          // KPIs y segmentos sobre el universo COMPLETO (sin filtro de búsqueda).
          final total = _clientes(aplicarBusqueda: false);
          final recurrentes = total.where((c) => c.reservas >= 2).length;
          final mesActual = _mesActualIso();
          final nuevos =
              total.where((c) => c.primera.startsWith(mesActual)).length;
          final maxGasto =
              total.fold<double>(0, (m, c) => c.gastado > m ? c.gastado : m);
          int cuentaSeg(String seg) => seg == 'todos'
              ? total.length
              : total
                  .where((c) => c.segmentos(maxGasto, mesActual).contains(seg))
                  .length;

          // Lista visible: búsqueda + filtro de segmento.
          var todos = _clientes();
          if (_seg != 'todos') {
            todos = todos
                .where((c) => c.segmentos(maxGasto, mesActual).contains(_seg))
                .toList();
          }

          return Column(
            children: [
              _KpiFila(
                total: total.length,
                recurrentes: recurrentes,
                nuevos: nuevos,
              ),
              // Segmentos (chips con conteo): filtra a quién atender —VIP,
              // recurrentes, nuevos, EN RIESGO (churn) y deudores.
              SizedBox(
                height: 40,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  children: [
                    for (final (clave, _) in _segmentos)
                      _SegChip(
                        seg: clave,
                        n: cuentaSeg(clave),
                        activo: _seg == clave,
                        onTap: () => setState(() => _seg = clave),
                      ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: TextField(
                  onChanged: (v) => setState(() => _busqueda = v),
                  decoration: InputDecoration(
                    hintText: 'Buscar cliente…',
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    filled: true,
                    fillColor: Theme.of(context).colorScheme.surface,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    _OrdenChip(
                        texto: 'Frecuentes',
                        activo: _orden == _Orden.frecuentes,
                        onTap: () =>
                            setState(() => _orden = _Orden.frecuentes)),
                    _OrdenChip(
                        texto: 'Mayor gasto',
                        activo: _orden == _Orden.gasto,
                        onTap: () => setState(() => _orden = _Orden.gasto)),
                    _OrdenChip(
                        texto: 'Recientes',
                        activo: _orden == _Orden.recientes,
                        onTap: () =>
                            setState(() => _orden = _Orden.recientes)),
                  ],
                ),
              ),
              const SizedBox(height: 4),
              Expanded(
                child: todos.isEmpty
                    ? _Vacio(hayBusqueda: _busqueda.trim().isNotEmpty)
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                        itemCount: todos.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (_, i) => _ClienteCard(
                          cliente: todos[i],
                          badge: todos[i].badge(maxGasto, mesActual),
                        ),
                      ),
              ),
            ],
          );
        },
      )),
    );
  }

  static String _mesActualIso() {
    final d = DateTime.now();
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}';
  }
}

/// Ficha agregada de un cliente (derivada de sus reservas).
class _Cliente {
  _Cliente({required this.email});
  final String email;
  String clave = ''; // clave de agregación (correo o 'n:nombre'); para notas
  String nombre = '';
  String telefono = '';
  String nivel = '';
  String moneda = 'S/';
  int reservas = 0;
  double gastado = 0; // caja real (pagadas)
  double porCobrar = 0; // activas sin pagar
  int noShows = 0;
  String ultima = '';
  String primera = '';

  String get nombreVisible {
    if (nombre.isNotEmpty) return nombre;
    if (email.isNotEmpty) return email.split('@').first;
    return 'Cliente';
  }

  String get inicial {
    final n = nombreVisible.trim();
    return n.isEmpty ? '?' : n[0].toUpperCase();
  }

  /// Días desde la última visita (grande si nunca vino), para detectar churn.
  int get diasDesdeUltima {
    if (ultima.isEmpty) return 1 << 30;
    final d = DateTime.tryParse(ultima);
    if (d == null) return 1 << 30;
    final hoy = DateTime.now();
    return DateTime(hoy.year, hoy.month, hoy.day)
        .difference(DateTime(d.year, d.month, d.day))
        .inDays;
  }

  /// Segmentos a los que pertenece. [maxGasto] da el umbral VIP relativo (top
  /// gasto del universo) y [mesActual] ('YYYY-MM') define a los nuevos.
  Set<String> segmentos(double maxGasto, String mesActual) {
    final s = <String>{};
    if (reservas >= 2) s.add('recurrente');
    if (primera.startsWith(mesActual)) s.add('nuevo');
    if (reservas >= 3 && maxGasto > 0 && gastado >= 0.6 * maxGasto) {
      s.add('vip');
    }
    if (porCobrar > 0) s.add('moroso');
    if (reservas >= 2 && diasDesdeUltima >= _diasRiesgo) s.add('riesgo');
    return s;
  }

  /// Segmento MÁS accionable para el badge de la tarjeta (deudor/riesgo primero).
  String? badge(double maxGasto, String mesActual) {
    final s = segmentos(maxGasto, mesActual);
    for (final k in ['moroso', 'riesgo', 'vip', 'nuevo']) {
      if (s.contains(k)) return k;
    }
    return null;
  }
}

/// Color y rótulo de cada segmento (para chips y badges).
({Color color, String label}) _segEstilo(String seg) {
  switch (seg) {
    case 'vip':
      return (color: amarillo, label: 'VIP');
    case 'recurrente':
      return (color: teal, label: 'Recurrente');
    case 'nuevo':
      return (color: lima, label: 'Nuevo');
    case 'riesgo':
      return (color: naranja, label: 'En riesgo');
    case 'moroso':
      return (color: clayOscuro, label: 'Debe');
    default:
      return (color: bosque, label: 'Todos');
  }
}

class _KpiFila extends StatelessWidget {
  const _KpiFila(
      {required this.total, required this.recurrentes, required this.nuevos});
  final int total;
  final int recurrentes;
  final int nuevos;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
      child: Row(
        children: [
          // Colores VISIBLES en claro y oscuro (no charcoal, que se pierde en
          // fondo negro).
          _Kpi(valor: '$total', label: 'Clientes', color: cs.primary),
          const SizedBox(width: 10),
          _Kpi(valor: '$recurrentes', label: 'Recurrentes', color: teal),
          const SizedBox(width: 10),
          _Kpi(valor: '$nuevos', label: 'Nuevos (mes)', color: amarillo),
        ],
      ),
    );
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({required this.valor, required this.label, required this.color});
  final String valor;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFEEEAE0)),
          boxShadow: const [
            BoxShadow(
                color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 3)),
          ],
        ),
        child: Column(
          children: [
            Text(valor,
                style: TextStyle(
                    fontSize: 22, fontWeight: FontWeight.w800, color: color)),
            const SizedBox(height: 2),
            Text(label,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    color: textoTenueDe(context))),
          ],
        ),
      ),
    );
  }
}

/// Chip de SEGMENTO (con conteo). Estilo Airbnb: transparente con borde; al
/// activarse se tiñe con el color del segmento.
class _SegChip extends StatelessWidget {
  const _SegChip(
      {required this.seg,
      required this.n,
      required this.activo,
      required this.onTap});
  final String seg;
  final int n;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final e = _segEstilo(seg);
    final color = seg == 'todos' ? Theme.of(context).colorScheme.primary : e.color;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 3),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: activo ? color.withOpacity(0.16) : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
                color:
                    activo ? color : textoTenueDe(context).withOpacity(0.4)),
          ),
          child: Text('${e.label} · $n',
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: activo ? FontWeight.w700 : FontWeight.w500,
                  color: activo ? color : textoTenueDe(context))),
        ),
      ),
    );
  }
}

/// Badge de esquina del segmento más accionable de un cliente (VIP, En riesgo…).
class _BadgeSeg extends StatelessWidget {
  const _BadgeSeg({required this.seg});
  final String seg;

  @override
  Widget build(BuildContext context) {
    final e = _segEstilo(seg);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: e.color.withOpacity(0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(e.label,
          style: TextStyle(
              color: e.color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

class _OrdenChip extends StatelessWidget {
  const _OrdenChip(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Theme-aware (funciona en claro y oscuro): pastilla transparente con borde;
    // al activarse se tiñe con el acento. Nada de blanco fijo ni charcoal.
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: activo ? cs.primary.withOpacity(0.15) : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
                color: activo
                    ? cs.primary
                    : textoTenueDe(context).withOpacity(0.4)),
          ),
          child: Text(texto,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: activo ? FontWeight.w700 : FontWeight.w500,
                  color: activo ? cs.primary : textoTenueDe(context))),
        ),
      ),
    );
  }
}

class _ClienteCard extends StatelessWidget {
  const _ClienteCard({required this.cliente, this.badge});
  final _Cliente cliente;

  /// Segmento más accionable (badge de esquina), o null.
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final verificado =
        cliente.email.isNotEmpty && appState.estaVerificado(cliente.email);
    final tieneNota = appState.notaCliente(cliente.clave).isNotEmpty;
    return InkWell(
      onTap: () => _abrirDetalle(context),
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFEEEAE0)),
          boxShadow: const [
            BoxShadow(
                color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 4)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: _colorInicial(cliente.nombreVisible),
                  backgroundImage: _fotoCliente(cliente) != null
                      ? CachedNetworkImageProvider(_fotoCliente(cliente)!)
                      : null,
                  child: _fotoCliente(cliente) == null
                      ? Text(cliente.inicial,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              fontSize: 18))
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(cliente.nombreVisible,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: t.titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                          ),
                          if (verificado) ...[
                            const SizedBox(width: 5),
                            Icon(Icons.verified,
                                size: 16, color: cs.primary),
                          ],
                          if (tieneNota) ...[
                            const SizedBox(width: 5),
                            Icon(Icons.sticky_note_2_outlined,
                                size: 15, color: textoTenueDe(context)),
                          ],
                          if (badge != null) ...[
                            const SizedBox(width: 6),
                            _BadgeSeg(seg: badge!),
                          ],
                        ],
                      ),
                      const SizedBox(height: 1),
                      Text(
                        _contacto(cliente),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context)),
                      ),
                    ],
                  ),
                ),
                if (cliente.email.isNotEmpty)
                  IconButton(
                    tooltip: 'Chatear',
                    icon: const Icon(Icons.chat_bubble_outline),
                    color: cs.primary,
                    onPressed: () => _chatear(context),
                  )
                else if (cliente.telefono.isNotEmpty)
                  IconButton(
                    tooltip: 'WhatsApp',
                    icon: const Icon(Icons.chat),
                    color: lima,
                    onPressed: () => WhatsAppLink.abrir(cliente.telefono,
                        'Hola ${cliente.nombreVisible} 👋'),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _Chip(
                    icono: Icons.event_available,
                    texto:
                        '${cliente.reservas} ${cliente.reservas == 1 ? 'reserva' : 'reservas'}',
                    color: teal),
                _Chip(
                    icono: Icons.payments_outlined,
                    texto:
                        '${cliente.moneda}${cliente.gastado.toStringAsFixed(2)} gastado',
                    color: cs.primary),
                if (cliente.porCobrar > 0)
                  _Chip(
                      icono: Icons.schedule,
                      texto:
                          'debe ${cliente.moneda}${cliente.porCobrar.toStringAsFixed(2)}',
                      color: clayOscuro),
                if (cliente.ultima.isNotEmpty)
                  _Chip(
                      icono: Icons.history,
                      texto: 'última ${_fechaCorta(cliente.ultima)}',
                      color: textoTenueDe(context)),
                if (cliente.noShows > 0)
                  _Chip(
                      icono: Icons.person_off,
                      texto:
                          '${cliente.noShows} no-show${cliente.noShows == 1 ? '' : 's'}',
                      color: clayOscuro),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _chatear(BuildContext context) {
    final owner = appState.usuario?.email ?? '';
    if (owner.isEmpty || cliente.email.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: cliente.email,
        titulo: cliente.nombreVisible,
        soyProfe: true,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }

  /// Ficha ampliada del cliente (analítica + notas del dueño + acciones).
  void _abrirDetalle(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => _DetalleClienteSheet(cliente: cliente),
    );
  }
}

/// Ficha ampliada de un cliente: perfil de consumo (ticket promedio, cancha y
/// horario preferidos, medio de pago habitual, % no-show), notas privadas del
/// dueño (device-first), historial y acciones (reservar, cobrar, chat).
class _DetalleClienteSheet extends StatefulWidget {
  const _DetalleClienteSheet({required this.cliente});
  final _Cliente cliente;

  @override
  State<_DetalleClienteSheet> createState() => _DetalleClienteSheetState();
}

class _DetalleClienteSheetState extends State<_DetalleClienteSheet> {
  late final TextEditingController _nota =
      TextEditingController(text: appState.notaCliente(widget.cliente.clave));
  bool _notaSucia = false;

  @override
  void dispose() {
    _nota.dispose();
    super.dispose();
  }

  _Cliente get cliente => widget.cliente;

  /// Reservas de este cliente en las canchas del dueño (más recientes primero).
  List<Reserva> get _suyas {
    final mias = {for (final c in appState.misCanchas) c.id: c};
    return appState.reservas.where((r) {
      if (!mias.containsKey(r.canchaId)) return false;
      final email = r.usuario.trim().toLowerCase();
      if (cliente.email.isNotEmpty) return email == cliente.email;
      return r.jugador.trim().toLowerCase() ==
          cliente.nombreVisible.toLowerCase();
    }).toList()
      ..sort((a, b) => b.fecha.compareTo(a.fecha));
  }

  /// La moda (valor más repetido) de una lista, o vacío.
  String _moda(Iterable<String> vals) {
    final c = <String, int>{};
    for (final v in vals) {
      if (v.trim().isEmpty) continue;
      c[v] = (c[v] ?? 0) + 1;
    }
    if (c.isEmpty) return '';
    return c.entries.reduce((a, b) => b.value > a.value ? b : a).key;
  }

  static const _mediosLabel = {
    'yape': 'Yape',
    'tarjeta': 'Tarjeta',
    'efectivo': 'Efectivo',
    'sena': 'Seña + saldo',
    'manual': 'Manual',
    'online': 'Online',
  };

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final suyas = _suyas;
    final mias = {for (final c in appState.misCanchas) c.id: c};

    // Perfil de consumo (con lo que ya hay, sin SQL nuevo).
    final pagadas = suyas.where((r) => r.pagado).toList();
    final ticket = pagadas.isEmpty
        ? 0.0
        : pagadas.fold<double>(0, (s, r) => s + r.totalConExtras) /
            pagadas.length;
    final canchaPref = _moda(suyas
        .map((r) => mias[r.canchaId]?.nombre ?? '')
        .where((s) => s.isNotEmpty));
    final horaPref = _moda(suyas.map((r) => r.horaInicio));
    final medioPref = _moda(suyas.map((r) => r.medioPago));
    final pctNoShow =
        cliente.reservas == 0 ? 0 : (cliente.noShows * 100 / cliente.reservas);

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.95,
      builder: (_, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                  color: const Color(0xFFDDDDDD),
                  borderRadius: BorderRadius.circular(999)),
            ),
          ),
          const SizedBox(height: 16),
          // Cabecera: avatar + nombre + acción rápida de contacto.
          Row(
            children: [
              CircleAvatar(
                radius: 24,
                backgroundColor: _colorInicial(cliente.nombreVisible),
                backgroundImage: _fotoCliente(cliente) != null
                    ? CachedNetworkImageProvider(_fotoCliente(cliente)!)
                    : null,
                child: _fotoCliente(cliente) == null
                    ? Text(cliente.inicial,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                            fontSize: 20))
                    : null,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cliente.nombreVisible,
                        style: t.titleLarge
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    Text(_contacto(cliente),
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
              if (cliente.email.isNotEmpty)
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: teal),
                  onPressed: () {
                    Navigator.of(context).pop();
                    _chatear(context);
                  },
                  icon: const Icon(Icons.chat_bubble_outline, size: 18),
                  label: const Text('Chat'),
                )
              else if (cliente.telefono.isNotEmpty)
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: lima),
                  onPressed: () => WhatsAppLink.abrir(cliente.telefono,
                      'Hola ${cliente.nombreVisible} 👋'),
                  icon: const Icon(Icons.chat, size: 18),
                  label: const Text('WhatsApp'),
                ),
            ],
          ),
          const SizedBox(height: 16),
          // Perfil de consumo: mosaico de datos que el dueño no calculaba a mano.
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Dato(
                  icono: Icons.confirmation_number_outlined,
                  titulo: 'Ticket prom.',
                  valor: '${cliente.moneda}${ticket.toStringAsFixed(2)}'),
              if (canchaPref.isNotEmpty)
                _Dato(
                    icono: Icons.stadium_outlined,
                    titulo: 'Cancha fav.',
                    valor: canchaPref),
              if (horaPref.isNotEmpty)
                _Dato(
                    icono: Icons.schedule,
                    titulo: 'Horario fav.',
                    valor: horaPref),
              if (medioPref.isNotEmpty)
                _Dato(
                    icono: Icons.account_balance_wallet_outlined,
                    titulo: 'Paga con',
                    valor: _mediosLabel[medioPref] ?? medioPref),
              _Dato(
                  icono: Icons.event_available,
                  titulo: 'Reservas',
                  valor: '${cliente.reservas}'),
              if (cliente.noShows > 0)
                _Dato(
                    icono: Icons.person_off,
                    titulo: 'No-show',
                    valor: '${pctNoShow.round()}%',
                    color: clayOscuro),
              if (cliente.diasDesdeUltima >= _diasRiesgo &&
                  cliente.reservas >= 2)
                _Dato(
                    icono: Icons.warning_amber_rounded,
                    titulo: 'Sin volver',
                    valor: '${cliente.diasDesdeUltima} días',
                    color: naranja),
            ],
          ),
          if (cliente.porCobrar > 0) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: clayOscuro.withOpacity(0.08),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  const Icon(Icons.schedule, size: 18, color: clayOscuro),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                        'Te debe ${cliente.moneda}'
                        '${cliente.porCobrar.toStringAsFixed(2)} (efectivo por cobrar)',
                        style: t.bodyMedium?.copyWith(
                            color: clayOscuro, fontWeight: FontWeight.w700)),
                  ),
                  if (cliente.telefono.isNotEmpty || cliente.email.isNotEmpty)
                    TextButton(
                      onPressed: _recordarCobro,
                      child: const Text('Recordar'),
                    ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          // Acciones: reservar para este cliente (pre-llena su ficha).
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _reservarParaCliente,
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Reservar'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          // Notas privadas del dueño (el "cuaderno del club").
          Text('Notas privadas',
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text('Solo tú las ves. Ej: "prefiere Cancha 2, juega martes, paga efectivo".',
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(height: 8),
          TextField(
            controller: _nota,
            minLines: 2,
            maxLines: 5,
            onChanged: (_) {
              if (!_notaSucia) setState(() => _notaSucia = true);
            },
            decoration: InputDecoration(
              hintText: 'Escribe una nota…',
              filled: true,
              fillColor: Theme.of(context).colorScheme.surface,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: const BorderSide(color: Color(0xFFE4E4E4)),
              ),
            ),
          ),
          if (_notaSucia)
            Align(
              alignment: Alignment.centerRight,
              child: Padding(
                padding: const EdgeInsets.only(top: 8),
                child: FilledButton.icon(
                  onPressed: () async {
                    await appState.guardarNotaCliente(
                        cliente.clave, _nota.text);
                    if (mounted) setState(() => _notaSucia = false);
                  },
                  icon: const Icon(Icons.check, size: 18),
                  label: const Text('Guardar nota'),
                ),
              ),
            ),
          const SizedBox(height: 18),
          Text('Historial de reservas',
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          for (final r in suyas)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Icon(
                    r.estado == EstadoReserva.noShow
                        ? Icons.person_off
                        : (r.pagado ? Icons.check_circle : Icons.schedule),
                    size: 18,
                    color: r.estado == EstadoReserva.noShow
                        ? clayOscuro
                        : (r.pagado ? lima : amarillo),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      '${_fechaCorta(r.fecha)} · ${r.horaInicio}'
                      '${mias[r.canchaId] != null ? ' · ${mias[r.canchaId]!.nombre}' : ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: t.bodyMedium,
                    ),
                  ),
                  Text(
                    '${r.monedaSimbolo}${r.totalConExtras.toStringAsFixed(2)}',
                    style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ),
          if (suyas.isEmpty)
            Text('Sin reservas registradas.',
                style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
        ],
      ),
    );
  }

  void _chatear(BuildContext context) {
    final owner = appState.usuario?.email ?? '';
    if (owner.isEmpty || cliente.email.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: cliente.email,
        titulo: cliente.nombreVisible,
        soyProfe: true,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }

  /// Abre "Reserva manual" con este cliente ya prellenado. Función PRO.
  Future<void> _reservarParaCliente() async {
    Navigator.of(context).pop();
    if (!await exigirPro(context, funcion: 'La reserva manual')) return;
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ReservaManualScreen(
        clienteEmailInicial: cliente.email,
        clienteNombreInicial: cliente.nombreVisible,
        clienteFotoInicial: _fotoCliente(cliente) ?? '',
        clienteTelefonoInicial: cliente.telefono,
      ),
    ));
  }

  /// Recordatorio de cobro por WhatsApp (si hay teléfono) o chat.
  void _recordarCobro() {
    final saldo = '${cliente.moneda}${cliente.porCobrar.toStringAsFixed(2)}';
    final msg =
        'Hola ${cliente.nombreVisible} 👋 Te recordamos tu saldo pendiente '
        'de $saldo por tu reserva. ¡Gracias!';
    if (cliente.telefono.isNotEmpty) {
      WhatsAppLink.abrir(cliente.telefono, msg);
    } else if (cliente.email.isNotEmpty) {
      Navigator.of(context).pop();
      _chatear(context);
    }
  }
}

/// Celda de dato del perfil de consumo (ticket, cancha fav., etc.).
class _Dato extends StatelessWidget {
  const _Dato(
      {required this.icono,
      required this.titulo,
      required this.valor,
      this.color});
  final IconData icono;
  final String titulo;
  final String valor;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFEEEAE0)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono, size: 16, color: c),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(titulo,
                  style: TextStyle(
                      fontSize: 11, color: textoTenueDe(context))),
              Text(valor,
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w800)),
            ],
          ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(
      {required this.icono, required this.texto, required this.color});
  final IconData icono;
  final String texto;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.10),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono, size: 13, color: color),
          const SizedBox(width: 5),
          Text(texto,
              style: TextStyle(
                  color: color, fontSize: 12, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio({required this.hayBusqueda});
  final bool hayBusqueda;

  @override
  Widget build(BuildContext context) {
    return VacioAirbnb(
      icono: hayBusqueda ? Icons.search_off : Icons.groups_outlined,
      colorIcono: const Color(0xFF7B61FF),
      titulo: hayBusqueda
          ? 'No hay clientes\nque coincidan'
          : 'Aún no tienes\nclientes',
      mensaje: hayBusqueda
          ? 'Prueba con otro nombre o correo.'
          : 'Cuando te reserven una cancha, tus clientes aparecerán aquí '
              'con su historial y cuánto han gastado.',
    );
  }
}

/// Subtítulo de contacto del cliente: prioriza lo que sirve para ubicarlo
/// (correo si tiene cuenta, si no el teléfono del cuaderno), luego el nivel.
String _contacto(_Cliente c) {
  if (c.email.isNotEmpty) return c.email;
  if (c.telefono.isNotEmpty) return c.telefono;
  if (c.nivel.isNotEmpty) return c.nivel;
  return 'Sin contacto';
}

/// Color estable del avatar a partir del nombre (paleta de marca).
Color _colorInicial(String nombre) {
  const paleta = [bosque, pino, coral, clayOscuro, Color(0xFF119861)];
  var h = 0;
  for (final code in nombre.codeUnits) {
    h = (h * 31 + code) & 0x7fffffff;
  }
  return paleta[h % paleta.length];
}

/// Foto real del cliente (regla de la app: avatar con foto). null si no hay.
String? _fotoCliente(_Cliente c) {
  final f = (appState.fotoDe(c.email) ?? '').trim();
  return f.isEmpty ? null : f;
}

/// "2026-07-15" → "15 jul".
String _fechaCorta(String iso) {
  if (iso.isEmpty) return '—';
  final p = iso.split('-');
  if (p.length != 3) return iso;
  const meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun', //
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  final m = int.tryParse(p[1]) ?? 0;
  final d = int.tryParse(p[2]) ?? 0;
  if (m < 1 || m > 12) return iso;
  return '$d ${meses[m - 1]}';
}
