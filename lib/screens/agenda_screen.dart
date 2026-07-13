import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';

/// Agenda REAL del dueño: las franjas del día de SUS canchas con las reservas
/// reales. Se trabaja dentro de UN local: selector de local (si tiene varios) +
/// selector de cancha de ese local + Hoy/Mañana + mini-KPIs del local, todo
/// sobre datos reales (no demo).
class AgendaScreen extends StatefulWidget {
  const AgendaScreen({super.key});

  @override
  State<AgendaScreen> createState() => _AgendaScreenState();
}

class _AgendaScreenState extends State<AgendaScreen> {
  Cancha? _cancha;
  String _dia = 'Hoy';

  static String _isoDe(String dia) {
    final base = DateTime.now();
    final d = dia == 'Mañana' ? base.add(const Duration(days: 1)) : base;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  Reserva? _reservaEn(String canchaId, String iso, String hora) {
    for (final r in appState.reservas) {
      if (r.canchaId == canchaId && r.fecha == iso && r.horaInicio == hora) {
        return r;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).brightness == Brightness.dark
          ? Theme.of(context).scaffoldBackgroundColor
          : papelCalido,
      body: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          if (canchas.isEmpty) return const _VacioAgenda();

          // Mantén una selección válida aunque cambien las canchas.
          if (_cancha == null || !canchas.any((c) => c.id == _cancha!.id)) {
            _cancha = canchas.first;
          }
          final cancha = _cancha!;

          // Locales del dueño (distintos), en orden de aparición. La agenda se
          // trabaja SIEMPRE dentro de UN local: header, KPIs y el selector de
          // cancha se limitan al local de la cancha elegida, para no mezclar
          // canchas de otro local (p. ej. "Fútbol 1" de Joga Bonito bajo
          // "Campo Deportivo Machuca").
          final locales = <String>[];
          for (final c in canchas) {
            if (!locales.contains(c.club)) locales.add(c.club);
          }
          final localSel = cancha.club;
          final delLocal = canchas.where((c) => c.club == localSel).toList();

          final iso = _isoDe(_dia);
          final horas = cancha.horariosSlots();
          final tablet = MediaQuery.of(context).size.width >= 720;

          // Vista de la agenda del día (compartida por móvil y tablet).
          final slotsView = horas.isEmpty
              ? Center(
                  child: Text('Esta cancha no tiene horarios configurados.',
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(color: textoTenueDe(context))),
                )
              : ListView.separated(
                  padding: const EdgeInsets.fromLTRB(18, 8, 18, 90),
                  itemCount: horas.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 9),
                  itemBuilder: (_, i) {
                    final hora = horas[i];
                    return _AgendaRow(
                      hora: hora,
                      valle: hora.compareTo('12:00') < 0,
                      reserva: _reservaEn(cancha.id, iso, hora),
                    );
                  },
                );

          return Column(
            children: [
              _HeaderAgenda(canchas: delLocal, iso: iso),
              // Día: Hoy / Mañana
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 4),
                child: Row(
                  children: [
                    for (final d in const ['Hoy', 'Mañana']) ...[
                      _Pildora(
                        texto: d,
                        activo: _dia == d,
                        onTap: () => setState(() => _dia = d),
                      ),
                      const SizedBox(width: 10),
                    ],
                  ],
                ),
              ),
              // Selector de LOCAL (si el dueño administra más de uno). Deja
              // claro a qué local pertenece la agenda que estás viendo.
              if (locales.length > 1)
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 6, 18, 0),
                  child: SizedBox(
                    height: 38,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: locales.length,
                      separatorBuilder: (_, __) => const SizedBox(width: 8),
                      itemBuilder: (_, i) {
                        final nom = locales[i];
                        final sel = nom == localSel;
                        return GestureDetector(
                          onTap: () {
                            // Al cambiar de local, salta a su primera cancha.
                            final primera =
                                canchas.firstWhere((c) => c.club == nom);
                            setState(() => _cancha = primera);
                          },
                          child: Container(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 14),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: sel ? limaSuave : Colors.white,
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(color: sel ? lima : trazo),
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.storefront,
                                    size: 15,
                                    color: sel ? lima : textoTenue),
                                const SizedBox(width: 6),
                                Text(nom,
                                    style: TextStyle(
                                        color: sel ? tinta : textoTenue,
                                        fontWeight: sel
                                            ? FontWeight.w800
                                            : FontWeight.w600)),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
              // TABLET/LANDSCAPE: master-detail (canchas a la izquierda, agenda
              // del día a la derecha, como un panel de control). MÓVIL: selector
              // horizontal de cancha + la lista del día debajo.
              if (tablet)
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SizedBox(
                        width: 264,
                        child: ListView(
                          padding: const EdgeInsets.fromLTRB(18, 10, 10, 24),
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(bottom: 6, left: 4),
                              child: Text('Canchas',
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelLarge
                                      ?.copyWith(
                                          color: textoTenueDe(context),
                                          fontWeight: FontWeight.w700)),
                            ),
                            for (final c in delLocal)
                              _CanchaTile(
                                cancha: c,
                                seleccionada: c.id == cancha.id,
                                onTap: () => setState(() => _cancha = c),
                              ),
                          ],
                        ),
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(child: slotsView),
                    ],
                  ),
                )
              else ...[
                // Selector de cancha DENTRO del local seleccionado (móvil).
                if (delLocal.length > 1)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(18, 6, 18, 4),
                    child: SizedBox(
                      height: 40,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: delLocal.length,
                        separatorBuilder: (_, __) => const SizedBox(width: 8),
                        itemBuilder: (_, i) {
                          final c = delLocal[i];
                          final sel = c.id == cancha.id;
                          return GestureDetector(
                            onTap: () => setState(() => _cancha = c),
                            child: Container(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 14),
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: sel ? tinta : Colors.white,
                                borderRadius: BorderRadius.circular(999),
                                border:
                                    Border.all(color: sel ? tinta : trazo),
                              ),
                              child: Row(
                                children: [
                                  Container(
                                    width: 9,
                                    height: 9,
                                    decoration: BoxDecoration(
                                        color: colorDeporte(c.deporte),
                                        borderRadius:
                                            BorderRadius.circular(2)),
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
                Expanded(child: slotsView),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _HeaderAgenda extends StatelessWidget {
  const _HeaderAgenda({required this.canchas, required this.iso});
  final List<Cancha> canchas;
  final String iso;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final barrio = canchas.isEmpty ? 'Lima' : canchas.first.distrito.etiqueta;
    final local = canchas.isEmpty ? 'Mis canchas' : canchas.first.club;

    // Saludo por hora del día (+ nombre del dueño si hay sesión). Antes decía
    // "Buenas, San Borja" — saludaba al distrito, que quedaba raro.
    final hora = DateTime.now().hour;
    final saludo = hora < 12
        ? 'Buenos días'
        : (hora < 19 ? 'Buenas tardes' : 'Buenas noches');
    final nombre = (appState.usuario?.nombre ?? '').trim().split(' ').first;
    final saludoTxt = nombre.isEmpty ? '$saludo 👋' : '$saludo, $nombre 👋';

    // KPIs REALES del día sobre las canchas del LOCAL seleccionado.
    final ids = canchas.map((c) => c.id).toSet();
    final delDia = appState.reservas
        .where((r) => ids.contains(r.canchaId) && r.fecha == iso)
        .toList();
    final totalSlots =
        canchas.fold<int>(0, (s, c) => s + c.horariosSlots().length);
    final ocupacion =
        totalSlots == 0 ? 0 : (delDia.length * 100) ~/ totalSlots;
    final porCobrar = delDia
        .where((r) => !r.pagado && r.estado != EstadoReserva.noShow)
        .fold<int>(0, (s, r) => s + r.precio);

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
          22, 18 + MediaQuery.of(context).padding.top, 22, 20),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [sage, verde, bosque],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(saludoTxt,
              style: t.bodyMedium?.copyWith(color: Colors.white70)),
          Text(local,
              style: t.titleLarge
                  ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Row(
            children: [
              const Icon(Icons.location_on, size: 14, color: Colors.white70),
              const SizedBox(width: 4),
              Text(barrio,
                  style: t.bodySmall?.copyWith(color: Colors.white70)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _MiniKpi('${delDia.length}', 'Reservas'),
              const SizedBox(width: 10),
              _MiniKpi('$ocupacion%', 'Ocupación'),
              const SizedBox(width: 10),
              _MiniKpi('$monedaSimbolo$porCobrar', 'Por cobrar', accent: true),
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
            Text(label, style: t.bodySmall?.copyWith(color: Colors.white70)),
          ],
        ),
      ),
    );
  }
}

class _Pildora extends StatelessWidget {
  const _Pildora(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 9),
        decoration: BoxDecoration(
          color: activo ? tinta : Colors.white,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: activo ? tinta : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? Colors.white : textoTenue,
                fontWeight: FontWeight.w700)),
      ),
    );
  }
}

