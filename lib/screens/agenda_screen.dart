import 'package:flutter/material.dart';

import '../data/sample_data.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Agenda del panel del club (rediseño): header pino con saldo + mini-KPIs,
/// selector de cancha (un local con varias canchas) y franjas del día.
class AgendaScreen extends StatefulWidget {
  const AgendaScreen({super.key});

  @override
  State<AgendaScreen> createState() => _AgendaScreenState();
}

class _AgendaScreenState extends State<AgendaScreen> {
  late Cancha _cancha = SampleData.canchasDelClubActivo().first;

  @override
  Widget build(BuildContext context) {
    final canchas = SampleData.canchasDelClubActivo();
    return Scaffold(
      backgroundColor: papelCalido,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          final res = appState.simularReservaEntrante();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(res != null
                  ? '⚡ ¡Entró una reserva! $res'
                  : 'No quedan horas libres abiertas'),
            ),
          );
        },
        backgroundColor: clay,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.bolt),
        label: const Text('Simular reserva'),
      ),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final bloques = appState.bloquesDe(_cancha.id);
          return Column(
            children: [
              _HeaderClub(canchas: canchas),
              // Selector de cancha (multi-deporte)
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
                child: SizedBox(
                  height: 40,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: canchas.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 8),
                    itemBuilder: (_, i) {
                      final c = canchas[i];
                      final sel = c.id == _cancha.id;
                      return GestureDetector(
                        onTap: () => setState(() => _cancha = c),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14),
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: sel ? tinta : Colors.white,
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(color: sel ? tinta : trazo),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 9,
                                height: 9,
                                decoration: BoxDecoration(
                                    color: colorDeporte(c.deporte),
                                    borderRadius: BorderRadius.circular(2)),
                              ),
                              const SizedBox(width: 7),
                              Text(c.nombre,
                                  style: TextStyle(
                                      color: sel ? Colors.white : tinta,
                                      fontWeight: sel
                                          ? FontWeight.w700
                                          : FontWeight.w600)),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(18, 8, 18, 90),
                  itemCount: bloques.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 9),
                  itemBuilder: (_, i) => _AgendaRow(bloque: bloques[i]),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _HeaderClub extends StatelessWidget {
  const _HeaderClub({required this.canchas});
  final List<Cancha> canchas;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final barrio = canchas.isEmpty ? 'Lima' : canchas.first.distrito.etiqueta;

    // Mini-KPIs de hoy.
    final idsClub = canchas.map((c) => c.id).toSet();
    final reservasHoy = appState.reservas
        .where((r) => r.dia == 'Hoy' && idsClub.contains(r.canchaId))
        .toList();
    final bloquesHoy = appState.agenda.length;
    final ocupados = appState.agenda.where((b) => b.reservaId != null).length;
    final ocupacion = bloquesHoy == 0 ? 0 : (ocupados * 100) ~/ bloquesHoy;
    final porApp = reservasHoy.where((r) => r.traidaPorApp).length;

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 18 + MediaQuery.of(context).padding.top, 22, 20),
      decoration: const BoxDecoration(
        color: pino,
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                onTap: () => Navigator.of(context).maybePop(),
                child: const Padding(
                  padding: EdgeInsets.only(right: 12, top: 2),
                  child: Icon(Icons.arrow_back_ios_new,
                      color: Colors.white, size: 20),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Buenas, $barrio',
                        style: t.bodyMedium
                            ?.copyWith(color: Colors.white70)),
                    Text(appState.nombreClub,
                        style: t.titleLarge?.copyWith(
                            color: Colors.white, fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: lima.withOpacity(0.16),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: lima.withOpacity(0.4)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('Saldo', style: t.bodySmall?.copyWith(color: lima)),
                    Text('S/${appState.saldoClub}',
                        style: t.titleMedium?.copyWith(
                            color: lima, fontWeight: FontWeight.w700)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _MiniKpi('${reservasHoy.length}', 'Reservas hoy'),
              const SizedBox(width: 10),
              _MiniKpi('$ocupacion%', 'Ocupación'),
              const SizedBox(width: 10),
              _MiniKpi('+$porApp', 'Por la app', accent: true),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniKpi extends StatelessWidget {
  const _MiniKpi(this.valor, this.label, {this.accent = false});
  final String valor;
  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.08),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(valor,
                style: t.titleLarge?.copyWith(
                    color: accent ? lima : Colors.white,
                    fontWeight: FontWeight.w700)),
            Text(label,
                style: t.bodySmall?.copyWith(color: Colors.white70)),
          ],
        ),
      ),
    );
  }
}

class _AgendaRow extends StatelessWidget {
  const _AgendaRow({required this.bloque});
  final BloqueHorario bloque;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final reserva =
        bloque.reservaId != null ? appState.reservaPorId(bloque.reservaId!) : null;
    final esNuevaApp =
        reserva != null && reserva.traidaPorApp && reserva.estado == EstadoReserva.nueva;
    final esFija = reserva != null && !reserva.traidaPorApp;

    return Container(
      padding: const EdgeInsets.fromLTRB(15, 13, 15, 13),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border(
            left: BorderSide(
                color: esNuevaApp ? lima : Colors.transparent, width: 4)),
        boxShadow: const [
          BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          SizedBox(
            width: 50,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(bloque.hora,
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                if (bloque.esHoraValle)
                  Text('VALLE',
                      style: t.labelSmall?.copyWith(
                          color: clayOscuro, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          Container(width: 1, height: 38, color: trazo,
              margin: const EdgeInsets.symmetric(horizontal: 12)),
          Expanded(
            child: reserva == null
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Disponible',
                          style: t.bodyMedium?.copyWith(
                              color: const Color(0xFFB5AFA3),
                              fontWeight: FontWeight.w600)),
                      Text(bloque.disponible
                          ? 'Abierta en la app'
                          : 'Cerrada en la app',
                          style: t.bodySmall
                              ?.copyWith(color: const Color(0xFFC2BCB0))),
                    ],
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(reserva.jugador,
                          style: t.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      Text(
                        '${reserva.traidaPorApp ? "Por la app" : "Cliente de siempre"} · ${reserva.horaInicio}–${reserva.horaFin}',
                        style: t.bodySmall?.copyWith(color: textoTenue),
                      ),
                    ],
                  ),
          ),
          if (reserva == null)
            Switch(
              value: bloque.disponible,
              activeColor: pino,
              activeTrackColor: lima,
              onChanged: (_) => appState.alternarDisponibilidad(bloque),
            )
          else if (esNuevaApp)
            const _Badge('NUEVA · APP', bg: lima, fg: pinoOscuro)
          else if (esFija)
            const _Badge('FIJO', bg: Color(0xFFF0ECE2), fg: Color(0xFF5C574E))
          else
            const _Badge('APP', bg: Color(0xFFEAF6C2), fg: pinoOscuro),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.texto, {required this.bg, required this.fg});
  final String texto;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(texto,
          style: TextStyle(
              color: fg, fontSize: 11, fontWeight: FontWeight.w700, height: 1)),
    );
  }
}
