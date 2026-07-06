import 'package:flutter/material.dart';

import '../data/reservas_repo.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';
import '../widgets/marca.dart';
import 'login_google_sheet.dart';
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
  late Cancha _cancha = widget.canchaInicial ?? widget.club.canchas.first;
  String _dia = 'Hoy';
  String? _hora;

  /// Horas reservables reales de la cancha elegida (apertura→cierre, paso = duración).
  /// Para "Hoy" se omiten las horas que ya pasaron.
  List<String> get _horas {
    int? desde;
    if (_dia == 'Hoy') {
      final n = DateTime.now();
      desde = n.hour * 60 + n.minute;
    }
    return _cancha.horariosSlots(desdeMinutos: desde);
  }

  /// Fecha real (ISO) según el día elegido; "Hoy/Mañana" es solo la etiqueta.
  String get _fechaIso {
    final base = DateTime.now();
    final d = _dia == 'Mañana' ? base.add(const Duration(days: 1)) : base;
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  @override
  void initState() {
    super.initState();
    // Al abrir la ficha, sincroniza el estado REAL de la cancha con el backend:
    // - pendiente → puede pasar a verificada (quita el cartel "pendiente").
    // - verificada → puede DEGRADARSE si el admin la rechazó/revocó (quita los
    //   horarios). Antes solo se sincronizaba si estaba pendiente, así que una
    //   cancha rechazada seguía mostrándose reservable.
    if (_cancha.registrada) _sincronizarFicha();
    // Refresca las reservas de la nube para que la grilla no muestre libre un
    // horario que otro dispositivo ya tomó (integridad la garantiza el UNIQUE,
    // esto es solo para que se vea al día).
    appState.cargarReservasRemotas();
  }

  /// Sincroniza la cancha mostrada (sea mía o no) y refleja el cambio en vivo.
  Future<void> _sincronizarFicha() async {
    final act = await appState.sincronizarCanchaMostrada(_cancha);
    if (!mounted || act == null) return;
    setState(() => _cancha = act);
  }

  Future<void> _refrescarPropiedad() async {
    await appState.sincronizarPropiedades();
    if (!mounted) return;
    await _sincronizarFicha();
  }

  /// Pull-to-refresh: recarga canchas y reservas de la nube + re-sincroniza el
  /// estado de esta cancha (para que un rechazo/aprobación del admin se vea sin
  /// reiniciar la app).
  Future<void> _pullRefresh() async {
    await appState.cargarCanchasRemotas();
    await appState.cargarReservasRemotas();
    if (!mounted) return;
    await _sincronizarFicha();
  }

  /// Al volver del registro, re-resolvemos la cancha que se muestra. Preferimos
  /// la cancha RECIÉN CREADA por su ID EXACTO (no "saltar" a otra cancha del
  /// mismo lugar, que podría estar verificada por otro dueño). Si el reclamo se
  /// revirtió (creada == null), re-resolvemos por proximidad pero SOLO a una
  /// cancha MÍA (nunca a una verificada ajena).
  Future<void> _refrescarDescubierta(Cancha? creada) async {
    // Tras reclamar, MOSTRAR SIEMPRE la cancha recién creada (pendiente de
    // verificación). NO re-resolvemos por proximidad/dedup: una cancha
    // "verificada" cacheada localmente (de pruebas viejas, sin registro en el
    // backend) podía secuestrar la ficha y mostrar la página de reserva.
    if (creada != null) {
      if (creada.id != _cancha.id) setState(() => _cancha = creada);
      return;
    }
    // Reclamo revertido (creada == null): solo re-sincroniza el estado por si
    // otro usuario reclamó el lugar; el panel de descubierta se re-consulta solo.
    await appState.sincronizarPropiedades();
  }

  Color get _color => colorDeporte(_cancha.deporte);

  bool _ocupada(String hora) => appState.reservas.any((r) =>
      r.canchaId == _cancha.id && r.fecha == _fechaIso && r.horaInicio == hora);

  bool _esValle(String hora) => hora.compareTo('12:00') < 0;

  Future<void> _reservar() async {
    final hora = _hora;
    if (hora == null) return;
    if (!_cancha.reservable) return; // no se reserva si está pendiente/descubierta
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) return;
    }
    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
    // Piloto: pago en cancha (efectivo), sin seña con tarjeta.
    final res =
        await appState.agregarReservaJugador(_cancha, _fechaIso, _dia, hora);
    if (!mounted) return;
    if (res == ResultadoReserva.ocupado) {
      setState(() => _hora = null); // libera selección; la grilla se refresca
      messenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text('Ese horario acaba de tomarse. Elige otro, por favor.'),
      ));
      return;
    }
    nav.pop();
    // Solo es "confirmada" si llegó a Supabase (fuente de verdad anti-doble
    // reserva). Con sinConexion/error se guarda local pero NO está garantizada.
    final confirmada = res == ResultadoReserva.ok;
    messenger.showSnackBar(
      SnackBar(
        backgroundColor: confirmada ? pino : const Color(0xFFB4471F),
        duration: const Duration(seconds: 5),
        content: Text(
            confirmada
                ? '✅ Reserva confirmada en ${_cancha.nombre} · $_dia $hora'
                : '⚠️ Guardamos tu reserva, pero no pudimos confirmarla con el '
                    'servidor. Otra persona podría tomar el mismo horario; '
                    'reconéctate para asegurarla.',
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
      body: RefreshIndicator(
        onRefresh: _pullRefresh,
        child: CustomScrollView(
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
                    _PanelDescubierta(
                        cancha: _cancha, onReclamada: _refrescarDescubierta)
                  else if (pendiente)
                    _PanelPendiente(
                        cancha: _cancha, onActualizar: _refrescarPropiedad)
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
                    if (_horas.isEmpty)
                      Text(
                        _dia == 'Hoy'
                            ? 'No quedan horarios para hoy. Elige "Mañana".'
                            : 'Sin horarios disponibles.',
                        style: t.bodyMedium?.copyWith(color: textoTenue),
                      )
                    else
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
  final double precio;
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
                        text: 'S/${precio.toStringAsFixed(2)}',
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

/// Panel de una cancha descubierta en Google. Antes de ofrecer "Reclamar",
/// consulta al backend si ese lugar ya tiene un reclamo activo de OTRO usuario;
/// si es así, bloquea el botón y avisa que ya fue reclamada.
class _PanelDescubierta extends StatefulWidget {
  const _PanelDescubierta({required this.cancha, this.onReclamada});
  final Cancha cancha;

  /// Se invoca al volver del registro con la cancha creada (o null si se revirtió)
  /// para que la ficha re-resuelva por ID exacto y pase a "pendiente de
  /// verificación" o "ya reclamada".
  final Future<void> Function(Cancha? creada)? onReclamada;

  @override
  State<_PanelDescubierta> createState() => _PanelDescubiertaState();
}

class _PanelDescubiertaState extends State<_PanelDescubierta> {
  bool _cargando = true;
  bool _reclamadaPorOtro = false;
  bool _reclamadaPorMi = false;
  String _estadoReclamo = '';

  Cancha get cancha => widget.cancha;

  @override
  void initState() {
    super.initState();
    _consultar();
  }

  Future<void> _consultar() async {
    if (!PropiedadService.disponible) {
      if (mounted) setState(() => _cargando = false);
      return;
    }
    final r = await PropiedadService.lugarReclamado(
      lat: cancha.ubicacion.latitude,
      lng: cancha.ubicacion.longitude,
      canchaId: cancha.id,
      solicitante: appState.usuario?.email ?? '',
    );
    if (!mounted) return;
    setState(() {
      _cargando = false;
      final reclamada = r != null && r['reclamada'] == true;
      final porMi = r != null && r['por_mi'] == true;
      // Ya reclamada por OTRO → bloqueo. Ya reclamada por MÍ → no re-reclamar:
      // aviso que ya la reclamé (en revisión o ya activa), sin volver a caer en
      // la página de reserva.
      _reclamadaPorOtro = reclamada && !porMi;
      _reclamadaPorMi = reclamada && porMi;
      _estadoReclamo = (r?['estado'] ?? '').toString();
    });
  }

  Future<void> _reclamar() async {
    // Pedimos login ANTES de abrir el formulario: así el reclamo nace con dueño
    // definido y el usuario no cae en otra pantalla tras loguearse a mitad.
    if (!appState.logueado) {
      final ok = await LoginGoogleSheet.mostrar(context);
      if (!ok || !mounted) return;
    }
    final creada = await Navigator.of(context).push<Cancha?>(
      MaterialPageRoute(builder: (_) => RegistrarCanchaScreen(base: cancha)),
    );
    if (!mounted) return;
    // Al volver: re-resuelve por la cancha creada (ID exacto). Si prosperó, la
    // ficha pasa a "pendiente de verificación"; si no, re-consultamos por si
    // otro usuario la reclamó mientras tanto.
    await widget.onReclamada?.call(creada);
    if (!mounted) return;
    await _consultar();
  }

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
      child: _reclamadaPorOtro
          ? _yaReclamada(t)
          : _reclamadaPorMi
              ? _yaReclamadaPorMi(t)
              : _reclamable(t),
    );
  }

  Widget _yaReclamadaPorMi(TextTheme t) {
    final activa = _estadoReclamo == 'activada';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(activa ? Icons.verified : Icons.hourglass_top, color: pino),
            const SizedBox(width: 8),
            Expanded(
              child: Text(activa ? 'Ya es tuya' : 'Tu reclamo está en revisión',
                  style: t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Text(
          activa
              ? 'Esta cancha ya está verificada y es tuya. Adminístrala desde '
                  '"Mis canchas" (horarios, precios y cobros).'
              : 'Ya enviaste tu solicitud para esta cancha. Está en revisión; te '
                  'avisamos cuando se apruebe. No necesitas reclamarla otra vez.',
          style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
        ),
      ],
    );
  }

  Widget _yaReclamada(TextTheme t) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.lock_clock, color: clayOscuro),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Cancha ya reclamada',
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Esta cancha ya fue reclamada por otro usuario y está en revisión. '
            'No se puede reclamar dos veces. Si crees que es tuya, escríbenos '
            'para resolverlo.',
            style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
          ),
        ],
      );

  Widget _reclamable(TextTheme t) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.travel_explore, color: pino),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Encontramos esta cancha en Google Maps',
                    style:
                        t.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
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
              onPressed: _cargando ? null : _reclamar,
              icon: _cargando
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.add_location_alt),
              label: Text(_cargando
                  ? 'Verificando disponibilidad…'
                  : 'Reclamar / registrar esta cancha'),
            ),
          ),
        ],
      );
}

