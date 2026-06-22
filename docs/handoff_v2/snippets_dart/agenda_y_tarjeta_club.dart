// ─────────────────────────────────────────────────────────────────────────
// SNIPPETS DART (parte 2) — Pichangol rediseño
//
//   C) ClubAgendaScreen → agenda del panel del club con SELECTOR de cancha
//                         (un local con varias canchas / deportes)
//   D) ClubCard          → tarjeta de club para el listado y el sheet del mapa
//
// Referencia para pegar en lib/screens/ y lib/widgets/. Ajustar a tus models
// reales (Club, Cancha, Deporte, ReservaFranja). Usa tokens de theme.dart.
// ─────────────────────────────────────────────────────────────────────────

import 'package:flutter/material.dart';

import '../theme.dart';
import '../models/models.dart';

// ===========================================================================
// C) AGENDA DEL CLUB — cambiar entre las canchas del local
// ===========================================================================
class ClubAgendaScreen extends StatefulWidget {
  const ClubAgendaScreen({super.key, required this.club});
  final Club club;

  @override
  State<ClubAgendaScreen> createState() => _ClubAgendaScreenState();
}

class _ClubAgendaScreenState extends State<ClubAgendaScreen> {
  late Cancha _cancha = widget.club.canchas.first;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: papelCalido,
      body: Column(children: [
        // ── Header pino: club + saldo + mini-KPIs ──────────────────────────
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(22, 56, 22, 20),
          decoration: const BoxDecoration(
            color: tinta,
            borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Buenas, ${widget.club.barrio}',
                  style: t.bodyMedium?.copyWith(color: Colors.white70)),
                Text(widget.club.nombre,
                  style: t.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
              ]),
              // chip de saldo prepago
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: lima.withOpacity(0.16),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: lima.withOpacity(0.4)),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('Saldo', style: t.bodySmall?.copyWith(color: lima)),
                  Text('S/${widget.club.saldo}',
                    style: t.titleMedium?.copyWith(color: lima, fontWeight: FontWeight.w700)),
                ]),
              ),
            ]),
            const SizedBox(height: 18),
            Row(children: [
              _MiniKpi('${widget.club.reservasHoy}', 'Reservas hoy'),
              const SizedBox(width: 10),
              _MiniKpi('${widget.club.ocupacionPct}%', 'Ocupación'),
              const SizedBox(width: 10),
              _MiniKpi('+${widget.club.porApp}', 'Por la app', accent: true),
            ]),
          ]),
        ),

        // ── Selector de cancha (multi-deporte) ──────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
          child: Row(children: [
            Expanded(
              child: SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: widget.club.canchas.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (_, i) {
                    final c = widget.club.canchas[i];
                    final sel = c == _cancha;
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
                        child: Row(children: [
                          Container(width: 9, height: 9, decoration: BoxDecoration(
                            color: colorDeporte(c.deporte), borderRadius: BorderRadius.circular(2))),
                          const SizedBox(width: 7),
                          Text(c.nombre, style: t.bodyMedium?.copyWith(
                            color: sel ? Colors.white : tinta,
                            fontWeight: sel ? FontWeight.w700 : FontWeight.w600)),
                        ]),
                      ),
                    );
                  },
                ),
              ),
            ),
          ]),
        ),

        // ── Lista de franjas de la cancha seleccionada ──────────────────────
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 24),
            itemCount: _cancha.agendaHoy.length,
            separatorBuilder: (_, __) => const SizedBox(height: 9),
            itemBuilder: (_, i) => _AgendaRow(item: _cancha.agendaHoy[i]),
          ),
        ),
      ]),
    );
  }
}

