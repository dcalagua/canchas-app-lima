// ─────────────────────────────────────────────────────────────────────────
// SNIPPETS DART DE ARRANQUE — Pichangol rediseño
//
// Código de referencia para 2 piezas clave del flujo nuevo:
//   A) ClubDetailScreen  → ficha de club con SELECTOR de canchas (multi-deporte)
//   B) GoogleLoginSheet   → hoja de login (solo Google) al pulsar Reservar
//
// Pensado para pegarse en lib/screens/ y adaptarse a tus models reales
// (Club, Cancha, Deporte). Usa los tokens de theme.dart (pino, lima, clay…).
// No pretende compilar 1:1 sin ajustar imports/tipos a tu proyecto.
// ─────────────────────────────────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../theme.dart';
import '../models/models.dart';

// ===========================================================================
// A) FICHA DE CLUB — un local con varias canchas / deportes
// ===========================================================================
class ClubDetailScreen extends StatefulWidget {
  const ClubDetailScreen({super.key, required this.club});
  final Club club; // club.canchas: List<Cancha>; cada Cancha tiene deporte, precioHora, nombre

  @override
  State<ClubDetailScreen> createState() => _ClubDetailScreenState();
}

class _ClubDetailScreenState extends State<ClubDetailScreen> {
  late Cancha _cancha = widget.club.canchas.first; // cancha seleccionada
  int? _horaSel; // índice de franja elegida

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: papel,
      body: CustomScrollView(
        slivers: [
          // Hero con gradiente del deporte de la cancha seleccionada
          SliverAppBar(
            pinned: false,
            expandedHeight: 300,
            backgroundColor: colorDeporte(_cancha.deporte),
            leading: const _RoundIcon(Icons.arrow_back_ios_new),
            actions: const [
              _RoundIcon(Icons.ios_share),
              _RoundIcon(Icons.favorite_border),
              SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: DecoratedBox(
                decoration: BoxDecoration(gradient: gradienteDeporte(_cancha.deporte)),
                child: const _CourtLines(), // líneas de cancha dibujadas
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(22, 18, 22, 120),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // badges
                  Row(children: [
                    _Badge('CLUB FUNDADOR', bg: pino, fg: lima),
                    const SizedBox(width: 6),
                    _Badge('DIGITALIZADA', bg: const Color(0xFFF0ECE2), fg: const Color(0xFF5C574E)),
                  ]),
                  const SizedBox(height: 12),
                  // nombre del CLUB (no de la cancha) + deportes
                  Text(widget.club.nombre, style: t.headlineSmall),
                  const SizedBox(height: 2),
                  Text(
                    '${widget.club.barrio} · ${widget.club.canchas.length} canchas · '
                    '${widget.club.deportes.map((d) => d.label).join(' · ')}',
                    style: t.bodyMedium?.copyWith(color: textoTenue),
                  ),
                  const SizedBox(height: 18),

                  // ── SELECTOR "Elige cancha" ──────────────────────────────
                  Text('Elige cancha', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 11),
                  SizedBox(
                    height: 44,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: widget.club.canchas.length,
                      separatorBuilder: (_, __) => const SizedBox(width: 8),
                      itemBuilder: (_, i) {
                        final c = widget.club.canchas[i];
                        final sel = c == _cancha;
                        return GestureDetector(
                          onTap: () => setState(() { _cancha = c; _horaSel = null; }),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 13),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: sel ? const Color(0xFFEAF6C2) : Colors.white,
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(color: sel ? pino : const Color(0xFFE3DECF), width: 1.5),
                            ),
                            child: Row(children: [
                              Container(width: 9, height: 9, decoration: BoxDecoration(
                                color: colorDeporte(c.deporte), borderRadius: BorderRadius.circular(2))),
                              const SizedBox(width: 7),
                              Text('${c.nombre}',
                                style: t.bodyMedium?.copyWith(
                                  fontWeight: sel ? FontWeight.w700 : FontWeight.w600, color: tinta)),
                            ]),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 18),

                  // ── Horarios de la cancha seleccionada ───────────────────
                  Text('Horarios · ${_cancha.nombre}',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 12),
                  Wrap(spacing: 9, runSpacing: 9, children: [
                    for (var i = 0; i < _cancha.franjas.length; i++)
                      _SlotChip(
                        franja: _cancha.franjas[i],
                        selected: _horaSel == i,
                        onTap: _cancha.franjas[i].ocupada ? null : () => setState(() => _horaSel = i),
                      ),
                  ]),
                ],
              ),
            ),
          ),
        ],
      ),
      // Barra fija inferior con CTA Reservar (pino/lima)
      bottomNavigationBar: _ReservarBar(
        precio: _cancha.precioHora,
        hora: _horaSel == null ? null : _cancha.franjas[_horaSel!],
        onReservar: _horaSel == null ? null : () => _onReservar(context),
      ),
    );
  }

  Future<void> _onReservar(BuildContext context) async {
    // Login SOLO al reservar, SOLO Google. Si ya hay sesión, salta directo.
    final user = await ensureGoogleSession(context, reserva: ReservaPendiente(
      club: widget.club, cancha: _cancha, franja: _cancha.franjas[_horaSel!],
    ));
    if (user == null) return; // canceló el login → no perdemos la selección
    if (!context.mounted) return;
    Navigator.of(context).pushNamed('/checkout-sena'); // paso de la seña
  }
}

