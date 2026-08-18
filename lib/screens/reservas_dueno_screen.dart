import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/push_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';
import 'chat_screen.dart';
import 'recordar_reservas_screen.dart';
import 'reportes_hub_screen.dart';
import 'reserva_manual_screen.dart';
import 'reservas_fijas_screen.dart';

/// Panel de RESERVAS del dueño (vista LISTA del hub de Reservas): lista las
/// reservas reales de sus canchas, con botones para registrar el pago en
/// efectivo o marcar no-show, y un mini libro de caja (cobrado / por cobrar).
/// Es la contraparte del flujo "pago en cancha": el jugador reserva y el dueño
/// confirma el cobro aquí. También se abre standalone (push desde la
/// notificación de nueva reserva o desde la ficha del club).
class ReservasDuenoScreen extends StatefulWidget {
  const ReservasDuenoScreen({super.key, this.embedded = false});

  /// Cuando va dentro del hub (conmutador Lista/Calendario) se OCULTA su propia
  /// AppBar: el hub aporta el título y las acciones. Sigue funcionando standalone
  /// (push desde notificación de reserva o desde la ficha) con embedded=false.
  final bool embedded;

  @override
  State<ReservasDuenoScreen> createState() => _ReservasDuenoScreenState();
}

/// Acciones de la barra de Reservas (recordatorios, clientes fijos, reportes).
/// Compartidas por la pantalla standalone y por el hub Lista/Calendario, para
/// no duplicar el menú.
List<Widget> accionesReservas(BuildContext context) => [
      IconButton(
        tooltip: 'Recordar reservas (anti no-show)',
        icon: const Icon(Icons.notifications_active_outlined),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const RecordarReservasScreen())),
      ),
      IconButton(
        tooltip: 'Clientes fijos (pensionados)',
        icon: const Icon(Icons.event_repeat),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const ReservasFijasScreen())),
      ),
      IconButton(
        tooltip: 'Reportes',
        icon: const Icon(Icons.bar_chart),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const ReportesHubScreen(inicial: 2))),
      ),
    ];

class _ReservasDuenoScreenState extends State<ReservasDuenoScreen> {
  // Filtro por tiempo: 'proximas' (default) muestra hoy/futuras; 'pasadas' es el
  // historial. Evita que se acumulen decenas de reservas viejas en una sola lista.
  String _filtro = 'proximas';

  // Filtro por ORIGEN del cobro: todos | online (pagó por la app) | efectivo
  // (cobra en la cancha, incluye seña) | manual (cliente propio del dueño).
  String _medio = 'todos';

  /// Grupo de cobro de una reserva (para el filtro Online/Efectivo/Manual).
  static String _grupoMedio(Reserva r) {
    switch (r.medioPago) {
      case 'yape':
      case 'tarjeta':
      case 'bono':
        return 'online';
      case 'sena':
      case 'efectivo':
        return 'efectivo';
      case 'manual':
        return 'manual';
    }
    // Reservas viejas sin medio guardado: se deduce por su naturaleza.
    if (!r.traidaPorApp) return 'manual';
    return r.pagado ? 'online' : 'efectivo';
  }

  @override
  void initState() {
    super.initState();
    // Al abrir: trae las reservas frescas de la nube (las que hicieron jugadores
    // en otros dispositivos) para no depender de un pull-to-refresh manual.
    appState.cargarReservasRemotas();
    // Carga qué jugadores están verificados (insignia) y sus PERFILES (foto real
    // en la tarjeta, regla de la app). Precargar para que la foto ya esté lista.
    final emails = appState.reservas
        .where((r) => appState.miCanchaDeReserva(r.canchaId) != null)
        .map((r) => r.usuario)
        .where((e) => e.isNotEmpty)
        .toList();
    appState.sincronizarVerificados(emails);
    appState.cargarPerfiles(emails);
    // Se REFRESCA solo cuando llega un push de "Nueva reserva" (estilo WhatsApp).
    PushService.nuevaReserva.addListener(_alLlegarReserva);
  }

  @override
  void dispose() {
    PushService.nuevaReserva.removeListener(_alLlegarReserva);
    super.dispose();
  }

