import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../config/pais.dart';
import '../data/partidos_repo.dart';
import '../models/academia.dart';
import '../models/club.dart';
import '../models/models.dart';
import '../models/partido.dart';
import '../services/convocatorias_service.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/cargando_pichangol.dart';
import 'chat_screen.dart';
import 'convocatorias_screen.dart';
import 'login_google_sheet.dart';
import 'ranking_global_screen.dart';

/// "Partidos abiertos" — el **Match** del benchmark: cualquier jugador publica un
/// partido con cupos ("busco 2 para completar fulbito el sábado") y otros se
/// apuntan. Distinto de las pichangas de club (esas las organiza el dueño): esto
/// es matchmaking entre jugadores. Cada partido tiene su chat de coordinación
/// (reusa la infraestructura de grupos).
class PartidosScreen extends StatefulWidget {
  const PartidosScreen({super.key});

  @override
  State<PartidosScreen> createState() => _PartidosScreenState();
}

class _PartidosScreenState extends State<PartidosScreen> {
  List<PartidoAbierto> _partidos = const [];
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _cargar();
    // Datos del circuito para la tarjeta de descubrimiento (best-effort).
    appState.cargarAcademiasRemotas();
    appState.cargarRetosResultados();
    appState.cargarMiembrosPro();
  }

  Future<void> _cargar() async {
    final lista = await PartidosRepo.abiertos();
    if (!mounted) return;
    // Filtro por país (como las academias): partidos del país donde estás; los
    // que no tienen ubicación se muestran igual (no se puede discriminar).
    final iso = paisActual.iso;
    final filtrados = [
      for (final p in lista)
        if (p.ubicacion == null ||
            paisDeCoordenadas(p.ubicacion!.latitude, p.ubicacion!.longitude)
                    .iso ==
                iso)
          p
    ];
    setState(() {
      _partidos = filtrados;
      _cargando = false;
    });
  }

  Future<void> _crear() async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'publicar tu partido')) {
      return;
    }
    if (!mounted) return;
    final creado = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => const _CrearPartidoSheet(),
    );
    if (creado == true) {
      _snack('¡Partido publicado! Ya pueden apuntarse.');
      _cargar();
    }
  }

  Future<void> _apuntarse(PartidoAbierto p) async {
    if (!await LoginGoogleSheet.mostrar(context,
        motivo: 'apuntarte al partido')) {
      return;
    }
    if (!mounted) return;
    final u = appState.usuario!;
    final res = await PartidosRepo.apuntarse(p.id, u.email, u.nombre, p.cupos);
    if (!mounted) return;
    _snack(switch (res) {
      'ok' => '¡Te apuntaste! Coordinen por el chat del partido.',
      'lleno' => '⛔ El partido ya se llenó (otro jugador tomó el último '
          'cupo). Pídele al creador que amplíe los cupos o busca otro.',
      _ => 'No se pudo apuntar. Revisa tu conexión.',
    });
    _cargar(); // refresca el conteo real aunque no haya entrado
  }

  Future<void> _bajarse(PartidoAbierto p) async {
    final u = appState.usuario;
    if (u == null) return;
    final ok = await PartidosRepo.bajarse(p.id, u.email);
    if (!mounted) return;
    _snack(ok ? 'Te bajaste del partido.' : 'No se pudo.');
    if (ok) _cargar();
  }

  Future<void> _eliminar(PartidoAbierto p) async {
    final ok = await PartidosRepo.eliminar(p.id);
    if (!mounted) return;
    _snack(ok ? 'Partido eliminado.' : 'No se pudo eliminar.');
    if (ok) _cargar();
  }

  void _coordinar(PartidoAbierto p) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ChatScreen(
        academiaId: '',
        cuentaEmail: '',
        titulo: p.titulo,
        soyProfe: false,
        tipo: 'grupo',
        refId: p.id,
      ),
    ));
  }

  void _pichangasDeClub() {
    final club = appState.nombreClub;
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ConvocatoriasScreen(
          clubId: ConvocatoriasService.slugClub(club), clubNombre: club),
    ));
  }

  void _snack(String m) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: lima,
        foregroundColor: Colors.white,
        onPressed: _crear,
        icon: const Icon(Icons.add),
        label: const Text('Crear partido'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Cabecera verde (lenguaje WhatsApp) con acceso a pichangas de club.
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(20, 18, 16, 18),
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [lima, teal],
                ),
                borderRadius:
                    BorderRadius.vertical(bottom: Radius.circular(22)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Partidos',
                      style: t.headlineSmall?.copyWith(
                          color: Colors.white, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 2),
                  Text('Publica un partido y encuentra con quién jugar.',
                      style: t.bodyMedium
                          ?.copyWith(color: Colors.white.withOpacity(0.92))),
                  const SizedBox(height: 12),
                  InkWell(
                    onTap: _pichangasDeClub,
                    borderRadius: BorderRadius.circular(10),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.18),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.event_available,
                              color: Colors.white, size: 18),
                          const SizedBox(width: 8),
                          Text('Pichangas de mi club',
                              style: t.bodySmall?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700)),
                          const SizedBox(width: 4),
                          const Icon(Icons.chevron_right,
                              color: Colors.white, size: 18),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const _CircuitoPreview(),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _cargar,
                child: _cargando
                    ? const CargandoPichangol()
                    : _partidos.isEmpty
                        ? ListView(children: const [
                            SizedBox(height: 80),
                            _Vacio(),
                          ])
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
                            itemCount: _partidos.length,
                            itemBuilder: (_, i) => _PartidoCard(
                              partido: _partidos[i],
                              onApuntarse: () => _apuntarse(_partidos[i]),
                              onBajarse: () => _bajarse(_partidos[i]),
                              onCoordinar: () => _coordinar(_partidos[i]),
                              onEliminar: () => _eliminar(_partidos[i]),
                            ),
                          ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Tarjeta de DESCUBRIMIENTO del Circuito Pichangol en la pestaña Partidos:
