import 'dart:async';
import 'package:flutter/material.dart';

import '../models/models.dart';
import '../models/cargo_servicio.dart';
import '../models/boleador.dart';
import '../widgets/cargo_servicio_info.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/dialogo_pichangol.dart';
import '../services/pagos_service.dart';
import '../widgets/ilustracion_pichangol.dart';
import '../utils/ubicacion_share.dart';
import '../widgets/court_lines.dart';
import '../utils/moneda.dart';
import '../widgets/responsive.dart';
import '../widgets/sesion_requerida.dart';
import 'chat_screen.dart';
import '../widgets/icono_vivo.dart';

/// Reservas hechas por el jugador logueado (rediseño premium, handoff v2):
/// tabs Próximas/Historial + card destacada bosque de la próxima reserva.
class MisReservasScreen extends StatefulWidget {
  const MisReservasScreen({super.key});

  @override
  State<MisReservasScreen> createState() => _MisReservasScreenState();
}

class _MisReservasScreenState extends State<MisReservasScreen> {
  int _tab = 0; // 0 = Próximas, 1 = Historial

  @override
  void initState() {
    super.initState();
    // Puntos DISPONIBLES reales (ganados − canjeados) al abrir la pantalla.
    appState.cargarPuntosCanjeados();
    // Estado de los boleadores contratados (esperando / confirmado / devuelto).
    final email = appState.usuario?.email ?? '';
    if (email.isNotEmpty) {
      Boleadores.refrescarSolicitudes(email).then((ok) {
        if (ok && mounted) setState(() {});
      });
    }
  }

  Cancha? _cancha(String id) {
    for (final c in appState.todasLasCanchas()) {
      if (c.id == id) return c;
    }
    return null;
  }

  DateTime? _fechaHora(String fechaIso, String hora) {
    try {
      final p = hora.split(':');
      final d = DateTime.parse(fechaIso);
      return DateTime(d.year, d.month, d.day, int.parse(p[0]), int.parse(p[1]));
    } catch (_) {
      return null;
    }
  }

  /// Colapsa las reservas de varias horas seguidas (mismo `grupoReservaId`) en
  /// UNA sola tarjeta: rango completo (18:00–20:00) y precio/seña sumados. Las
  /// reservas sueltas (grupo vacío) quedan igual.
  List<Reserva> _agrupar(List<Reserva> rs) {
    final porGrupo = <String, List<Reserva>>{};
    final salida = <Reserva>[];
    for (final r in rs) {
      if (r.grupoReservaId.isEmpty) {
        salida.add(r);
      } else {
        porGrupo.putIfAbsent(r.grupoReservaId, () => []).add(r);
      }
    }
    for (final grupo in porGrupo.values) {
      grupo.sort((a, b) => a.horaInicio.compareTo(b.horaInicio));
      final p = grupo.first;
      final u = grupo.last;
      salida.add(Reserva(
        id: p.id,
        canchaId: p.canchaId,
        jugador: p.jugador,
        nivel: p.nivel,
        fecha: p.fecha,
        dia: p.dia,
        horaInicio: p.horaInicio,
        horaFin: u.horaFin, // rango completo del bloque
        estado: p.estado,
        traidaPorApp: p.traidaPorApp,
        precio: grupo.fold<int>(0, (a, r) => a + r.precio),
        sena: grupo.fold<int>(0, (a, r) => a + r.sena),
        pagado: p.pagado,
        usuario: p.usuario,
        deporte: p.deporte,
        moneda: p.moneda,
        extras: p.extras,
        telefono: p.telefono,
        grupoReservaId: p.grupoReservaId,
        medioPago: p.medioPago,
        // Cargo por servicio: va en la 1.ª hora del bloque; se suma por si acaso.
        cargoServicio: grupo.fold<double>(0, (a, r) => a + r.cargoServicio),
        cargoDesglose: grupo
            .map((r) => r.cargoDesglose)
            .firstWhere((d) => d.isNotEmpty, orElse: () => const []),
      ));
    }
    return salida;
  }