  void _alLlegarReserva() {
    if (!mounted) return;
    appState.cargarReservasRemotas(); // baja la nueva reserva y repinta la lista
  }

  static const _diasSem = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
  static const _mesesAbr = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  /// Etiqueta amigable de una fecha ISO: "Hoy" / "Mañana" / "Ayer" / "vie 8 ago".
  static String _fechaLabel(String iso) {
    if (iso.isEmpty) return 'Sin fecha';
    final hoy = DateTime.now();
    final d = DateTime.tryParse(iso);
    if (d == null) return iso;
    String f(DateTime x) => '${x.year.toString().padLeft(4, '0')}-'
        '${x.month.toString().padLeft(2, '0')}-'
        '${x.day.toString().padLeft(2, '0')}';
    if (iso == f(hoy)) return 'Hoy';
    if (iso == f(hoy.add(const Duration(days: 1)))) return 'Mañana';
    if (iso == f(hoy.subtract(const Duration(days: 1)))) return 'Ayer';
    return '${_diasSem[d.weekday - 1]} ${d.day} ${_mesesAbr[d.month - 1]}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: widget.embedded
          ? null
          : AppBar(
              title: const Text('Reservas'),
              actions: accionesReservas(context),
            ),
      // Anota la reserva de un cliente que llamó/vino (digitaliza el cuaderno).
      floatingActionButton: FloatingActionButton.extended(
        // Tag único: convive con el FAB de la vista Calendario en el hub
        // (IndexedStack) sin chocar heroTags al abrir una ruta.
        heroTag: 'fab-reservas',
        backgroundColor: lima,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: const Text('Reserva manual'),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const ReservaManualScreen())),
      ),
      body: AnchoLectura(child: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          // Resuelve cada reserva a la cancha del dueño a la que pertenece
          // (tolerante a ids duplicados del mismo local). Solo quedan las suyas.
          final canchaDe = <String, Cancha>{}; // reservaId → su cancha (dueño)
          final reservas = <Reserva>[];
          for (final r in appState.reservas) {
            final c = appState.miCanchaDeReserva(r.canchaId);
            if (c != null) {
              canchaDe[r.id] = c;
              reservas.add(r);
            }
          }
          final mias = {for (final c in appState.misCanchas) c.id: c};

          // Pasada = la reserva ya TERMINÓ (fin < ahora). Considera el cruce de
          // medianoche (si horaFin <= horaInicio, termina al día siguiente).
          final ahora = DateTime.now();
          bool esPasada(Reserva r) {
            final fp = r.fecha.split('-');
            final hi = r.horaInicio.split(':');
            final hf = r.horaFin.split(':');
            if (fp.length < 3 || hi.length < 2 || hf.length < 2) return false;
            try {
              var fin = DateTime(int.parse(fp[0]), int.parse(fp[1]),
                  int.parse(fp[2]), int.parse(hf[0]), int.parse(hf[1]));
              final iniMin = int.parse(hi[0]) * 60 + int.parse(hi[1]);
              final finMin = int.parse(hf[0]) * 60 + int.parse(hf[1]);
              if (finMin <= iniMin) fin = fin.add(const Duration(days: 1));
              return fin.isBefore(ahora);
            } catch (_) {
              return false;
            }
          }

          final nPasadas = reservas.where(esPasada).length;
          final nProximas = reservas.length - nPasadas;
          final verPasadas = _filtro == 'pasadas';
          final mostradas =
              reservas.where((r) => esPasada(r) == verPasadas).toList()
                ..sort((a, b) {
                  final byFecha = a.fecha.compareTo(b.fecha);
                  final c = byFecha != 0
                      ? byFecha
                      : a.horaInicio.compareTo(b.horaInicio);
                  // Próximas: la más cercana primero; Pasadas: la más reciente.
                  return verPasadas ? -c : c;
                });

          // Caja: resumen de plata sobre TODO lo activo (no depende del filtro).
          final activas =
              reservas.where((r) => r.estado != EstadoReserva.noShow);
          // Las reservas pagadas con BONO no suman aquí: su dinero ya entró al
          // COMPRAR el bono (se ve en la billetera "por recibir"), no al canjear.
          final cobrado = activas
              .where((r) => r.pagado && !r.esBono)
              .fold<int>(0, (s, r) => s + r.totalConExtras.round());
          final porCobrar = activas
              .where((r) => !r.pagado)
              .fold<int>(0, (s, r) => s + r.totalConExtras.round());

          // Filtro por ORIGEN del cobro (Online / Efectivo / Manual).
          final mostradasMedio = _medio == 'todos'
              ? mostradas
              : mostradas.where((r) => _grupoMedio(r) == _medio).toList();

          // Agrupa lo MOSTRADO por DÍA (respeta el orden ya definido arriba).
          final porDia = <String, List<Reserva>>{};
          for (final r in mostradasMedio) {
            porDia.putIfAbsent(r.fecha, () => []).add(r);
          }

          // Columnas según el ANCHO DISPONIBLE (no el de la pantalla): en el
          // hub de tablet esta lista vive en un panel angosto junto al
          // calendario y ahí debe caer a 1 columna aunque la pantalla sea ancha.
          Widget cardsDe(List<Reserva> rs) {
            return LayoutBuilder(builder: (context, cons) {
              final cols = cons.maxWidth >= 1100
                  ? 3
                  : cons.maxWidth >= 680
                      ? 2
                      : 1;
              if (cols == 1) {
                return Column(
                  children: [
                    for (final r in rs)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _ReservaCard(
                          reserva: r,
                          cancha: canchaDe[r.id]!,
                          fechaLabel: _fechaLabel(r.fecha),
                        ),
                      ),
                  ],
                );
              }
              final w = (cons.maxWidth - 12 * (cols - 1)) / cols;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  for (final r in rs)
                    SizedBox(
                      width: w,
                      child: _ReservaCard(
                        reserva: r,
                        cancha: canchaDe[r.id]!,
                        fechaLabel: _fechaLabel(r.fecha),
                      ),
                    ),
                ],
              );
            });
          }

          return RefreshIndicator(
            onRefresh: () => appState.cargarReservasRemotas(),
            child: reservas.isEmpty
                ? ListView(children: const [SizedBox(height: 120), _Vacio()])
                : ListView(
                    padding: const EdgeInsets.fromLTRB(18, 16, 18, 90),
                    children: [
                      _Caja(
                          cobrado: cobrado,
                          porCobrar: porCobrar,
                          moneda: mias.values.isNotEmpty
                              ? mias.values.first.monedaSimbolo
                              : 'S/'),
                      const SizedBox(height: 14),
                      // Filtro por tiempo: Próximas (default) / Pasadas (historial).
                      _FiltroTiempo(
                        filtro: _filtro,
                        nProximas: nProximas,
                        nPasadas: nPasadas,
                        onCambio: (v) => setState(() => _filtro = v),
                      ),
                      const SizedBox(height: 10),
                      // Filtro por origen del cobro (chips estilo Airbnb).
                      _FiltroMedio(
                        medio: _medio,
                        contar: (m) => m == 'todos'
                            ? mostradas.length
                            : mostradas
                                .where((r) => _grupoMedio(r) == m)
                                .length,
                        onCambio: (v) => setState(() => _medio = v),
                      ),
                      const SizedBox(height: 14),
                      if (mostradasMedio.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 40),
                          child: Text(
                              _medio != 'todos' && mostradas.isNotEmpty
                                  ? 'No hay reservas con ese tipo de cobro.'
                                  : verPasadas
                                      ? 'No hay reservas pasadas.'
                                      : 'No tienes reservas próximas. Las '
                                          'nuevas aparecen aquí.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: textoTenueDe(context))),
                        )
                      else
                        // Agrupado por DÍA con su encabezado ("Hoy", "vie 8 ago").
                        for (final e in porDia.entries) ...[
                          _DiaHeader(
                              label: _fechaLabel(e.key), n: e.value.length),
                          const SizedBox(height: 10),
                          cardsDe(e.value),
                          const SizedBox(height: 18),
                        ],
                    ],
                  ),
          );
        },
      )),
    );
  }
}

