import 'package:flutter/material.dart';

import '../models/club.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';
import '../widgets/marca.dart';
import 'login_google_sheet.dart';
import 'pago_sheet.dart';
import 'registrar_cancha_screen.dart';

/// Ficha de CLUB (rediseño): un local con varias canchas. Selector "Elige
/// cancha" + horarios de la cancha elegida + reserva con seña.
class ClubDetalleScreen extends StatefulWidget {
  const ClubDetalleScreen({super.key, required this.club, this.canchaInicial});

  final Club club;
  final Cancha? canchaInicial;

  @override
  State<ClubDetalleScreen> createState() => _ClubDetalleScreenState();
}

class _ClubDetalleScreenState extends State<ClubDetalleScreen> {
  static const _horas = [
    '07:00', '08:00', '09:00', '10:00', '11:00',
    '16:00', '17:00', '18:00', '19:00', '20:00',
  ];

  late Cancha _cancha = widget.canchaInicial ?? widget.club.canchas.first;
  String _dia = 'Hoy';
  String? _hora;

  Color get _color => colorDeporte(_cancha.deporte);

  bool _ocupada(String hora) => appState.reservas.any((r) =>
      r.canchaId == _cancha.id && r.dia == _dia && r.horaInicio == hora);

  bool _esValle(String hora) => hora.compareTo('12:00') < 0;

