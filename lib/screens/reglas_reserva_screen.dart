import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/club_pagos_service.dart';
import '../state/app_state.dart';
import '../ui/ds.dart';

const _dias = ['lun', 'mar', 'mie', 'jue', 'vie', 'sab', 'dom'];
const _nombreDia = {
  'lun': 'Lunes', 'mar': 'Martes', 'mie': 'Miércoles', 'jue': 'Jueves',
  'vie': 'Viernes', 'sab': 'Sábado', 'dom': 'Domingo',
};
const _corto = {'lun': 'L', 'mar': 'M', 'mie': 'X', 'jue': 'J', 'vie': 'V', 'sab': 'S', 'dom': 'D'};

/// REGLAS DE RESERVA de una cancha (plan nocturno A2). El backend
/// (`reservas/reglas.py`) es la fuente de verdad: valida, recorta y las aplica
/// a la disponibilidad, los precios y la política de cancelación. Una cancha
/// sin reglas funciona como siempre.
class ReglasReservaScreen extends StatefulWidget {
  const ReglasReservaScreen({super.key, required this.cancha});
  final Cancha cancha;

  @override
  State<ReglasReservaScreen> createState() => _ReglasReservaScreenState();
}

class _ReglasReservaScreenState extends State<ReglasReservaScreen> {
  RespuestaClub? _r;
  Map<String, dynamic> _reglas = {};
  Map<String, dynamic> _base = {};
  bool _todasDelLocal = false;
  bool _guardando = false;
  bool _cambios = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    final r = await ClubPagosService.reglas(widget.cancha.id);
    if (!mounted) return;
    setState(() {
      _r = r;
      _reglas = Map<String, dynamic>.from(r.datos['reglas'] as Map? ?? {});
      _base = Map<String, dynamic>.from(r.datos['base'] as Map? ?? {});
    });
  }

  void _set(String k, Object? v) => setState(() {
        if (v == null) {
          _reglas.remove(k);
        } else {
          _reglas[k] = v;
        }
        _cambios = true;
      });

  List<Cancha> get _delLocal =>
      appState.misCanchas.where((c) => c.club == widget.cancha.club && c.verificada).toList();

  String get _moneda => (_base['moneda'] ?? 'S/').toString().isEmpty ? 'S/' : _base['moneda'].toString();

  Future<void> _guardar() async {
    setState(() => _guardando = true);
    final ids = _todasDelLocal ? [for (final c in _delLocal) c.id] : [widget.cancha.id];
    final r = await ClubPagosService.guardarReglas(ids, _reglas);
    if (!mounted) return;
    setState(() {
      _guardando = false;
      if (r.ok) {
        _reglas = Map<String, dynamic>.from(r.datos['reglas'] as Map? ?? _reglas);
        _cambios = false;
      }
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(r.ok ? 'Reglas guardadas en ${ids.length} cancha${ids.length == 1 ? '' : 's'}' : r.mensaje)));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_cambios,
      onPopInvokedWithResult: (pop, _) async {
        if (pop) return;
        final salir = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('¿Salir sin guardar?'),
            content: const Text('Perderás los cambios en las reglas.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Seguir editando')),
              FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Salir')),
            ],
          ),
        );
        if (salir == true && context.mounted) Navigator.of(context).pop();
      },
      child: Scaffold(
        appBar: AppBar(title: Text('Reglas · ${widget.cancha.nombre}')),
        bottomNavigationBar: _r?.ok == true
            ? SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Esp.x4, Esp.x2, Esp.x4, Esp.x3),
                  child: CLBoton(texto: 'Guardar reglas', cargando: _guardando, onPressed: _cambios ? _guardar : null),
                ),
              )
            : null,
        body: _r == null
            ? ListView(padding: Esp.pantalla, children: [const SizedBox(height: Esp.x4), CLSkeleton.lista(n: 5)])
            : !_r!.ok
                ? CLError(mensaje: _r!.mensaje, onReintentar: _cargar)
                : ListView(
                    padding: const EdgeInsets.fromLTRB(Esp.x4, 0, Esp.x4, Esp.x10),
                    children: [
                      if (_r!.datos['disponible'] == false)
                        const Padding(
                          padding: EdgeInsets.only(top: Esp.x3),
                          child: CLAviso(tono: CLTono.aviso, texto: 'Las reglas se activarán cuando terminemos de habilitarlas en tu zona.'),
                        ),
                      ..._horario(context),
                      ..._franjas(context),
                      ..._luz(context),
                      ..._ventana(context),
                      ..._cancelacion(context),
                      ..._cierres(context),
                      if (_delLocal.length > 1) ...[
                        const SizedBox(height: Esp.x4),
                        CheckboxListTile(
                          value: _todasDelLocal,
                          onChanged: (v) => setState(() {
                            _todasDelLocal = v ?? false;
                            _cambios = true;
                          }),
                          title: Text('Aplicar a las ${_delLocal.length} canchas de ${widget.cancha.club}'),
                          contentPadding: EdgeInsets.zero,
                        ),
                      ],
                    ],
                  ),
      ),
    );
  }

  // ── horario por día ──
  List<Widget> _horario(BuildContext context) {
    final hs = Map<String, dynamic>.from(_reglas['horario_semana'] as Map? ?? {});
    final ap = (_base['hora_apertura'] ?? '07:00').toString();
    final ci = (_base['hora_cierre'] ?? '23:00').toString();
    void guardar(Map<String, dynamic> n) => _set('horario_semana', n.isEmpty ? null : n);
    return [
      CLSeccion(titulo: 'Horario por día', bajada: 'General: $ap a $ci (el cierre es la hora del último turno).'),
      CLTarjeta(
        padding: const EdgeInsets.symmetric(vertical: Esp.x2),
        child: Column(children: [
          for (final d in _dias)
            _FilaDia(
              dia: _nombreDia[d]!,
              cerrado: hs.containsKey(d) && hs[d] == null,
              propio: hs[d] is Map,
              apertura: hs[d] is Map ? hs[d]['apertura'].toString() : ap,
              cierre: hs[d] is Map ? hs[d]['cierre'].toString() : ci,
              alAbrir: (abierto) {
                final n = Map<String, dynamic>.from(hs);
                if (abierto) {
                  n.remove(d);
                } else {
                  n[d] = null;
                }
                guardar(n);
              },
              alHora: (a, c) {
                final n = Map<String, dynamic>.from(hs);
                if (a == ap && c == ci) {
                  n.remove(d);
                } else {
                  n[d] = {'apertura': a, 'cierre': c};
                }
                guardar(n);
              },
            ),
        ]),
      ),
    ];
  }

  // ── franjas de precio ──
  List<Widget> _franjas(BuildContext context) {
    final fr = [for (final f in (_reglas['franjas'] as List? ?? [])) Map<String, dynamic>.from(f as Map)];
    return [
      CLSeccion(
        titulo: 'Precios por franja',
        bajada: 'Hora punta, fin de semana… Manda sobre la hora feliz.',
        accion: TextButton.icon(onPressed: () => _editarFranja(fr, null), icon: const Icon(Icons.add_rounded), label: const Text('Agregar')),
      ),
      if (fr.isEmpty)
        CLAviso(texto: 'Sin franjas: se cobra el precio general ($_moneda ${_base['precio_hora'] ?? ''} por hora).')
      else
        for (var i = 0; i < fr.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: Esp.x3),
            child: CLTarjeta(
              onTap: () => _editarFranja(fr, i),
              semantica: 'Editar franja ${fr[i]['nombre']}',
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text((fr[i]['nombre'] ?? '').toString().isEmpty ? 'Franja ${i + 1}' : fr[i]['nombre'].toString(),
                        style: Tipo.subtitulo(context)),
                    Text('${[for (final d in fr[i]['dias'] as List) _corto[d]].join(' ')} · ${fr[i]['desde']}–${fr[i]['hasta']}',
                        style: Tipo.detalle(context)),
                  ]),
                ),
                CLPrecio(
                  monto: ((fr[i]['precio_turno'] as num?) ?? 0) > 0 ? fr[i]['precio_turno'] as num : (fr[i]['precio_hora'] as num? ?? 0),
                  moneda: _moneda,
                  unidad: ((fr[i]['precio_turno'] as num?) ?? 0) > 0 ? '/turno' : '/h',
                ),
              ]),
            ),
          ),
    ];
  }

  Future<void> _editarFranja(List<Map<String, dynamic>> fr, int? i) async {
    final res = await mostrarHojaCL<Map<String, dynamic>>(
      context,
      titulo: i == null ? 'Nueva franja' : 'Editar franja',
      contenido: (_) => _FormFranja(inicial: i == null ? null : fr[i], moneda: _moneda, puedeBorrar: i != null),
    );
    if (res == null) return;
    final n = List<Map<String, dynamic>>.from(fr);
    if (res['_borrar'] == true) {
      n.removeAt(i!);
    } else if (i == null) {
      n.add(res);
    } else {
      n[i] = res;
    }
    _set('franjas', n.isEmpty ? null : n);
  }

  // ── recargo de luz ──
  List<Widget> _luz(BuildContext context) {
    final rl = _reglas['recargo_luz'] as Map?;
    return [
      const CLSeccion(titulo: 'Recargo de iluminación', bajada: 'Monto fijo por turno desde una hora.'),
      CLTarjeta(
        child: Column(children: [
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Cobrar luz en los turnos de noche'),
            value: rl != null,
            onChanged: (v) => _set('recargo_luz', v ? {'desde': '18:30', 'monto': 10} : null),
          ),
          if (rl != null)
            Row(children: [
              Expanded(
                child: _BotonHora(
                  etiqueta: 'Desde',
                  hora: rl['desde'].toString(),
                  alCambiar: (h) => _set('recargo_luz', {...rl, 'desde': h}),
                ),
              ),
              const SizedBox(width: Esp.x3),
              Expanded(
                child: _Paso(
                  etiqueta: 'Monto ($_moneda)',
                  valor: (rl['monto'] as num).toInt(),
                  min: 1,
                  max: 200,
                  paso: 1,
                  alCambiar: (v) => _set('recargo_luz', {...rl, 'monto': v}),
                ),
              ),
            ]),
        ]),
      ),
    ];
  }

  // ── ventana / bloque / tope ──
  List<Widget> _ventana(BuildContext context) {
    int? n(String k) => (_reglas[k] as num?)?.toInt();
    return [
      const CLSeccion(titulo: 'Cuándo y cuánto se puede reservar'),
      CLTarjeta(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _Opciones(
            etiqueta: 'Anticipación mínima',
            opciones: const {0: 'Sin mínimo', 1: '1 h', 2: '2 h', 3: '3 h', 6: '6 h', 12: '12 h', 24: '1 día'},
            valor: n('anticipacion_min_horas') ?? 0,
            alCambiar: (v) => _set('anticipacion_min_horas', v == 0 ? null : v),
          ),
          _Opciones(
            etiqueta: 'Reservas hasta',
            opciones: const {0: 'Lo de siempre', 7: '1 semana', 14: '2 semanas', 30: '1 mes', 60: '2 meses', 90: '3 meses'},
            valor: n('anticipacion_max_dias') ?? 0,
            alCambiar: (v) => _set('anticipacion_max_dias', v == 0 ? null : v),
          ),
          _Opciones(
            etiqueta: 'Turnos seguidos mínimos',
            opciones: const {0: 'Libre', 2: '2', 3: '3', 4: '4'},
            valor: n('min_turnos') ?? 0,
            alCambiar: (v) => _set('min_turnos', v == 0 ? null : v),
          ),
          _Opciones(
            etiqueta: 'Turnos seguidos máximos',
            opciones: const {0: 'Libre', 1: '1', 2: '2', 3: '3', 4: '4', 6: '6'},
            valor: n('max_turnos') ?? 0,
            alCambiar: (v) => _set('max_turnos', v == 0 ? null : v),
          ),
          _Opciones(
            etiqueta: 'Reservas por jugador al día',
            opciones: const {0: 'Sin tope', 1: '1', 2: '2', 3: '3'},
            valor: n('max_reservas_dia_jugador') ?? 0,
            alCambiar: (v) => _set('max_reservas_dia_jugador', v == 0 ? null : v),
          ),
        ]),
      ),
    ];
  }

  List<Widget> _cancelacion(BuildContext context) {
    final v = (_reglas['cancelacion_horas'] as num?)?.toInt();
    return [
      const CLSeccion(
          titulo: 'Política de cancelación',
          bajada: 'Con al menos estas horas de anticipación el jugador recupera su dinero.'),
      CLTarjeta(
        child: _Opciones(
          etiqueta: 'Devolución si cancela con',
          opciones: const {-1: 'La de la app', 2: '2 h', 6: '6 h', 12: '12 h', 24: '24 h', 48: '48 h'},
          valor: v ?? -1,
          alCambiar: (x) => _set('cancelacion_horas', x < 0 ? null : x),
        ),
      ),
    ];
  }

  List<Widget> _cierres(BuildContext context) {
    final ci = [for (final c in (_reglas['cierres'] as List? ?? [])) Map<String, dynamic>.from(c as Map)];
    return [
      CLSeccion(
        titulo: 'Días cerrados',
        bajada: 'Feriados, mantenimiento o eventos privados.',
        accion: TextButton.icon(onPressed: () => _agregarCierre(ci), icon: const Icon(Icons.event_busy_rounded), label: const Text('Agregar')),
      ),
      if (ci.isEmpty)
        const CLAviso(texto: 'No tienes días cerrados programados.')
      else
        CLTarjeta(
          padding: const EdgeInsets.symmetric(vertical: Esp.x1),
          child: Column(children: [
            for (var i = 0; i < ci.length; i++)
              ListTile(
                leading: const Icon(Icons.event_busy_rounded),
                title: Text(ci[i]['fecha'].toString()),
                subtitle: (ci[i]['motivo'] ?? '').toString().isEmpty ? null : Text(ci[i]['motivo'].toString()),
                trailing: IconButton(
                  tooltip: 'Quitar día cerrado',
                  icon: const Icon(Icons.close_rounded),
                  onPressed: () {
                    final n = List<Map<String, dynamic>>.from(ci)..removeAt(i);
                    _set('cierres', n.isEmpty ? null : n);
                  },
                ),
              ),
          ]),
        ),
    ];
  }

  Future<void> _agregarCierre(List<Map<String, dynamic>> ci) async {
    final hoy = DateTime.now();
    final f = await showDatePicker(
        context: context, firstDate: hoy, lastDate: hoy.add(const Duration(days: 365)), initialDate: hoy);
    if (f == null || !mounted) return;
    final iso = '${f.year.toString().padLeft(4, '0')}-${f.month.toString().padLeft(2, '0')}-${f.day.toString().padLeft(2, '0')}';
    final ctl = TextEditingController();
    final motivo = await mostrarHojaCL<String>(
      context,
      titulo: 'Motivo (opcional)',
      contenido: (ctx) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        CLCampo(etiqueta: 'Lo verá el jugador', controller: ctl, maxLength: 80),
        CLBoton(texto: 'Cerrar el $iso', onPressed: () => Navigator.pop(ctx, ctl.text.trim())),
      ]),
    );
    ctl.dispose();
    if (motivo == null) return;
    _set('cierres', [...ci.where((c) => c['fecha'] != iso), {'fecha': iso, 'motivo': motivo}]);
  }
}