/// muestra el top-3 del ranking global (o invita a arrancarlo) y lleva al
/// Ranking Global. Es el gancho para que el jugador entre al loop competitivo.
class _CircuitoPreview extends StatelessWidget {
  const _CircuitoPreview();

  void _abrir(BuildContext context) => Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const RankingGlobalScreen()));

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        // El circuito es capa de TENIS: no ensuciar Partidos (matchmaking de
        // todos los deportes) si no hay circuito de raqueta vivo ni el usuario
        // se unió.
        if (!appState.hayCircuitoTenis) return const SizedBox.shrink();
        final deportes =
            appState.deportesConRanking.where((d) => d.esRaqueta).toList();
        final dep = deportes.isNotEmpty ? deportes.first : null;
        final top = dep == null
            ? const <RankingGlobalFila>[]
            : appState.rankingGlobal(deporte: dep).take(3).toList();
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
          child: Material(
            color: Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: () => _abrir(context),
              child: Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: trazo),
                ),
                padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                              color: limaSuave,
                              borderRadius: BorderRadius.circular(11)),
                          child: const Icon(Icons.emoji_events,
                              color: bosque, size: 21),
                        ),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Circuito Pichangol',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 15.5)),
                              Text('Ranking de tu ciudad · rétalos y sube',
                                  style: TextStyle(
                                      color: textoTenue, fontSize: 12.5)),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right, color: textoTenue),
                      ],
                    ),
                    if (top.isEmpty) ...[
                      const SizedBox(height: 10),
                      Text(
                          '¡Arranca el circuito! Reta a un jugador y aparece en '
                          'el ranking de tu ciudad.',
                          style: TextStyle(
                              color: textoTenueDe(context),
                              fontSize: 12.5,
                              height: 1.3)),
                    ] else ...[
                      const SizedBox(height: 8),
                      const _MiniHeaderRanking(),
                      const SizedBox(height: 2),
                      for (var i = 0; i < top.length; i++)
                        _MiniFila(
                            posicion: i + 1,
                            f: top[i],
                            esPro: appState.esProEmail(top[i].emailIdentidad)),
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

// Anchos de las columnas numéricas del mini-ranking (comunes al encabezado y a
// las filas → alineación perfecta entre sí y entre filas).
const double _wPj = 30, _wG = 24, _wP = 24, _wPts = 40;

/// Encabezado del mini-ranking: rótulos PJ · G · P · Pts alineados con las
/// columnas de cada fila.
class _MiniHeaderRanking extends StatelessWidget {
  const _MiniHeaderRanking();
  Widget _h(String t, double w, {bool fuerte = false}) => SizedBox(
        width: w,
        child: Text(t,
            textAlign: TextAlign.right,
            style: TextStyle(
                color: textoTenue,
                fontSize: 10.5,
                fontWeight: fuerte ? FontWeight.w900 : FontWeight.w700)),
      );
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        children: [
          const SizedBox(width: 30), // medalla + gap
          const Expanded(child: SizedBox()),
          _h('PJ', _wPj),
          _h('G', _wG),
          _h('P', _wP),
          _h('Pts', _wPts, fuerte: true),
        ],
      ),
    );
  }
}