/// Panel cuando la cancha está reclamada/registrada pero aún sin verificar la
/// propiedad: no se puede reservar online hasta validar al dueño (anti-fraude).
class _PanelPendiente extends StatefulWidget {
  const _PanelPendiente({required this.cancha, this.onActualizar});
  final Cancha cancha;
  final Future<void> Function()? onActualizar;

  @override
  State<_PanelPendiente> createState() => _PanelPendienteState();
}

class _PanelPendienteState extends State<_PanelPendiente> {
  bool _consultando = false;
  bool _reenviando = false;
  bool _rechazada = false; // el admin no aprobó la solicitud de este usuario
  String? _diag;

  @override
  void initState() {
    super.initState();
    _consultarInicial();
  }

  /// Al abrir la ficha pendiente, consulta el backend: si el reclamo fue
  /// RECHAZADO, mostramos el panel de "Solicitud no aprobada" (solo lo ve quien
  /// reclamó; para el resto la cancha queda libre para reclamar).
  Future<void> _consultarInicial() async {
    if (!PropiedadService.disponible) return;
    final est = await PropiedadService.estado(widget.cancha.id);
    if (!mounted || est == null) return;
    if (est['estado'] == 'rechazada') setState(() => _rechazada = true);
  }

  Future<void> _reenviar() async {
    setState(() {
      _reenviando = true;
      _diag = null;
    });
    final c = widget.cancha;
    final email = c.dueno.isNotEmpty ? c.dueno : (appState.usuario?.email ?? '');
    if (!PropiedadService.disponible) {
      setState(() {
        _reenviando = false;
        _diag = '⚠️ La app no tiene backend configurado (GROWTH_API_URL vacío).';
      });
      return;
    }
    final res = await PropiedadService.crearReclamo(
      canchaId: c.id,
      solicitanteId: email,
      nombreLocal: c.nombre,
      ubicacion: c.ubicacion,
    );
    if (!mounted) return;
    final ok = res != null && res['ok'] == true;
    setState(() {
      _reenviando = false;
      // Si prosperó, la solicitud vuelve a estar EN REVISIÓN: salimos del estado
      // "rechazada" y mostramos de nuevo el panel pendiente.
      if (ok) _rechazada = false;
      _diag = ok
          ? '✅ Solicitud enviada. Está en revisión; te avisamos cuando se '
              'apruebe.'
          : '⚠️ No se pudo enviar la solicitud. Reintenta en un momento.';
    });
  }

