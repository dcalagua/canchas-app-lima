import 'package:flutter/material.dart';

import '../data/reservas_repo.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../models/resena.dart';
import '../services/avisos_service.dart';
import '../services/location_service.dart';
import '../services/pagos_service.dart';
import '../services/places_service.dart';
import '../services/propiedad_service.dart';
import '../services/whatsapp_link.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/ancho_lectura.dart';
import '../widgets/chat_burbuja.dart';
import '../models/bono.dart';
import '../widgets/cargando_pichangol.dart';
import '../widgets/court_lines.dart';
import '../widgets/candado_pro.dart';
import '../widgets/dialogo_pichangol.dart';
import '../widgets/marca.dart';
import 'bonos_dueno_screen.dart';
import 'chat_screen.dart';
import 'editar_cancha_screen.dart';
import '../utils/moneda.dart';
import '../utils/ubicacion_share.dart';
import 'login_google_sheet.dart';
import '../widgets/pago_tarjeta_sheet.dart';
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
  // Deporte elegido para reservar (solo si la cancha es multideporte). null =
  // usa el principal de la cancha.
  Deporte? _deporteSel;
  Deporte get _deporteEfectivo => _deporteSel ?? _cancha.deporte;
  String _dia = 'Hoy';
  // Horas SELECCIONADAS (bloque contiguo). El jugador puede reservar 1 o varias
  // horas seguidas; el bloque siempre queda ordenado (inicio = primera, fin =
  // última + duración), así nunca hay un rango invertido (fin antes del inicio).
  final List<String> _slots = [];
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
    // Refresca el snapshot con la versión MÁS FRESCA (por si el dueño acaba de
    // editar duración de slot / precio / horario): el jugador debe ver el
    // cambio al instante, no el snapshot con el que se abrió la ficha.
    _cancha = appState.canchaVigente(_cancha);
    // Al abrir la ficha, sincroniza el estado REAL de la cancha con el backend:
    // - pendiente → puede pasar a verificada (quita el cartel "pendiente").
    // - verificada → puede DEGRADARSE si el admin la rechazó/revocó (quita los
    //   horarios). Antes solo se sincronizaba si estaba pendiente, así que una
    //   cancha rechazada seguía mostrándose reservable.
    if (_cancha.registrada) {
      _sincronizarFicha();
      _evaluarReclamoRechazado();
    }
    // Baja de Supabase la versión FRESCA de las canchas y re-aplica la vigente:
    // así, en OTRO equipo (el jugador), la duración/precio/horario que el dueño
    // editó se ven al abrir la ficha, sin depender de un pull-to-refresh manual
    // ni de reiniciar la app.
    _refrescarCanchasYFicha();
    // Refresca las reservas de la nube para que la grilla no muestre libre un
    // horario que otro dispositivo ya tomó (integridad la garantiza el UNIQUE,
    // esto es solo para que se vea al día).
    appState.cargarReservasRemotas();
    // Horarios bloqueados por el dueño (no reservables).
    appState.cargarBloqueos();
    // Lista de espera del local (para marcar los slots con cola y ofrecer
    // anotarse en una hora tomada).
    appState.cargarEspera(widget.club.canchas.map((c) => c.id).toList());
    // Bonos del local (ofertas) + saldo de bono del jugador (para el canje).
    appState.cargarBonosClub(_cancha.club);
    appState.cargarMisBonos();
  }

  /// ¿El slot [h] ya pasó? (para "Hoy", una hora anterior a ahora).
  bool _esPasado(String h) {
    final fp = _fechaSlot(h).split('-');
    final hp = h.split(':');
    if (fp.length < 3 || hp.length < 2) return false;
    final y = int.tryParse(fp[0]),
        mo = int.tryParse(fp[1]),
        d = int.tryParse(fp[2]),
        hh = int.tryParse(hp[0]),
        mi = int.tryParse(hp[1]);
    if (y == null || mo == null || d == null || hh == null || mi == null) {
      return false;
    }
    return DateTime(y, mo, d, hh, mi).isBefore(DateTime.now());
  }

  /// El jugador tocó una hora TOMADA: ofrecer lista de espera (anotarse / salir).
  Future<void> _ofrecerEspera(String h) async {
    if (_soyDueno) return;
    if (!appState.logueado) {
      await avisarPichangol(context,
          titulo: 'Inicia sesión',
          mensaje: 'Entra con tu cuenta para anotarte en la lista de espera '
              'de una hora tomada.');
      return;
    }
    final fecha = _fechaSlot(h);
    if (appState.estoyEnEspera(_cancha.id, fecha, h)) {
      final salir = await confirmarPichangol(context,
          titulo: 'Ya estás en la lista de espera',
          mensaje: 'Te avisaremos si las $h se liberan. ¿Quieres salir de la '
              'lista de espera?',
          textoConfirmar: 'Salir',
          destructivo: true,
          icono: Icons.hourglass_bottom);
      if (salir == true) {
        await appState.salirDeEspera(_cancha.id, fecha, h);
        if (mounted) {
          setState(() {});
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text('Saliste de la lista de espera.')));
        }
      }
      return;
    }
    final ok = await confirmarPichangol(context,
        titulo: 'Esa hora está tomada',
        mensaje: 'Las $h ya están reservadas. ¿Te anotamos en la lista de '
            'espera? Si se libera, el dueño te contacta.',
        textoConfirmar: 'Avísame',
        icono: Icons.notifications_active_outlined);
    if (ok == true) {
      await appState.unirmeAEspera(_cancha.id, fecha, h);
      if (mounted) {
        setState(() {});
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            backgroundColor: lima,
            content: Text('Te anotamos para las $h. Te avisaremos si se '
                'libera.')));
      }
    }
  }

  /// Horas del día visible que el jugador ESPERABA y ahora están LIBRES
  /// (device-first: al reabrir la ficha ve que se liberó sin depender de push).
  List<String> _horasLiberadas() {
    if (!appState.logueado || _soyDueno) return const [];
    final out = <String>[];
    for (final h in _horas) {
      if (_ocupada(h) || _esPasado(h)) continue;
      if (appState.estoyEnEspera(_cancha.id, _fechaSlot(h), h)) out.add(h);
    }
    return out;
  }

  /// El DUEÑO tocó una hora reservada: ve la lista de espera y contacta a quien
  /// espera (para ofrecerle la hora si se libera). Si no hay cola, ofrece
  /// bloquear/gestionar como antes.
  void _verEsperaDueno(String h) {
    final fecha = _fechaSlot(h);
    final cola = appState.esperaSlot(_cancha.id, fecha, h);
    if (cola.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Las $h están reservadas. Nadie en lista de espera '
              'todavía.')));
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (ctx) {
        final t = Theme.of(ctx).textTheme;
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.hourglass_top, color: lima),
                    const SizedBox(width: 8),
                    Text('Lista de espera · $h',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                  ],
                ),
                const SizedBox(height: 2),
                Text('Si esta hora se libera, contáctalos por orden de llegada.',
                    style: t.bodySmall?.copyWith(color: textoTenueDe(ctx))),
                const SizedBox(height: 12),
                for (var i = 0; i < cola.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        CircleAvatar(
                          radius: 16,
                          backgroundColor: lima.withOpacity(0.15),
                          child: Text('${i + 1}',
                              style: const TextStyle(
                                  color: lima, fontWeight: FontWeight.w800)),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                              cola[i].nombre.isEmpty
                                  ? cola[i].usuario
                                  : cola[i].nombre,
                              style: t.bodyMedium
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                        ),
                        if (cola[i].telefono.isNotEmpty)
                          IconButton(
                            tooltip: 'WhatsApp',
                            icon: const Icon(Icons.chat, color: lima),
                            onPressed: () => WhatsAppLink.abrir(
                                cola[i].telefono,
                                'Hola ${cola[i].nombre} 👋 Se liberó la hora de '
                                'las $h en ${widget.club.nombre}. ¿La tomas?'),
                          )
                        else
                          IconButton(
                            tooltip: 'Chatear',
                            icon: Icon(Icons.chat_bubble_outline,
                                color: Theme.of(ctx).colorScheme.primary),
                            onPressed: () {
                              Navigator.of(ctx).pop();
                              _chatearConEspera(cola[i].usuario,
                                  cola[i].nombre.isEmpty
                                      ? cola[i].usuario
                                      : cola[i].nombre);
                            },
                          ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  /// Chat del dueño con un jugador en lista de espera.
  void _chatearConEspera(String email, String nombre) {
    final owner = appState.usuario?.email ?? '';
    if (owner.isEmpty || email.isEmpty) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: email,
        titulo: nombre,
        soyProfe: true,
        tipo: 'cancha',
        refId: owner,
      ),
    ));
  }

  /// Baja las canchas de Supabase y, si la cancha mostrada cambió (p. ej. la
  /// duración del turno la editó el dueño desde otro equipo), refresca `_cancha`.
  Future<void> _refrescarCanchasYFicha() async {
    await appState.cargarCanchasRemotas();
    if (!mounted) return;
    final vig = appState.canchaVigente(_cancha);
    if (vig.id == _cancha.id && !identical(vig, _cancha)) {
      setState(() => _cancha = vig);
    }
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
    // Primero, la versión local más fresca (duración/precio/horario editados).
    final vig = appState.canchaVigente(_cancha);
    if (mounted && vig.id == _cancha.id && !identical(vig, _cancha)) {
      setState(() => _cancha = vig);
    }
    // Luego, el estado real del backend (verificada/rechazada).
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

  /// Chat interno con el DUEÑO del local (dudas de horarios/precios antes de
  /// reservar). Exige cuenta; si no hay sesión, pide login con el portón único.
  Future<void> _chatearConDueno() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'escribirle al dueño')) {
      return;
    }
    if (!mounted) return;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: appState.usuario!.email,
        titulo: _cancha.club.isNotEmpty ? _cancha.club : _cancha.nombre,
        soyProfe: false,
        tipo: 'cancha',
        refId: _cancha.dueno,
      ),
    ));
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

  void _verBonos() {
    Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => BonosDuenoScreen(
            club: _cancha.club, moneda: _cancha.monedaSimbolo)));
  }

  // Fecha REAL del slot: los de madrugada (horario que cruza medianoche) caen en
  // el día siguiente. Ocupación, bloqueo y precio se comparan contra esta fecha.
  String _fechaSlot(String hora) => _cancha.fechaRealSlot(_fechaIso, hora);

  bool _reservado(String hora) => appState.reservas.any((r) =>
      r.canchaId == _cancha.id &&
      r.fecha == _fechaSlot(hora) &&
      r.horaInicio == hora);

  bool _bloqueado(String hora) =>
      appState.estaBloqueado(_cancha.id, _fechaSlot(hora), hora);

  // Un slot NO se puede reservar si está reservado o bloqueado por el dueño.
  bool _ocupada(String hora) => _reservado(hora) || _bloqueado(hora);

  bool _esValle(String hora) => hora.compareTo('12:00') < 0;

  /// Descuento efectivo del slot para mostrar: el puntual del dueño si lo tiene,
  /// si no la hora feliz de las mañanas (valle).
  int _descEfectivo(String hora) {
    final slot = appState.descuentoSlotPct(_cancha.id, _fechaSlot(hora), hora);
    if (slot > 0) return slot;
    return _esValle(hora) ? _cancha.descuentoValle : 0;
  }

  /// Selección de un BLOQUE CONTIGUO de horas (para reservar más de una hora).
  /// Tap: si no hay nada, elige esa hora; si tocas un extremo del bloque lo
  /// achica; si tocas otra hora y TODAS las del rango entre el bloque y ella
  /// están libres, rellena el bloque (18:00 → 20:00 = 2 h); si hay una hora
  /// ocupada en medio, empieza un bloque nuevo en la hora tocada.
  void _tapSlot(String h) {
    // Slot TOMADO (reservado, no bloqueado por el dueño) y a futuro → ofrecer
    // lista de espera (waitlist): si se libera, el dueño te contacta.
    if (_reservado(h) && !_esPasado(h)) {
      _ofrecerEspera(h);
      return;
    }
    if (_ocupada(h)) return;
    final todas = _horas;
    setState(() {
      if (_slots.isEmpty) {
        _slots.add(h);
        return;
      }
      if (_slots.contains(h)) {
        // Tocar un extremo lo quita; una hora interna reinicia a esa sola.
        if (h == _slotsOrd.first || h == _slotsOrd.last) {
          _slots.remove(h);
        } else {
          _slots
            ..clear()
            ..add(h);
        }
        return;
      }
      final iH = todas.indexOf(h);
      final iFirst = todas.indexOf(_slotsOrd.first);
      final iLast = todas.indexOf(_slotsOrd.last);
      if (iH < 0 || iFirst < 0 || iLast < 0) {
        _slots
          ..clear()
          ..add(h);
        return;
      }
      final lo = iH < iFirst ? iH : iFirst;
      final hi = iH > iLast ? iH : iLast;
      final rango = [for (var i = lo; i <= hi; i++) todas[i]];
      // El bloque solo se forma si TODAS las horas del rango están libres.
      if (rango.every((s) => !_ocupada(s))) {
        _slots
          ..clear()
          ..addAll(rango);
      } else {
        _slots
          ..clear()
          ..add(h);
      }
    });
  }

  /// Horas del bloque, ordenadas.
  List<String> get _slotsOrd {
    final l = [..._slots];
    l.sort();
    return l;
  }

  /// Total base (sin extras) del bloque: suma del precio efectivo de cada hora
  /// (respeta valle/descuento por hora, así 2 h no es un simple ×2).
  double get _totalBloque => _slots.fold(
      0.0, (a, h) => a + appState.precioSlotEfectivo(_cancha, _fechaSlot(h), h));

  /// El dueño bloquea/desbloquea un horario (los reservados no se tocan).
  Future<void> _alternarBloqueo(String hora) async {
    // Función PRO (regla del director): bloquear/reabrir horas exige la
    // suscripción; sin ella, CTA "Hazte Pro".
    if (!await exigirPro(context, funcion: 'El bloqueo de horas')) return;
    if (!mounted) return;
    if (_reservado(hora)) return; // no bloquear un slot ya reservado
    // El set se actualiza de forma síncrona dentro de alternarBloqueo; el
    // setState refleja el cambio al instante y la red va por detrás.
    final f = appState.alternarBloqueo(_cancha.id, _fechaSlot(hora), hora);
    if (mounted) setState(() {});
    await f;
  }

  /// Hoja "Resumen de tu reserva" (estilo Airbnb) antes de pagar. Devuelve el
  /// método elegido: 'online' (Yape/Tarjeta) o 'cancha' (efectivo), o null si se
  /// cancela. El efectivo SOLO se ofrece si el dueño tiene saldo (destacado): así
  /// PCG cobra su comisión de ese saldo; sin saldo, solo online (comisión al pagar).
  Future<ResumenResultado?> _mostrarResumen(List<String> slots, num total) async {
    final ord = [...slots]..sort();
    return showModalBottomSheet<ResumenResultado>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _ResumenReserva(
        cancha: _cancha,
        dia: _dia,
        hora: ord.first,
        horaFin: _cancha.horaFinDe(ord.last),
        nSlots: ord.length,
        deporte: _deporteEfectivo,
        nombreCliente: appState.usuario?.nombre ?? '',
        total: total,
        permiteEfectivo: appState.esDestacada(_cancha),
        saldoBono: appState.miSaldoBono(_cancha.club),
      ),
    );
  }

  Future<void> _reservar() async {
    if (_slots.isEmpty) return;
    if (!_cancha.reservable) return; // no se reserva si está pendiente/descubierta
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'reservar tu cancha')) {
      return;
    }
    if (!mounted) return;
    final slots = _slotsOrd; // bloque contiguo ordenado (1 o varias horas)
    // Total del bloque = SUMA del precio efectivo de cada hora (respeta valle/
    // descuento por hora, así 2 h no es un simple ×2). La comisión de Pichangol
    // es 100% del lado del dueño; nunca se le suma al jugador.
    final base = _totalBloque;
    // Resumen estilo Airbnb ANTES de pagar. Devuelve método + servicios extra.
    final r = await _mostrarResumen(slots, base);
    if (r == null || !mounted) return;
    final metodo = r.metodo; // 'online' | 'sena' | 'cancha' | 'bono'
    final extras = r.extras;
    // BONO: canje de horas prepagadas. Valida el saldo antes de reservar (no
    // cobra nada; el pago fue al comprar el pack).
    if (metodo == 'bono') {
      if (appState.miSaldoBono(_cancha.club) < slots.length) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No te alcanza el saldo de bono para esas horas.')));
        return;
      }
    }
    // El jugador paga las horas + los servicios extra que eligió (una sola vez).
    final total = base + extras.fold(0.0, (a, s) => a + s.precio);
    // CANJE DE PUNTOS (solo pago ONLINE, en soles): 100 pts = S/3 de descuento.
    // El dueño recibe su bruto completo (la liquidación va con el precio real);
    // el descuento lo absorbe Pichangol de su comisión.
    final canjea = metodo == 'online' &&
        r.usarPuntos &&
        appState.misPuntosDisponibles >= 100 &&
        _cancha.monedaSimbolo == 'S/' &&
        total > 3.0;
    final descuentoPuntos = canjea ? 3.0 : 0.0;
    // Seña anti no-show: % del TOTAL de las horas (sin extras).
    final esSena = metodo == 'sena';
    final senaMonto =
        _cancha.senaPct > 0 ? (base * _cancha.senaPct / 100).round() : 0;
    final mon = _cancha.monedaSimbolo;
    // Etiqueta del bloque para conceptos/mensajes ('18:00–20:00' o '18:00').
    final etiqueta = slots.length > 1
        ? '${slots.first}–${_cancha.horaFinDe(slots.last)}'
        : slots.first;
    final pagoOnline = metodo == 'online';
    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
    // ── FASE 1 (solo si hay COBRO por adelantado): ASEGURA el horario ANTES de
    // cobrar. El UNIQUE de Supabase decide al ganador AQUÍ: si 3 jugadores van
    // por la misma hora a la vez, 2 ven "ocupado" SIN haber puesto su tarjeta
    // (antes se les cobraba y recién después se enteraban). Si el pago luego
    // falla o se cancela, el bloque se LIBERA al instante.
    List<Reserva>? aseguradas;
    if (pagoOnline || esSena) {
      final (resHold, tomadas) = await appState.asegurarBloqueJugador(
          _cancha, _fechaIso, _dia, slots,
          deporte: _deporteEfectivo);
      if (!mounted) return;
      if (resHold == ResultadoReserva.ocupado) {
        setState(() => _slots.clear()); // libera selección; la grilla refresca
        messenger.showSnackBar(const SnackBar(
          backgroundColor: Colors.redAccent,
          content: Text(
              '⛔ Esa hora ya está ocupada: otro jugador la acaba de reservar. '
              'Elige otro horario, por favor. No se te cobró nada.'),
        ));
        return;
      }
      if (resHold != ResultadoReserva.ok) {
        // Sin señal no se puede garantizar el slot NI cobrar online.
        messenger.showSnackBar(const SnackBar(
          backgroundColor: Color(0xFFB4471F),
          content: Text(
              '⚠️ Sin conexión: para pagar online necesitas señal. Puedes '
              'elegir "Pagar en la cancha" mientras tanto.'),
        ));
        return;
      }
      aseguradas = tomadas;
    }
    if (metodo == 'online') {
      // Pago con tarjeta/Yape (Culqi/Libélula). Si cancela o falla, se libera
      // el horario asegurado y no se reserva.
      final pagado = await PagoTarjeta.cobrar(
        context,
        monto: total - descuentoPuntos,
        concepto: 'Reserva · ${_cancha.nombre} · $_dia $etiqueta'
            '${canjea ? ' (−S/3 puntos)' : ''}',
        email: appState.usuario?.email ?? '',
        moneda: mon,
      );
      if (!pagado) {
        await appState.liberarBloqueAsegurado(aseguradas!);
        if (PagoTarjeta.ultimoError.isNotEmpty) {
          appState.avisarPagoRechazado(
              cancha: _cancha,
              fecha: _cancha.fechaRealSlot(_fechaIso, slots.first),
              horas: etiqueta,
              motivo: PagoTarjeta.ultimoError);
        }
        return;
      }
    } else if (esSena) {
      // El jugador ADELANTA la seña (del total). El resto lo paga en la cancha.
      final pagado = await PagoTarjeta.cobrar(
        context,
        monto: senaMonto,
        concepto: 'Seña · ${_cancha.nombre} · $_dia $etiqueta',
        email: appState.usuario?.email ?? '',
        moneda: mon,
      );
      if (!pagado) {
        await appState.liberarBloqueAsegurado(aseguradas!);
        if (PagoTarjeta.ultimoError.isNotEmpty) {
          appState.avisarPagoRechazado(
              cancha: _cancha,
              fecha: _cancha.fechaRealSlot(_fechaIso, slots.first),
              horas: etiqueta,
              motivo: PagoTarjeta.ultimoError);
        }
        return;
      }
    }
    // 'cancha' → sin pasarela: se reserva y el dueño cobra en efectivo.
    // Crea una Reserva por hora (mismo grupo). Con bloque asegurado, CONFIRMA
    // esas mismas filas (estampa pago/medio/seña); sin asegurar (efectivo/bono)
    // verifica que TODAS estén libres como siempre.
    final res = await appState.agregarReservasJugadorMulti(
        _cancha, _fechaIso, _dia, slots,
        deporte: _deporteEfectivo, extras: extras,
        cobro: metodo == 'cancha' ? 'efectivo' : metodo,
        medioPago: esSena
            ? 'sena'
            : pagoOnline
                ? (PagoTarjeta.ultimoMetodo.isNotEmpty
                    ? PagoTarjeta.ultimoMetodo
                    : 'online')
                : (metodo == 'bono' ? 'bono' : 'efectivo'),
        conSena: esSena,
        aseguradas: aseguradas);
    if (!mounted) return;
    if (res == ResultadoReserva.ocupado) {
      setState(() => _slots.clear()); // libera selección; la grilla se refresca
      messenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.redAccent,
        content:
            Text('Alguna de esas horas acaba de tomarse. Elige otras, por favor.'),
      ));
      return;
    }
    nav.pop();
    // Solo es "confirmada" si llegó a Supabase (fuente de verdad anti-doble
    // reserva). Con sinConexion/error se guarda local pero NO está garantizada.
    final confirmada = res == ResultadoReserva.ok;
    if (confirmada) {
      // Ya reservaste: sal de la lista de espera de esas horas (si estabas).
      for (final h in _slotsOrd) {
        if (appState.estoyEnEspera(_cancha.id, _fechaSlot(h), h)) {
          appState.salirDeEspera(_cancha.id, _fechaSlot(h), h);
        }
      }
      // Canje de bono: descuenta las horas usadas (recién al confirmar el slot).
      if (metodo == 'bono') {
        appState.usarBonoHoras(_cancha.club, slots.length);
      }
      // Canje de PUNTOS: se registra recién con la reserva confirmada y el
      // pago hecho (100 pts consumidos, S/3 aplicados).
      if (canjea) {
        appState.canjearPuntos(
            puntos: 100,
            soles: 3.0,
            referencia: '${_cancha.id}_${_fechaIso}_${slots.first}');
      }
    }
    messenger.showSnackBar(
      SnackBar(
        backgroundColor: confirmada ? pino : const Color(0xFFB4471F),
        duration: Duration(seconds: confirmada ? 5 : 9),
        content: Text(
            res == ResultadoReserva.error
                ? '⚠️ No se pudo registrar en el servidor. Queda pendiente y se '
                    'reintenta. Detalle: ${ReservasRepo.ultimoError}'
                : confirmada
                ? (metodo == 'bono'
                    ? '✅ Reserva confirmada con tu bono en ${_cancha.nombre} · $_dia $etiqueta · te quedan ${appState.miSaldoBono(_cancha.club)} h'
                    : esSena
                    ? '✅ Seña pagada · Reserva confirmada en ${_cancha.nombre} · $_dia $etiqueta · paga $mon ${(total - senaMonto).toStringAsFixed(2)} en la cancha'
                    : pagoOnline
                        ? '✅ Pago OK · Reserva confirmada en ${_cancha.nombre} · $_dia $etiqueta'
                        : '✅ Reserva confirmada en ${_cancha.nombre} · $_dia $etiqueta · pagas en la cancha')
                : '⚠️ Sin señal: guardamos tu reserva como PENDIENTE y la '
                    'confirmaremos sola al recuperar conexión. Si para entonces '
                    'otra persona tomó el horario, te avisaremos.',
            style: const TextStyle(color: Colors.white)),
      ),
    );
  }


  // ── Bloques de la ficha (compartidos por el layout de teléfono y el de
  // tablet a 2 columnas). Devuelven los widgets TAL CUAL iban en la columna
  // original; solo cambia cómo se componen en build(). ──

  /// Foto de la cancha (card redondeada con carrusel + contador).
  Widget _wHero({required double alto}) => ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: SizedBox(height: alto, child: _HeroGaleria(cancha: _cancha)),
      );

  /// "Elige la cancha": chips por cancha del local (si hay más de una).
  List<Widget> _wSelectorCancha(bool descubierta, bool pendiente) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final c = widget.club;
    return [
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
                              // Versión vigente (el club es un snapshot de la
                              // navegación; podría traer duración/precio viejos).
                              _cancha = appState.canchaVigente(cc);
                              _slots.clear();
                              _deporteSel = null; // se ajusta a la nueva cancha
                            }),
                            child: Container(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 14),
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: sel ? limaSuave : cs.surface,
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
                                          color: sel ? tinta : cs.onSurface)),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
    ];
  }

  /// Cancha multideporte: elegir qué se va a jugar.
  List<Widget> _wDeporte(bool descubierta, bool pendiente) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return [
                  // Cancha multideporte (loza multiuso): elegir qué se va a jugar.
                  // No afecta la disponibilidad (agenda compartida), solo registra
                  // el deporte de la reserva.
                  if (!descubierta && !pendiente && _cancha.esMultideporte) ...[
                    Text('¿Qué vas a jugar?',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final d in _cancha.deportesJugables)
                          ChoiceChip(
                            label: Text('${emojiDeporte(d)}  ${d.etiqueta}'),
                            selected: _deporteEfectivo == d,
                            selectedColor: colorDeporte(d),
                            labelStyle: TextStyle(
                                color: _deporteEfectivo == d
                                    ? Colors.white
                                    : cs.onSurface,
                                fontWeight: FontWeight.w600),
                            onSelected: (_) =>
                                setState(() => _deporteSel = d),
                          ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],
    ];
  }

  /// Fila de badges (fundador / en Google / pendiente / digitalizada / sello).
  Widget _wBadges(bool descubierta, bool pendiente) {
    final c = widget.club;
    return Row(
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
                        const _Badge('📋 DIGITALIZADA',
                            bg: Color(0xFFF0ECE2), fg: Color(0xFF5C574E)),
                      if (!descubierta && _cancha.verificada) ...[
                        const SizedBox(width: 6),
                        const SelloVerificada(),
                      ],
      ],
    );
  }

  /// Panel según el modo: descubierta / pendiente / dueño / reserva pública.
  List<Widget> _wPanel(bool descubierta, bool pendiente) {
    final t = Theme.of(context).textTheme;
    return [
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
                  else if (_soyDueno) ...[
                    _PanelDueno(
                        cancha: _cancha,
                        onEditar: _editar,
                        onVerReservas: _verReservas,
                        onBonos: _verBonos),
                    const SizedBox(height: 22),
                    Text('Bloquear horarios',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text(
                        'Cierra horas que no quieras alquilar (mantenimiento, o '
                        'walk-in que tomó la cancha). Los jugadores no podrán '
                        'reservarlas. Toca para bloquear/reabrir.',
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        _DiaChip('Hoy', _dia == 'Hoy',
                            () => setState(() => _dia = 'Hoy')),
                        const SizedBox(width: 10),
                        _DiaChip('Mañana', _dia == 'Mañana',
                            () => setState(() => _dia = 'Mañana')),
                      ],
                    ),
                    const SizedBox(height: 14),
                    if (_horas.isEmpty)
                      Text(
                          _dia == 'Hoy'
                              ? 'No quedan horas para hoy. Elige "Mañana".'
                              : 'Sin horas configuradas.',
                          style: t.bodyMedium
                              ?.copyWith(color: textoTenueDe(context)))
                    else
                      Wrap(
                        spacing: 9,
                        runSpacing: 9,
                        children: [
                          for (final h in _horas)
                            _SlotChip(
                              hora: h,
                              // Reservado = ocupada (no se toca); bloqueado =
                              // chip con candado (tap para reabrir); libre = tap
                              // para bloquear.
                              ocupada: _reservado(h),
                              bloqueada: _bloqueado(h),
                              valle: _esValle(h),
                              descuento: _descEfectivo(h),
                              seleccionada: false,
                              nEspera: appState.nEnEspera(
                                  _cancha.id, _fechaSlot(h), h),
                              onTap: () => _reservado(h)
                                  ? _verEsperaDueno(h)
                                  : _alternarBloqueo(h),
                            ),
                        ],
                      ),
                  ] else ...[
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
                            () => setState(() { _dia = 'Hoy'; _slots.clear(); })),
                        const SizedBox(width: 10),
                        _DiaChip('Mañana', _dia == 'Mañana',
                            () => setState(() { _dia = 'Mañana'; _slots.clear(); })),
                      ],
                    ),
                    const SizedBox(height: 20),

                    // Horarios
                    Text('Horarios · ${_cancha.nombre}',
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('Las mañanas (valle) suelen estar más libres.',
                        style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
                    const SizedBox(height: 12),
                    // Banner device-first: una hora que esperabas se liberó.
                    if (_horasLiberadas().isNotEmpty) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: limaSuave,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: lima),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.celebration, color: lima),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                  '¡Se liberó ${_horasLiberadas().join(', ')} que '
                                  'esperabas! Tócala abajo para reservar.',
                                  style: t.bodySmall?.copyWith(
                                      color: bosque,
                                      fontWeight: FontWeight.w700,
                                      height: 1.3)),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],
                    if (_horas.isEmpty)
                      Text(
                        _dia == 'Hoy'
                            ? 'No quedan horarios para hoy. Elige "Mañana".'
                            : 'Sin horarios disponibles.',
                        style: t.bodyMedium?.copyWith(color: textoTenueDe(context)),
                      )
                    else ...[
                      Wrap(
                        spacing: 9,
                        runSpacing: 9,
                        children: [
                          for (final h in _horas)
                            _SlotChip(
                              hora: h,
                              ocupada: _ocupada(h),
                              valle: _esValle(h),
                              descuento: _descEfectivo(h),
                              seleccionada: _slots.contains(h),
                              enEspera: _reservado(h) &&
                                  appState.estoyEnEspera(
                                      _cancha.id, _fechaSlot(h), h),
                              onTap: () => _tapSlot(h),
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.touch_app_outlined,
                              size: 15, color: textoTenueDe(context)),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                                'Toca varias horas seguidas para reservar más '
                                'tiempo (ej. 18:00–20:00 = 2 h).',
                                style: t.bodySmall
                                    ?.copyWith(color: textoTenueDe(context))),
                          ),
                        ],
                      ),
                    ],
                  ],
    ];
  }

  /// Bonos + reseñas del local.
  List<Widget> _wExtras(bool descubierta, bool pendiente) => [
                  // Reseñas del local: reputación real (visible para dueño y
                  // jugadores en canchas ya registradas).
                  if (!descubierta && !pendiente && !_soyDueno) ...[
                    const SizedBox(height: 26),
                    _SeccionBonos(cancha: _cancha),
                  ],
                  if (!descubierta && !pendiente) ...[
                    const SizedBox(height: 26),
                    _SeccionResenas(
                      club: widget.club,
                      canchaDestino: _cancha,
                      puedeResenar: appState.logueado && !_soyDueno,
                    ),
                  ],
      ];

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
      // Globo de chat con el dueño (solo si hay dueño y no soy yo): siempre a la
      // mano, sin scroll. Es nuestra "burbuja" (chat interno Pichangol).
      floatingActionButton: (_cancha.dueno.isNotEmpty && !_soyDueno)
          ? ChatBurbuja(logoUrl: _cancha.fotoUrl, onTap: _chatearConDueno)
          : null,
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
                  colors: [lima, teal], // verde WhatsApp
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
                      [
                        if (c.barrio.isNotEmpty) c.barrio,
                        '${c.canchas.length} ${c.canchas.length == 1 ? 'cancha' : 'canchas'}',
                        c.deportes.map((d) => d.etiqueta).join(' · '),
                      ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: t.bodySmall?.copyWith(color: Colors.white70),
                ),
              ],
            ),
            actions: [
              IconButton(
                  tooltip: 'Compartir ubicación',
                  icon: const Icon(Icons.ios_share, color: Colors.white),
                  onPressed: () => UbicacionShare.menu(context,
                      punto: _cancha.ubicacion,
                      titulo: c.nombre)),
              IconButton(
                  tooltip: 'Guardar en favoritos',
                  icon: Icon(
                      appState.esFavorito(widget.club.id)
                          ? Icons.favorite
                          : Icons.favorite_border,
                      color: appState.esFavorito(widget.club.id)
                          ? const Color(0xFFE0245E)
                          : Colors.white),
                  onPressed: () => setState(
                      () => appState.alternarFavorito(widget.club.id))),
              const SizedBox(width: 6),
            ],
          ),
          SliverToBoxAdapter(
            child: AnchoLectura(
              // En tablet las 2 columnas necesitan más aire que la lectura.
              max: 1150,
              child: Padding(
                // El "labio" redondeado que monta sobre la foto lo dibuja el
                // hero (ver _HeroGaleria); aquí el contenido sigue seamless
                // sobre papel.
                padding: const EdgeInsets.fromLTRB(22, 14, 22, 110),
                // TABLET (≥900 dp): ficha a 2 COLUMNAS estilo Airbnb — foto,
                // badges, bonos y reseñas a la IZQUIERDA; selección de cancha,
                // día y horarios (o el panel del modo) a la DERECHA. En
                // teléfono, la columna única de siempre (mismos bloques).
                child: MediaQuery.sizeOf(context).width >= 900
                    ? Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            flex: 11,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _wHero(alto: 340),
                                const SizedBox(height: 16),
                                _wBadges(descubierta, pendiente),
                                ..._wExtras(descubierta, pendiente),
                              ],
                            ),
                          ),
                          const SizedBox(width: 28),
                          Expanded(
                            flex: 9,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                ..._wSelectorCancha(descubierta, pendiente),
                                ..._wDeporte(descubierta, pendiente),
                                ..._wPanel(descubierta, pendiente),
                              ],
                            ),
                          ),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _wHero(alto: 200),
                          const SizedBox(height: 16),
                          ..._wSelectorCancha(descubierta, pendiente),
                          ..._wDeporte(descubierta, pendiente),
                          _wBadges(descubierta, pendiente),
                          const SizedBox(height: 16),
                          ..._wPanel(descubierta, pendiente),
                          ..._wExtras(descubierta, pendiente),
                        ],
                      ),
              ),
            ),
          ),
        ],
        ),
      ),
      bottomNavigationBar: (descubierta || pendiente || _soyDueno)
          ? null
          : _ReservarBar(
              // Sin selección: precio base /hora. Con bloque: TOTAL de las horas.
              monto: _slots.isEmpty ? _cancha.precioHora : _totalBloque,
              sufijo: _slots.isEmpty ? ' /hora' : '',
              moneda: _cancha.monedaSimbolo,
              detalle: _slots.isEmpty
                  ? 'Elige una hora'
                  : '${_slots.length} h · ${_slotsOrd.first}–${_cancha.horaFinDe(_slotsOrd.last)}',
              onReservar: _slots.isEmpty ? null : _reservar,
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
      required this.onVerReservas,
      required this.onBonos});
  final Cancha cancha;
  final VoidCallback onEditar;
  final VoidCallback onVerReservas;
  final VoidCallback onBonos;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: cs.surface,
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
                    color: limaSuave,
                    borderRadius: BorderRadius.circular(10)),
                child: const Icon(Icons.verified_user, size: 19, color: pino),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Text('Administras esta cancha',
                    style: t.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700, color: cs.onSurface)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Eres el dueño registrado. Los jugadores la ven y reservan; tú '
            'ajustas aquí el precio y los horarios.',
            style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
          ),
          const SizedBox(height: 16),
          // Resumen de precio y horario.
          Row(
            children: [
              Expanded(
                child: _DatoDueno(
                    etiqueta: 'Precio por hora',
                    valor: '${cancha.monedaSimbolo}${cancha.precioHora.toStringAsFixed(2)}'),
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
                backgroundColor: lima,
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
                foregroundColor: lima,
                side: const BorderSide(color: lima, width: 1.5),
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.receipt_long, size: 19),
              label: const Text('Ver reservas y cobros',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onBonos,
              style: OutlinedButton.styleFrom(
                foregroundColor: teal,
                side: const BorderSide(color: teal, width: 1.5),
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              icon: const Icon(Icons.confirmation_number_outlined, size: 19),
              label: const Text('Bonos de horas (packs)',
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
    final cs = Theme.of(context).colorScheme;
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
                  color: cs.surface,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: trazo),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(a.icono, size: 17, color: cs.primary),
                    const SizedBox(width: 7),
                    Text(a.etiqueta,
                        style: t.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600, color: cs.onSurface)),
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
      {required this.monto,
      required this.moneda,
      required this.sufijo,
      required this.detalle,
      required this.onReservar});
  final double monto; // /hora cuando no hay selección; total del bloque si hay
  final String moneda;
  final String sufijo; // ' /hora' o '' (total)
  final String detalle; // 'Elige una hora' o '2 h · 18:00–20:00'
  final VoidCallback? onReservar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: EdgeInsets.fromLTRB(
          22, 12, 22, 16 + MediaQuery.of(context).padding.bottom),
      decoration: BoxDecoration(
        color: cs.surface,
        border: const Border(top: BorderSide(color: trazo)),
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
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
                    children: [
                      TextSpan(
                        text: '$moneda${monto.toStringAsFixed(2)}',
                        style: t.titleLarge?.copyWith(
                            color: cs.onSurface, fontWeight: FontWeight.w700),
                      ),
                      TextSpan(text: sufijo),
                    ],
                  ),
                ),
                Text(detalle,
                    style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
              ],
            ),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: lima,
              foregroundColor: Colors.white,
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