/// Fila de cancha del panel MASTER (columna izquierda en tablet/landscape):
/// punto del deporte + nombre; resaltada cuando es la cancha seleccionada.
class _CanchaTile extends StatelessWidget {
  const _CanchaTile(
      {required this.cancha,
      required this.seleccionada,
      required this.onTap});
  final Cancha cancha;
  final bool seleccionada;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: seleccionada ? tinta : Theme.of(context).colorScheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: seleccionada ? tinta : trazo),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
            child: Row(
              children: [
                Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(
                      color: colorDeporte(cancha.deporte),
                      borderRadius: BorderRadius.circular(2)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(cancha.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: seleccionada ? Colors.white : tinta,
                          fontWeight: seleccionada
                              ? FontWeight.w800
                              : FontWeight.w600)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AgendaRow extends StatelessWidget {
  const _AgendaRow(
      {required this.hora, required this.valle, required this.reserva});
  final String hora;
  final bool valle;
  final Reserva? reserva;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final r = reserva;
    final ocupada = r != null;

    return Container(
      padding: const EdgeInsets.fromLTRB(15, 13, 15, 13),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border(
            left: BorderSide(
                color: ocupada ? lima : Colors.transparent, width: 4)),
        boxShadow: const [
          BoxShadow(
              color: Color(0x14000000), blurRadius: 16, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          SizedBox(
            width: 50,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(hora,
                    style:
                        t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                if (valle)
                  Text('VALLE',
                      style: t.labelSmall?.copyWith(
                          color: clayOscuro, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          Container(
              width: 1,
              height: 38,
              color: trazo,
              margin: const EdgeInsets.symmetric(horizontal: 12)),
          Expanded(
            child: !ocupada
                ? Text('Libre',
                    style: t.bodyMedium?.copyWith(
                        color: const Color(0xFFB5AFA3),
                        fontWeight: FontWeight.w600))
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(r.jugador.isEmpty ? 'Reservado' : r.jugador,
                          style: t.bodyMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      Text(
                        '${r.horaInicio}–${r.horaFin} · '
                        '${r.pagado ? 'Pagado' : 'Por cobrar'} $monedaSimbolo${r.precio}',
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                      ),
                    ],
                  ),
          ),
          if (ocupada) _ChipEstado(estado: r.estado),
        ],
      ),
    );
  }
}

class _ChipEstado extends StatelessWidget {
  const _ChipEstado({required this.estado});
  final EstadoReserva estado;

  @override
  Widget build(BuildContext context) {
    final (bg, fg, txt) = switch (estado) {
      EstadoReserva.confirmada => (estadoOkBg, estadoOkFg, 'Confirmada'),
      EstadoReserva.nueva => (lima, Colors.white, 'Nueva'),
      EstadoReserva.completada => (estadoNeutroBg, estadoNeutroFg, 'Jugada'),
      EstadoReserva.noShow => (estadoBadBg, estadoBadFg, 'No-show'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(txt,
          style: TextStyle(
              color: fg, fontSize: 11, fontWeight: FontWeight.w700, height: 1)),
    );
  }
}

class _VacioAgenda extends StatelessWidget {
  const _VacioAgenda();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.calendar_month, size: 60, color: verdeClaro),
            const SizedBox(height: 14),
            Text('Aún no tienes canchas',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              'Registra o reclama una cancha para ver aquí su agenda del día.',
              textAlign: TextAlign.center,
              style: t.bodyMedium?.copyWith(color: textoTenueDe(context)),
            ),
          ],
        ),
      ),
    );
  }
}
