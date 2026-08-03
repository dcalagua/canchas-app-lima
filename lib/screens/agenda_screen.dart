import 'package:flutter/material.dart';

import '../config/pais.dart';
import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../utils/moneda.dart';
import '../widgets/ancho_lectura.dart';
import 'llenar_cancha_screen.dart';

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
  // Día que se está viendo (cualquiera: historial atrás, planificación adelante).
  DateTime _dia = _hoy();

  static DateTime _hoy() {
    final n = DateTime.now();
    return DateTime(n.year, n.month, n.day);
  }

  static String _iso(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  static const _diasSem = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
  static const _mesesAbr = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  /// "Hoy" / "Mañana" / "Ayer" / "vie 8 ago".
  static String _labelDia(DateTime d) {
    final diff =
        DateTime(d.year, d.month, d.day).difference(_hoy()).inDays;
    if (diff == 0) return 'Hoy';
    if (diff == 1) return 'Mañana';
    if (diff == -1) return 'Ayer';
    return '${_diasSem[d.weekday - 1]} ${d.day} ${_mesesAbr[d.month - 1]}';
  }

  Reserva? _reservaEn(String canchaId, String iso, String hora) {
    for (final r in appState.reservas) {
      // Match tolerante a ids duplicados del mismo local (igual que el panel de
      // Reservas): resuelve la reserva a la cancha del dueño antes de comparar.
      if (r.fecha == iso &&
          r.horaInicio == hora &&
          appState.miCanchaDeReserva(r.canchaId)?.id == canchaId) {
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
      floatingActionButton: appState.misCanchas.isEmpty
          ? null
          : FloatingActionButton.extended(
              backgroundColor: lima,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.campaign),
              label: const Text('Llenar cancha'),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) =>
                      LlenarCanchaScreen(canchaInicial: _cancha))),
            ),
      body: AnchoLectura(child: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          if (canchas.isEmpty) return const _VacioAgenda();

          // Mantén una selección válida aunque cambien las canchas.
          if (_cancha == null || !canchas.any((c) => c.id == _cancha!.id)) {
            _cancha = canchas.first;
          }
          // Versión FRESCA por id: si el dueño acaba de cambiar la duración/
          // precio, `misCanchas` ya la trae actualizada; el snapshot guardado en
          // `_cancha` puede estar viejo. Así la agenda usa la duración nueva.
          final cancha = canchas.firstWhere((c) => c.id == _cancha!.id,
              orElse: () => canchas.first);

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
          // Si el dueño tiene canchas en más de un país, la pastilla del local
          // muestra también el país (deducido de la moneda de la cancha).
          final variosPaisesAg =
              canchas.map((c) => c.monedaSimbolo).toSet().length > 1;

          final iso = _iso(_dia);
          final horasGrilla = cancha.horariosSlots();
          // Reservas de la SESIÓN de este día (tolerante a ids duplicados). La
          // sesión incluye la MADRUGADA del día siguiente si el horario cruza
          // medianoche (esas reservas viven con fecha = iso+1).
          final reservasDia = appState.reservas.where((r) =>
              appState.miCanchaDeReserva(r.canchaId)?.id == cancha.id &&
              cancha.reservaEnSesion(iso, r.fecha, r.horaInicio));
          // Horas de reservas que NO calzan con la grilla actual (p. ej. se
          // reservó con duración 1 h y luego el dueño cambió a 1.5 h): se
          // muestran IGUAL para que la reserva NO desaparezca de la agenda.
          final extras = <String>{
            for (final r in reservasDia)
              if (!horasGrilla.contains(r.horaInicio)) r.horaInicio
          }.toList();
          final horas = [...horasGrilla, ...extras]..sort();
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
                      reserva: _reservaEn(
                          cancha.id, cancha.fechaRealSlot(iso, hora), hora),
                      fueraDeGrilla: extras.contains(hora),
                    );
                  },
                );

          return Column(
            children: [
              _HeaderAgenda(canchas: delLocal, iso: iso),
              // Día: navegador (‹ · fecha/calendario · ›). Permite CUALQUIER día
              // (historial hacia atrás, planificación hacia adelante), no solo
              // Hoy/Mañana. La fecha es tocable y abre el calendario.
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 12, 18, 2),
                child: Row(
                  children: [
                    _NavDia(
                      icono: Icons.chevron_left,
                      onTap: () => setState(
                          () => _dia = _dia.subtract(const Duration(days: 1))),
                    ),
                    Expanded(
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () async {
                          final d = await showDatePicker(
                            context: context,
                            initialDate: _dia,
                            firstDate: DateTime(2024, 1, 1),
                            lastDate:
                                DateTime.now().add(const Duration(days: 365)),
                            helpText: 'Elige el día',
                          );
                          if (d != null && mounted) {
                            setState(
                                () => _dia = DateTime(d.year, d.month, d.day));
                          }
                        },
                        child: Column(
                          children: [
                            Text(_labelDia(_dia),
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w800)),
                            Text(
                                '${_dia.day.toString().padLeft(2, '0')}/'
                                '${_dia.month.toString().padLeft(2, '0')}/'
                                '${_dia.year} · toca para elegir',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(color: textoTenueDe(context))),
                          ],
                        ),
                      ),
                    ),
                    _NavDia(
                      icono: Icons.chevron_right,
                      onTap: () => setState(
                          () => _dia = _dia.add(const Duration(days: 1))),
                    ),
                  ],
                ),
              ),
              if (_iso(_dia) != _iso(_hoy()))
                Align(
                  alignment: Alignment.center,
                  child: TextButton.icon(
                    onPressed: () => setState(() => _dia = _hoy()),
                    icon: const Icon(Icons.today, size: 16),
                    label: const Text('Volver a hoy'),
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
                                Text(
                                    variosPaisesAg
                                        ? '$nom · ${_paisDeMonedaAg(canchas.firstWhere((c) => c.club == nom).monedaSimbolo)}'
                                        : nom,
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
                                // Seleccionada = verde suave (igual que el
                                // selector de escritorio), nunca negro.
                                color: sel ? limaSuave : Colors.white,
                                borderRadius: BorderRadius.circular(999),
                                border:
                                    Border.all(color: sel ? lima : trazo),
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
                                          color: tinta,
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
      )),
    );
  }
}

