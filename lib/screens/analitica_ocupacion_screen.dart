import 'package:flutter/material.dart';

import '../models/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';

/// ANALÍTICA DE OCUPACIÓN del dueño (pestaña "Ocupación" del hub de Reportes).
/// Inteligencia de negocio estilo Playtomic/dashboards, calculada sobre las
/// reservas REALES de sus canchas (sin SQL nuevo): mapa de calor hora × día
/// (cuándo se llena), hora y día pico, ocupación promedio, tasa de no-show,
/// ingreso por cancha y comparativa mes vs mes. Ayuda a decidir precios,
/// promos de valle y en qué cancha invertir.
class AnaliticaOcupacionScreen extends StatefulWidget {
  const AnaliticaOcupacionScreen({super.key});

  @override
  State<AnaliticaOcupacionScreen> createState() =>
      _AnaliticaOcupacionScreenState();
}

/// Período de análisis (ventana hacia atrás desde hoy).
enum _Periodo { d30, d90, mes, todo }

class _AnaliticaOcupacionScreenState extends State<AnaliticaOcupacionScreen> {
  _Periodo _periodo = _Periodo.d90;

  static const _diasSem = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  static const _diasSemLargo = [
    'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'
  ];
  static const _mesesAbr = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];

  @override
  void initState() {
    super.initState();
    // Trae reservas frescas de la nube para que la analítica no dependa de un
    // refresco manual (device-first: pinta con lo que hay y actualiza detrás).
    appState.cargarReservasRemotas();
  }

  static String _iso(DateTime d) => '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  /// Fecha de inicio del período (hasta = hoy). Para "todo" cae a la reserva
  /// más antigua del dueño (o hoy si no hay).
  DateTime _desde(DateTime hoy, String primeraReserva) {
    switch (_periodo) {
      case _Periodo.d30:
        return hoy.subtract(const Duration(days: 29));
      case _Periodo.d90:
        return hoy.subtract(const Duration(days: 89));
      case _Periodo.mes:
        return DateTime(hoy.year, hoy.month, 1);
      case _Periodo.todo:
        final p = DateTime.tryParse(primeraReserva);
        return p ?? hoy;
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return AnchoLectura(
      child: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          final canchas = appState.misCanchas;
          final mias = appState.reservas
              .where((r) => appState.miCanchaDeReserva(r.canchaId) != null)
              .toList();
          final moneda =
              canchas.isNotEmpty ? canchas.first.monedaSimbolo : 'S/';

          final hoyD = DateTime.now();
          final hoy = DateTime(hoyD.year, hoyD.month, hoyD.day);
          final primera = mias.isEmpty
              ? _iso(hoy)
              : mias.map((r) => r.fecha).where((f) => f.isNotEmpty).fold<String>(
                  _iso(hoy), (m, f) => f.compareTo(m) < 0 ? f : m);
          final desde = _desde(hoy, primera);
          final desdeIso = _iso(desde);
          final hoyIso = _iso(hoy);
          final diasPeriodo =
              hoy.difference(DateTime(desde.year, desde.month, desde.day))
                      .inDays +
                  1;

          // Reservas dentro del período (resueltas a MI cancha).
          bool enRango(Reserva r) =>
              r.fecha.isNotEmpty &&
              r.fecha.compareTo(desdeIso) >= 0 &&
              r.fecha.compareTo(hoyIso) <= 0;
          final enPeriodo = mias.where(enRango).toList();
          final activas =
              enPeriodo.where((r) => r.estado != EstadoReserva.noShow).toList();
          final noShows =
              enPeriodo.where((r) => r.estado == EstadoReserva.noShow).length;

          // Filas del mapa: horas reservables (unión de las grillas de las
          // canchas + cualquier hora reservada fuera de grilla).
          final horasSet = <String>{};
          for (final c in canchas) {
            horasSet.addAll(c.horariosSlots());
          }
          for (final r in activas) {
            horasSet.add(r.horaInicio);
          }
          final horas = horasSet.toList()..sort();

          // Conteo por (díaSemana 0..6, hora) + totales por hora y por día.
          final celda = <String, int>{};
          final porHora = <String, int>{};
          final porDia = List<int>.filled(7, 0);
          var maxCelda = 0;
          for (final r in activas) {
            final d = DateTime.tryParse(r.fecha);
            if (d == null) continue;
            final ds = d.weekday - 1; // 0=lunes
            final k = '$ds|${r.horaInicio}';
            final v = (celda[k] ?? 0) + 1;
            celda[k] = v;
            if (v > maxCelda) maxCelda = v;
            porHora[r.horaInicio] = (porHora[r.horaInicio] ?? 0) + 1;
            porDia[ds] = porDia[ds] + 1;
          }

          // Hora y día pico.
          String horaPico = '';
          var horaPicoN = 0;
          porHora.forEach((h, n) {
            if (n > horaPicoN) {
              horaPicoN = n;
              horaPico = h;
            }
          });
          var diaPicoIdx = -1, diaPicoN = 0;
          for (var i = 0; i < 7; i++) {
            if (porDia[i] > diaPicoN) {
              diaPicoN = porDia[i];
              diaPicoIdx = i;
            }
          }

          // Ocupación promedio del período = reservas activas / (slots por día ×
          // días). Aproximación honesta con la config actual de las canchas.
          final slotsDia =
              canchas.fold<int>(0, (s, c) => s + c.horariosSlots().length);
          final capacidad = slotsDia * diasPeriodo;
          final ocupPct =
              capacidad == 0 ? 0 : (activas.length * 100 / capacidad).round();
          final noShowPct = enPeriodo.isEmpty
              ? 0
              : (noShows * 100 / enPeriodo.length).round();

          // Ingreso (cobrado) por cancha, dentro del período.
          final ingCancha = <String, int>{};
          final nombreCancha = <String, String>{};
          for (final r in activas.where((r) => r.pagado)) {
            final c = appState.miCanchaDeReserva(r.canchaId);
            if (c == null) continue;
            ingCancha[c.id] = (ingCancha[c.id] ?? 0) + r.precio;
            nombreCancha[c.id] = c.nombre;
          }
          final ingList = ingCancha.entries.toList()
            ..sort((a, b) => b.value.compareTo(a.value));
          final maxIng =
              ingList.isEmpty ? 0 : ingList.first.value;

          // Mes vs mes (independiente del selector de período).
          final claveMes = hoyIso.substring(0, 7);
          final mesPasadoD = DateTime(hoy.year, hoy.month - 1, 1);
          final claveMesPasado = _iso(mesPasadoD).substring(0, 7);
          int ingresoDe(String claveYm) => mias
              .where((r) =>
                  r.fecha.startsWith(claveYm) &&
                  r.pagado &&
                  r.estado != EstadoReserva.noShow)
              .fold<int>(0, (a, r) => a + r.precio);
          final ingMes = ingresoDe(claveMes);
          final ingMesPasado = ingresoDe(claveMesPasado);

          final sinDatos = activas.isEmpty;

          final contenido = ListView(
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 28),
            children: [
              Text('Inteligencia de ocupación',
                  style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 2),
              Text('Cuándo se llena, qué cancha rinde y cómo vienes vs el mes '
                  'pasado — para decidir precios y promos.',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              const SizedBox(height: 12),

              // Selector de período.
              Row(
                children: [
                  _PeriodoChip(
                      texto: '30 días',
                      activo: _periodo == _Periodo.d30,
                      onTap: () => setState(() => _periodo = _Periodo.d30)),
                  _PeriodoChip(
                      texto: '90 días',
                      activo: _periodo == _Periodo.d90,
                      onTap: () => setState(() => _periodo = _Periodo.d90)),
                  _PeriodoChip(
                      texto: 'Este mes',
                      activo: _periodo == _Periodo.mes,
                      onTap: () => setState(() => _periodo = _Periodo.mes)),
                  _PeriodoChip(
                      texto: 'Todo',
                      activo: _periodo == _Periodo.todo,
                      onTap: () => setState(() => _periodo = _Periodo.todo)),
                ],
              ),
              const SizedBox(height: 14),

              if (sinDatos)
                _AvisoVacio()
              else ...[
                // KPIs.
                Row(
                  children: [
                    Expanded(
                      child: _Kpi(
                          valor: '$ocupPct%',
                          label: 'Ocupación prom.',
                          color: lima),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _Kpi(
                          valor: horaPico.isEmpty ? '—' : horaPico,
                          label: horaPico.isEmpty
                              ? 'Hora pico'
                              : 'Hora pico ($horaPicoN)',
                          color: teal),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _Kpi(
                          valor: diaPicoIdx < 0
                              ? '—'
                              : _diasSem[diaPicoIdx],
                          label: diaPicoIdx < 0
                              ? 'Día pico'
                              : 'Día pico (${_diasSemLargo[diaPicoIdx]})',
                          color: amarillo),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _Kpi(
                          valor: '$noShowPct%',
                          label: 'No-show',
                          color: noShowPct >= 15 ? clayOscuro : textoTenueDe(context)),
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                // Mapa de calor hora × día.
                _Tarjeta(
                  titulo: 'Mapa de calor · hora × día',
                  subtitulo:
                      'Reservas por franja en el período. Más oscuro = más lleno.',
                  child: _Heatmap(
                    horas: horas,
                    diasSem: _diasSem,
                    celda: celda,
                    maxCelda: maxCelda,
                  ),
                ),
                const SizedBox(height: 14),

                // Ingreso por cancha.
                if (ingList.isNotEmpty)
                  _Tarjeta(
                    titulo: 'Ingreso por cancha (cobrado)',
                    subtitulo: 'En el período seleccionado.',
                    child: Column(
                      children: [
                        for (final e in ingList)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 10),
                            child: _BarraIngreso(
                              nombre: nombreCancha[e.key] ?? 'Cancha',
                              valor: e.value,
                              max: maxIng,
                              moneda: moneda,
                            ),
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 14),

                // Mes vs mes.
                _Tarjeta(
                  titulo: 'Este mes vs mes pasado (cobrado)',
                  child: _MesVsMes(
                    actual: ingMes,
                    pasado: ingMesPasado,
                    moneda: moneda,
                  ),
                ),
              ],
            ],
          );

          return MediaQuery.of(context).size.width >= 720
              ? Center(
                  child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 880),
                      child: contenido))
              : contenido;
        },
      ),
    );
  }
}