/// Fila compacta del top-3 en la tarjeta del circuito: medalla + nombre + tabla
/// PJ · G · P · Pts (columnas de ancho fijo, alineadas).
class _MiniFila extends StatelessWidget {
  const _MiniFila(
      {required this.posicion, required this.f, required this.esPro});
  final int posicion;
  final RankingGlobalFila f;
  final bool esPro;

  Widget _num(String v, double w, Color c,
          {bool fuerte = false, double size = 12.5}) =>
      SizedBox(
        width: w,
        child: Text(v,
            textAlign: TextAlign.right,
            style: TextStyle(
                color: c,
                fontSize: size,
                fontWeight: fuerte ? FontWeight.w900 : FontWeight.w700)),
      );

  @override
  Widget build(BuildContext context) {
    final medalla = switch (posicion) {
      1 => '🥇',
      2 => '🥈',
      3 => '🥉',
      _ => '$posicion',
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
              width: 22,
              child: Text(medalla,
                  style: const TextStyle(fontSize: 15),
                  textAlign: TextAlign.center)),
          const SizedBox(width: 8),
          Expanded(
            child: Row(
              children: [
                Flexible(
                  child: Text(f.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 13.5)),
                ),
                if (esPro) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                        color: bosque, borderRadius: BorderRadius.circular(5)),
                    child: const Text('PRO',
                        style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            fontSize: 8.5)),
                  ),
                ],
              ],
            ),
          ),
          // Tabla: partidos jugados, ganados (verde), perdidos (rojo) y puntos.
          _num('${f.pj}', _wPj, textoTenue),
          _num('${f.pg}', _wG, lima),
          _num('${f.pp}', _wP, clayOscuro),
          _num('${f.puntos}', _wPts, bosque, fuerte: true, size: 14),
        ],
      ),
    );
  }
}

class _Vacio extends StatelessWidget {
  const _Vacio();
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        children: [
          Icon(Icons.sports_soccer, size: 56, color: lima.withOpacity(0.6)),
          const SizedBox(height: 14),
          const Text('Todavía no hay partidos abiertos',
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 6),
          Text(
              '¿Te falta gente para jugar? Publica tu partido con el botón '
              '"Crear partido" y deja que otros se apunten.',
              textAlign: TextAlign.center,
              style: TextStyle(color: textoTenueDe(context), height: 1.35)),
        ],
      ),
    );
  }
}

/// Formatea 'YYYY-MM-DD' + 'HH:mm' a algo legible: "vie 18 jul · 8:00 p.m.".
String _fechaLegible(String fecha, String hora) {
  const dias = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
  const meses = [
    'ene', 'feb', 'mar', 'abr', 'may', 'jun',
    'jul', 'ago', 'set', 'oct', 'nov', 'dic'
  ];
  final d = DateTime.tryParse(fecha);
  final base = d != null
      ? '${dias[d.weekday - 1]} ${d.day} ${meses[d.month - 1]}'
      : fecha;
  return hora.isNotEmpty ? '$base · $hora' : base;
}