// ── piezas ──

class _FilaDia extends StatelessWidget {
  const _FilaDia({
    required this.dia,
    required this.cerrado,
    required this.propio,
    required this.apertura,
    required this.cierre,
    required this.alAbrir,
    required this.alHora,
  });

  final String dia;
  final bool cerrado;
  final bool propio;
  final String apertura;
  final String cierre;
  final ValueChanged<bool> alAbrir;
  final void Function(String apertura, String cierre) alHora;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Esp.x3, vertical: Esp.x1),
      child: Row(children: [
        SizedBox(width: 84, child: Text(dia, style: Tipo.etiqueta(context))),
        Expanded(
          child: cerrado
              ? Text('Cerrado', style: Tipo.detalle(context))
              : Row(children: [
                  _ChipHora(hora: apertura, propio: propio, alCambiar: (h) => alHora(h, cierre), semantica: '$dia abre'),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Esp.x1),
                    child: Text('a', style: Tipo.detalle(context)),
                  ),
                  _ChipHora(hora: cierre, propio: propio, alCambiar: (h) => alHora(apertura, h), semantica: '$dia último turno'),
                ]),
        ),
        Switch(value: !cerrado, onChanged: alAbrir),
      ]),
    );
  }
}

Future<String?> _elegirHora(BuildContext context, String hora) async {
  final p = hora.split(':');
  final t = await showTimePicker(
    context: context,
    initialTime: TimeOfDay(hour: int.tryParse(p.first) ?? 7, minute: int.tryParse(p.length > 1 ? p[1] : '0') ?? 0),
    builder: (ctx, child) => MediaQuery(data: MediaQuery.of(ctx).copyWith(alwaysUse24HourFormat: true), child: child!),
  );
  if (t == null) return null;
  return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

class _ChipHora extends StatelessWidget {
  const _ChipHora({required this.hora, required this.propio, required this.alCambiar, required this.semantica});
  final String hora;
  final bool propio;
  final ValueChanged<String> alCambiar;
  final String semantica;

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        label: '$semantica $hora',
        excludeSemantics: true,
        child: ActionChip(
          label: Text(hora),
          labelPadding: const EdgeInsets.symmetric(horizontal: Esp.x1),
          visualDensity: VisualDensity.compact,
          side: propio ? BorderSide(color: Theme.of(context).colorScheme.primary) : null,
          onPressed: () async {
            final h = await _elegirHora(context, hora);
            if (h != null) alCambiar(h);
          },
        ),
      );
}