/// Filtro por tiempo (Próximas / Pasadas) — pastillas estilo Airbnb, con conteo.
class _FiltroTiempo extends StatelessWidget {
  const _FiltroTiempo({
    required this.filtro,
    required this.nProximas,
    required this.nPasadas,
    required this.onCambio,
  });
  final String filtro;
  final int nProximas;
  final int nPasadas;
  final ValueChanged<String> onCambio;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Widget pill(String valor, String texto, int n) {
      final sel = filtro == valor;
      return Expanded(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onCambio(valor),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 3),
            padding: const EdgeInsets.symmetric(vertical: 10),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: sel ? lima : cs.surface,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: sel ? lima : trazo),
            ),
            child: Text('$texto ($n)',
                style: TextStyle(
                    color: sel ? Colors.white : cs.onSurface,
                    fontWeight: FontWeight.w700,
                    fontSize: 13.5)),
          ),
        ),
      );
    }

    return Row(children: [
      pill('proximas', 'Próximas', nProximas),
      pill('pasadas', 'Pasadas', nPasadas),
    ]);
  }
}

/// Filtro por ORIGEN del cobro (Todos / Online / Efectivo / Manual) — pastillas
/// estilo Airbnb en fila desplazable, con conteo por grupo.
class _FiltroMedio extends StatelessWidget {
  const _FiltroMedio({
    required this.medio,
    required this.contar,
    required this.onCambio,
  });
  final String medio;
  final int Function(String) contar;
  final ValueChanged<String> onCambio;