  Future<void> _reservar() async {
    final hora = _hora;
    if (hora == null) return;
    if (!_cancha.reservable) return; // no se reserva si está pendiente/descubierta
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) return;
    }
    final sena = (_cancha.precioHora * 0.3).round();
    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
    final pago = await PagoSheet.mostrar(
      context,
      monto: sena,
      concepto: 'Seña · ${_cancha.nombre}',
    );
    if (pago == null || !pago.exito) return;
    appState.agregarReservaJugador(_cancha, _dia, hora);
    nav.pop();
    messenger.showSnackBar(
      SnackBar(
        backgroundColor: pino,
        content: Text('✅ Reserva confirmada en ${_cancha.nombre} · $_dia $hora',
            style: const TextStyle(color: Colors.white)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final c = widget.club;
    final descubierta = !_cancha.registrada;
    final pendiente = _cancha.pendienteVerificacion;
    return Scaffold(
      backgroundColor: papel,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 280,
            pinned: true,
            backgroundColor: _color,
            foregroundColor: Colors.white,
            flexibleSpace: FlexibleSpaceBar(
              background: _HeroGaleria(cancha: _cancha),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(22, 18, 22, 120),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (c.clubFundador)
                        const _Badge('CLUB FUNDADOR', bg: pino, fg: lima),
                      if (c.clubFundador) const SizedBox(width: 6),
                      if (descubierta)
                        const _Badge('◎ EN GOOGLE',
                            bg: Color(0xFF3A352E), fg: Colors.white)
                      else if (pendiente)
                        const _Badge('⏳ PENDIENTE DE VERIFICACIÓN',
                            bg: Color(0xFFFBEAD2), fg: clayOscuro)
                      else
                        const _Badge('DIGITALIZADA',
                            bg: Color(0xFFF0ECE2), fg: Color(0xFF5C574E)),
                      if (_cancha.verificada) ...[
                        const SizedBox(width: 6),
                        const SelloVerificada(),
                      ],
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(c.nombre, style: t.headlineSmall),
                  const SizedBox(height: 3),
                  Text(
                    c.direccion ??
                        '${c.barrio} · ${c.canchas.length} ${c.canchas.length == 1 ? 'cancha' : 'canchas'} · ${c.deportes.map((d) => d.etiqueta).join(' · ')}',
                    style: t.bodyMedium?.copyWith(color: textoTenue),
                  ),
                  const SizedBox(height: 20),

                  if (descubierta)
                    _PanelDescubierta()
                  else if (pendiente)
                    const _PanelPendiente()
                  else ...[
                    // Selector "Elige cancha"
                    if (c.canchas.length > 1) ...[
                      Text('Elige cancha',
                          style: t.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 11),
                      SizedBox(
                        height: 44,
                        child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemCount: c.canchas.length,
                          separatorBuilder: (_, __) => const SizedBox(width: 8),
                          itemBuilder: (_, i) {
                            final cc = c.canchas[i];
                            final sel = cc.id == _cancha.id;
                            return GestureDetector(
                              onTap: () => setState(() {
                                _cancha = cc;
                                _hora = null;
                              }),
                              child: Container(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 14),
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: sel
                                      ? const Color(0xFFEAF6C2)
                                      : Colors.white,
                                  borderRadius: BorderRadius.circular(999),
                                  border: Border.all(
                                      color: sel
                                          ? pino
                                          : const Color(0xFFE3DECF),
                                      width: 1.5),
                                ),
                                child: Row(
                                  children: [
                                    Container(
                                      width: 9,
                                      height: 9,
                                      decoration: BoxDecoration(
                                          color: colorDeporte(cc.deporte),
                                          borderRadius:
                                              BorderRadius.circular(2)),
                                    ),
                                    const SizedBox(width: 7),
                                    Text(cc.nombre,
                                        style: t.bodyMedium?.copyWith(
                                            fontWeight: sel
                                                ? FontWeight.w700
                                                : FontWeight.w600,
                                            color: tinta)),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],

                    // Día
                    Text('Elige el día',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _DiaChip('Hoy', _dia == 'Hoy',
                            () => setState(() { _dia = 'Hoy'; _hora = null; })),
                        const SizedBox(width: 10),
                        _DiaChip('Mañana', _dia == 'Mañana',
                            () => setState(() { _dia = 'Mañana'; _hora = null; })),
                      ],
                    ),
                    const SizedBox(height: 20),

                    // Horarios
                    Text('Horarios · ${_cancha.nombre}',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('Las mañanas (valle) suelen estar más libres.',
                        style: t.bodySmall?.copyWith(color: textoTenue)),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 9,
                      runSpacing: 9,
                      children: [
                        for (final h in _horas)
                          _SlotChip(
                            hora: h,
                            ocupada: _ocupada(h),
                            valle: _esValle(h),
                            seleccionada: _hora == h,
                            onTap: () => setState(() => _hora = h),
                          ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: (descubierta || pendiente)
          ? null
          : _ReservarBar(
              precio: _cancha.precioHora,
              hora: _hora,
              onReservar: _hora == null ? null : _reservar,
            ),
    );
  }
}

class _ReservarBar extends StatelessWidget {
  const _ReservarBar(
      {required this.precio, required this.hora, required this.onReservar});
  final int precio;
  final String? hora;
  final VoidCallback? onReservar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: EdgeInsets.fromLTRB(
          22, 12, 22, 16 + MediaQuery.of(context).padding.bottom),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: trazo)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                RichText(
                  text: TextSpan(
                    style: t.bodySmall?.copyWith(color: textoTenue),
                    children: [
                      TextSpan(
                        text: 'S/$precio',
                        style: t.titleLarge?.copyWith(
                            color: tinta, fontWeight: FontWeight.w700),
                      ),
                      const TextSpan(text: ' /hora'),
                    ],
                  ),
                ),
                Text(hora == null ? 'Elige una hora' : 'Hora $hora',
                    style: t.bodySmall?.copyWith(color: textoTenue)),
              ],
            ),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: pino,
              foregroundColor: lima,
              padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 16),
            ),
            onPressed: onReservar,
            child: const Text('Reservar'),
          ),
        ],
      ),
    );
  }
}

class _DiaChip extends StatelessWidget {
  const _DiaChip(this.texto, this.activo, this.onTap);
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
        decoration: BoxDecoration(
          color: activo ? pino : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: activo ? pino : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? lima : tinta, fontWeight: FontWeight.w700)),
      ),
    );
  }
}