class _BotonHora extends StatelessWidget {
  const _BotonHora({required this.etiqueta, required this.hora, required this.alCambiar});
  final String etiqueta;
  final String hora;
  final ValueChanged<String> alCambiar;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(etiqueta, style: Tipo.micro(context)),
        const SizedBox(height: Esp.x1),
        _ChipHora(hora: hora, propio: true, alCambiar: alCambiar, semantica: etiqueta),
      ]);
}

class _Paso extends StatelessWidget {
  const _Paso({required this.etiqueta, required this.valor, required this.min, required this.max, required this.paso, required this.alCambiar});
  final String etiqueta;
  final int valor, min, max, paso;
  final ValueChanged<int> alCambiar;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(etiqueta, style: Tipo.micro(context)),
        Row(children: [
          IconButton(
              tooltip: 'Menos',
              onPressed: valor - paso >= min ? () => alCambiar(valor - paso) : null,
              icon: const Icon(Icons.remove_circle_outline_rounded)),
          Text('$valor', style: Tipo.subtitulo(context)),
          IconButton(
              tooltip: 'Más',
              onPressed: valor + paso <= max ? () => alCambiar(valor + paso) : null,
              icon: const Icon(Icons.add_circle_outline_rounded)),
        ]),
      ]);
}

class _Opciones extends StatelessWidget {
  const _Opciones({required this.etiqueta, required this.opciones, required this.valor, required this.alCambiar});
  final String etiqueta;
  final Map<int, String> opciones;
  final int valor;
  final ValueChanged<int> alCambiar;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: Esp.x4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(etiqueta, style: Tipo.etiqueta(context)),
          const SizedBox(height: Esp.x2),
          Wrap(spacing: Esp.x2, runSpacing: Esp.x2, children: [
            for (final e in opciones.entries)
              ChoiceChip(label: Text(e.value), selected: e.key == valor, onSelected: (_) => alCambiar(e.key)),
          ]),
        ]),
      );
}

