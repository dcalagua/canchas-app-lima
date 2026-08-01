import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';
import 'chat_screen.dart';
import 'recordar_reservas_screen.dart';
import 'reporte_canchas_screen.dart';
import 'reserva_manual_screen.dart';
import 'reservas_fijas_screen.dart';

/// Panel de RESERVAS del dueño (piloto): lista las reservas reales de sus
/// canchas, con botones para registrar el pago en efectivo o marcar no-show,
/// y un mini libro de caja (cobrado / por cobrar). Es la contraparte del flujo
/// "pago en cancha": el jugador reserva y el dueño confirma el cobro aquí.
class ReservasDuenoScreen extends StatefulWidget {
  const ReservasDuenoScreen({super.key});

  @override
  State<ReservasDuenoScreen> createState() => _ReservasDuenoScreenState();
}

class _ReservasDuenoScreenState extends State<ReservasDuenoScreen> {
  @override
  void initState() {
    super.initState();
    // Carga qué jugadores están verificados para mostrar la insignia.
    final emails = appState.reservas
        .where((r) => appState.miCanchaDeReserva(r.canchaId) != null)
        .map((r) => r.usuario);
    appState.sincronizarVerificados(emails);
  }

  /// Etiqueta amigable de una fecha ISO ("Hoy"/"Mañana"/"2026-06-28").
  static String _fechaLabel(String iso) {
    if (iso.isEmpty) return 'Sin fecha';
    final hoy = DateTime.now();
    String f(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
    if (iso == f(hoy)) return 'Hoy';
    if (iso == f(hoy.add(const Duration(days: 1)))) return 'Mañana';
    return iso;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Reservas'),
        actions: [
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
            tooltip: 'Reporte de cobros',
            icon: const Icon(Icons.bar_chart),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => const ReporteCanchasScreen())),
          ),
        ],
      ),
      // Anota la reserva de un cliente que llamó/vino (digitaliza el cuaderno).
      floatingActionButton: FloatingActionButton.extended(
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
          reservas.sort((a, b) {
            final byFecha = b.fecha.compareTo(a.fecha); // más recientes arriba
            return byFecha != 0
                ? byFecha
                : b.horaInicio.compareTo(a.horaInicio);
          });
          final mias = {for (final c in appState.misCanchas) c.id: c};

          // Libro de caja del piloto (excluye no-shows del "por cobrar").
          final activas =
              reservas.where((r) => r.estado != EstadoReserva.noShow);
          // Los totales incluyen los servicios extra (árbitro/pelotero…).
          final cobrado = activas
              .where((r) => r.pagado)
              .fold<int>(0, (s, r) => s + r.totalConExtras.round());
          final porCobrar = activas
              .where((r) => !r.pagado)
              .fold<int>(0, (s, r) => s + r.totalConExtras.round());

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
                      const SizedBox(height: 16),
                      // Tablet/landscape: reservas en grilla de 2-3 columnas.
                      if (MediaQuery.of(context).size.width >= 720)
                        LayoutBuilder(builder: (context, cons) {
                          final cols = cons.maxWidth >= 1100 ? 3 : 2;
                          final w = (cons.maxWidth - 12 * (cols - 1)) / cols;
                          return Wrap(
                            spacing: 12,
                            runSpacing: 12,
                            children: [
                              for (final r in reservas)
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
                        })
                      else
                        for (final r in reservas)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _ReservaCard(
                              reserva: r,
                              cancha: canchaDe[r.id]!,
                              fechaLabel: _fechaLabel(r.fecha),
                            ),
                          ),
                    ],
                  ),
          );
        },
      )),
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
              Container(
                width: 9,
                height: 9,
                decoration: BoxDecoration(
                    color: colorDeporte(cancha.deporte),
                    borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(width: 8),
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
              _EstadoChip(reserva: reserva),
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
    if (reserva.estado == EstadoReserva.noShow) {
      texto = 'NO-SHOW';
      bg = const Color(0xFFF0ECE2);
      fg = const Color(0xFF8A8175);
    } else if (reserva.pagado) {
      texto = 'PAGADO';
      bg = limaSuave;
      fg = pino;
    } else {
      texto = 'POR COBRAR';
      bg = const Color(0xFFFBEAD2);
      fg = clayOscuro;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(texto,
          style: TextStyle(
              color: fg, fontSize: 10, fontWeight: FontWeight.w800, height: 1)),
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