/// Resultado del resumen: método de pago elegido + servicios extra marcados.
typedef ResumenResultado = ({
  String metodo,
  List<ServicioExtra> extras,
  bool usarPuntos,
});

/// Ícono para un servicio extra según su clave.
IconData iconoServicio(String clave) => switch (clave) {
      'arbitro' => Icons.sports,
      'pelotero' => Icons.sports_handball,
      'pelota' => Icons.sports_soccer,
      'pecheras' => Icons.checkroom,
      'hidratacion' => Icons.local_drink_outlined,
      'parrilla' => Icons.outdoor_grill,
      _ => Icons.add_circle_outline,
    };

/// Hoja "Resumen de tu reserva" (estilo Airbnb): detalle + servicios extra
/// opcionales (árbitro/pelotero…) que suman al total, y un ÚNICO total (sin
/// desglosar comisiones). Devuelve [ResumenResultado] al elegir método de pago.
class _ResumenReserva extends StatefulWidget {
  const _ResumenReserva({
    required this.cancha,
    required this.dia,
    required this.hora,
    required this.horaFin,
    required this.nSlots,
    required this.deporte,
    required this.nombreCliente,
    required this.total,
    required this.permiteEfectivo,
    this.saldoBono = 0,
  });

  final Cancha cancha;
  final String dia;
  final String hora;
  final String horaFin;
  final int nSlots; // cuántas horas seguidas (1 = una hora)
  final Deporte deporte;
  final String nombreCliente;
  final num total; // precio base del bloque (suma de las horas, sin extras)
  final bool permiteEfectivo; // efectivo solo si el dueño tiene saldo
  final int saldoBono; // horas de bono prepagado del jugador en este local