class _FormFranja extends StatefulWidget {
  const _FormFranja({required this.inicial, required this.moneda, required this.puedeBorrar});
  final Map<String, dynamic>? inicial;
  final String moneda;
  final bool puedeBorrar;

  @override
  State<_FormFranja> createState() => _FormFranjaState();
}

class _FormFranjaState extends State<_FormFranja> {
  late final _nombre = TextEditingController(text: (widget.inicial?['nombre'] ?? '').toString());
  late final Set<String> _sel = {...((widget.inicial?['dias'] as List?) ?? ['lun', 'mar', 'mie', 'jue', 'vie']).map((e) => e.toString())};
  late String _desde = (widget.inicial?['desde'] ?? '18:00').toString();
  late String _hasta = (widget.inicial?['hasta'] ?? '23:59').toString();
  late bool _porTurno = ((widget.inicial?['precio_turno'] as num?) ?? 0) > 0;
  late final _precio = TextEditingController(text: _precioInicial());

  String _precioInicial() {
    final ini = widget.inicial;
    if (ini == null) return '';
    final v = _porTurno ? ini['precio_turno'] : ini['precio_hora'];
    return v == null ? '' : v.toString();
  }
  String? _error;

  @override
  void dispose() {
    _nombre.dispose();
    _precio.dispose();
    super.dispose();
  }