  /// Una reserva es "próxima" si aún no terminó y no está jugada/no-show.
  bool _esProxima(Reserva r) {
    if (r.estado == EstadoReserva.completada ||
        r.estado == EstadoReserva.noShow) {
      return false;
    }
    final fin = _fechaHora(r.fecha, r.horaFin);
    if (fin == null) return true;
    return fin.isAfter(DateTime.now());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Mis reservas')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (!appState.logueado) {
            return const SesionRequerida(
              motivo: 'ver tus reservas',
              icono: Icons.sports_soccer,
              titulo: 'Tus reservas te esperan',
            );
          }
          final todas = appState.misReservas;
          // Reservas de varias horas seguidas (mismo grupo) se muestran como UNA
          // tarjeta: rango completo (18:00–20:00) y precio sumado.
          final proximas = _agrupar(todas.where(_esProxima).toList())
            ..sort((a, b) => (_fechaHora(a.fecha, a.horaInicio) ?? DateTime.now())
                .compareTo(_fechaHora(b.fecha, b.horaInicio) ?? DateTime.now()));
          final historial = _agrupar(todas.where((r) => !_esProxima(r)).toList())
            ..sort((a, b) => (_fechaHora(b.fecha, b.horaInicio) ?? DateTime(2000))
                .compareTo(_fechaHora(a.fecha, a.horaInicio) ?? DateTime(2000)));
          final lista = _tab == 0 ? proximas : historial;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Puntos Pichangol: acumulado + "por confirmar" (la palanca para
              // que el jugador exija al dueño marcar su pago en efectivo).
              Padding(
                padding: EdgeInsets.fromLTRB(ladoTablet(context, 18, 760), 4,
                    ladoTablet(context, 18, 760), 10),
                child: _PuntosCard(
                  puntos: appState.misPuntosDisponibles,
                  pendientes: appState.misPuntosPendientes,
                ),
              ),
              Padding(
                // Regla app: contenido centrado (ancho máx) en pantallas anchas.
                padding: EdgeInsets.fromLTRB(
                    ladoTablet(context, 18, 760), 4, ladoTablet(context, 18, 760), 12),
                child: _SegTabs(
                  seleccion: _tab,
                  etiquetas: const ['Próximas', 'Historial'],
                  onTap: (i) => setState(() => _tab = i),
                ),
              ),
              Expanded(
                child: lista.isEmpty
                    ? _Vacio(historial: _tab == 1)
                    : ListView.separated(
                        padding: EdgeInsets.fromLTRB(
                            ladoTablet(context, 18, 760), 4,
                            ladoTablet(context, 18, 760), 28),
                        itemCount: lista.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 14),
                        itemBuilder: (context, i) {
                          final r = lista[i];
                          final cancha = _cancha(r.canchaId);
                          // La primera PRÓXIMA va destacada (card bosque).
                          if (_tab == 0 && i == 0) {
                            return _ReservaDestacada(reserva: r, cancha: cancha);
                          }
                          return _ReservaCard(reserva: r, cancha: cancha);
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Tarjeta de PUNTOS Pichangol del jugador (estilo Airbnb: blanca, sombra
/// sutil): acumulado grande + línea ámbar de "por confirmar" cuando hay pagos
/// en efectivo que el local aún no marcó (el jugador los reclama).
class _PuntosCard extends StatelessWidget {
  const _PuntosCard({required this.puntos, required this.pendientes});
  final int puntos;
  final int pendientes;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 10, offset: Offset(0, 4)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(13),
                ),
                child: const IconoVivo(Icons.stars, color: bosque, size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('$puntos puntos Pichangol',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    Text(
                        'Ganas 1 punto por S/ 1 pagado por la app · cada 100 '
                        'puntos = S/ 3 de descuento al reservar online.',
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
            ],
          ),
          if (pendientes > 0) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
              decoration: BoxDecoration(
                color: const Color(0xFFFBEAD2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  const IconoVivo(Icons.hourglass_top,
                      size: 16, color: Color(0xFF8A5A00)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '+$pendientes por confirmar: pídele al local que marque '
                      'tu pago en efectivo para acreditarlos.',
                      style: t.bodySmall?.copyWith(
                          color: const Color(0xFF8A5A00),
                          fontWeight: FontWeight.w700,
                          height: 1.25),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Control segmentado (píldoras) estilo handoff: Próximas / Historial.
class _SegTabs extends StatelessWidget {
  const _SegTabs(
      {required this.seleccion, required this.etiquetas, required this.onTap});
  final int seleccion;
  final List<String> etiquetas;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var i = 0; i < etiquetas.length; i++) ...[
          if (i > 0) const SizedBox(width: 10),
          _SegChip(
            texto: etiquetas[i],
            activo: seleccion == i,
            onTap: () => onTap(i),
          ),
        ],
      ],
    );
  }
}

class _SegChip extends StatelessWidget {
  const _SegChip(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        decoration: BoxDecoration(
          // Activo = verde WhatsApp (marca), no negro. Congruente con la app.
          color: activo ? lima : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: activo ? lima : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? Colors.white : textoTenueDe(context),
                fontWeight: FontWeight.w700,
                fontSize: 14)),
      ),
    );
  }
}

class _ReservaDestacada extends StatelessWidget {
  const _ReservaDestacada({required this.reserva, required this.cancha});
  final Reserva reserva;
  final Cancha? cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final dep = cancha?.deporte ?? Deporte.futbol;
    // Card claro con acento verde (nunca fondo negro): se distingue como "la
    // próxima" por el borde lima y la pastilla, no por un fondo oscuro.
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: lima, width: 2),
        boxShadow: const [
          BoxShadow(
              color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 6)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                    color: lima, borderRadius: BorderRadius.circular(999)),
                child: Text('PRÓXIMA · ${reserva.diaVisible.toUpperCase()}',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.w800)),
              ),
              const Spacer(),
              if (appState.reservaPendienteSync(reserva.id) ||
                  appState.reservaNoConfirmada(reserva.id))
                _EstadoChip(estado: reserva.estado, reservaId: reserva.id)
              else
                Text(_estadoLabel(reserva.estado),
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              _MenuReserva(reserva: reserva, cancha: cancha),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Container(
                width: 58,
                height: 58,
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  gradient: gradienteDeporte(dep),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const CourtLines(opacity: 0.5),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(cancha?.nombre ?? 'Cancha',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    Text(
                      '${cancha?.club ?? dep.etiqueta} · ${reserva.horaInicio}–${reserva.horaFin}',
                      style: t.bodyMedium
                          ?.copyWith(color: textoTenueDe(context)),
                    ),
                    if (reserva.esBono)
                      Text('Pagado con tu bono 🎟️',
                          style: t.bodySmall?.copyWith(
                              color: teal, fontWeight: FontWeight.w800))
                    else if (reserva.sena > 0)
                      Text(
                          'Seña pagada ${reserva.monedaSimbolo}${reserva.sena} · '
                          'resto ${reserva.monedaSimbolo}${(reserva.totalConExtras - reserva.sena).toStringAsFixed(2)} en la cancha',
                          style: t.bodySmall?.copyWith(
                              color: lima, fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: lima,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 13)),
                  onPressed: cancha == null
                      ? null
                      : () => UbicacionShare.abrirMapa(cancha!.ubicacion),
                  icon: const Icon(Icons.directions, size: 18),
                  label: const Text('Cómo llegar'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: lima,
                    side: const BorderSide(color: lima, width: 1.5),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  onPressed: () => _mostrarPase(context, reserva, cancha),
                  child: const Text('Ver pase'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReservaCard extends StatelessWidget {
  const _ReservaCard({required this.reserva, required this.cancha});
  final Reserva reserva;
  final Cancha? cancha;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final dep = cancha?.deporte ?? Deporte.futbol;
    return GestureDetector(
      onTap: () => _mostrarPase(context, reserva, cancha),
      child: Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              gradient: gradienteDeporte(dep),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const CourtLines(opacity: 0.5),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(cancha?.nombre ?? 'Cancha',
                    style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(
                  '${cancha?.club ?? ''} · ${reserva.diaVisible} ${reserva.horaInicio}–${reserva.horaFin}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                ),
                const SizedBox(height: 6),
                _EstadoChip(estado: reserva.estado, reservaId: reserva.id),
              ],
            ),
          ),
          Text('${reserva.monedaSimbolo}${reserva.precio}',
              style: t.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.onSurface)),
          if (_puedeChatear(context))
            IconButton(
              icon: const Icon(Icons.chat_bubble_outline, size: 20),
              tooltip: 'Mensaje al dueño',
              visualDensity: VisualDensity.compact,
              onPressed: () => _chatearConDueno(context),
            ),
          _MenuReserva(reserva: reserva, cancha: cancha),
        ],
      ),
      ),
    );
  }

  bool _puedeChatear(BuildContext context) {
    final owner = (cancha?.dueno ?? '').toLowerCase();
    final me = (appState.usuario?.email ?? '').toLowerCase();
    return owner.isNotEmpty && me.isNotEmpty && owner != me;
  }

  /// Abre el chat con el dueño de la cancha (conversación de cancha).
  void _chatearConDueno(BuildContext context) {
    final owner = cancha?.dueno ?? '';
    final me = appState.usuario?.email ?? '';
    if (owner.isEmpty || me.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: me,
        titulo: (cancha?.club.isNotEmpty ?? false)
            ? cancha!.club
            : (cancha?.nombre ?? 'Dueño'),
        soyProfe: false,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }
}