  @override
  State<_ResumenReserva> createState() => _ResumenReservaState();
}

class _ResumenReservaState extends State<_ResumenReserva> {
  final Set<String> _sel = {}; // claves de servicios extra elegidos

  Cancha get cancha => widget.cancha;

  String get _duracion {
    // Duración TOTAL del bloque = nº de horas × duración del slot.
    final unit = cancha.duracionSlotMin <= 0 ? 60 : cancha.duracionSlotMin;
    final min = unit * (widget.nSlots <= 0 ? 1 : widget.nSlots);
    final h = min ~/ 60;
    final m = min % 60;
    if (h == 0) return '$m min';
    return m == 0 ? '$h h' : '$h h $m min';
  }

  List<ServicioExtra> get _elegidos =>
      cancha.serviciosExtra.where((s) => _sel.contains(s.clave)).toList();

  double get _totalFinal =>
      widget.total + _elegidos.fold(0.0, (a, s) => a + s.precio);

  /// ¿Esta cancha exige seña por adelantado (anti no-show)?
  bool get _exigeSena => cancha.exigeSena;

  /// Monto de la seña: % del precio de la cancha (no incluye servicios extra).
  int get _senaMonto => (widget.total * cancha.senaPct / 100).round();

  /// Lo que el jugador paga en la cancha si adelanta la seña (total − seña).
  double get _restoEnCancha => _totalFinal - _senaMonto;