/// Fila de la agenda: hora + estado (reserva, nueva por app, libre con toggle, fija).
class _AgendaRow extends StatelessWidget {
  const _AgendaRow({required this.item});
  final AgendaItem item;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final esNuevaApp = item.estado == EstadoFranja.nuevaApp;
    return Container(
      padding: const EdgeInsets.fromLTRB(15, 13, 15, 13),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border(left: BorderSide(
          color: esNuevaApp ? lima : Colors.transparent, width: 4)),
        boxShadow: const [BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, 4))],
      ),
      child: Row(children: [
        SizedBox(width: 48, child: Column(children: [
          Text(item.hora, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          if (item.valle) Text('VALLE', style: t.labelSmall?.copyWith(color: clayOscuro, fontWeight: FontWeight.w700)),
        ])),
        Container(width: 1, height: 38, color: trazo, margin: const EdgeInsets.symmetric(horizontal: 12)),
        Expanded(child: switch (item.estado) {
          EstadoFranja.libre => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Disponible', style: t.bodyMedium?.copyWith(color: const Color(0xFFB5AFA3), fontWeight: FontWeight.w600)),
              Text('Abierta en la app', style: t.bodySmall?.copyWith(color: const Color(0xFFC2BCB0))),
            ]),
          _ => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(item.cliente ?? '', style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
              if (item.subtitulo != null) Text(item.subtitulo!, style: t.bodySmall?.copyWith(color: textoTenue)),
            ]),
        }),
        switch (item.estado) {
          EstadoFranja.libre => _Switch(on: item.abiertaApp), // toggle abrir/cerrar en app
          EstadoFranja.nuevaApp => _Badge('NUEVA · APP', bg: lima, fg: pinoOscuro),
          EstadoFranja.fija => _Badge('FIJO', bg: const Color(0xFFF0ECE2), fg: const Color(0xFF5C574E)),
          _ => const SizedBox.shrink(),
        },
      ]),
    );
  }
}

// ===========================================================================
// D) TARJETA DE CLUB — listado y sheet del mapa (nivel local, multi-deporte)
// ===========================================================================
class ClubCard extends StatelessWidget {
  const ClubCard({super.key, required this.club, this.compact = false, this.onTap});
  final Club club;
  final bool compact; // true = versión chica para el sheet del mapa
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final portada = club.canchas.first.deporte; // deporte de la portada
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFFEEEAE0)),
          boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 20, offset: Offset(0, 6))],
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // portada con gradiente de deporte + badge + corazón
          Stack(children: [
            Container(height: compact ? 0 : 128,
              decoration: BoxDecoration(gradient: gradienteDeporte(portada)),
              child: const _CourtLines()),
            if (!compact) Positioned(top: 14, left: 14,
              child: _Badge('CLUB FUNDADOR', bg: pino, fg: lima)),
            if (!compact) const Positioned(top: 14, right: 14, child: _HeartButton()),
          ]),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text(club.nombre, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                Text('★ ${club.rating}', style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
              ]),
              const SizedBox(height: 2),
              Text('${club.barrio} · ${club.distancia} · ${club.canchas.length} canchas',
                style: t.bodySmall?.copyWith(color: textoTenue)),
              const SizedBox(height: 8),
              // chips de DEPORTES del club
              Wrap(spacing: 6, children: [
                for (final d in club.deportes)
                  _Badge(d.label, bg: const Color(0xFFF0ECE2), fg: const Color(0xFF5C574E)),
              ]),
              const SizedBox(height: 12),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, crossAxisAlignment: CrossAxisAlignment.end, children: [
                RichText(text: TextSpan(style: t.bodySmall?.copyWith(color: textoTenue), children: [
                  const TextSpan(text: 'desde '),
                  TextSpan(text: 'S/${club.precioDesde}',
                    style: t.titleMedium?.copyWith(color: tinta, fontWeight: FontWeight.w700)),
                  const TextSpan(text: ' /hora'),
                ])),
                // pastilla verde "N horas hoy"
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(color: lima, borderRadius: BorderRadius.circular(9)),
                  child: Text('${club.horasHoy} horas hoy',
                    style: t.bodySmall?.copyWith(color: pinoOscuro, fontWeight: FontWeight.w700)),
                ),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ── widgets de apoyo (implementar con tokens del theme) ────────────────────
// _MiniKpi(valor,label,{accent})  → bloque de KPI en el header pino
// _Switch(on)                     → toggle "abierta en la app" (track lima)
// _Badge(text,{bg,fg})            → píldora de etiqueta
// _CourtLines()                   → líneas de cancha con CustomPaint
// _HeartButton()                  → botón favorito translúcido sobre la portada
//
// Tipos de modelo de apoyo a mapear a tus models reales:
//   enum EstadoFranja { reserva, nuevaApp, libre, fija }
//   class AgendaItem { String hora; bool valle; EstadoFranja estado;
//                      String? cliente, subtitulo; bool abiertaApp; }
//   extension on Deporte { String get label => switch (this) {
//       Deporte.tenis => 'Tenis', Deporte.padel => 'Pádel', Deporte.futbol => 'Fútbol' }; }