/// ¿La reserva ya terminó su ciclo (historial)? Cambia el texto del menú.
bool _esHistorial(Reserva r) =>
    r.estado == EstadoReserva.completada || r.estado == EstadoReserva.noShow;

/// Menú "⋮" de una reserva: permite al jugador CANCELAR (si es próxima) o
/// QUITAR del historial. Libera el slot y borra la reserva.
class _MenuReserva extends StatelessWidget {
  const _MenuReserva({required this.reserva, this.cancha, this.color});
  final Reserva reserva;
  final Cancha? cancha;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final historial = _esHistorial(reserva);
    return PopupMenuButton<String>(
      icon: Icon(Icons.more_vert, size: 20, color: color),
      tooltip: 'Opciones',
      onSelected: (v) {
        if (v == 'cancelar') _confirmarCancelar(context, reserva, cancha);
      },
      itemBuilder: (_) => [
        PopupMenuItem(
          value: 'cancelar',
          child: Row(
            children: [
              Icon(historial ? Icons.delete_outline : Icons.cancel_outlined,
                  size: 18, color: clayOscuro),
              const SizedBox(width: 10),
              Text(historial ? 'Quitar del historial' : 'Cancelar reserva'),
            ],
          ),
        ),
      ],
    );
  }
}

/// ¿La reserva se PAGÓ EN LÍNEA (Culqi/Yape, en el app o en la web)? Esas se
/// cancelan a través del backend con la política de devoluciones; las que se
/// pagan en la cancha o el historial se resuelven en el teléfono.
bool _pagadaEnLinea(Reserva r) =>
    r.pagado && (r.medioPago == 'yape' || r.medioPago == 'tarjeta');

