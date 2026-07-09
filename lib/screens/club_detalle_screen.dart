import 'package:flutter/material.dart';

import '../data/reservas_repo.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../services/location_service.dart';
import '../services/propiedad_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/court_lines.dart';
import '../widgets/marca.dart';
import 'editar_cancha_screen.dart';
import 'login_google_sheet.dart';
import 'pago_sheet.dart';
import 'registrar_cancha_screen.dart';
import 'reservas_dueno_screen.dart';

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
  bool _reclamoRechazado = false; // MI reclamo de esta cancha fue rechazado
  bool _reclamablePorRechazo = false; // reclamo AJENO rechazado → libre para reclamar

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
    if (_cancha.registrada) {
      _sincronizarFicha();
      _evaluarReclamoRechazado();
    }
    // Refresca las reservas de la nube para que la grilla no muestre libre un
    // horario que otro dispositivo ya tomó (integridad la garantiza el UNIQUE,
    // esto es solo para que se vea al día).
    appState.cargarReservasRemotas();
  }

  /// Si el (último) reclamo de esta cancha fue RECHAZADO y NO es mío, la cancha
  /// vuelve a estar LIBRE: se muestra como reclamable (el dueño real, u otro,
  /// puede reclamarla). El que fue rechazado ve su propio panel "no aprobada".
  Future<void> _evaluarReclamoRechazado() async {
    if (!PropiedadService.disponible) return;
    if (!_cancha.registrada || _cancha.verificada) return;
    final est = await PropiedadService.estado(_cancha.id,
        solicitante: appState.usuario?.email);
    if (!mounted || est == null) return;
    if (est['estado'] == 'rechazada' && est['es_mio'] != true) {
      setState(() => _reclamablePorRechazo = true);
    }
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

  /// ¿El usuario logueado es el DUEÑO de esta cancha? (para mostrarle el panel
  /// de administración en vez de la vista pública de "Reservar").
  bool get _soyDueno {
    final email = appState.usuario?.email ?? '';
    return email.isNotEmpty && _cancha.dueno == email;
  }

  /// Abre la edición de la cancha (precio, horarios, deporte…) y, al volver,
  /// re-resuelve la cancha mostrada para reflejar los cambios al instante.
  Future<void> _editar() async {
    final nav = Navigator.of(context);
    await nav.push(MaterialPageRoute(
        builder: (_) => EditarCanchaScreen(cancha: _cancha)));
    if (!mounted) return;
    Cancha? act;
    for (final x in appState.todasLasCanchas()) {
      if (x.id == _cancha.id) {
        act = x;
        break;
      }
    }
    if (act != null) setState(() => _cancha = act!);
  }

  /// Abre el panel de reservas/cobros del dueño.
  void _verReservas() {
    Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const ReservasDuenoScreen()));
  }

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
    // Pago (SIMULADO en el piloto): cierra el ciclo de reserva. Si el usuario
    // cancela o el pago no fue exitoso, no se reserva. La pasarela real
    // (Culqi/Yape) se conecta en la fase de pagos sin tocar este flujo.
    final pago = await PagoSheet.mostrar(
      context,
      monto: _cancha.precioHora.round(),
      concepto: 'Reserva · ${_cancha.nombre} · $_dia $hora',
    );
    if (pago == null || !pago.exito || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
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
                ? '✅ Pago OK · Reserva confirmada en ${_cancha.nombre} · $_dia $hora'
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
    // Una cancha con reclamo AJENO rechazado se trata como DESCUBIERTA (libre
    // para reclamar), no como pendiente.
    final descubierta = !_cancha.registrada || _reclamablePorRechazo;
    final pendiente = _cancha.registrada &&
        !_cancha.verificada &&
        !_reclamablePorRechazo;
    return Scaffold(
      backgroundColor: papel,
      body: RefreshIndicator(
        onRefresh: _pullRefresh,
        child: CustomScrollView(
        slivers: [
          // Cabecera FIJA en degradado sage (no se mueve al hacer scroll),
          // igual al estilo del panel "Mis canchas". La foto va en una card
          // dentro del contenido.
          SliverAppBar(
            pinned: true,
            toolbarHeight: 86,
            automaticallyImplyLeading: false,
            backgroundColor: sage,
            foregroundColor: Colors.white,
            elevation: 0,
            flexibleSpace: const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [sage, verde, bosque],
                ),
                borderRadius: BorderRadius.vertical(bottom: Radius.circular(22)),
              ),
            ),
            leadingWidth: 52,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white),
              onPressed: () => Navigator.of(context).maybePop(),
            ),
            titleSpacing: 0,
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(c.nombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: t.titleLarge?.copyWith(
                        color: Colors.white, fontWeight: FontWeight.w700)),
                Text(
                  c.direccion ??
                      '${c.barrio} · ${c.canchas.length} ${c.canchas.length == 1 ? 'cancha' : 'canchas'} · ${c.deportes.map((d) => d.etiqueta).join(' · ')}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.bodySmall?.copyWith(color: Colors.white70),
                ),
              ],
            ),
            actions: [
              IconButton(
                  icon: const Icon(Icons.ios_share, color: Colors.white),
                  onPressed: () {}),
              IconButton(
                  icon: const Icon(Icons.favorite_border, color: Colors.white),
                  onPressed: () {}),
              const SizedBox(width: 6),
            ],
          ),
          SliverToBoxAdapter(
            child: Padding(
              // El "labio" redondeado que monta sobre la foto lo dibuja el hero
              // (ver _HeroGaleria); aquí el contenido sigue seamless sobre papel.
              padding: const EdgeInsets.fromLTRB(22, 14, 22, 110),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Foto de la cancha (card redondeada con carrusel + contador).
                  ClipRRect(
                    borderRadius: BorderRadius.circular(20),
                    child: SizedBox(
                      height: 200,
                      child: _HeroGaleria(cancha: _cancha),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Elige la cancha/deporte: la foto y la info de arriba cambian
                  // según la cancha elegida (cada una tiene sus fotos y precio).
                  if (!descubierta && !pendiente && c.canchas.length > 1) ...[
                    Text('Elige la cancha',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 10),
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
                                    color:
                                        sel ? pino : const Color(0xFFE3DECF),
                                    width: 1.5),
                              ),
                              child: Row(
                                children: [
                                  Icon(iconoDeporte(cc.deporte),
                                      size: 16,
                                      color: colorDeporte(cc.deporte)),
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
                    const SizedBox(height: 16),
                  ],
                  Row(
                    children: [
                      if (c.clubFundador)
                        const _Badge('CLUB FUNDADOR', bg: pino, fg: lima),
                      if (c.clubFundador) const SizedBox(width: 6),
                      if (descubierta)
                        const _Badge('◎ EN GOOGLE',
                            bg: Color(0xFF3A352E), fg: Colors.white)
                      else if (_reclamoRechazado)
                        const _Badge('⛔ SOLICITUD RECHAZADA',
                            bg: Color(0xFFFBE7E7), fg: Color(0xFF8A1A17))
                      else if (pendiente)
                        const _Badge('⏳ PENDIENTE DE VERIFICACIÓN',
                            bg: Color(0xFFFBEAD2), fg: clayOscuro)
                      else
                        const _Badge('DIGITALIZADA',
                            bg: Color(0xFFF0ECE2), fg: Color(0xFF5C574E)),
                      if (!descubierta && _cancha.verificada) ...[
                        const SizedBox(width: 6),
                        const SelloVerificada(),
                      ],
                    ],
                  ),
                  const SizedBox(height: 16),

                  if (descubierta)
                    _PanelDescubierta(
                        cancha: _cancha, onReclamada: _refrescarDescubierta)
                  else if (pendiente)
                    _PanelPendiente(
                        cancha: _cancha,
                        onActualizar: _refrescarPropiedad,
                        onRechazado: (v) {
                          if (mounted) setState(() => _reclamoRechazado = v);
                        })
                  else if (_soyDueno)
                    _PanelDueno(
                        cancha: _cancha,
                        onEditar: _editar,
                        onVerReservas: _verReservas)
                  else ...[
                    // Fila de datos clave (estilo Airbnb): deporte · horario ·
                    // duración · precio, con íconos.
                    _FilaDatos(cancha: _cancha),
                    const SizedBox(height: 18),
                    // Strip de confianza (handoff): garantías reales del producto.
                    const _StripConfianza(),
                    const SizedBox(height: 20),
                    // Servicios (amenities) que el dueño marcó para esta cancha.
                    if (_cancha.amenidades.isNotEmpty) ...[
                      _FilaAmenities(claves: _cancha.amenidades),
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
      bottomNavigationBar: (descubierta || pendiente || _soyDueno)
          ? null
          : _ReservarBar(
              precio: _cancha.precioHora,
              hora: _hora,
              onReservar: _hora == null ? null : _reservar,
            ),
    );
  }
}

/// Panel que ve el DUEÑO al abrir la ficha de SU cancha (ya verificada): en vez
/// de la vista pública de "Reservar", administra su cancha desde aquí (editar
/// precio/horarios y ver sus reservas/cobros).
class _PanelDueno extends StatelessWidget {
  const _PanelDueno(
      {required this.cancha,
      required this.onEditar,
      required this.onVerReservas});
  final Cancha cancha;
  final VoidCallback onEditar;
  final VoidCallback onVerReservas;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: trazo),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                    color: const Color(0xFFEAF6C2),
                    borderRadius: BorderRadius.circular(10)),
                child: const Icon(Icons.verified_user, size: 19, color: pino),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Text('Administras esta cancha',
                    style: t.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Eres el dueño registrado. Los jugadores la ven y reservan; tú '
            'ajustas aquí el precio y los horarios.',
            style: t.bodySmall?.copyWith(color: textoTenue),
          ),
          const SizedBox(height: 16),
          // Resumen de precio y horario.
          Row(
            children: [
              Expanded(
                child: _DatoDueno(
                    etiqueta: 'Precio por hora',
                    valor: 'S/${cancha.precioHora.toStringAsFixed(2)}'),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _DatoDueno(
                    etiqueta: 'Atención',
                    valor:
                        '${cancha.horaApertura}–${cancha.horaCierre}'),
              ),
            ],
          ),
          const SizedBox(height: 6),
          _DatoDueno(
              etiqueta: 'Duración por reserva',
              valor: '${cancha.duracionSlotMin} min'),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: onEditar,
              style: FilledButton.styleFrom(
                backgroundColor: pino,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.edit, size: 19),
              label: const Text('Editar precio y horarios',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onVerReservas,
              style: OutlinedButton.styleFrom(
                foregroundColor: pino,
                side: const BorderSide(color: pino, width: 1.5),
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.receipt_long, size: 19),
              label: const Text('Ver reservas y cobros',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }
}

class _DatoDueno extends StatelessWidget {
  const _DatoDueno({required this.etiqueta, required this.valor});
  final String etiqueta;
  final String valor;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(
        color: papel,
        borderRadius: BorderRadius.circular(11),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(etiqueta, style: t.bodySmall?.copyWith(color: textoTenue)),
          const SizedBox(height: 3),
          Text(valor,
              style: t.titleMedium
                  ?.copyWith(fontWeight: FontWeight.w700, color: tinta)),
        ],
      ),
    );
  }
}