  // CANJE DE PUNTOS (economía aprobada): 100 pts = S/3 de descuento pagando
  // ONLINE, un canje por reserva. Solo se ofrece en soles y si alcanza.
  bool _usarPuntos = false;
  bool get _puedeCanjear =>
      appState.misPuntosDisponibles >= 100 &&
      cancha.monedaSimbolo == 'S/' &&
      _totalFinal > 3.0;

  void _cerrar(String metodo) => Navigator.of(context)
      .pop((metodo: metodo, extras: _elegidos, usarPuntos: _usarPuntos));

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    final dir = (cancha.direccion ?? '').trim();
    final cliente =
        widget.nombreCliente.trim().isEmpty ? 'Ti' : widget.nombreCliente.trim();
    final mon = cancha.monedaSimbolo;
    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      padding: EdgeInsets.fromLTRB(
          20, 12, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                    color: Colors.black12,
                    borderRadius: BorderRadius.circular(10)),
              ),
            ),
            const SizedBox(height: 16),
            Text('Resumen de tu reserva',
                style: t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 14),
            _fila(context, iconoDeporte(widget.deporte),
                colorDeporte(widget.deporte),
                '${cancha.nombre} · ${widget.deporte.etiqueta}'),
            _fila(context, Icons.event, cs.primary,
                '${widget.dia} · ${widget.hora}–${widget.horaFin}  ($_duracion)'),
            if (dir.isNotEmpty)
              _fila(context, Icons.place_outlined, cs.primary, dir),
            _fila(context, Icons.person_outline, cs.primary,
                'A nombre de: $cliente'),
            // Servicios extra (si la cancha ofrece): opcionales, suman al total.
            if (cancha.serviciosExtra.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('¿Agregar servicios?',
                  style: t.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 6),
              for (final s in cancha.serviciosExtra)
                _FilaServicio(
                  servicio: s,
                  moneda: mon,
                  marcado: _sel.contains(s.clave),
                  onTap: () => setState(() => _sel.contains(s.clave)
                      ? _sel.remove(s.clave)
                      : _sel.add(s.clave)),
                ),
            ],
            const SizedBox(height: 8),
            Divider(color: trazo),
            const SizedBox(height: 4),
            Row(
              children: [
                Expanded(
                  child: Text('Total a pagar',
                      style:
                          t.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                ),
                Text(
                    '$mon ${(_usarPuntos ? _totalFinal - 3.0 : _totalFinal).toStringAsFixed(2)}',
                    style: t.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800, color: cs.primary)),
              ],
            ),
            // Canje de PUNTOS Pichangol: 100 pts = S/3, solo pagando online.
            if (_puedeCanjear) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: limaSuave,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.stars, size: 18, color: bosque),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Usar 100 puntos: −S/ 3.00 (tienes '
                        '${appState.misPuntosDisponibles}). Válido pagando '
                        'online.',
                        style: t.bodySmall?.copyWith(
                            color: bosque,
                            fontWeight: FontWeight.w700,
                            height: 1.25),
                      ),
                    ),
                    Switch(
                      value: _usarPuntos,
                      activeColor: pino,
                      onChanged: (v) => setState(() => _usarPuntos = v),
                    ),
                  ],
                ),
              ),
            ],
            // Con SEÑA: desglose claro de cuánto adelanta hoy y cuánto en la
            // cancha, con el aviso de que la seña no se devuelve.
            if (_exigeSena) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: lima.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: lima.withOpacity(0.25)),
                ),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Icon(Icons.shield_outlined, size: 18, color: pino),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                              'Seña ahora (asegura tu hora)',
                              style: t.bodyMedium
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                        ),
                        Text('$mon ${_senaMonto.toDouble().toStringAsFixed(2)}',
                            style: t.titleMedium?.copyWith(
                                fontWeight: FontWeight.w800, color: pino)),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const SizedBox(width: 26),
                        Expanded(
                          child: Text('Resto en la cancha',
                              style: t.bodyMedium
                                  ?.copyWith(color: textoTenue)),
                        ),
                        Text('$mon ${_restoEnCancha.toStringAsFixed(2)}',
                            style: t.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: textoTenue)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.info_outline,
                            size: 14, color: textoTenue),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                              'La seña no es reembolsable: si no llegas, se '
                              'queda a favor de la cancha.',
                              style: t.bodySmall?.copyWith(
                                  color: textoTenue, height: 1.3)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.lock_outline, size: 15, color: textoTenue),
                const SizedBox(width: 6),
                Text('Pago seguro · Confirmación al instante',
                    style: t.bodySmall?.copyWith(color: textoTenue)),
              ],
            ),
            const SizedBox(height: 16),
            // Bono prepagado: si el jugador tiene horas para este local, la
            // opción MÁS conveniente (no paga de nuevo). Descuenta sus horas.
            if (widget.saldoBono >= widget.nSlots) ...[
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: teal,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15)),
                  onPressed: () => _cerrar('bono'),
                  icon: const Icon(Icons.confirmation_number, size: 18),
                  label: Text(
                      'Usar mi bono (${widget.nSlots} h · te quedan ${widget.saldoBono})',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 14)),
                ),
              ),
              const SizedBox(height: 10),
            ],
            // Botón principal: con seña, pagar la seña; sin seña, pagar todo.
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: () => _cerrar(_exigeSena ? 'sena' : 'online'),
                icon: const Icon(Icons.lock, size: 18),
                label: Text(
                    _exigeSena
                        ? 'Pagar seña $mon ${_senaMonto.toDouble().toStringAsFixed(2)} y reservar'
                        : 'Pagar ahora (Yape / Tarjeta)',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 15)),
              ),
            ),
            // Con seña, ofrecemos también pagar TODO ahora (sin ir a la cancha).
            if (_exigeSena) ...[
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: lima,
                      side: BorderSide(color: lima.withOpacity(0.6)),
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: () => _cerrar('online'),
                  icon: const Icon(Icons.credit_card, size: 18),
                  label: Text(
                      'Pagar todo ahora ($mon ${_totalFinal.toStringAsFixed(2)})',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 14)),
                ),
              ),
            ],
            // Efectivo puro (sin adelanto) solo si NO hay seña y el dueño tiene
            // saldo (así PCG cobra su comisión de ese saldo).
            if (!_exigeSena && widget.permiteEfectivo) ...[
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      foregroundColor: lima,
                      side: BorderSide(color: lima.withOpacity(0.6)),
                      padding: const EdgeInsets.symmetric(vertical: 14)),
                  onPressed: () => _cerrar('cancha'),
                  icon: const Icon(Icons.payments_outlined, size: 18),
                  label: const Text('Pagar en la cancha (efectivo)',
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _fila(BuildContext context, IconData icono, Color color, String texto) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icono, size: 20, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Text(texto,
                style: const TextStyle(fontSize: 14.5, height: 1.3)),
          ),
        ],
      ),
    );
  }
}