/// Chip de período (estilo Airbnb, tiñe con lima al activarse).
class _PeriodoChip extends StatelessWidget {
  const _PeriodoChip(
      {required this.texto, required this.activo, required this.onTap});
  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: activo ? lima.withOpacity(0.16) : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(
                color: activo ? lima : textoTenueDe(context).withOpacity(0.4)),
          ),
          child: Text(texto,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: activo ? FontWeight.w700 : FontWeight.w500,
                  color: activo ? bosque : textoTenueDe(context))),
        ),
      ),
    );
  }
}

/// Tarjeta contenedora estándar (título + subtítulo opcional + contenido).
class _Tarjeta extends StatelessWidget {
  const _Tarjeta(
      {required this.titulo, this.subtitulo, required this.child});
  final String titulo;
  final String? subtitulo;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(
              color: Color(0x0F000000), blurRadius: 12, offset: Offset(0, 5)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo,
              style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
          if (subtitulo != null) ...[
            const SizedBox(height: 2),
            Text(subtitulo!,
                style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
          ],
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

/// KPI compacto (valor grande + etiqueta), color visible en claro/oscuro.
class _Kpi extends StatelessWidget {
  const _Kpi(
      {required this.valor, required this.label, required this.color});
  final String valor;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: trazo),
      ),
      child: Column(
        children: [
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(valor,
                style: TextStyle(
                    fontSize: 20, fontWeight: FontWeight.w800, color: color)),
          ),
          const SizedBox(height: 2),
          Text(label,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w600,
                  color: textoTenueDe(context))),
        ],
      ),
    );
  }
}