/// Confirma y ejecuta la cancelación/eliminación de una reserva del jugador.
Future<void> _confirmarCancelar(
    BuildContext context, Reserva r, Cancha? cancha) async {
  final historial = _esHistorial(r);
  if (!historial && _pagadaEnLinea(r)) {
    await _cancelarPagadaEnLinea(context, r, cancha);
    return;
  }
  final ok = await confirmarPichangol(
    context,
    titulo: historial ? '¿Quitar del historial?' : '¿Cancelar esta reserva?',
    mensaje: historial
        ? 'Se eliminará esta reserva de tu historial. No se puede deshacer.'
        : 'Se liberará el horario ${r.diaVisible} ${r.horaInicio}–${r.horaFin} y '
                'dejará de aparecer en tus reservas.'
            '${r.sena > 0 && !r.pagado ? '\n\nLa seña de ${r.monedaSimbolo} ${r.sena} que adelantaste NO se devuelve (queda para el local); el resto ya no lo pagas.' : ''}'
            '${r.pagado ? '\n\nEsta reserva ya está pagada: la cancelación no genera reembolso automático.' : ''}',
    textoConfirmar: historial ? 'Sí, quitar' : 'Sí, cancelar',
    textoCancelar: 'No',
    destructivo: historial,
    icono: Icons.event_busy_outlined,
  );
  if (!ok) return;
  await appState.cancelarReserva(r);
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: bosque,
      content: Text(historial
          ? 'Reserva eliminada del historial.'
          : 'Reserva cancelada. El horario quedó libre.'),
    ));
  }
}