/// Fila seleccionable de un servicio extra en el resumen de reserva.
class _FilaServicio extends StatelessWidget {
  const _FilaServicio({
    required this.servicio,
    required this.moneda,
    required this.marcado,
    required this.onTap,
  });
  final ServicioExtra servicio;
  final String moneda;
  final bool marcado;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            Icon(iconoServicio(servicio.clave),
                size: 20, color: marcado ? cs.primary : textoTenue),
            const SizedBox(width: 12),
            Expanded(
              child: Text(servicio.nombre,
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: marcado ? FontWeight.w700 : FontWeight.w500)),
            ),
            Text('+$moneda ${servicio.precio.toStringAsFixed(2)}',
                style: TextStyle(
                    color: cs.primary,
                    fontWeight: FontWeight.w700,
                    fontSize: 13.5)),
            const SizedBox(width: 10),
            Icon(
                marcado
                    ? Icons.check_circle
                    : Icons.radio_button_unchecked,
                color: marcado ? cs.primary : trazo,
                size: 22),
          ],
        ),
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
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
        decoration: BoxDecoration(
          // Seleccionado = verde WhatsApp + texto blanco (nunca negro).
          color: activo ? lima : cs.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: activo ? lima : trazo),
        ),
        child: Text(texto,
            style: TextStyle(
                color: activo ? Colors.white : cs.onSurface,
                fontWeight: FontWeight.w700)),
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
    this.bloqueada = false,
    this.descuento = 0,
    this.enEspera = false,
    this.nEspera = 0,
  });
  final String hora;
  final bool ocupada;
  final bool valle;
  final bool seleccionada;
  final VoidCallback onTap;
  final bool bloqueada; // slot cerrado por el dueño (tappable para reabrir)
  final int descuento; // "hora feliz": % de descuento si valle (0 = ninguno)
  final bool enEspera; // el jugador está en la lista de espera de este slot
  final int nEspera; // cuántos esperan (vista del dueño); 0 = no mostrar

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // Slot BLOQUEADO (vista del dueño): candado + tappable para desbloquear.
    if (bloqueada) {
      return GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            color: bosque,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.lock, size: 14, color: Colors.white),
              const SizedBox(width: 5),
              Text(hora,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700)),
            ],
          ),
        ),
      );
    }
    if (ocupada) {
      // Tomado: tappable → lista de espera (jugador) o ver quién espera (dueño).
      return GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            color: enEspera ? limaSuave : const Color(0xFFF0ECE2),
            borderRadius: BorderRadius.circular(14),
            border: enEspera ? Border.all(color: lima) : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(hora,
                  style: TextStyle(
                      color: enEspera ? lima : const Color(0xFFB5AFA3),
                      fontWeight: enEspera ? FontWeight.w700 : FontWeight.w400,
                      decoration:
                          enEspera ? null : TextDecoration.lineThrough)),
              if (enEspera) ...[
                const SizedBox(width: 5),
                const Icon(Icons.hourglass_top, size: 13, color: lima),
              ] else if (nEspera > 0) ...[
                const SizedBox(width: 5),
                Icon(Icons.hourglass_top, size: 12, color: textoTenueDe(context)),
                Text('$nEspera',
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: textoTenueDe(context))),
              ],
            ],
          ),
        ),
      );
    }
    // Slot seleccionado = verde WhatsApp (marca), nunca negro. Es la selección
    // más visible al reservar; congruente con el resto de la app.
    final Color borde = seleccionada
        ? lima
        : valle
            ? clay
            : trazo;
    final Color fondo = seleccionada ? lima : cs.surface;
    final Color texto = seleccionada
        ? Colors.white
        : valle
            ? clayOscuro
            : cs.onSurface;
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
            // Con descuento (hora feliz de mañana o descuento puntual del dueño)
            // se muestra "🔥 -N%" en cualquier hora; si no, "valle" en las valle.
            if (!seleccionada && descuento > 0) ...[
              const SizedBox(width: 5),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                    color: lima.withOpacity(0.14),
                    borderRadius: BorderRadius.circular(999)),
                child: Text('🔥 -$descuento%',
                    style: const TextStyle(
                        color: lima, fontSize: 10, fontWeight: FontWeight.w800)),
              ),
            ] else if (valle && !seleccionada) ...[
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
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'reclamar esta cancha')) {
      return;
    }
    if (!mounted) return;
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
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
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
            Icon(activa ? Icons.verified : Icons.hourglass_top,
                color: Theme.of(context).colorScheme.primary),
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
              Icon(Icons.travel_explore,
                  color: Theme.of(context).colorScheme.primary),
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
    // Reclamar exige identificarse: la solicitud debe viajar SIEMPRE con la
    // cuenta (correo + nombre) del que reclama, no anónima.
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'reclamar esta cancha')) {
      return;
    }
    if (!mounted) return;
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
      solicitanteNombre: appState.usuario?.nombre ?? '',
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
      } else if (verif && est['es_mio'] == true) {
        // SEGURIDAD: solo se anuncia la aprobación si el reclamo aprobado es
        // DEL que pregunta — la aprobación de un tercero sobre el mismo lugar
        // no activa la copia de otro reclamante.
        msg = '✅ ¡Aprobada! Habilitando tus reservas…';
        await widget.onActualizar?.call();
      } else if (verif || estado == 'reclamada_por_otro') {
        msg = '⚠️ Este local ya tiene un dueño aprobado con otra cuenta. Si el '
            'local es tuyo, escríbenos para revisarlo.';
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
                  backgroundColor: lima, foregroundColor: Colors.white),
              onPressed: _reenviando ? null : _reenviar,
              icon: _reenviando
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
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
              CircleAvatar(
                radius: 16,
                backgroundColor: clayOscuro.withOpacity(0.14),
                child: const Text('⏳', style: TextStyle(fontSize: 16)),
              ),
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
                    backgroundColor: lima, foregroundColor: Colors.white),
                onPressed: _reenviando ? null : _reenviar,
                icon: _reenviando
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
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

  /// Fotos de Google bajadas EN VIVO al abrir la ficha (solo canchas
  /// descubiertas sin fotos propias; máx 3, con caché de sesión). La lista de
  /// Explorar sigue siempre con placeholder — esto es solo para la ficha.
  List<String> _fotosVivo = const [];

  List<String> get _fotos => widget.cancha.fotos.isNotEmpty
      ? widget.cancha.fotos
      : (widget.cancha.fotoUrl != null
          ? [widget.cancha.fotoUrl!]
          : _fotosVivo);

  @override
  void initState() {
    super.initState();
    _cargarFotosVivo();
  }

  Future<void> _cargarFotosVivo() async {
    final c = widget.cancha;
    // Solo descubiertas/cosechadas: las reclamadas lucen las fotos del dueño.
    if (c.registrada || c.fotos.isNotEmpty || c.fotoUrl != null) return;
    final urls = await PlacesService.fotosFicha(c.id);
    if (mounted && urls.isNotEmpty) setState(() => _fotosVivo = urls);
  }

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
    final cs = Theme.of(context).colorScheme;
    Widget dato(IconData ic, String txt) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(ic, size: 18, color: cs.primary),
            const SizedBox(width: 6),
            Text(txt,
                style: t.bodyMedium
                    ?.copyWith(color: cs.onSurface, fontWeight: FontWeight.w600)),
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
            '${cancha.monedaSimbolo}${montoTxt(cancha.precioHora)} /h'),
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