class _PartidoCard extends StatelessWidget {
  const _PartidoCard({
    required this.partido,
    required this.onApuntarse,
    required this.onBajarse,
    required this.onCoordinar,
    required this.onEliminar,
  });
  final PartidoAbierto partido;
  final VoidCallback onApuntarse;
  final VoidCallback onBajarse;
  final VoidCallback onCoordinar;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final email = appState.usuario?.email;
    final apuntado = partido.apuntado(email);
    final esCreador = partido.esCreador(email);
    final p = partido;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: trazo),
        boxShadow: const [
          BoxShadow(color: Color(0x14000000), blurRadius: 14, offset: Offset(0, 5)),
        ],
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: colorDeporte(p.deporte),
                child: Icon(iconoDeporte(p.deporte), color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.titulo,
                        style: t.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text(_fechaLegible(p.fecha, p.hora),
                        style: t.bodySmall
                            ?.copyWith(color: textoTenueDe(context))),
                  ],
                ),
              ),
              // Chip "faltan N" / "completo".
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: p.lleno ? const Color(0xFFEBEBEB) : limaSuave,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                    p.lleno ? 'Completo' : 'Faltan ${p.faltan}',
                    style: TextStyle(
                        color: p.lleno ? textoTenue : bosque,
                        fontWeight: FontWeight.w800,
                        fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (p.sedeNombre.isNotEmpty)
            _Linea(Icons.place_outlined, p.sedeNombre),
          _Linea(Icons.groups_outlined,
              '${p.inscritos} de ${p.cupos} jugadores · ${p.deporte.etiqueta}'),
          if (p.nota.isNotEmpty) _Linea(Icons.sticky_note_2_outlined, p.nota),
          const SizedBox(height: 12),
          Row(
            children: [
              if (apuntado) ...[
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: lima, foregroundColor: Colors.white),
                    onPressed: onCoordinar,
                    icon: const Icon(Icons.chat_bubble_outline, size: 18),
                    label: const Text('Coordinar'),
                  ),
                ),
                const SizedBox(width: 8),
                if (esCreador)
                  OutlinedButton(
                    onPressed: onEliminar,
                    style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFFC0392B)),
                    child: const Text('Eliminar'),
                  )
                else
                  OutlinedButton(
                    onPressed: onBajarse,
                    child: const Text('Salir'),
                  ),
              ] else
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: p.lleno ? const Color(0xFFBDBDBD) : lima,
                        foregroundColor: Colors.white),
                    onPressed: p.lleno ? null : onApuntarse,
                    icon: const Icon(Icons.add, size: 18),
                    label: Text(p.lleno ? 'Completo' : 'Me apunto'),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Linea extends StatelessWidget {
  const _Linea(this.icono, this.texto);
  final IconData icono;
  final String texto;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icono, size: 16, color: textoTenueDe(context)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(texto,
                style: TextStyle(
                    color: textoTenueDe(context), fontSize: 13, height: 1.3)),
          ),
        ],
      ),
    );
  }
}

/// Hoja para publicar un partido nuevo.
class _CrearPartidoSheet extends StatefulWidget {
  const _CrearPartidoSheet();
  @override
  State<_CrearPartidoSheet> createState() => _CrearPartidoSheetState();
}

class _CrearPartidoSheetState extends State<_CrearPartidoSheet> {
  Deporte _deporte = Deporte.futbol;
  final _titulo = TextEditingController();
  final _sede = TextEditingController();
  final _nota = TextEditingController();
  DateTime? _fecha;
  TimeOfDay? _hora;
  int _cupos = 10;
  bool _guardando = false;
  LatLng? _sedeUbic;

  late final Map<String, LatLng> _sedes = _cargarSedes();

  Map<String, LatLng> _cargarSedes() {
    final m = <String, LatLng>{};
    for (final c in Club.agrupar(appState.todasLasCanchas())) {
      if (c.nombre.trim().isNotEmpty) m.putIfAbsent(c.nombre, () => c.ubicacion);
    }
    return m;
  }