/// Cancelación de una reserva PAGADA EN LÍNEA: la misma política de
/// devoluciones que la web (`pagos/devoluciones.py`). (1) Pide al backend qué
/// pasa si cancela ahora (a saldo 100 % con cargo · al medio original solo el
/// precio · arrepentimiento 100 % · tarde sin devolución); (2) muestra la hoja
/// con las opciones; (3) el backend cancela, devuelve, libera el horario y
/// avisa por push; (4) el app quita su copia local. Sin red NO se cancela:
/// hay plata en juego y la devolución la decide el servidor.
Future<void> _cancelarPagadaEnLinea(
    BuildContext context, Reserva r, Cancha? cancha) async {
  final email = appState.usuario?.email.trim().toLowerCase() ?? '';
  if (email.isEmpty) {
    await avisarPichangol(context,
        titulo: 'Inicia sesión',
        mensaje: 'Para cancelar una reserva pagada necesitamos tu cuenta.',
        icono: Icons.lock_outline);
    return;
  }
  final ref = r.grupoReservaId.isNotEmpty ? r.grupoReservaId : r.id;
  final est = await _conEspera(
      context, 'Consultando la política de cancelación…',
      () => PagosService.estadoCancelacionReserva(ref, email));
  if (!context.mounted) return;
  if (est == null) {
    await avisarPichangol(context,
        titulo: 'Sin conexión',
        mensaje:
            'No pudimos consultar tu devolución. Revisa tu conexión e inténtalo de nuevo: '
            'una reserva pagada solo se cancela con el servidor en línea.',
        icono: Icons.wifi_off_outlined);
    return;
  }
  if (est['puede'] != true) {
    const motivos = {
      'ya_empezo': 'El turno ya empezó o ya pasó: ya no se puede cancelar.',
      'ya_cancelada': 'Esta reserva ya estaba cancelada.',
      'ajena': 'Esta reserva no es de tu cuenta.',
      'sin_reserva':
          'No encontramos esta reserva en el servidor. Si ya la cancelaste en otro equipo, desliza para actualizar.',
    };
    await avisarPichangol(context,
        titulo: 'No se puede cancelar',
        mensaje: motivos[est['motivo']] ?? 'No se pudo cancelar la reserva.',
        icono: Icons.event_busy_outlined);
    return;
  }
  final medio = await showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Theme.of(context).colorScheme.surface,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (_) => _HojaCancelarOnline(reserva: r, cancha: cancha, estado: est),
  );
  if (medio == null || !context.mounted) return;
  final res = await _conEspera(context, 'Cancelando tu reserva…',
      () => PagosService.cancelarReservaOnline(
          ref: ref, email: email, medio: medio));
  if (!context.mounted) return;
  if (res == null) {
    await avisarPichangol(context,
        titulo: 'Sin conexión',
        mensaje: 'No pudimos cancelar. Tu reserva sigue vigente; inténtalo de nuevo.',
        icono: Icons.wifi_off_outlined);
    return;
  }
  if (res['ok'] != true) {
    await avisarPichangol(context,
        titulo: 'No se pudo cancelar',
        mensaje: (res['mensaje'] ?? 'Inténtalo de nuevo.').toString(),
        icono: Icons.error_outline);
    return;
  }
  // El backend ya liberó el horario y avisó al dueño: solo limpiamos la copia.
  await appState.cancelarReserva(r, enNube: false);
  final mon = r.monedaSimbolo;
  final dev = ((res['monto_devuelto'] ?? 0) as num).toDouble();
  final devTxt = '$mon ${dev.toStringAsFixed(2)}';
  final reembolso = (res['reembolso'] ?? '').toString();
  final incluyeCargo = res['incluye_cargo'] == true;
  final msg = switch (reembolso) {
    'saldo' =>
      'Reserva cancelada. Te devolvimos $devTxt a tu saldo Pichangol (cargo incluido): ya lo puedes usar.',
    'reembolsado' =>
      'Reserva cancelada. Te devolvemos $devTxt al mismo medio de pago en 3 a 7 días hábiles.'
          '${!incluyeCargo && r.cargoServicio > 0 ? ' El cargo por servicio no se devuelve.' : ''}',
    'manual' =>
      'Reserva cancelada. Te devolvemos $devTxt; te escribimos para coordinar.',
    'fallo' =>
      'Reserva cancelada. Tu devolución está en proceso; te escribimos en breve.',
    'sin_reembolso' => 'Reserva cancelada sin devolución.',
    _ => 'Reserva cancelada. El horario quedó libre.',
  };
  if (reembolso == 'saldo') unawaited(appState.sincronizarSaldo());
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: bosque,
        duration: const Duration(seconds: 6),
        content: Text(msg)));
  }
}

/// Velo con spinner (preloader) mientras se espera al servidor; se cierra
/// solo al terminar. Devuelve lo que devuelva [accion].
Future<T> _conEspera<T>(
    BuildContext context, String texto, Future<T> Function() accion) async {
  var abierto = true;
  unawaited(showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => PopScope(
      canPop: false,
      child: Center(
        child: Material(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 22, 22, 20),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const SizedBox(
                  width: 34,
                  height: 34,
                  child: CircularProgressIndicator(strokeWidth: 3, color: lima)),
              const SizedBox(height: 14),
              Text(texto,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, color: tinta, fontSize: 14)),
            ]),
          ),
        ),
      ),
    ),
  ).then((_) => abierto = false));
  try {
    return await accion();
  } finally {
    if (abierto && context.mounted) Navigator.of(context, rootNavigator: true).pop();
  }
}

/// Hoja "Cancelar reserva" de una reserva pagada en línea (mismo contenido que
/// el modal de la web): qué pasa, y si hay devolución, A DÓNDE va
/// ("A tu saldo Pichangol · Recomendado" / "Al mismo medio de pago"), cada
/// opción con su monto y su nota. Devuelve el medio elegido o null.
class _HojaCancelarOnline extends StatefulWidget {
  const _HojaCancelarOnline(
      {required this.reserva, required this.cancha, required this.estado});
  final Reserva reserva;
  final Cancha? cancha;
  final Map<String, dynamic> estado;

  @override
  State<_HojaCancelarOnline> createState() => _HojaCancelarOnlineState();
}