  Future<void> _verificarAhora() async {
    setState(() {
      _consultando = true;
      _diag = null;
    });
    if (!PropiedadService.disponible) {
      setState(() {
        _consultando = false;
        _diag = '⚠️ La app no tiene backend configurado (GROWTH_API_URL vacío). '
            'El reclamo no llega al servidor.';
      });
      return;
    }
    final est = await PropiedadService.estado(widget.cancha.id);
    if (!mounted) return;
    String msg;
    if (est == null) {
      msg = '⚠️ No se pudo consultar al servidor (sin respuesta). '
          'ID consultado: ${widget.cancha.id}';
    } else if (est['existe'] != true) {
      msg = '❌ El servidor NO tiene un reclamo para esta cancha.\n'
          'ID consultado: ${widget.cancha.id}\n'
          'Esto significa que el reclamo no se creó en el backend.';
    } else {
      final estado = est['estado'] ?? '—';
      final verif = est['verificada'] == true;
      if (estado == 'rechazada') {
        _rechazada = true;
        msg = '';
      } else if (verif) {
        msg = '✅ ¡Aprobada! Habilitando tus reservas…';
        await widget.onActualizar?.call();
      } else {
        msg = '⏳ Tu solicitud sigue en revisión. Te avisamos cuando se apruebe.';
      }
    }
    if (!mounted) return;
    setState(() {
      _consultando = false;
      _diag = msg.isEmpty ? null : msg;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _rechazada ? const Color(0xFFFBE7E7) : const Color(0xFFFDF6EC),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
            color: _rechazada
                ? const Color(0xFFE9C2C2)
                : const Color(0xFFE9D9C2)),
      ),
      child: _rechazada ? _panelRechazada(t) : _panelPendiente(t),
    );
  }

  Widget _diagBox(TextTheme t) => (_diag == null)
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFF3EFE7),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(_diag!,
                style: t.bodySmall?.copyWith(color: tinta, height: 1.4)),
          ),
        );

  Widget _panelRechazada(TextTheme t) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.cancel_outlined, color: Color(0xFFB4231F)),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Solicitud no aprobada',
                    style: t.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: const Color(0xFF8A1A17))),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'No pudimos confirmar que seas el dueño de esta cancha, así que tu '
            'solicitud no fue aprobada. Si crees que es un error, vuelve a '
            'enviarla con tus datos correctos o escríbenos para resolverlo.',
            style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: bosque, foregroundColor: lima),
              onPressed: _reenviando ? null : _reenviar,
              icon: _reenviando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.refresh, size: 18),
              label: Text(_reenviando ? 'Enviando…' : 'Volver a solicitar'),
            ),
          ),
          _diagBox(t),
        ],
      );

  Widget _panelPendiente(TextTheme t) => Column(
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
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _consultando ? null : _verificarAhora,
              icon: _consultando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.sync, size: 18),
              label: Text(_consultando
                  ? 'Consultando al servidor…'
                  : 'Verificar estado ahora'),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                  backgroundColor: bosque, foregroundColor: lima),
              onPressed: _reenviando ? null : _reenviar,
              icon: _reenviando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: lima))
                  : const Icon(Icons.send, size: 18),
              label: Text(_reenviando
                  ? 'Reenviando…'
                  : 'Reenviar solicitud de verificación'),
            ),
          ),
          _diagBox(t),
        ],
      );
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