  void _listo() {
    final p = double.tryParse(_precio.text.replaceAll(',', '.'));
    if (p == null || p <= 0) {
      setState(() => _error = 'Escribe un precio mayor a 0');
      return;
    }
    if (_sel.isEmpty || _desde == _hasta) {
      setState(() => _error = 'Elige al menos un día y un rango de horas');
      return;
    }
    Navigator.of(context).pop({
      'nombre': _nombre.text.trim(),
      'dias': [for (final d in _dias) if (_sel.contains(d)) d],
      'desde': _desde,
      'hasta': _hasta,
      'precio_hora': _porTurno ? 0 : p,
      'precio_turno': _porTurno ? p : 0,
    });
  }

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        CLCampo(etiqueta: 'Nombre (opcional)', controller: _nombre, ayuda: 'Ej.: Hora punta, Fin de semana', maxLength: 40),
        Text('Días', style: Tipo.etiqueta(context)),
        const SizedBox(height: Esp.x2),
        Wrap(spacing: Esp.x2, runSpacing: Esp.x2, children: [
          for (final d in _dias)
            FilterChip(
              label: Text(_nombreDia[d]!.substring(0, 3)),
              selected: _sel.contains(d),
              onSelected: (v) => setState(() => v ? _sel.add(d) : _sel.remove(d)),
            ),
        ]),
        const SizedBox(height: Esp.x4),
        Row(children: [
          Expanded(child: _BotonHora(etiqueta: 'Desde', hora: _desde, alCambiar: (h) => setState(() => _desde = h))),
          Expanded(child: _BotonHora(etiqueta: 'Hasta', hora: _hasta, alCambiar: (h) => setState(() => _hasta = h))),
        ]),
        const SizedBox(height: Esp.x4),
        SegmentedButton<bool>(
          segments: const [ButtonSegment(value: false, label: Text('Por hora')), ButtonSegment(value: true, label: Text('Por turno'))],
          selected: {_porTurno},
          onSelectionChanged: (s) => setState(() => _porTurno = s.first),
        ),
        const SizedBox(height: Esp.x3),
        CLCampo(
          etiqueta: _porTurno ? 'Precio por turno' : 'Precio por hora',
          controller: _precio,
          prefijo: '${widget.moneda} ',
          teclado: const TextInputType.numberWithOptions(decimal: true),
          error: _error,
        ),
        CLBoton(texto: 'Guardar franja', onPressed: _listo),
        if (widget.puedeBorrar)
          CLBoton(texto: 'Quitar franja', tipo: CLBotonTipo.texto, onPressed: () => Navigator.of(context).pop({'_borrar': true})),
      ]);
}