class _HojaCancelarOnlineState extends State<_HojaCancelarOnline> {
  String? _medio;

  List<Map<String, dynamic>> get _opciones {
    final pol = widget.estado['politica'];
    if (pol is! Map) return const [];
    return ((pol['opciones'] as List?) ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  }

  String get _motivo =>
      ((widget.estado['politica'] as Map?)?['motivo'] ?? '').toString();

  bool get _reembolsable =>
      widget.estado['reembolsable'] == true && _opciones.isNotEmpty;

  @override
  void initState() {
    super.initState();
    if (_reembolsable) _medio = _opciones.first['medio']?.toString();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final r = widget.reserva;
    final est = widget.estado;
    final mon = r.monedaSimbolo;
    final horas = ((est['horas'] ?? 0) as num).toDouble();
    final minimo = ((est['minimo_horas'] ?? 6) as num).toInt();
    final totalPagado = ((est['total_pagado'] ?? r.totalPagado) as num).toDouble();
    final pol = (est['politica'] as Map?) ?? const {};
    final arrepHoras = ((pol['arrepentimiento_horas'] ?? 1) as num);
    final nombre = widget.cancha?.club.isNotEmpty == true
        ? widget.cancha!.club
        : (widget.cancha?.nombre ?? 'la reserva');
    final String explicacion;
    final Color fondo, frente;
    if (_reembolsable) {
      fondo = estadoOkBg;
      frente = estadoOkFg;
      explicacion = _motivo == 'arrepentimiento'
          ? 'Pagaste hace menos de ${arrepHoras.toStringAsFixed(arrepHoras == arrepHoras.roundToDouble() ? 0 : 1)} h y faltan más de 24 h: te devolvemos el 100 %, cargo por servicio incluido, por el medio que elijas.'
          : 'Faltan ${horas.toStringAsFixed(horas >= 10 ? 0 : 1)} h para tu turno: puedes cancelar con devolución. Elige a dónde te la mandamos.';
    } else {
      fondo = estadoBadBg;
      frente = estadoBadFg;
      explicacion =
          'Faltan menos de $minimo h para el turno: la cancelación NO tiene devolución (política publicada). Puedes mantener la reserva y jugar.';
    }
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
            20, 12, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                        color: trazo, borderRadius: BorderRadius.circular(2))),
              ),
              const SizedBox(height: 18),
              Text('¿Cancelar $nombre?',
                  style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text(
                  '${r.diaVisible} · ${r.horaInicio}–${r.horaFin} · pagaste $mon ${totalPagado.toStringAsFixed(2)}',
                  style: t.bodyMedium?.copyWith(color: textoTenue)),
              const SizedBox(height: 14),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: fondo, borderRadius: BorderRadius.circular(14)),
                child: Text(explicacion,
                    style: t.bodyMedium?.copyWith(
                        color: frente, fontWeight: FontWeight.w600, height: 1.35)),
              ),
              if (_reembolsable) ...[
                const SizedBox(height: 16),
                Text('¿A dónde te devolvemos?',
                    style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                for (var i = 0; i < _opciones.length; i++)
                  _OpcionDevolucion(
                    opcion: _opciones[i],
                    recomendada: i == 0,
                    seleccionada: _medio == _opciones[i]['medio'],
                    onTap: () => setState(
                        () => _medio = _opciones[i]['medio']?.toString()),
                  ),
              ],
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.of(context).pop(),
                      style: OutlinedButton.styleFrom(
                          foregroundColor: tinta,
                          side: const BorderSide(color: trazo),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      child: const Text('Mantener reserva',
                          style: TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton(
                      onPressed: () =>
                          Navigator.of(context).pop(_medio ?? 'original'),
                      style: FilledButton.styleFrom(
                          backgroundColor: _reembolsable ? bosque : clayOscuro,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14))),
                      child: Text(
                          _reembolsable
                              ? 'Sí, cancelar'
                              : 'Cancelar sin devolución',
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Una opción de devolución (tarjeta seleccionable estilo Airbnb: borde suave,
/// tinte esmeralda al elegir, nunca borde negro).
class _OpcionDevolucion extends StatelessWidget {
  const _OpcionDevolucion(
      {required this.opcion,
      required this.recomendada,
      required this.seleccionada,
      required this.onTap});
  final Map<String, dynamic> opcion;
  final bool recomendada;
  final bool seleccionada;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final mon = (opcion['simbolo'] ?? 'S/').toString();
    final monto = ((opcion['monto'] ?? 0) as num).toDouble();
    final esSaldo = opcion['medio'] == 'saldo';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
          decoration: BoxDecoration(
            color: seleccionada ? limaSuave : Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: seleccionada ? lima : trazo, width: 1),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 1),
                child: Icon(
                    seleccionada
                        ? Icons.radio_button_checked
                        : Icons.radio_button_off,
                    size: 20,
                    color: seleccionada ? lima : textoTenue),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                            esSaldo
                                ? Icons.account_balance_wallet_outlined
                                : Icons.credit_card_outlined,
                            size: 18,
                            color: tinta),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                              '${opcion['etiqueta'] ?? ''} · $mon ${monto.toStringAsFixed(2)}',
                              style: t.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w800, height: 1.2)),
                        ),
                      ],
                    ),
                    if (recomendada)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                              color: estadoOkBg,
                              borderRadius: BorderRadius.circular(999)),
                          child: const Text('Recomendado',
                              style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
                                  color: estadoOkFg)),
                        ),
                      ),
                    const SizedBox(height: 4),
                    Text((opcion['nota'] ?? '').toString(),
                        style: t.bodySmall
                            ?.copyWith(color: textoTenue, height: 1.3)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Hoja "pase de reserva": el DETALLE que ve el jugador al tocar una reserva o
/// pulsar "Ver pase". Muestra los datos y permite "Cómo llegar".
void _mostrarPase(BuildContext context, Reserva reserva, Cancha? cancha) {
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: Theme.of(context).colorScheme.surface,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) {
      final t = Theme.of(ctx).textTheme;
      final dep = cancha?.deporte ?? Deporte.futbol;
      final id = reserva.id;
      final codigo = (id.length > 6 ? id.substring(id.length - 6) : id)
          .toUpperCase();
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                        color: trazo,
                        borderRadius: BorderRadius.circular(999))),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Container(
                    width: 54,
                    height: 54,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(
                        gradient: gradienteDeporte(dep),
                        borderRadius: BorderRadius.circular(14)),
                    child: const CourtLines(opacity: 0.5),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(cancha?.nombre ?? 'Cancha',
                            style: t.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        Text(cancha?.club ?? dep.etiqueta,
                            style:
                                t.bodySmall?.copyWith(color: textoTenue)),
                      ],
                    ),
                  ),
                  _EstadoChip(estado: reserva.estado, reservaId: reserva.id),
                ],
              ),
              const SizedBox(height: 18),
              // Local + FECHA REAL + hora (pedido del director): la fecha sale
              // del ISO de la reserva ("mié 19 ago"), no de la etiqueta "Hoy"
              // que envejece mal.
              _PaseFila(
                  Icons.storefront_outlined,
                  'Local',
                  (cancha != null && cancha.club.trim().isNotEmpty)
                      ? cancha.club
                      : (cancha?.nombre ?? '—')),
              _PaseFila(Icons.event_outlined, 'Fecha',
                  AppState.fechaBonita(reserva.fecha)),
              _PaseFila(Icons.schedule, 'Hora',
                  '${reserva.horaInicio}–${reserva.horaFin}'),
              _PaseFila(Icons.sports_soccer, 'Deporte', dep.etiqueta),
              _PaseFila(
                  Icons.payments_outlined,
                  'Precio',
                  '${reserva.monedaSimbolo}${reserva.precio} · '
                  '${reserva.medioPago == 'fidelidad' ? 'gratis · premio de fidelidad 🎁' : reserva.pagado ? 'pagado ✓' : reserva.sena > 0 ? 'seña pagada, resto en la cancha' : 'pagas en la cancha'}'),
              // BOLEADOR contratado con la reserva (módulo Boleadores): quién y
              // en qué quedó (esperando confirmación / confirmado / devuelto).
              for (final x in reserva.extras.where((x) => x.esBoleador))
                _PaseFila(
                    Icons.sports_tennis,
                    'Boleador',
                    '${x.nombre.replaceFirst('Boleador · ', '')} · '
                    '${reserva.monedaSimbolo}${x.precio.toStringAsFixed(2)} · '
                    '${Boleadores.deReserva(reserva)?.etiquetaEstado ?? (x.estado.isEmpty ? 'esperando confirmación' : x.estado)}'),
              // Cargo por servicio Pichangol (si lo pagó): línea aparte, total
              // pagado y el desglose con un toque, como en el comprobante web.
              if (reserva.cargoServicio > 0) ...[
                InkWell(
                  onTap: () => mostrarDesgloseCargo(
                      context,
                      CotizacionCargo.congelada(
                          linea: 'reservas',
                          moneda: reserva.monedaSimbolo,
                          baseSoles: reserva.totalConExtras,
                          cargoSoles: reserva.cargoServicio,
                          desglose: reserva.cargoDesglose),
                      simbolo: reserva.monedaSimbolo),
                  child: _PaseFila(
                      Icons.verified_user_outlined,
                      'Cargo por servicio',
                      '${reserva.monedaSimbolo}${reserva.cargoServicio.toStringAsFixed(2)} · toca para ver qué incluye'),
                ),
                _PaseFila(Icons.receipt_long_outlined, 'Total pagado',
                    '${reserva.monedaSimbolo}${reserva.totalPagado.toStringAsFixed(2)}'),
              ],
              // Puntos de ESTA reserva: acreditados si ya está pagada; si es
              // efectivo sin marcar, el jugador sabe cuántos están en juego.
              if (reserva.traidaPorApp &&
                  reserva.estado != EstadoReserva.noShow)
                _PaseFila(
                    Icons.stars,
                    'Puntos',
                    reserva.pagado
                        ? '+${reserva.totalConExtras.round()} ⭐'
                        : '+${reserva.totalConExtras.round()} al confirmarse tu pago'),
              _PaseFila(Icons.confirmation_number_outlined, 'Código', codigo),
              const SizedBox(height: 18),
              if (cancha != null)
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14)),
                    onPressed: () {
                      Navigator.pop(ctx);
                      UbicacionShare.abrirMapa(cancha.ubicacion);
                    },
                    icon: const Icon(Icons.directions, size: 18),
                    label: const Text('Cómo llegar'),
                  ),
                ),
            ],
          ),
        ),
      );
    },
  );
}