  static const _opciones = [
    ('todos', 'Todas', ''),
    ('online', 'Online', '🌐'),
    ('efectivo', 'Efectivo', '💵'),
    ('manual', 'Manual', '✍️'),
  ];

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final (valor, texto, emoji) in _opciones)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: GestureDetector(
                onTap: () => onCambio(valor),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
                  decoration: BoxDecoration(
                    color: medio == valor ? const Color(0xFFEBEBEB) : cs.surface,
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                        color: medio == valor
                            ? const Color(0xFFD6D6D6)
                            : trazo),
                  ),
                  child: Text(
                    '${emoji.isEmpty ? '' : '$emoji '}$texto (${contar(valor)})',
                    style: TextStyle(
                        fontSize: 12.5,
                        fontWeight:
                            medio == valor ? FontWeight.w800 : FontWeight.w600,
                        color: cs.onSurface),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Encabezado de día en la lista de reservas ("Hoy · 3 reservas").
class _DiaHeader extends StatelessWidget {
  const _DiaHeader({required this.label, required this.n});
  final String label;
  final int n;
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Row(
      children: [
        Text(label,
            style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(width: 8),
        Text('$n ${n == 1 ? 'reserva' : 'reservas'}',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
      ],
    );
  }
}

/// Avatar del jugador con su FOTO real (regla de la app: nunca ícono genérico
/// donde va una persona). Cae a la inicial de color solo si no hay foto. Anillo
/// del color del deporte.
class _AvatarJugador extends StatelessWidget {
  const _AvatarJugador(
      {required this.email, required this.nombre, required this.colorRing});
  final String email;
  final String nombre;
  final Color colorRing;

  @override
  Widget build(BuildContext context) {
    final foto = (appState.fotoDe(email) ?? '').trim();
    final inicial =
        nombre.trim().isNotEmpty ? nombre.trim()[0].toUpperCase() : '?';
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: colorRing.withOpacity(0.6), width: 2)),
      child: CircleAvatar(
        radius: 16,
        backgroundColor: limaSuave,
        backgroundImage:
            foto.isNotEmpty ? CachedNetworkImageProvider(foto) : null,
        child: foto.isEmpty
            ? Text(inicial,
                style: const TextStyle(
                    color: bosque, fontWeight: FontWeight.w800, fontSize: 14))
            : null,
      ),
    );
  }
}

