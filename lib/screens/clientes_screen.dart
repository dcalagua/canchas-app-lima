import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import 'chat_screen.dart';

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

class _ClientesScreenState extends State<ClientesScreen> {
  _Orden _orden = _Orden.frecuentes;
  String _busqueda = '';

  @override
  void initState() {
    super.initState();
    // Insignia de verificado: consulta qué clientes están verificados.
    final mias = appState.misCanchas.map((c) => c.id).toSet();
    final emails = appState.reservas
        .where((r) => mias.contains(r.canchaId))
        .map((r) => r.usuario)
        .where((e) => e.trim().isNotEmpty);
    appState.sincronizarVerificados(emails);
  }

  /// Agrega las reservas de las canchas del dueño en una ficha por cliente.
  /// [aplicarBusqueda] false = universo completo (para los KPIs de arriba).
  List<_Cliente> _clientes({bool aplicarBusqueda = true}) {
    final mias = {for (final c in appState.misCanchas) c.id};
    final map = <String, _Cliente>{};
    for (final r in appState.reservas) {
      if (!mias.contains(r.canchaId)) continue;
      final email = r.usuario.trim().toLowerCase();
      final nombre = r.jugador.trim();
      // Clave estable: por correo si lo hay; si no, por nombre (walk-in).
      final key = email.isNotEmpty ? email : 'n:${nombre.toLowerCase()}';
      if (email.isEmpty && nombre.isEmpty) continue;
      final cl = map.putIfAbsent(key, () => _Cliente(email: email));
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
          final todos = _clientes();
          // KPIs sobre el universo COMPLETO (sin filtro de búsqueda).
          final total = _clientes(aplicarBusqueda: false);
          final recurrentes = total.where((c) => c.reservas >= 2).length;
          final mesActual = _mesActualIso();
          final nuevos =
              total.where((c) => c.primera.startsWith(mesActual)).length;

          return Column(
            children: [
              _KpiFila(
                total: total.length,
                recurrentes: recurrentes,
                nuevos: nuevos,
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
                        itemBuilder: (_, i) => _ClienteCard(cliente: todos[i]),
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
  const _ClienteCard({required this.cliente});
  final _Cliente cliente;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final verificado =
        cliente.email.isNotEmpty && appState.estaVerificado(cliente.email);
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
                  child: Text(cliente.inicial,
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                          fontSize: 18)),
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

  /// Ficha ampliada: historial de reservas de este cliente en tus canchas.
  void _abrirDetalle(BuildContext context) {
    final mias = {for (final c in appState.misCanchas) c.id: c};
    final suyas = appState.reservas.where((r) {
      if (!mias.containsKey(r.canchaId)) return false;
      final email = r.usuario.trim().toLowerCase();
      if (cliente.email.isNotEmpty) return email == cliente.email;
      return r.jugador.trim().toLowerCase() ==
          cliente.nombreVisible.toLowerCase();
    }).toList()
      ..sort((a, b) => b.fecha.compareTo(a.fecha));

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (ctx) {
        final t = Theme.of(ctx).textTheme;
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.6,
          maxChildSize: 0.9,
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
              Row(
                children: [
                  CircleAvatar(
                    radius: 24,
                    backgroundColor: _colorInicial(cliente.nombreVisible),
                    child: Text(cliente.inicial,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                            fontSize: 20)),
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
                                ?.copyWith(color: textoTenueDe(ctx))),
                      ],
                    ),
                  ),
                  if (cliente.email.isNotEmpty)
                    FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: teal),
                      onPressed: () {
                        Navigator.of(ctx).pop();
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
                            : (r.pagado
                                ? Icons.check_circle
                                : Icons.schedule),
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
                        style: t.bodyMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                ),
              if (suyas.isEmpty)
                Text('Sin reservas registradas.',
                    style: t.bodyMedium?.copyWith(color: textoTenueDe(ctx))),
            ],
          ),
        );
      },
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
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(hayBusqueda ? Icons.search_off : Icons.groups_outlined,
                size: 56, color: textoTenueDe(context)),
            const SizedBox(height: 14),
            Text(
              hayBusqueda
                  ? 'No hay clientes que coincidan.'
                  : 'Aún no tienes clientes.',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
            ),
            const SizedBox(height: 6),
            Text(
              hayBusqueda
                  ? 'Prueba con otro nombre o correo.'
                  : 'Cuando te reserven una cancha, tus clientes aparecerán '
                      'aquí con su historial y cuánto han gastado.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenueDe(context)),
            ),
          ],
        ),
      ),
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