/// Una fila del pase: ícono + etiqueta + valor.
class _PaseFila extends StatelessWidget {
  const _PaseFila(this.icono, this.label, this.valor);
  final IconData icono;
  final String label;
  final String valor;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          IconoVivo(icono, size: 18, color: lima),
          const SizedBox(width: 12),
          Text(label,
              style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          const SizedBox(width: 16),
          Expanded(
            child: Text(valor,
                textAlign: TextAlign.right,
                style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

/// Chip de estado de la reserva (Confirmada/Jugada/No-show). Con [reservaId] además
/// refleja el estado de SINCRONIZACIÓN offline: "Pendiente de confirmar" (aún no
/// llegó al servidor) o "No se confirmó" (el slot lo tomó otro / sincronizó tarde).
class _EstadoChip extends StatelessWidget {
  const _EstadoChip({required this.estado, this.reservaId = ''});
  final EstadoReserva estado;
  final String reservaId;

  @override
  Widget build(BuildContext context) {
    // Estado de sincronización tiene prioridad sobre el estado del booking.
    if (reservaId.isNotEmpty && appState.reservaPendienteSync(reservaId)) {
      return _pill('⏳  Pendiente de confirmar',
          const Color(0xFFFBEAD2), const Color(0xFF8A5A00));
    }
    if (reservaId.isNotEmpty && appState.reservaNoConfirmada(reservaId)) {
      return _pill('⚠️  No se confirmó', estadoBadBg, estadoBadFg);
    }
    final (bg, fg) = switch (estado) {
      EstadoReserva.confirmada || EstadoReserva.nueva => (estadoOkBg, estadoOkFg),
      EstadoReserva.noShow => (estadoBadBg, estadoBadFg),
      _ => (estadoNeutroBg, estadoNeutroFg),
    };
    // Emoji vivo por estado (mismo lenguaje que las notificaciones).
    final emoji = switch (estado) {
      EstadoReserva.confirmada || EstadoReserva.nueva => '✅',
      EstadoReserva.completada => '🏁',
      EstadoReserva.noShow => '🚫',
    };
    return _pill('$emoji  ${_estadoLabel(estado)}', bg, fg);
  }

  static Widget _pill(String texto, Color bg, Color fg) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
        decoration:
            BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
        child: Text(texto,
            style:
                TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700)),
      );
}

String _estadoLabel(EstadoReserva e) => switch (e) {
      EstadoReserva.confirmada || EstadoReserva.nueva => 'Confirmada',
      EstadoReserva.completada => 'Jugada',
      EstadoReserva.noShow => 'No-show',
    };

class _Vacio extends StatelessWidget {
  const _Vacio({this.historial = false});
  final bool historial;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const IlustracionPichangol(
                clave: 'reservas_vacias', emoji: '🎾', size: 120),
            const SizedBox(height: 16),
            Text(
                historial ? 'Sin reservas anteriores' : 'Aún no tienes reservas',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(
              historial
                  ? 'Aquí verás tus partidos ya jugados.'
                  : 'Busca una cancha en el mapa y reserva tu próximo partido.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: textoTenue),
            ),
          ],
        ),
      ),
    );
  }
}