/// Strip de confianza del handoff: tres garantías reales del producto en
/// tarjetitas lima suave (Verificada · Pago seguro · Soporte).
class _StripConfianza extends StatelessWidget {
  const _StripConfianza();

  @override
  Widget build(BuildContext context) {
    return const Row(
      children: [
        Expanded(child: _Garantia(titulo: '✓ Verificada', sub: 'por Pichangol')),
        SizedBox(width: 10),
        Expanded(child: _Garantia(titulo: 'Pago seguro', sub: 'seña protegida')),
        SizedBox(width: 10),
        Expanded(child: _Garantia(titulo: 'Soporte', sub: 'todos los días')),
      ],
    );
  }
}

class _Garantia extends StatelessWidget {
  const _Garantia({required this.titulo, required this.sub});
  final String titulo;
  final String sub;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      decoration: BoxDecoration(
        color: limaSuave,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Text(titulo,
              textAlign: TextAlign.center,
              style: t.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w700, color: bosque)),
          const SizedBox(height: 2),
          Text(sub,
              textAlign: TextAlign.center,
              style: t.bodySmall?.copyWith(color: verde, fontSize: 11)),
        ],
      ),
    );
  }
}

/// Fila de servicios (amenities) de la cancha: ícono + etiqueta por cada uno
/// que el dueño marcó. Solo se muestra si hay al menos uno.
class _FilaAmenities extends StatelessWidget {
  const _FilaAmenities({required this.claves});
  final List<String> claves;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final items = [
      for (final k in claves)
        if (amenidadPorClave(k) != null) amenidadPorClave(k)!,
    ];
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Servicios',
            style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 11),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final a in items)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: trazo),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(a.icono, size: 17, color: bosque),
                    const SizedBox(width: 7),
                    Text(a.etiqueta,
                        style: t.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600, color: tinta)),
                  ],
                ),
              ),
          ],
        ),
      ],
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
  const _PanelPendiente(
      {required this.cancha, this.onActualizar, this.onRechazado});
  final Cancha cancha;
  final Future<void> Function()? onActualizar;
  // Notifica al padre si el reclamo está rechazado (para el badge de la ficha).
  final void Function(bool rechazado)? onRechazado;

  @override
  State<_PanelPendiente> createState() => _PanelPendienteState();
}