/// Mapa de calor: filas = horas, columnas = días de la semana (L..D). La
/// intensidad de cada celda escala con el conteo relativo al máximo.
class _Heatmap extends StatelessWidget {
  const _Heatmap(
      {required this.horas,
      required this.diasSem,
      required this.celda,
      required this.maxCelda});
  final List<String> horas;
  final List<String> diasSem;
  final Map<String, int> celda;
  final int maxCelda;

  // Rampa del calor: verde claro → verde WhatsApp (lima) intenso.
  static const _calorClaro = Color(0xFFCFEDE6);

  Color _color(int n) {
    if (n <= 0) return const Color(0xFFEFEFEF);
    final f = maxCelda <= 0 ? 0.0 : (n / maxCelda).clamp(0.0, 1.0);
    return Color.lerp(_calorClaro, lima, f) ?? lima;
  }

  @override
  Widget build(BuildContext context) {
    if (horas.isEmpty) {
      return Text('Sin franjas configuradas.',
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: textoTenueDe(context)));
    }
    const anchoHora = 42.0;
    return Column(
      children: [
        // Cabecera de días.
        Row(
          children: [
            const SizedBox(width: anchoHora),
            for (final d in diasSem)
              Expanded(
                child: Center(
                  child: Text(d,
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: textoTenueDe(context))),
                ),
              ),
          ],
        ),
        const SizedBox(height: 4),
        for (final h in horas)
          Padding(
            padding: const EdgeInsets.only(bottom: 3),
            child: Row(
              children: [
                SizedBox(
                  width: anchoHora,
                  child: Text(h,
                      style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          color: textoTenueDe(context))),
                ),
                for (var ds = 0; ds < 7; ds++)
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Tooltip(
                        message:
                            '${celda['$ds|$h'] ?? 0} reserva(s) · $h ${diasSem[ds]}',
                        child: AspectRatio(
                          aspectRatio: 1.6,
                          child: Container(
                            decoration: BoxDecoration(
                              color: _color(celda['$ds|$h'] ?? 0),
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        const SizedBox(height: 8),
        // Leyenda menos → más.
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text('menos',
                style: TextStyle(fontSize: 10, color: textoTenueDe(context))),
            const SizedBox(width: 6),
            for (final f in [0.0, 0.25, 0.5, 0.75, 1.0])
              Container(
                width: 14,
                height: 14,
                margin: const EdgeInsets.symmetric(horizontal: 1),
                decoration: BoxDecoration(
                  color: f == 0.0
                      ? const Color(0xFFEFEFEF)
                      : Color.lerp(_calorClaro, lima, f),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            const SizedBox(width: 6),
            Text('más',
                style: TextStyle(fontSize: 10, color: textoTenueDe(context))),
          ],
        ),
      ],
    );
  }
}

/// Barra horizontal de ingreso por cancha (normalizada al máximo).
class _BarraIngreso extends StatelessWidget {
  const _BarraIngreso(
      {required this.nombre,
      required this.valor,
      required this.max,
      required this.moneda});
  final String nombre;
  final int valor;
  final int max;
  final String moneda;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final f = max <= 0 ? 0.0 : (valor / max).clamp(0.03, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
            ),
            Text('$moneda $valor',
                style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w800)),
          ],
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: f,
            minHeight: 9,
            backgroundColor: const Color(0xFFECEFE8),
            valueColor: const AlwaysStoppedAnimation(lima),
          ),
        ),
      ],
    );
  }
}