/// Nombre de país desde el símbolo de moneda de la cancha (proxy de país).
String _paisDeMonedaAg(String m) => switch (m.trim()) {
      'S/' => 'Perú',
      'Bs' => 'Bolivia',
      r'$' => 'Ecuador',
      _ => m,
    };

class _HeaderAgenda extends StatelessWidget {
  const _HeaderAgenda({required this.canchas, required this.iso});
  final List<Cancha> canchas;
  final String iso;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final barrio =
        canchas.isEmpty ? paisActual.nombre : canchas.first.zonaMostrable;
    final local = canchas.isEmpty ? 'Mis canchas' : canchas.first.club;

    // Saludo por hora del día (+ nombre del dueño si hay sesión). Antes decía
    // "Buenas, San Borja" — saludaba al distrito, que quedaba raro.
    final hora = DateTime.now().hour;
    final saludo = hora < 12
        ? 'Buenos días'
        : (hora < 19 ? 'Buenas tardes' : 'Buenas noches');
    final nombre = (appState.usuario?.nombre ?? '').trim().split(' ').first;
    final saludoTxt = nombre.isEmpty ? '$saludo 👋' : '$saludo, $nombre 👋';

    // KPIs REALES del día sobre las canchas del LOCAL seleccionado. Se resuelve
    // cada reserva a la cancha del dueño (tolerante a ids duplicados del local).
    final ids = canchas.map((c) => c.id).toSet();
    final delDia = appState.reservas.where((r) {
      final c = appState.miCanchaDeReserva(r.canchaId);
      if (c == null || !ids.contains(c.id)) return false;
      // Sesión del día (incluye la madrugada del día siguiente si cruza medianoche).
      return c.reservaEnSesion(iso, r.fecha, r.horaInicio);
    }).toList();
    final totalSlots =
        canchas.fold<int>(0, (s, c) => s + c.horariosSlots().length);
    final ocupacion =
        totalSlots == 0 ? 0 : (delDia.length * 100) ~/ totalSlots;
    final porCobrar = delDia
        .where((r) => !r.pagado && r.estado != EstadoReserva.noShow)
        .fold<int>(0, (s, r) => s + r.precio);
    // Moneda del local (sus canchas comparten país).
    final moneda = canchas.isNotEmpty ? canchas.first.monedaSimbolo : 'S/';

    final padTop = MediaQuery.of(context).padding.top;
    // Poca altura (celular apaisado) → cabecera COMPACTA: KPIs a la derecha del
    // título en vez de debajo, y menos padding. Así el banner no se come media
    // pantalla y se ve la agenda. En retrato/tablet queda el layout amplio.
    final compacto = MediaQuery.of(context).size.height < 520;