class _PanelPendienteState extends State<_PanelPendiente> {
  bool _consultando = false;
  bool _reenviando = false;
  bool _rechazada = false; // el admin no aprobó la solicitud de este usuario
  bool _esMio = false; // ¿el que mira la ficha es quien reclamó / el dueño?
  String? _diag;

  /// Es "mío" si mi correo coincide con el dueño local de la cancha (fiable sin
  /// backend). Se confirma con es_mio del servidor en la consulta inicial.
  bool get _duenoLocal {
    final email = appState.usuario?.email ?? '';
    return email.isNotEmpty && widget.cancha.dueno == email;
  }

  @override
  void initState() {
    super.initState();
    _esMio = _duenoLocal;
    _consultarInicial();
  }

  /// Al abrir la ficha pendiente, consulta el backend: si el reclamo fue
  /// RECHAZADO, mostramos el panel de "Solicitud no aprobada" (solo lo ve quien
  /// reclamó; para el resto la cancha queda libre para reclamar).
  Future<void> _consultarInicial() async {
    if (!PropiedadService.disponible) return;
    final est = await PropiedadService.estado(widget.cancha.id,
        solicitante: appState.usuario?.email);
    if (!mounted || est == null) return;
    final mio = est['es_mio'] == true;
    setState(() => _esMio = _esMio || mio);
    // El estado "rechazada" SOLO lo ve quien reclamó (es_mio). Un usuario sin
    // sesión o con otra cuenta ve la ficha pendiente normal, no el rechazo.
    if (est['estado'] == 'rechazada' && mio) {
      setState(() => _rechazada = true);
      widget.onRechazado?.call(true);
    }
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
    // Ubicación del DISPOSITIVO al re-reclamar: el admin necesita ver desde
    // dónde se está enviando nuevamente la solicitud (anti-fraude "estás en el
    // lugar"). Si el permiso está denegado, queda null y el panel lo indica.
    final desdeAqui = await LocationService.ubicacionPrecisa();
    if (!mounted) return;
    final res = await PropiedadService.crearReclamo(
      canchaId: c.id,
      solicitanteId: email,
      nombreLocal: c.nombre,
      ubicacion: c.ubicacion,
      solicitanteUbicacion: desdeAqui,
    );
    if (!mounted) return;
    final ok = res != null && res['ok'] == true;
    if (ok) widget.onRechazado?.call(false); // el badge vuelve a "pendiente"
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
    final est = await PropiedadService.estado(widget.cancha.id,
        solicitante: appState.usuario?.email);
    if (!mounted) return;
    String msg;
    if (est == null) {
      msg = '⚠️ No se pudo consultar al servidor. Reintenta en un momento.';
    } else if (est['existe'] != true) {
      msg = '⏳ Tu solicitud sigue en revisión. Te avisamos cuando se apruebe.';
    } else {
      final estado = est['estado'] ?? '—';
      final verif = est['verificada'] == true;
      // El rechazo solo se muestra al que reclamó (es_mio).
      if (estado == 'rechazada' && est['es_mio'] == true) {
        _rechazada = true;
        widget.onRechazado?.call(true);
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
            _esMio
                ? 'Tu solicitud está en revisión. Por seguridad, las reservas '
                    'online se habilitan recién cuando confirmemos la propiedad.'
                : 'Esta cancha aún no está activa en Pichangol; todavía no se '
                    'puede reservar online.',
            style: t.bodyMedium?.copyWith(color: textoTenue, height: 1.4),
          ),
          // Los controles del reclamo SOLO los ve quien reclamó (dueño). Un
          // usuario sin sesión o ajeno no ve "Verificar"/"Reenviar".
          if (_esMio) ...[
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
                bottom: 12,
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
          // Contador de fotos "1 / N" (sobre la foto, abajo a la derecha).
          if (fotos.length > 1)
            Positioned(
              bottom: 12,
              right: 12,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.55),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text('${_pagina + 1} / ${fotos.length}',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w700)),
              ),
            ),
        ],
      ),
    );
  }
}

