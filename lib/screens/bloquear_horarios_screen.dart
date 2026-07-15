import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// El DUEÑO cierra horas de su cancha (mantenimiento, walk-in, clase) para que
/// nadie las reserve. Antes esto solo vivía en la ficha pública (inalcanzable
/// para el dueño); ahora se abre directo desde "Mis canchas". Un slot cerrado
/// cuenta como ocupado para el jugador. Los ya reservados no se pueden bloquear.
class BloquearHorariosScreen extends StatefulWidget {
  const BloquearHorariosScreen({super.key, required this.cancha});
  final Cancha cancha;

  @override
  State<BloquearHorariosScreen> createState() => _BloquearHorariosScreenState();
}

class _BloquearHorariosScreenState extends State<BloquearHorariosScreen> {
  DateTime _fecha = _hoy();

  static DateTime _hoy() {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  @override
  void initState() {
    super.initState();
    appState.cargarBloqueos(); // fuente de verdad en la nube
  }

  String get _iso {
    final d = _fecha;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  bool _reservado(String hora) => appState.reservas.any((r) =>
      r.canchaId == widget.cancha.id &&
      r.fecha == _iso &&
      r.horaInicio == hora);

  bool _bloqueado(String hora) =>
      appState.estaBloqueado(widget.cancha.id, _iso, hora);

  @override
  Widget build(BuildContext context) {
    final c = widget.cancha;
    final t = Theme.of(context).textTheme;
    final slots = c.horariosSlots();
    return Scaffold(
      appBar: AppBar(title: const Text('Bloquear horarios')),
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 28),
            children: [
              Text(c.nombre,
                  style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              Text('${c.horaApertura}–${c.horaCierre}',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              const SizedBox(height: 14),
              _SelectorDia(
                fecha: _fecha,
                onElegir: (d) => setState(() => _fecha = d),
              ),
              const SizedBox(height: 18),
              Text('Toca una hora para cerrarla o reabrirla',
                  style: t.bodyMedium?.copyWith(color: textoTenueDe(context))),
              const SizedBox(height: 12),
              if (slots.isEmpty)
                Text('Esta cancha no tiene horarios configurados.',
                    style: TextStyle(color: textoTenueDe(context)))
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final h in slots)
                      _SlotBloqueo(
                        hora: h,
                        reservado: _reservado(h),
                        bloqueado: _bloqueado(h),
                        onTap: _reservado(h)
                            ? null
                            : () => appState.alternarBloqueo(
                                widget.cancha.id, _iso, h),
                      ),
                  ],
                ),
              const SizedBox(height: 20),
              const _Leyenda(),
            ],
          );
        },
      ),
    );
  }
}

class _SelectorDia extends StatelessWidget {
  const _SelectorDia({required this.fecha, required this.onElegir});
  final DateTime fecha;
  final ValueChanged<DateTime> onElegir;

  static const _dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hoy = _BloquearHorariosScreenState._hoy();
    return SizedBox(
      height: 66,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: 14, // dos semanas
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final d = hoy.add(Duration(days: i));
          final sel = d == fecha;
          final etiqueta =
              i == 0 ? 'Hoy' : (i == 1 ? 'Mañ' : _dias[d.weekday - 1]);
          return GestureDetector(
            onTap: () => onElegir(d),
            child: Container(
              width: 52,
              decoration: BoxDecoration(
                color: sel ? cs.primary : Colors.transparent,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                    color: sel
                        ? cs.primary
                        : textoTenueDe(context).withOpacity(0.4)),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(etiqueta,
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w700,
                          color: sel ? Colors.white : textoTenueDe(context))),
                  const SizedBox(height: 2),
                  Text('${d.day}',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: sel ? Colors.white : cs.onSurface)),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SlotBloqueo extends StatelessWidget {
  const _SlotBloqueo({
    required this.hora,
    required this.reservado,
    required this.bloqueado,
    required this.onTap,
  });
  final String hora;
  final bool reservado;
  final bool bloqueado;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Reservado = ocupado por un jugador (no se toca). Bloqueado = cerrado por
    // el dueño (rojo Airbnb). Libre = transparente con borde.
    final Color bg, fg, borde;
    if (reservado) {
      bg = textoTenueDe(context).withOpacity(0.12);
      fg = textoTenueDe(context);
      borde = Colors.transparent;
    } else if (bloqueado) {
      bg = clayOscuro.withOpacity(0.15);
      fg = clayOscuro;
      borde = clayOscuro;
    } else {
      bg = Colors.transparent;
      fg = cs.onSurface;
      borde = textoTenueDe(context).withOpacity(0.4);
    }
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: borde),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (reservado)
              Padding(
                padding: const EdgeInsets.only(right: 5),
                child: Icon(Icons.event_busy, size: 14, color: fg),
              )
            else if (bloqueado)
              const Padding(
                padding: EdgeInsets.only(right: 5),
                child: Icon(Icons.lock, size: 14, color: clayOscuro),
              ),
            Text(hora,
                style: TextStyle(
                    fontSize: 13.5, fontWeight: FontWeight.w700, color: fg)),
          ],
        ),
      ),
    );
  }
}

class _Leyenda extends StatelessWidget {
  const _Leyenda();

  @override
  Widget build(BuildContext context) {
    Widget item(Color c, String txt) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                    color: c, borderRadius: BorderRadius.circular(4))),
            const SizedBox(width: 6),
            Text(txt,
                style: TextStyle(
                    fontSize: 12, color: textoTenueDe(context))),
          ],
        );
    return Wrap(
      spacing: 16,
      runSpacing: 8,
      children: [
        item(clayOscuro, 'Cerrado por ti'),
        item(textoTenueDe(context).withOpacity(0.4), 'Reservado (ocupado)'),
      ],
    );
  }
}