/// BONOS de horas prepagadas del local (vista del jugador): muestra su saldo si
/// tiene, y los packs disponibles para comprar (paga con Culqi → horas que
/// descuenta al reservar en este local).
class _SeccionBonos extends StatefulWidget {
  const _SeccionBonos({required this.cancha});
  final Cancha cancha;

  @override
  State<_SeccionBonos> createState() => _SeccionBonosState();
}

class _SeccionBonosState extends State<_SeccionBonos> {
  bool _comprando = false;

  String get _club => widget.cancha.club;

  Future<void> _comprar(BonoOferta o) async {
    if (!await LoginGoogleSheet.mostrar(context, motivo: 'comprar tu bono')) {
      return;
    }
    if (!mounted) return;
    final u = appState.usuario;
    if (u == null) return;
    setState(() => _comprando = true);
    var operacion = '';
    final pagado = await PagoTarjeta.cobrar(
      context,
      // El sheet recibe el monto EN LA MONEDA LOCAL (S//Bs/$), lo pasa a
      // céntimos y lo muestra tal cual. NO multiplicar por 100 aquí.
      monto: o.precio,
      concepto: 'Bono ${o.horas}h · $_club',
      email: u.email,
      moneda: widget.cancha.monedaSimbolo,
      onOperacion: (op) => operacion = op,
    );
    if (!mounted) {
      _comprando = false;
      return;
    }
    if (!pagado) {
      setState(() => _comprando = false);
      return;
    }
    final ventaId = operacion.isNotEmpty
        ? operacion
        : '${o.id}_${u.email}_${DateTime.now().millisecondsSinceEpoch}';
    await conPreload(context, () async {
      // 1) Crédito del jugador. 2) Contabilidad de venta (por recibir del dueño
      //    − comisión), idempotente por ventaId. 3) Push al dueño.
      await appState.comprarBono(o, ventaId);
      await PagosService.venta(
        vendedorId: o.dueno,
        montoSoles: o.precio,
        ventaId: ventaId,
        concepto: 'Bono ${o.horas}h · $_club',
        compradorEmail: u.email.toLowerCase(),
        compradorNombre: u.nombre,
      );
      AvisosService.enviar(
        email: o.dueno,
        titulo: '¡Vendiste un bono! 🎟️',
        cuerpo: '${u.nombre} compró tu pack de ${o.horas} horas en $_club.',
        tipo: 'bono',
      );
    }, texto: 'Confirmando tu bono…');
    if (!mounted) return;
    setState(() => _comprando = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: lima,
        content: Text('¡Bono activado! Tienes ${appState.miSaldoBono(_club)} '
            'horas en $_club.')));
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final t = Theme.of(context).textTheme;
        final ofertas = appState.bonosDeClub(_club);
        final saldo = appState.miSaldoBono(_club);
        if (ofertas.isEmpty && saldo == 0) return const SizedBox.shrink();
        final mon = widget.cancha.monedaSimbolo;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.confirmation_number_outlined, color: teal),
                const SizedBox(width: 8),
                Text('Bonos de horas',
                    style:
                        t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 2),
            Text(
                'Paga por adelantado y ahorra: cada bono te da horas para '
                'reservar aquí.',
                style: t.bodySmall?.copyWith(color: textoTenueDe(context))),
            if (saldo > 0) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: teal.withOpacity(0.10),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle, color: teal, size: 20),
                    const SizedBox(width: 8),
                    Text('Tienes $saldo ${saldo == 1 ? 'hora' : 'horas'} de bono',
                        style: t.bodyMedium?.copyWith(
                            color: teal, fontWeight: FontWeight.w800)),
                  ],
                ),
              ),
            ],
            for (final o in ofertas) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: trazo),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                          color: lima.withOpacity(0.14),
                          borderRadius: BorderRadius.circular(12)),
                      child: Text('${o.horas}h',
                          style: const TextStyle(
                              color: lima,
                              fontWeight: FontWeight.w800,
                              fontSize: 15)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(o.nombre.isEmpty ? '${o.horas} horas' : o.nombre,
                              style: t.bodyLarge
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                          Text('$mon ${montoTxt(o.precioHora)}/hora',
                              style: t.bodySmall
                                  ?.copyWith(color: textoTenueDe(context))),
                        ],
                      ),
                    ),
                    FilledButton(
                      style: FilledButton.styleFrom(backgroundColor: lima),
                      onPressed: _comprando ? null : () => _comprar(o),
                      child: Text('$mon ${montoTxt(o.precio)}',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                    ),
                  ],
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