// ===========================================================================
// B) LOGIN CON GOOGLE — hoja modal disparada al pulsar Reservar
// ===========================================================================

/// Devuelve el usuario si hay/logra sesión; null si el usuario cancela.
Future<GoogleSignInAccount?> ensureGoogleSession(
  BuildContext context, {required ReservaPendiente reserva}) async {
  final google = GoogleSignIn(scopes: const ['email']);
  if (await google.isSignedIn()) {
    return google.signInSilently();
  }
  return showModalBottomSheet<GoogleSignInAccount>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    barrierColor: const Color(0x8C16140F), // rgba(22,20,15,.55)
    builder: (_) => GoogleLoginSheet(reserva: reserva, google: google),
  );
}

class GoogleLoginSheet extends StatelessWidget {
  const GoogleLoginSheet({super.key, required this.reserva, required this.google});
  final ReservaPendiente reserva;
  final GoogleSignIn google;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(26, 18, 26, 36),
      decoration: const BoxDecoration(
        color: papel,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Center(child: Container(width: 38, height: 5, margin: const EdgeInsets.only(bottom: 22),
          decoration: BoxDecoration(color: const Color(0xFFD8D3C6), borderRadius: BorderRadius.circular(3)))),
        // marca
        Container(width: 60, height: 60, alignment: Alignment.center,
          decoration: BoxDecoration(color: pino, borderRadius: BorderRadius.circular(18)),
          child: Text('P', style: t.headlineSmall?.copyWith(color: lima, fontWeight: FontWeight.w700))),
        const SizedBox(height: 18),
        Text('Inicia sesión para\nreservar tu cancha', style: t.headlineSmall),
        const SizedBox(height: 10),
        Text('Explora y busca libre. Solo te pedimos cuenta al confirmar — y siempre es con Google.',
          style: t.bodyMedium?.copyWith(color: const Color(0xFF7C766B))),
        const SizedBox(height: 20),
        // contexto de la reserva
        Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16),
            border: Border.all(color: trazo)),
          child: Row(children: [
            Container(width: 46, height: 46, decoration: BoxDecoration(
              gradient: gradienteDeporte(reserva.cancha.deporte), borderRadius: BorderRadius.circular(11))),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${reserva.cancha.nombre} · ${reserva.cancha.deporte.label} · ${reserva.franja.label}',
                style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
              Text('Seña S/${reserva.club.sena} · resto en cancha',
                style: t.bodySmall?.copyWith(color: textoTenue)),
            ])),
          ]),
        ),
        const SizedBox(height: 16),
        // BOTÓN GOOGLE (blanco, borde, ícono Google)
        SizedBox(
          height: 58,
          child: OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              backgroundColor: Colors.white,
              side: const BorderSide(color: Color(0xFFE3DECF), width: 1.5),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              foregroundColor: tinta,
            ),
            icon: Image.asset('assets/google_g.png', width: 22, height: 22), // logo G oficial
            label: Text('Continuar con Google',
              style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
            onPressed: () async {
              final acc = await google.signIn(); // null si cancela
              if (context.mounted) Navigator.of(context).pop(acc);
            },
          ),
        ),
        const SizedBox(height: 16),
        Center(child: Text('Al continuar aceptas los Términos y la Privacidad de Pichangol.',
          textAlign: TextAlign.center, style: t.bodySmall?.copyWith(color: const Color(0xFFA39D91)))),
      ]),
    );
  }
}

// ── helpers de modelo de apoyo (ajustar a tus models reales) ───────────────
class ReservaPendiente {
  final Club club; final Cancha cancha; final Franja franja;
  ReservaPendiente({required this.club, required this.cancha, required this.franja});
}

// _RoundIcon, _Badge, _CourtLines, _SlotChip, _ReservarBar:
//   widgets de presentación a implementar con los tokens del theme
//   (botón redondo translúcido del hero, badge de píldora, líneas de cancha
//    dibujadas con CustomPaint, chip de franja horaria, barra fija de reserva).