/// Comparativa mes actual vs mes pasado con variación porcentual.
class _MesVsMes extends StatelessWidget {
  const _MesVsMes(
      {required this.actual, required this.pasado, required this.moneda});
  final int actual;
  final int pasado;
  final String moneda;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final delta = pasado == 0 ? null : ((actual - pasado) * 100 / pasado);
    final sube = (delta ?? 0) >= 0;
    final color = delta == null
        ? textoTenueDe(context)
        : (sube ? lima : clayOscuro);
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Este mes',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              Text('$moneda $actual',
                  style: t.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w800, color: lima)),
            ],
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Mes pasado',
                  style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              Text('$moneda $pasado',
                  style: t.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: textoTenueDe(context))),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Icon(
                delta == null
                    ? Icons.remove
                    : (sube ? Icons.trending_up : Icons.trending_down),
                color: color),
            Text(
                delta == null
                    ? 's/ref'
                    : '${sube ? '+' : ''}${delta.round()}%',
                style: t.bodyMedium
                    ?.copyWith(color: color, fontWeight: FontWeight.w800)),
          ],
        ),
      ],
    );
  }
}

class _AvisoVacio extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          const CircleAvatar(
              radius: 18,
              backgroundColor: teal,
              child: Icon(Icons.insights, size: 19, color: Colors.white)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Aún no hay reservas en este período. Cuando entren reservas, '
              'aquí verás cuándo se llenan tus canchas, tu hora pico y qué '
              'cancha rinde más.',
              style: t.bodySmall?.copyWith(color: bosque, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