/// RESEÑAS del local (⭐ real). Muestra el promedio + cantidad, la lista de
/// reseñas y —para jugadores logueados que no son el dueño— una tarjeta para
/// calificar (estrellas + comentario). Reemplaza el rating "presentacional".
class _SeccionResenas extends StatefulWidget {
  const _SeccionResenas({
    required this.club,
    required this.canchaDestino,
    required this.puedeResenar,
  });
  final Club club;
  final Cancha canchaDestino; // a qué cancha se atribuye la reseña del usuario
  final bool puedeResenar;

  @override
  State<_SeccionResenas> createState() => _SeccionResenasState();
}

class _SeccionResenasState extends State<_SeccionResenas> {
  final _comentario = TextEditingController();
  int _estrellas = 0;
  bool _enviando = false;
  bool _editor = false; // muestra el formulario para calificar

  List<String> get _canchaIds => widget.club.canchas.map((c) => c.id).toList();

  @override
  void initState() {
    super.initState();
    appState.cargarResenas(_canchaIds);
  }

  @override
  void dispose() {
    _comentario.dispose();
    super.dispose();
  }

  /// ¿Este correo tiene alguna reserva en el local? → sello "reservó aquí".
  bool _reservoAqui(String email) {
    final e = email.trim().toLowerCase();
    final ids = _canchaIds.toSet();
    return appState.reservas.any((r) =>
        ids.contains(r.canchaId) && r.usuario.trim().toLowerCase() == e);
  }