/// Fila de datos clave de la cancha (deporte · horario · duración · precio),
/// con íconos, al estilo de la ficha de Airbnb.
class _FilaDatos extends StatelessWidget {
  const _FilaDatos({required this.cancha});
  final Cancha cancha;

  String get _dur {
    final m = cancha.duracionSlotMin;
    if (m % 60 == 0) return '${m ~/ 60} h';
    if (m == 90) return '1 h 30';
    return '$m min';
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    Widget dato(IconData ic, String txt) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(ic, size: 18, color: bosque),
            const SizedBox(width: 6),
            Text(txt,
                style: t.bodyMedium
                    ?.copyWith(color: tinta, fontWeight: FontWeight.w600)),
          ],
        );
    return Wrap(
      spacing: 16,
      runSpacing: 10,
      children: [
        dato(iconoDeporte(cancha.deporte), cancha.deporte.etiqueta),
        if (cancha.superficie.isNotEmpty)
          dato(iconoSuperficie(cancha.superficie), cancha.superficie),
        dato(Icons.schedule, '${cancha.horaApertura}–${cancha.horaCierre}'),
        dato(Icons.timer_outlined, _dur),
        dato(Icons.payments_outlined,
            'S/${cancha.precioHora.toStringAsFixed(0)} /h'),
      ],
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