class _SlotChip extends StatelessWidget {
  const _SlotChip({
    required this.hora,
    required this.ocupada,
    required this.valle,
    required this.seleccionada,
    required this.onTap,
  });
  final String hora;
  final bool ocupada;
  final bool valle;
  final bool seleccionada;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    if (ocupada) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          color: const Color(0xFFF0ECE2),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(hora,
            style: const TextStyle(
                color: Color(0xFFB5AFA3),
                decoration: TextDecoration.lineThrough)),
      );
    }
    final Color borde = seleccionada
        ? tinta
        : valle
            ? clay
            : trazo;
    final Color fondo = seleccionada ? tinta : Colors.white;
    final Color texto = seleccionada
        ? Colors.white
        : valle
            ? clayOscuro
            : tinta;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: borde, width: 1.5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(hora,
                style: TextStyle(color: texto, fontWeight: FontWeight.w700)),
            if (valle && !seleccionada) ...[
              const SizedBox(width: 5),
              const Text('valle',
                  style: TextStyle(
                      color: clayOscuro,
                      fontSize: 10,
                      fontWeight: FontWeight.w700)),
            ],
          ],
        ),
      ),
    );
  }
}

class _PanelDescubierta extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.travel_explore, color: pino),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Encontramos esta cancha en Google Maps',
                    style: t.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Todavía no está activa en Pichangol, así que aún no se puede '
            'reservar online. ¿Es tuya? Regístrala y empieza a recibir reservas.',
            style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                    builder: (_) => const RegistrarCanchaScreen()),
              ),
              icon: const Icon(Icons.add_location_alt),
              label: const Text('Reclamar / registrar esta cancha'),
            ),
          ),
        ],
      ),
    );
  }
}

/// Panel cuando la cancha está reclamada/registrada pero aún sin verificar la
/// propiedad: no se puede reservar online hasta validar al dueño (anti-fraude).
class _PanelPendiente extends StatelessWidget {
  const _PanelPendiente();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFFDF6EC),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFE9D9C2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.verified_user_outlined, color: clayOscuro),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Cancha pendiente de verificación',
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Alguien la registró como suya y estamos validando que sea el dueño '
            'real. Por seguridad, las reservas online se habilitan recién cuando '
            'se confirme la propiedad.',
            style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
          ),
        ],
      ),
    );
  }
}

/// Hero con galería de fotos deslizable (puntos indicadores). Si no hay fotos,
/// muestra el gradiente del deporte con líneas de cancha.
class _HeroGaleria extends StatefulWidget {
  const _HeroGaleria({required this.cancha});
  final Cancha cancha;

  @override
  State<_HeroGaleria> createState() => _HeroGaleriaState();
}

class _HeroGaleriaState extends State<_HeroGaleria> {
  final _ctrl = PageController();
  int _pagina = 0;

  List<String> get _fotos => widget.cancha.fotos.isNotEmpty
      ? widget.cancha.fotos
      : (widget.cancha.fotoUrl != null ? [widget.cancha.fotoUrl!] : []);

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final fotos = _fotos;
    return DecoratedBox(
      decoration: BoxDecoration(gradient: gradienteDeporte(widget.cancha.deporte)),
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (fotos.isEmpty) ...[
            const Positioned.fill(child: CourtLines(opacity: 0.5)),
            Center(
              child: Icon(iconoDeporte(widget.cancha.deporte),
                  size: 96, color: Colors.white.withOpacity(0.9)),
            ),
          ] else ...[
            PageView.builder(
              controller: _ctrl,
              itemCount: fotos.length,
              onPageChanged: (i) => setState(() => _pagina = i),
              itemBuilder: (_, i) => Image.network(fotos[i],
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink()),
            ),
            if (fotos.length > 1)
              Positioned(
                bottom: 14,
                left: 0,
                right: 0,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var i = 0; i < fotos.length; i++)
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: i == _pagina ? 18 : 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color: i == _pagina
                              ? Colors.white
                              : Colors.white54,
                          borderRadius: BorderRadius.circular(999),
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

class _Badge extends StatelessWidget {
  const _Badge(this.texto, {required this.bg, required this.fg});
  final String texto;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(texto,
          style: TextStyle(
              color: fg, fontSize: 11, fontWeight: FontWeight.w700, height: 1)),
    );
  }
}