class _Caja extends StatelessWidget {
  const _Caja(
      {required this.cobrado, required this.porCobrar, required this.moneda});
  final int cobrado;
  final int porCobrar;
  final String moneda;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    // Card CLARO (nunca fondo negro): "Cobrado" en verde, "Por cobrar" en
    // charcoal, sobre superficie blanca con borde suave.
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Cobrado',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                Text('$moneda $cobrado',
                    style: t.titleLarge
                        ?.copyWith(color: lima, fontWeight: FontWeight.w800)),
              ],
            ),
          ),
          Container(width: 1, height: 38, color: trazo),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Por cobrar',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                Text('$moneda $porCobrar',
                    style: t.titleLarge?.copyWith(
                        color: cs.onSurface, fontWeight: FontWeight.w800)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReservaCard extends StatelessWidget {
  const _ReservaCard({
    required this.reserva,
    required this.cancha,
    required this.fechaLabel,
  });
  final Reserva reserva;
  final Cancha cancha;
  final String fechaLabel;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final noShow = reserva.estado == EstadoReserva.noShow;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _AvatarJugador(
                email: reserva.usuario,
                nombre: reserva.jugador,
                colorRing: colorDeporte(cancha.deporte),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Row(
                  children: [
                    Flexible(
                      child: Text(reserva.jugador,
                          style: t.titleSmall
                              ?.copyWith(fontWeight: FontWeight.w700),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                    ),
                    if (appState.estaVerificado(reserva.usuario)) ...[
                      const SizedBox(width: 4),
                      const Icon(Icons.verified, size: 15, color: pino),
                    ],
                  ],
                ),
              ),
              if (reserva.usuario.isNotEmpty)
                IconButton(
                  icon: const Icon(Icons.chat_bubble_outline, size: 20),
                  tooltip: 'Mensaje al jugador',
                  visualDensity: VisualDensity.compact,
                  onPressed: () => _chatearConJugador(context),
                ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  _EstadoChip(reserva: reserva),
                  if (reserva.medioPago.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    _MedioPagoChip(medio: reserva.medioPago),
                  ],
                ],
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${cancha.nombre} · $fechaLabel · ${reserva.horaInicio}–${reserva.horaFin}',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
          ),
          const SizedBox(height: 2),
          if (reserva.extras.isEmpty)
            Text('${reserva.monedaSimbolo} ${reserva.precio}',
                style: t.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w700))
          else ...[
            Text('Cancha: ${reserva.monedaSimbolo} ${reserva.precio}',
                style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            for (final s in reserva.extras)
              Text(
                  '+ ${s.nombre}: ${reserva.monedaSimbolo} ${s.precio.toStringAsFixed(2)}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            Text(
                'Total: ${reserva.monedaSimbolo} ${reserva.totalConExtras.toStringAsFixed(2)}',
                style: t.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurface,
                    fontWeight: FontWeight.w800)),
          ],
          // Seña anti no-show: ya pagada por adelantado (online). El dueño cobra
          // el resto en la cancha; si hay no-show, se queda con la seña.
          if (reserva.sena > 0) ...[
            const SizedBox(height: 4),
            Row(
              children: [
                const Icon(Icons.shield_outlined, size: 15, color: pino),
                const SizedBox(width: 5),
                Expanded(
                  child: Text(
                      noShow
                          ? 'Seña ${reserva.monedaSimbolo} ${reserva.sena} a tu favor (no vino)'
                          : 'Seña ${reserva.monedaSimbolo} ${reserva.sena} pagada · cobra ${reserva.monedaSimbolo} ${(reserva.totalConExtras - reserva.sena).toStringAsFixed(2)} en la cancha',
                      style: t.bodySmall?.copyWith(
                          color: pino, fontWeight: FontWeight.w700)),
                ),
              ],
            ),
          ],
          if (!noShow) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      // No pagado = CTA verde (marcar); pagado = verde suave
                      // (estado hecho). Sin fondos oscuros.
                      backgroundColor: reserva.pagado ? limaSuave : lima,
                      foregroundColor: reserva.pagado ? bosque : Colors.white,
                    ),
                    onPressed: () =>
                        appState.marcarPago(reserva, pagado: !reserva.pagado),
                    icon: Icon(
                        reserva.pagado ? Icons.check_circle : Icons.payments,
                        size: 18),
                    label: Text(reserva.pagado ? 'Pagado ✓' : 'Marcar pagado'),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () => _confirmarNoShow(context),
                  child: const Text('No-show'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Abre el chat con el jugador (conversación de cancha: dueño ↔ jugador).
  void _chatearConJugador(BuildContext context) {
    final owner = appState.usuario?.email ?? '';
    final player = reserva.usuario;
    if (owner.isEmpty || player.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: player,
        titulo: reserva.jugador.isNotEmpty ? reserva.jugador : 'Jugador',
        soyProfe: true,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }

  Future<void> _confirmarNoShow(BuildContext context) async {
    final ok = await confirmarPichangol(
      context,
      titulo: 'Marcar no-show',
      mensaje: '¿El jugador ${reserva.jugador} no se presentó a su reserva de '
          '${reserva.horaInicio}?'
          '${reserva.sena > 0 ? '\n\nLa seña de ${reserva.monedaSimbolo} ${reserva.sena} queda a tu favor (no es reembolsable).' : ''}',
      textoConfirmar: 'Sí, no vino',
      icono: Icons.person_off_outlined,
    );
    if (ok) appState.marcarNoShow(reserva);
  }
}

class _EstadoChip extends StatelessWidget {
  const _EstadoChip({required this.reserva});
  final Reserva reserva;

  @override
  Widget build(BuildContext context) {
    late final String texto;
    late final Color bg;
    late final Color fg;
    IconData? icono;
    if (reserva.estado == EstadoReserva.noShow) {
      texto = 'NO-SHOW';
      bg = const Color(0xFFF0ECE2);
      fg = const Color(0xFF8A8175);
    } else if (reserva.pagado) {
      texto = 'PAGADO';
      bg = limaSuave;
      fg = pino;
      icono = Icons.check_circle;
    } else {
      // "Por cobrar" bien visible: ámbar más fuerte + ícono (antes casi no se
      // notaba sobre el fondo blanco de la tarjeta).
      texto = 'POR COBRAR';
      bg = const Color(0xFFF6C453);
      fg = const Color(0xFF5A3E00);
      icono = Icons.schedule;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icono != null) ...[
            Icon(icono, size: 12, color: fg),
            const SizedBox(width: 4),
          ],
          Text(texto,
              style: TextStyle(
                  color: fg,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w800,
                  height: 1)),
        ],
      ),
    );
  }
}