    const deco = BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [lima, teal], // verde WhatsApp
      ),
      borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
    );

    final saludoW = Row(
      children: [
        // Atrás: sale del panel del dueño y vuelve a donde estabas (solo si hay
        // pantalla previa a la que volver).
        if (Navigator.of(context).canPop())
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => Navigator.of(context).maybePop(),
            child: const Padding(
              padding: EdgeInsets.only(right: 8),
              child: Icon(Icons.arrow_back, color: Colors.white, size: 20),
            ),
          ),
        Flexible(
          child: Text(saludoTxt,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.bodySmall?.copyWith(color: Colors.white70)),
        ),
      ],
    );
    final localW = Text(local,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: (compacto ? t.titleMedium : t.titleLarge)
            ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700));
    final barrioW = Row(
      children: [
        const Icon(Icons.location_on, size: 13, color: Colors.white70),
        const SizedBox(width: 4),
        Flexible(
          child: Text(barrio,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.bodySmall?.copyWith(color: Colors.white70)),
        ),
      ],
    );

    if (compacto) {
      return Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(20, 10 + padTop, 20, 12),
        decoration: deco,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [saludoW, localW, const SizedBox(height: 2), barrioW],
              ),
            ),
            const SizedBox(width: 14),
            _MiniKpi('${delDia.length}', 'Reservas', ancho: 92),
            const SizedBox(width: 8),
            _MiniKpi('$ocupacion%', 'Ocupación', ancho: 96),
            const SizedBox(width: 8),
            _MiniKpi('$moneda$porCobrar', 'Por cobrar', accent: true, ancho: 108),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(22, 18 + padTop, 22, 20),
      decoration: deco,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          saludoW,
          localW,
          const SizedBox(height: 4),
          barrioW,
          const SizedBox(height: 16),
          Row(
            children: [
              _MiniKpi('${delDia.length}', 'Reservas'),
              const SizedBox(width: 10),
              _MiniKpi('$ocupacion%', 'Ocupación'),
              const SizedBox(width: 10),
              _MiniKpi('$moneda$porCobrar', 'Por cobrar', accent: true),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniKpi extends StatelessWidget {
  const _MiniKpi(this.valor, this.label, {this.accent = false, this.ancho});
  final String valor;
  final String label;
  final bool accent;

  /// null = ocupa el ancho disponible (Expanded, layout vertical de retrato).
  /// Con valor = ancho fijo (layout horizontal compacto, p. ej. celular apaisado
  /// donde los KPIs van a la derecha del título y no debajo).
  final double? ancho;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final compacto = ancho != null;
    final card = Container(
      padding: EdgeInsets.symmetric(
          vertical: compacto ? 8 : 12, horizontal: 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.10),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(valor,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: (compacto ? t.titleMedium : t.titleLarge)?.copyWith(
                  // "Por cobrar" (accent) en DORADO: resalta y se lee sobre el
                  // fondo teal (antes era `lima` verde, casi invisible). Mismo
                  // color que "Por cobrar" en la tarjeta de caja.
                  color: accent ? amarillo : Colors.white,
                  fontWeight: FontWeight.w700)),
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: t.bodySmall?.copyWith(
                  color: Colors.white70, fontSize: compacto ? 11 : null)),
        ],
      ),
    );
    return ancho == null ? Expanded(child: card) : SizedBox(width: ancho, child: card);
  }
}

/// Flecha ‹ / › del navegador de día: botón redondo estilo Airbnb (blanco,
/// borde gris suave, relieve leve), nunca negro.
class _NavDia extends StatelessWidget {
  const _NavDia({required this.icono, required this.onTap});
  final IconData icono;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      shape: CircleBorder(side: BorderSide(color: trazo)),
      elevation: 0,
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(icono, size: 22, color: bosque),
        ),
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
        // Seleccionada = verde suave con borde lima, nunca negro. Congruente.
        color: seleccionada ? limaSuave : Theme.of(context).colorScheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: seleccionada ? lima : trazo),
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
                          color: tinta,
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
      {required this.hora,
      required this.valle,
      required this.reserva,
      this.fueraDeGrilla = false});
  final String hora;
  final bool valle;
  final Reserva? reserva;

  /// La reserva de esta fila NO calza con la grilla actual de la cancha (se hizo
  /// con otra duración y luego el dueño cambió la duración). Se muestra igual,
  /// con un rótulo, para que no desaparezca.
  final bool fueraDeGrilla;

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
                        '${r.pagado ? 'Pagado' : 'Por cobrar'} ${r.monedaSimbolo}${r.precio}',
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                      ),
                      if (fueraDeGrilla)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                              'Reserva con otra duración (fuera de la grilla actual)',
                              style: t.labelSmall?.copyWith(
                                  color: const Color(0xFFB26A00),
                                  fontWeight: FontWeight.w700)),
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