  @override
  void dispose() {
    _titulo.dispose();
    _sede.dispose();
    _nota.dispose();
    super.dispose();
  }

  Future<void> _elegirFecha() async {
    final hoy = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _fecha ?? hoy,
      firstDate: hoy,
      lastDate: hoy.add(const Duration(days: 90)),
    );
    if (d != null) setState(() => _fecha = d);
  }

  Future<void> _elegirHora() async {
    final h = await showTimePicker(
      context: context,
      initialTime: _hora ?? const TimeOfDay(hour: 20, minute: 0),
    );
    if (h != null) setState(() => _hora = h);
  }

  String _dosDig(int n) => n.toString().padLeft(2, '0');

  /// Atajos de "jugadores en total" según el deporte (etiqueta, total). El
  /// total incluye al creador. Ej.: dobles de tenis = 4; fútbol 7 = 14.
  List<(String, int)> _presetsDe(Deporte d) => switch (d) {
        Deporte.tenis ||
        Deporte.padel ||
        Deporte.pickleball =>
          const [('Singles', 2), ('Dobles', 4)],
        Deporte.futbol => const [
            ('Fut 5', 10),
            ('Fut 6', 12),
            ('Fut 7', 14),
            ('Fut 8', 16),
            ('Fut 11', 22),
          ],
        Deporte.voley => const [('4 vs 4', 8), ('6 vs 6', 12)],
        Deporte.basquet => const [('3 vs 3', 6), ('5 vs 5', 10)],
        Deporte.natacion => const [], // sin modalidades de partido
      };

  Future<void> _publicar() async {
    final u = appState.usuario;
    if (u == null) return;
    if (_fecha == null || _hora == null) {
      _err('Elige la fecha y la hora del partido.');
      return;
    }
    if (_sede.text.trim().isEmpty) {
      _err('¿Dónde se juega? Pon la cancha o el lugar.');
      return;
    }
    setState(() => _guardando = true);
    final ubic = _sedes[_sede.text.trim()] ?? _sedeUbic;
    final fechaIso =
        '${_fecha!.year}-${_dosDig(_fecha!.month)}-${_dosDig(_fecha!.day)}';
    final titulo = _titulo.text.trim().isNotEmpty
        ? _titulo.text.trim()
        : '${_deporte.etiqueta} · ${_sede.text.trim()}';
    final partido = PartidoAbierto(
      id: 'p_${DateTime.now().microsecondsSinceEpoch}',
      creadorEmail: u.email,
      creadorNombre: u.nombre,
      deporte: _deporte,
      titulo: titulo,
      fecha: fechaIso,
      hora: '${_dosDig(_hora!.hour)}:${_dosDig(_hora!.minute)}',
      sedeNombre: _sede.text.trim(),
      lat: ubic?.latitude,
      lng: ubic?.longitude,
      cupos: _cupos,
      nota: _nota.text.trim(),
      creado: DateTime.now(),
    );
    bool ok;
    try {
      ok = await conPreload(context, () => PartidosRepo.crear(partido),
          texto: 'Publicando…');
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      _err('No se pudo publicar. Revisa tu conexión.');
    }
  }

  void _err(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 18, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Nuevo partido',
                style: t.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 14),
            Text('Deporte', style: t.labelLarge),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final d in deportesActivos)
                  ChoiceChip(
                    label: Text(d.etiqueta),
                    selected: _deporte == d,
                    selectedColor: lima,
                    labelStyle: TextStyle(
                        color: _deporte == d ? Colors.white : cs.onSurface,
                        fontWeight: FontWeight.w600),
                    onSelected: (_) => setState(() {
                      _deporte = d;
                      // Al cambiar de deporte, propone un total típico de ese
                      // deporte (el primer atajo) para no arrastrar el anterior.
                      final ps = _presetsDe(d);
                      if (ps.isNotEmpty) _cupos = ps.first.$2;
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            Autocomplete<String>(
              optionsBuilder: (v) {
                final q = v.text.trim().toLowerCase();
                if (q.isEmpty) return const Iterable<String>.empty();
                return _sedes.keys
                    .where((n) => n.toLowerCase().contains(q))
                    .take(6);
              },
              onSelected: (sel) {
                _sede.text = sel;
                _sedeUbic = _sedes[sel];
              },
              fieldViewBuilder: (ctx, ctrl, focus, _) {
                return TextField(
                  controller: ctrl,
                  focusNode: focus,
                  // Espeja lo tecleado en nuestro controller (lo leemos al
                  // publicar); onSelected además captura la ubicación.
                  onChanged: (v) => _sede.text = v,
                  decoration: const InputDecoration(
                      labelText: '¿Dónde se juega?',
                      hintText: 'Cancha o lugar (ej.: La Molina)',
                      prefixIcon: Icon(Icons.place_outlined)),
                );
              },
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _SelectorCampo(
                    icono: Icons.calendar_today,
                    etiqueta: _fecha == null
                        ? 'Fecha'
                        : '${_fecha!.day}/${_dosDig(_fecha!.month)}',
                    onTap: _elegirFecha,
                    lleno: _fecha != null,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _SelectorCampo(
                    icono: Icons.access_time,
                    etiqueta: _hora == null
                        ? 'Hora'
                        : '${_dosDig(_hora!.hour)}:${_dosDig(_hora!.minute)}',
                    onTap: _elegirHora,
                    lleno: _hora != null,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Jugadores en total', style: t.labelLarge),
            const SizedBox(height: 2),
            Text('Tú ya cuentas como 1 · te faltan ${_cupos - 1}',
                style: TextStyle(color: textoTenue, fontSize: 12)),
            const SizedBox(height: 8),
            // Atajos por deporte (Singles/Dobles, Fut 5/6/7…): fijan el total sin
            // que el usuario tenga que hacer la cuenta.
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final p in _presetsDe(_deporte))
                  ChoiceChip(
                    label: Text('${p.$1} (${p.$2})'),
                    selected: _cupos == p.$2,
                    selectedColor: lima,
                    labelStyle: TextStyle(
                        color: _cupos == p.$2 ? Colors.white : cs.onSurface,
                        fontWeight: FontWeight.w600),
                    onSelected: (_) => setState(() => _cupos = p.$2),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                _StepBtn(
                    icon: Icons.remove,
                    onTap: () =>
                        setState(() => _cupos = (_cupos - 1).clamp(2, 40))),
                Expanded(
                  child: Center(
                    child: Text('$_cupos',
                        style: t.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800)),
                  ),
                ),
                _StepBtn(
                    icon: Icons.add,
                    onTap: () =>
                        setState(() => _cupos = (_cupos + 1).clamp(2, 40))),
              ],
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _titulo,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                  labelText: 'Título (opcional)',
                  hintText: 'Ej.: Fulbito de los viernes'),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _nota,
              maxLines: 2,
              textCapitalization: TextCapitalization.sentences,
              inputFormatters: [LengthLimitingTextInputFormatter(160)],
              decoration: const InputDecoration(
                  labelText: 'Nota (opcional)',
                  hintText: 'Nivel, si traer pechera, cómo se paga la cancha…'),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: lima,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 15)),
                onPressed: _guardando ? null : _publicar,
                child: const Text('Publicar partido'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectorCampo extends StatelessWidget {
  const _SelectorCampo({
    required this.icono,
    required this.etiqueta,
    required this.onTap,
    required this.lleno,
  });
  final IconData icono;
  final String etiqueta;
  final VoidCallback onTap;
  final bool lleno;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: lleno ? bosque : trazo),
        ),
        child: Row(
          children: [
            Icon(icono, size: 18, color: lleno ? bosque : textoTenue),
            const SizedBox(width: 10),
            Text(etiqueta,
                style: TextStyle(
                    color: lleno ? cs.onSurface : textoTenue,
                    fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _StepBtn extends StatelessWidget {
  const _StepBtn({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Material(
      color: limaSuave,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Icon(icon, color: bosque),
        ),
      ),
    );
  }
}