  Future<void> _guardar() async {
    if (_estrellas < 1) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Elige cuántas estrellas.')));
      return;
    }
    setState(() => _enviando = true);
    final ok = await appState.enviarResena(
        widget.canchaDestino.id, _estrellas, _comentario.text);
    if (!mounted) return;
    setState(() {
      _enviando = false;
      if (ok) _editor = false;
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(ok ? '¡Gracias por tu reseña!' : 'No se pudo guardar.'),
      backgroundColor: ok ? lima : null,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final t = Theme.of(context).textTheme;
        final resumen = appState.resumenResenas(_canchaIds);
        final lista = appState.resenasDe(_canchaIds);
        final mia = appState.miResena(_canchaIds);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Reseñas',
                    style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                const Spacer(),
                if (resumen.hay) ...[
                  const Icon(Icons.star, size: 18, color: amarillo),
                  const SizedBox(width: 4),
                  Text(resumen.promedio.toStringAsFixed(1),
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(width: 4),
                  Text('(${resumen.cantidad})',
                      style: TextStyle(color: textoTenueDe(context))),
                ],
              ],
            ),
            const SizedBox(height: 4),
            if (!resumen.hay)
              Text(
                widget.puedeResenar
                    ? 'Aún no hay reseñas. ¡Sé el primero en calificar!'
                    : 'Aún no hay reseñas de este local.',
                style: t.bodySmall?.copyWith(color: textoTenueDe(context)),
              ),

            // Tarjeta para calificar (jugador logueado, no dueño).
            if (widget.puedeResenar) ...[
              const SizedBox(height: 12),
              if (!_editor)
                OutlinedButton.icon(
                  onPressed: () {
                    setState(() {
                      _editor = true;
                      _estrellas = mia?.estrellas ?? 0;
                      _comentario.text = mia?.comentario ?? '';
                    });
                  },
                  icon: Icon(mia == null ? Icons.rate_review_outlined : Icons.edit,
                      size: 18),
                  label: Text(mia == null ? 'Calificar mi experiencia' : 'Editar mi reseña'),
                )
              else
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFFEEEAE0)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Tu reseña de ${widget.club.nombre}',
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          for (var i = 1; i <= 5; i++)
                            IconButton(
                              padding: const EdgeInsets.symmetric(horizontal: 2),
                              constraints: const BoxConstraints(),
                              onPressed: () => setState(() => _estrellas = i),
                              icon: Icon(
                                i <= _estrellas ? Icons.star : Icons.star_border,
                                color: amarillo,
                                size: 32,
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _comentario,
                        maxLines: 3,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: InputDecoration(
                          hintText: '¿Cómo estuvo la cancha? (opcional)',
                          isDense: true,
                          border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: trazo)),
                          enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: trazo)),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          TextButton(
                            onPressed: _enviando
                                ? null
                                : () => setState(() => _editor = false),
                            child: const Text('Cancelar'),
                          ),
                          const SizedBox(width: 6),
                          FilledButton(
                            style: FilledButton.styleFrom(backgroundColor: lima),
                            onPressed: _enviando ? null : _guardar,
                            child: Text(_enviando ? 'Guardando…' : 'Publicar'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
            ],

            // Lista de reseñas.
            for (final r in lista) ...[
              const SizedBox(height: 14),
              _ResenaCard(resena: r, reservoAqui: _reservoAqui(r.autorEmail)),
            ],
          ],
        );
      },
    );
  }
}

class _ResenaCard extends StatelessWidget {
  const _ResenaCard({required this.resena, required this.reservoAqui});
  final Resena resena;
  final bool reservoAqui;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final nombre = resena.autorNombre.trim().isNotEmpty
        ? resena.autorNombre.trim()
        : resena.autorEmail.split('@').first;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 18,
          backgroundColor: teal,
          child: Text(nombre.isEmpty ? '?' : nombre[0].toUpperCase(),
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w800)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Flexible(
                    child: Text(nombre,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                  if (reservoAqui) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                          color: lima.withOpacity(0.14),
                          borderRadius: BorderRadius.circular(999)),
                      child: const Text('✓ reservó aquí',
                          style: TextStyle(
                              color: lima,
                              fontSize: 10,
                              fontWeight: FontWeight.w800)),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 2),
              Row(
                children: [
                  for (var i = 1; i <= 5; i++)
                    Icon(i <= resena.estrellas ? Icons.star : Icons.star_border,
                        size: 14, color: amarillo),
                ],
              ),
              if (resena.comentario.trim().isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(resena.comentario.trim(), style: t.bodyMedium),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