/// Chip del MEDIO de pago (trazabilidad de por dónde vino la plata): Yape,
/// Tarjeta (online, ya cobrado), Efectivo (paga en cancha) o Manual.
class _MedioPagoChip extends StatelessWidget {
  const _MedioPagoChip({required this.medio});
  final String medio;

  @override
  Widget build(BuildContext context) {
    late final String texto;
    late final IconData icono;
    late final Color color;
    switch (medio) {
      case 'yape':
        texto = 'Yape';
        icono = Icons.qr_code_2;
        color = const Color(0xFF6B2FB3); // morado Yape
        break;
      case 'tarjeta':
        texto = 'Tarjeta';
        icono = Icons.credit_card;
        color = const Color(0xFF2AA9E0);
        break;
      case 'sena':
        texto = 'Seña + efectivo';
        icono = Icons.savings_outlined;
        color = const Color(0xFFB26A00);
        break;
      case 'efectivo':
        texto = 'Efectivo';
        icono = Icons.payments_outlined;
        color = pino;
        break;
      case 'manual':
        texto = 'Manual';
        icono = Icons.person_outline;
        color = const Color(0xFF8A8175);
        break;
      case 'bono':
        texto = 'Pagado con bono';
        icono = Icons.confirmation_number;
        color = teal;
        break;
      default:
        texto = 'Online';
        icono = Icons.language;
        color = const Color(0xFF2AA9E0);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icono, size: 12, color: color),
          const SizedBox(width: 4),
          Text(texto,
              style: TextStyle(
                  color: color,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w800,
                  height: 1)),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.event_available, size: 64, color: verdeClaro),
            const SizedBox(height: 16),
            Text('Aún no hay reservas',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'Cuando un jugador reserve una de tus canchas la verás aquí y '
              'podrás registrar el pago en efectivo.',
              textAlign: TextAlign.center,
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context)),
            ),
          ],
        ),
      ),
    );
  }
}
